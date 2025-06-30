import asyncio
import random
import gc
import inspect
import json
import logging
import os
import re
import signal
import sys
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, Generic, List, Optional, TypeVar, Union

from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
# from langchain_groq import ChatGroq
import websockets
import platform
from browser_use import Agent, ActionResult, Browser, BrowserConfig
from browser_use.controller.service import Controller
from browser_use.browser.context import BrowserContext

# Global tracking for active browser agent tasks
active_browser_agent_tasks = {}  # Track active tasks by tab_id
active_browser_agent_tasks_lock = asyncio.Lock()  # Lock for thread-safe access

# Load environment variables from .env file
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(dotenv_path)




def get_browser_path():
	    # Get the base directory where the executable is located
    if getattr(sys, 'frozen', False):
        # If running as bundled executable
        base_dir = os.path.dirname(sys.executable)
    else:
        # If running as script
        base_dir = os.path.dirname(os.path.abspath(__file__))

    # Determine path based on operating system
    if platform.system() == "Darwin":  # macOS
        # Check if using system installed app or bundled version
        system_path = '/Applications/Meteor.app/Contents/MacOS/Meteor'
        relative_path = os.path.join(base_dir, "Meteor")

        # Use system path if it exists, otherwise use relative
        if os.path.exists(system_path):
            return Path(system_path)
        else:
            return Path(relative_path)

    elif platform.system() == "Windows":
        # Windows path - assuming the browser executable is included with your app
        return Path(os.path.join(base_dir, "Bill-Gates-Browser.exe"))



# Fix resource access for PyInstaller
def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

# meteor version



# ### BROWSER OPTIONS
# browser = Browser(
#     config=BrowserConfig(
#         browser_instance_path=get_browser_path(),
#     )
# )

browser = Browser(config=BrowserConfig(browser_instance_path=get_browser_path()))

### LLM OPTIONS
# Get API key from environment or use a fallback mechanism
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    print("⚠️ WARNING: OPENAI_API_KEY not found in environment variables")
    print("Either set it in .env file or provide it explicitly")

try:
    llm = ChatOpenAI(
        model="gpt-4.1",
        api_key=openai_api_key,  # Explicitly pass the API key
    )
except Exception as e:
    print(f"Error initializing ChatOpenAI: {str(e)}")
    print("Falling back to a placeholder LLM that will fail gracefully")
    # Create a minimal placeholder that will fail with better error messages
    class PlaceholderLLM:
        def __init__(self):
            self._verified_api_keys = False
        async def ainvoke(self, *args, **kwargs):
            raise ValueError("OpenAI API key not configured correctly. Please check your .env file.")
        def invoke(self, *args, **kwargs):
            raise ValueError("OpenAI API key not configured correctly. Please check your .env file.")
    llm = PlaceholderLLM()

# For the second LLM, also check for API key
# groq_api_key = os.environ.get("GROQ_API_KEY")
# try:
#     llm2 = ChatGroq(
#         model="meta-llama/llama-4-maverick-17b-128e-instruct",
#         api_key=groq_api_key,
#     )
# except Exception as e:
#     print(f"Error initializing ChatGroq: {str(e)}")
#     print("GROQ LLM initialization failed, it will not be available")

### WEB SOCKET CONNECTION
websocket_connection = None
server = None
intervention_events = {}

# Global variable to track the current browser agent task
current_browser_agent_task = None

def set_websocket_connection(websocket):
    global websocket_connection
    print("WebSocket connection established")
    websocket_connection = websocket

# Add this function for tool call updates
async def send_tool_call_update(action_name, details="", status="in_progress", tab_id=None):
    """
    Sends a browser agent tool call update back to the client with enhanced formatting.

    Args:
        action_name: The name of the tool being called
        details: Description of the action being performed
        status: Current status (in_progress, completed, failed, cancelled)
        tab_id: The browser tab ID this action is associated with
    """
    global websocket_connection

    if not websocket_connection:
        print(f"⚠️ No WebSocket connection available to send tool call update for {action_name}")
        return

    # Use the current tab_id if none provided
    if tab_id is None:
        tab_id = "current"

    # Format the details for better readability
    formatted_details = details

    # Format specific tool types with cleaner details
    if "click" in action_name.lower():
        if "index" in details:
            # Extract the index and text if available
            parts = details.split(":")
            if len(parts) > 1:
                formatted_details = f"Clicking element: {parts[1].strip()}"
            else:
                formatted_details = "Clicking interface element"
    elif "input_text" in action_name.lower():
        # For text inputs, simplify the message and protect privacy
        formatted_details = "Typing text into form field"
    elif "search_google" in action_name.lower():
        # For search queries, highlight the query text
        if "Searched for" in details and '"' in details:
            query = details.split('"')[1]
            if query:
                formatted_details = f"Searching for: {query}"

    # Create the response with the enhanced tool call information
    response = {
        "type": "browser_agent_tool_call",
        "tab_id": tab_id,
        "tool_call": {
            "name": action_name,
            "status": status,
            "details": formatted_details
        },
        "timestamp": time.time()
    }

    # Send the response
    try:
        await websocket_connection.send(json.dumps(response))
        print(f"✅ Sent tool call update: {action_name} - {formatted_details}")
    except Exception as e:
        print(f"⚠️ Error sending tool call update: {e}")

async def send_completion_response(tab_id, result=None):
    """
    Sends a browser agent completion response back to the client with detailed agent results.
    """
    global websocket_connection

    if not result:
        result = {}

    # Default content
    content = "Task completed successfully"
    success = True

    print("====== BROWSER AGENT COMPLETION - DETAILED DEBUG ======")
    print(f"Result type: {type(result)}")

    try:
        # Handle cancelled task result
        if isinstance(result, dict) and result.get("cancelled"):
            content = result.get("message", "Task was cancelled by user")
            success = False
            print(f"TASK CANCELLED: {content}")
        # Handle error result
        elif isinstance(result, dict) and result.get("error"):
            content = result.get("message", "Task encountered an error")
            success = False
            print(f"TASK ERROR: {content}")
        # Standard result extraction approaches
        elif hasattr(result, 'is_done') and result.is_done():
            # If the agent is done, get the final result
            final_content = result.final_result()
            if final_content:
                content = final_content
                success = result.is_successful() if result.is_successful() is not None else True
                print(f"FOUND CONTENT USING final_result(): {content[:100]}...")
        elif hasattr(result, 'model_actions'):
            model_actions = result.model_actions()
            for action in reversed(model_actions):
                if 'done' in action and isinstance(action['done'], dict) and 'text' in action['done']:
                    content = action['done']['text']
                    success = action['done'].get('success', True)
                    print(f"FOUND CONTENT USING model_actions(): {content[:100]}...")
                    break
        elif hasattr(result, 'action_results'):
            action_results = result.action_results()
            for action_result in reversed(action_results):
                if hasattr(action_result, 'is_done') and action_result.is_done:
                    if hasattr(action_result, 'extracted_content') and action_result.extracted_content:
                        content = action_result.extracted_content
                        success = action_result.success if hasattr(action_result, 'success') else True
                        print(f"FOUND CONTENT USING action_results(): {content[:100]}...")
                        break
        elif hasattr(result, 'history') and result.history:
            last_history = result.history[-1]
            if hasattr(last_history, 'result') and last_history.result:
                last_result = last_history.result[-1]
                if hasattr(last_result, 'is_done') and last_result.is_done:
                    if hasattr(last_result, 'extracted_content') and last_result.extracted_content:
                        content = last_result.extracted_content
                        success = last_result.success if hasattr(last_result, 'success') else True
                        print(f"FOUND CONTENT BY DIRECT INSPECTION: {content[:100]}...")
        else:
            result_str = str(result)
            print(f"USING STRING EXTRACTION AS LAST RESORT")
            import re
            # Try to extract from the all_model_outputs part
            match = re.search(r"'done':\s*{'text':\s*'([^']+)'", result_str)
            if match:
                extracted = match.group(1)
                if len(extracted) > 50:  # Only use if substantial
                    content = extracted
                    print(f"EXTRACTED FROM STRING REPRESENTATION: {content[:100]}...")

    except Exception as e:
        print(f"ERROR in extraction: {str(e)}")
        traceback.print_exc()

    # Final sanity check - ensure content is a string and not empty
    if not isinstance(content, str) or not content.strip():
        content = "Task completed successfully"

    # Create the response with the extracted content
    response = {
        "type": "browser_agent_response",
        "tab_id": tab_id,
        "result": {
            "content": content,
            "success": success
        },
        "timestamp": time.time()
    }

    print(f"FINAL CONTENT LENGTH: {len(content)}")
    print(f"CONTENT PREVIEW: {content[:100] + '...' if len(content) > 100 else content}")
    print("====== END BROWSER AGENT COMPLETION DEBUG ======")

    # Send the response
    if websocket_connection:
        try:
            await websocket_connection.send(json.dumps(response))
            print(f"✅ Successfully sent browser agent completion to UI")
        except Exception as e:
            print(f"⚠️ Error sending completion response: {e}")
    else:
        print("⚠️ No WebSocket connection available to send browser agent completion")

async def end_server():
    global websocket_connection
    global server
    if websocket_connection:
        await websocket_connection.close()
        websocket_connection = None
    if server:
        await server.close()
        server = None

async def start_server():
    global server
    server = await websockets.serve(handle_websocket, "localhost", 8765)
    print("Server running on ws://localhost:8765")
    await server.wait_closed()

async def cleanup_browser_agent_task(tab_id, completed_task):
    """Clean up completed browser agent task"""
    global current_browser_agent_task
    global active_browser_agent_tasks

    async with active_browser_agent_tasks_lock:
        # Remove from active tasks
        if tab_id in active_browser_agent_tasks and active_browser_agent_tasks[tab_id] is completed_task:
            del active_browser_agent_tasks[tab_id]
            print(f"Browser agent task for tab {tab_id} completed and cleaned up")

        # Clear current task reference if it matches
        if current_browser_agent_task is completed_task:
            current_browser_agent_task = None

async def handle_websocket(websocket):
    global intervention_events
    global current_browser_agent_task
    global active_browser_agent_tasks

    print(f"New websocket connection established from: {websocket.remote_address}")
    # Store the websocket connection
    set_websocket_connection(websocket)

    try:
        async for message in websocket:
            print(f"Received message: {message}")

            try:
                data = json.loads(message)
                print(f"Parsed data: {data}")

                # Handle intervention completion message - This MUST be processed quickly!
                if data.get("type") == "human_intervention_complete" and "intervention_id" in data:
                    print("Human intervention response received")
                    intervention_id = data["intervention_id"]
                    if intervention_id in intervention_events:
                        # Signal the waiting task
                        intervention_events[intervention_id].set()
                        print(f"Intervention {intervention_id} completed")
                        # Send confirmation back to the client
                        await websocket.send(json.dumps({"status": "ok", "message": "Intervention completed"}))
                    else:
                        print(f"Warning: Intervention ID {intervention_id} not found in active events")

                elif data.get("type") == "end_connection":
                    print("Received end_connection request")
                    asyncio.create_task(end_server())

                # Handle browser agent requests with deduplication
                elif data.get("type") == "browser_agent_request":
                    print("Processing browser agent request")

                    # Extract tab_id for tracking
                    tab_id = data.get("tab_id", "current")
                    prompt = data.get("prompt", "")
                    request_id = data.get("id", str(uuid.uuid4()))

                    # Check if there's already an active task for this tab
                    async with active_browser_agent_tasks_lock:
                        if tab_id in active_browser_agent_tasks:
                            existing_task = active_browser_agent_tasks[tab_id]
                            if existing_task and not existing_task.done():
                                print(f"Browser agent task already running for tab {tab_id}, ignoring duplicate request")

                                # Send a response indicating duplicate
                                await websocket.send(json.dumps({
                                    "status": "duplicate",
                                    "message": f"Browser agent already processing task for tab {tab_id}",
                                    "tab_id": tab_id,
                                    "request_id": request_id
                                }))
                                continue

                        # Send acknowledgement immediately
                        await websocket.send(json.dumps({
                            "status": "processing",
                            "message": "Browser agent task started",
                            "tab_id": tab_id,
                            "request_id": request_id
                        }))

                        # Start the task and track it
                        task = asyncio.create_task(main(prompt, tab_id))
                        active_browser_agent_tasks[tab_id] = task
                        current_browser_agent_task = task

                        # Add cleanup callback
                        def task_done_callback(completed_task):
                            asyncio.create_task(cleanup_browser_agent_task(tab_id, completed_task))

                        task.add_done_callback(task_done_callback)

                elif data.get("type") == "regular_chat":
                    print("Processing regular chat message")
                    # Start the main task as a separate task
                    asyncio.create_task(main(data.get("regular_chat", message)))
                    # Send an immediate ack to the client
                    await websocket.send(json.dumps({"status": "processing", "message": "Task started"}))

                else:
                    # Handle other potential control messages
                    print('Processing unknown message type')
                    # Default to starting as a task if type is unknown
                    asyncio.create_task(main(message))
                    # Send an immediate ack to the client
                    await websocket.send(json.dumps({"status": "processing", "message": "Task started"}))

            except json.JSONDecodeError:
                # Handle non-JSON messages
                print('Received non-JSON message, treating as task')
                asyncio.create_task(main(message))
                # Send an immediate ack to the client
                await websocket.send(json.dumps({"status": "processing", "message": "Task started"}))

            except Exception as e:
                # Catch other errors during message processing
                print(f"Error processing message: {e}")
                # Send an error back to the client
                try:
                    await websocket.send(json.dumps({"status": "error", "message": f"Server error processing message: {e}"}))
                except:
                    pass # Ignore if sending error fails

    except websockets.exceptions.ConnectionClosed:
        print("WebSocket connection closed")
    except Exception as e:
        # Catch unexpected errors in the connection handler itself
        print(f"Unexpected error in handle_websocket: {e}")
    finally:
        # Clear the websocket connection when closed
        print(f"Connection closed: {websocket.remote_address}")
        if websocket_connection == websocket:
            set_websocket_connection(None)

# Updated main function with improved cancellation handling and cleanup
async def main(task_message, tab_id=None):
    global active_browser_agent_tasks

    if tab_id is None:
        tab_id = "current"  # Default tab ID if none found

    print(f"Running browser agent for tab {tab_id} with task: {task_message[:100]}...")

    # Create a closure that captures the current tab_id
    async def tool_call_callback(action_name, details="", status="in_progress"):
        await send_tool_call_update(action_name, details, status, tab_id)

    # Initialize the controller with the callback
    controller = Controller(
        # sends tools over websocket to electron build
        tool_call_callback=tool_call_callback
    )

    # Add human intervention action to this controller instance
    @controller.registry.action('Request human intervention')
    async def request_human_intervention(reason: str = "Action requires human intervention") -> ActionResult:
        """
        Programmatically pauses Browser-Use execution and requests human intervention via WebSocket.

        Args:
            reason: Description of why human intervention is needed

        Returns:
            ActionResult indicating success after human intervention completes
        """
        global websocket_connection, intervention_events

        intervention_id = str(uuid.uuid4())
        intervention_events[intervention_id] = asyncio.Event()

        # Prepare message for Nexus
        message = {
            "type": "human_intervention_required",
            "intervention_id": intervention_id,
            "reason": reason,
            "timestamp": time.time()
        }

        if websocket_connection:
            try:
                # Create an explicit task for the send operation
                send_task = asyncio.create_task(websocket_connection.send(json.dumps(message)))
                await send_task
                print(f"Sent intervention request: {reason}")
            except Exception as e:
                print(f"Error sending intervention request: {e}")
                return ActionResult(success=False, extracted_content=f"Failed to request intervention: {e}")
        else:
            print("No websocket connection available")
            return ActionResult(success=False, extracted_content="No websocket connection available")

        try:
            # Create a special task that periodically checks for cancellation while waiting
            wait_event_task = asyncio.create_task(intervention_events[intervention_id].wait())

            # Wait for resolution with timeout
            done, pending = await asyncio.wait(
                [wait_event_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=30000  # 8 hour timeout
            )

            # Cancel any pending tasks
            for task in pending:
                task.cancel()

            # Check if we timed out (neither task completed)
            if not done:
                print(f"Timeout waiting for human intervention: {reason}")
                return ActionResult(success=False, extracted_content="Timeout waiting for human intervention")

            # Normal completion
            print(f"Human intervention completed for: {reason}")
            return ActionResult(success=True, extracted_content=f"Human intervention completed for: {reason}")

        except asyncio.CancelledError:
            print(f"Intervention wait cancelled: {reason}")
            raise
        except asyncio.TimeoutError:
            print(f"Timeout waiting for human intervention: {reason}")
            return ActionResult(success=False, extracted_content="Timeout waiting for human intervention")
        finally:
            if intervention_id in intervention_events:
                del intervention_events[intervention_id]

    # First tool call update to show task starting
    await send_tool_call_update(
        "browser_agent_start",
        f"Starting task: {task_message}",
        "in_progress",
        tab_id
    )

    # this should work to connect to the available instance
    browser_session= BrowserSession(highlight_elements=False, cdp_url="http://localhost:9222", stealth=True)

    agent = Agent(
        browser_session=browser_session,
        task=task_message,
        llm=llm,
        controller=controller,
        use_vision=True
    )

    # Execute the agent's task and capture the result
    try:
        # Store reference to the agent for potential cancellation
        if current_browser_agent_task:
            current_browser_agent_task._agent = agent

        # Run the agent with the cancellation checker running in parallel
        result = await agent.run()

        # Send completion response back to the client
        await send_completion_response(tab_id, result)

        # Log completion
        print(f"Completion response sent to UI for tab {tab_id}")

        return result

    except Exception as e:
        print(f"Error in browser agent execution: {str(e)}")
        traceback.print_exc()

        # Send error response
        try:
            await send_tool_call_update(
                "browser_agent_error",
                f"Error: {str(e)}",
                "failed",
                tab_id
            )

            await send_completion_response(tab_id, {
                "error": True,
                "message": str(e)
            })
        except Exception as send_error:
            print(f"Error sending error response: {str(send_error)}")

        # Let the error propagate
        raise e

    finally:
        # Ensure resources are cleaned up
        try:
            # Clean up agent resources
            if agent.browser_context:
                try:
                    await agent.browser_context.close()
                except Exception as e:
                    print(f"Error closing browser context: {e}")

            # Ensure tab is removed from active tasks
            async with active_browser_agent_tasks_lock:
                if tab_id in active_browser_agent_tasks:
                    del active_browser_agent_tasks[tab_id]

        except Exception as cleanup_error:
            print(f"Error during cleanup: {cleanup_error}")

# Install signal handlers for graceful termination
def install_signal_handlers():
    def signal_handler(sig, frame):
        print(f"Received signal {sig}, initiating shutdown")

        # In a real app, you'd want to trigger shutdown of your asyncio loop here
        # But for this example we'll just exit
        if sig == signal.SIGINT or sig == signal.SIGTERM:
            print("Exiting due to signal")
            sys.exit(0)

    # Register signals
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # On Windows, SIGBREAK can be sent with Ctrl+Break
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, signal_handler)

# Install signal handlers at startup
install_signal_handlers()

# Run the websocket server
if __name__ == "__main__":
    try:
        asyncio.run(start_server())
    except KeyboardInterrupt:
        print("Server shutdown requested via KeyboardInterrupt")
    finally:
        print("Server shutdown complete")

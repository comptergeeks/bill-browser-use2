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

from dotenv import load_dotenv
import websockets
import platform
from browser_use import Agent, ActionResult, Browser, BrowserConfig
from browser_use.controller.service import Controller
from browser_use.browser.context import BrowserContext
import socket
import subprocess
import importlib.util
from browser_use.browser.profile import BrowserProfile
import shutil
from browser_use import Agent, ChatOpenAI
from browser_use.logging_config import setup_logging


os.environ["BROWSER_USE_LOGGING_LEVEL"] = "debug"
from browser_use.logging_config import setup_logging
setup_logging()

# Global flag to track if a kill command has been received
KILL_AGENT_REQUESTED = False

# Tab-specific kill requests tracking
tab_kill_requests = set()  # Track which tab_ids have kill requests
tab_kill_requests_lock = asyncio.Lock()  # Lock for thread-safe access

# Global tracking for active browser agent tasks
active_browser_agent_tasks = {}  # Track active tasks by tab_id
active_browser_agent_tasks_lock = asyncio.Lock()  # Lock for thread-safe access

# Load environment variables from the bundled/working directory.
# Using `resource_path` lets PyInstaller one-file builds locate .env inside the
# extracted _MEIPASS dir, while plain `python workflow_run.py` still works.

def resource_path(relative_path):
    """Return absolute path to resource.

    Works for both PyInstaller bundles (where files end up in the temporary
    `_MEIPASS` directory) and for running from source with `python
    workflow_run.py` regardless of the current working directory.
    """
    try:
        # When bundled by PyInstaller the files get extracted to a temporary
        # folder referenced by sys._MEIPASS (added by PyInstaller).  Use that
        # as base if it exists.
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except AttributeError:
        # Running from source – resolve relative to *this* file instead of the
        # current working directory so that `python anywhere/workflow_run.py`
        # still finds the resources beside the script.
        base_path = Path(__file__).resolve().parent

    return str(Path(base_path) / relative_path)

# Now that `resource_path` exists we can safely load the .env file (works both
# in a PyInstaller bundle and directly from source).
load_dotenv(resource_path('.env'))

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
        system_path = '/Applications/Bill-Gates-Browser.app/Contents/MacOS/Bill-Gates-Browser'
        relative_path = os.path.join(base_dir, "Bill-Gates-Browser")

        # Use system path if it exists, otherwise use relative
        if os.path.exists(system_path):
            return system_path
        else:
            return relative_path

    elif platform.system() == "Windows":
        # Windows path - assuming the browser executable is included with your app
        return os.path.join(base_dir, "Bill-Gates-Browser.exe")

    else:  # Linux or other
        return os.path.join(base_dir, "Bill-Gates-Browser")

### BROWSER OPTIONS
# Connect to an already-running Chromium instance (CDP on localhost:9222).
# `Browser` is an alias for `BrowserSession`.
browser = Browser(
    cdp_url="http://localhost:9222",  # CDP endpoint
    # Stealth mode requires Patchright + Node.js which may be missing in bundled builds.
    # Disable stealth to use standard Playwright when merely connecting to an existing CDP target.
    browser_profile=BrowserProfile(stealth=False, highlight_elements=False),
)

### LLM OPTIONS
# Retrieve the key (mainly to force-load the .env file for user feedback); the ChatOpenAI
# constructor will still fall back to `os.environ['OPENAI_API_KEY']` if we do not pass
# an explicit `api_key` argument.

openai_api_key = os.environ.get("OPENAI_API_KEY")

if not openai_api_key:
    print("⚠️  OPENAI_API_KEY not found in environment – ChatOpenAI will rely on runtime env var.")



# Build kwargs dynamically: only pass `api_key` if we actually found one; otherwise
# let the OpenAI client fall back to the environment variable.

llm_kwargs: dict[str, Any] = {
    "model": "gpt-4.1",
    "temperature": 0.0,
}

if openai_api_key:
    llm_kwargs["api_key"] = openai_api_key  # type: ignore[arg-type]

try:
    llm = ChatOpenAI(**llm_kwargs)  # type: ignore[arg-type]
except Exception as e:
    print(f"❌ Failed to initialise ChatOpenAI: {e}")
    print("Make sure OPENAI_API_KEY is set (via .env or environment) and accessible at runtime.")
    sys.exit(1)

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
    
    # Use the details as provided by the controller (already formatted)
    formatted_details = details
    
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
        server.close()
        await server.wait_closed()
        server = None

# =============================================
# Helper utilities for robust websocket server
# =============================================

PORT = 8765  # Central place for websocket port configuration


def _is_port_in_use(port: int) -> bool:
    """Return True if a TCP port on localhost is already bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex(("localhost", port)) == 0


def _force_kill_process_using_port(port: int):
    """Best-effort attempt to terminate any process currently listening on *port*.

    On POSIX systems we rely on the `lsof` utility.  On Windows we fall back to
    `netstat -ano` combined with `taskkill`.  If the necessary helpers are not
    available we merely log the failure; the caller may decide to proceed and
    handle the resulting `Address already in use` error.
    """
    try:
        if platform.system() == "Windows":
            # Capture PID from netstat output
            result = subprocess.check_output(
                ["netstat", "-ano", "-p", "tcp"], text=True, stderr=subprocess.DEVNULL
            )
            for line in result.splitlines():
                if f"0.0.0.0:{port}" in line or f"127.0.0.1:{port}" in line or f"[::]:{port}" in line:
                    parts = line.split()
                    pid = parts[-1]
                    if pid.isdigit():
                        subprocess.call(["taskkill", "/PID", pid, "/F", "/T"])
                        print(f"🔪  Killed process {pid} using port {port}")
        else:
            # macOS / Linux path using lsof
            result = subprocess.check_output(["lsof", "-t", f"-i:{port}"]).decode().strip()
            if result:
                for pid in result.split("\n"):
                    if pid:
                        os.kill(int(pid), signal.SIGTERM)
                        print(f"🔪  Killed process {pid} using port {port}")
    except subprocess.CalledProcessError:
        # No process found on port
        pass
    except FileNotFoundError:
        print("⚠️  Platform tools for forced-kill (lsof / taskkill) not available.")
    except Exception as e:
        print(f"⚠️  Unexpected error when killing port {port}: {e}")


async def _gracefully_close_existing_server(port: int):
    """Attempt to connect to an already running websocket server on *port* and
    request a graceful shutdown via the `end_connection` control message.
    """
    try:
        async with websockets.connect(f"ws://localhost:{port}") as ws:
            await ws.send(json.dumps({"type": "end_connection"}))
            print("ℹ️  Requested graceful shutdown of existing websocket server")
            # Give it a moment to release the socket
            await asyncio.sleep(1)
    except (ConnectionRefusedError, OSError, websockets.InvalidURI):
        # Nothing is listening yet – nothing to do
        pass
    except Exception as e:
        print(f"⚠️  Could not gracefully close existing server on port {port}: {e}")


async def ensure_port_available(port: int = PORT):
    """Ensure *port* is free for binding.  If another process is holding the port
    we first attempt a graceful shutdown; failing that we forcibly terminate
    the process.
    """
    if not _is_port_in_use(port):
        return  # Port already free

    # Try graceful shutdown through websocket control channel
    await _gracefully_close_existing_server(port)

    # Give the OS a moment to recycle the socket
    await asyncio.sleep(0.5)

    if _is_port_in_use(port):
        print(f"⚠️  Port {port} still busy after graceful attempt — forcing kill")
        _force_kill_process_using_port(port)

        # Final short wait; if still busy we will let the bind attempt fail and
        # propagate the error.
        await asyncio.sleep(0.5)

async def start_server():
    """Start the websocket server, guaranteeing the desired port is available.

    This helper makes repeated attempts to free the port by (1) sending an
    `end_connection` control message to any existing Browser-Use websocket
    instance, (2) forcibly killing the owning process if necessary.  This makes
    the executable far more robust when relaunched multiple times or if a
    previous instance crashed and left the port in `TIME_WAIT`.
    """
    global server

    await ensure_port_available(PORT)

    retries = 3
    delay = 1
    for attempt in range(1, retries + 1):
        try:
            server = await websockets.serve(handle_websocket, "localhost", PORT)
            print(f"✅ Server running on ws://localhost:{PORT}")
            break
        except OSError as e:
            if e.errno == 48 or "address already in use" in str(e).lower():
                print(f"⚠️  Port {PORT} still in use (attempt {attempt}/{retries}). Retrying in {delay}s…")
                await asyncio.sleep(delay)
                continue
            raise
    else:
        raise RuntimeError(f"Unable to start websocket server on port {PORT} after {retries} attempts")

    await server.wait_closed()


# ----------------------------------------------------------
#  Runtime restart endpoint (for use by external supervisors)
# ----------------------------------------------------------

async def restart_server():
    """Gracefully restart the websocket server in-process."""
    await end_server()
    await start_server()

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
    global KILL_AGENT_REQUESTED
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

                elif data.get("type") == "restart_server":
                    print("Received restart_server request – restarting websocket server")
                    asyncio.create_task(restart_server())

                elif data.get("type") == "kill_agent":
                    target_tab_id = data.get("tab_id")  # Optional - if provided, only kill this specific task
                    
                    if target_tab_id:
                        print(f"*** KILL AGENT REQUEST RECEIVED FOR SPECIFIC TAB: {target_tab_id} ***")
                        # Add this tab to the kill requests set
                        async with tab_kill_requests_lock:
                            tab_kill_requests.add(target_tab_id)
                    else:
                        print("*** KILL AGENT REQUEST RECEIVED FOR ALL TASKS ***")
                        # Set global flag for backwards compatibility when killing all tasks
                        KILL_AGENT_REQUESTED = True
                    
                    # Get tasks to cancel based on target
                    async with active_browser_agent_tasks_lock:
                        # Debug: Show what tasks are currently active
                        print(f"DEBUG: Active browser agent tasks: {list(active_browser_agent_tasks.keys())}")
                        
                        if target_tab_id:
                            # Kill only the specific task
                            if target_tab_id in active_browser_agent_tasks:
                                tasks_to_cancel = [(target_tab_id, active_browser_agent_tasks[target_tab_id])]
                                print(f"Found exact match for tab {target_tab_id}")
                            else:
                                # If exact match not found, check if there's a task running on "current" 
                                # and we have only one active task (likely the one we want to kill)
                                if len(active_browser_agent_tasks) == 1:
                                    # There's only one task running, kill it regardless of tab_id
                                    tasks_to_cancel = list(active_browser_agent_tasks.items())
                                    print(f"No exact match for tab {target_tab_id}, but killing the only active task: {list(active_browser_agent_tasks.keys())}")
                                else:
                                    tasks_to_cancel = []
                                    print(f"No exact match for tab {target_tab_id} and multiple tasks active: {list(active_browser_agent_tasks.keys())}")
                        else:
                            # Kill all tasks
                            tasks_to_cancel = list(active_browser_agent_tasks.items())
                            print(f"Killing all {len(tasks_to_cancel)} active tasks")
                    
                    cancelled_count = 0
                    for tab_id, task in tasks_to_cancel:
                        if task and not task.done():
                            try:
                                print(f"Attempting to kill agent task for tab {tab_id}")
                                
                                # Mark this specific task for cancellation
                                if hasattr(task, '_should_cancel'):
                                    task._should_cancel = True
                                
                                # Try to stop the agent gracefully first
                                if hasattr(task, '_agent') and task._agent:
                                    print("Setting agent stopped flag and forcing exit conditions")
                                    
                                    # Set multiple exit conditions to ensure the agent stops
                                    task._agent.state.stopped = True
                                    task._agent.state.consecutive_failures = 999
                                    
                                    # Force the agent to exit its main loop
                                    if hasattr(task._agent.state, 'max_failures'):
                                        task._agent.state.max_failures = 0
                                    
                                                                    # Try to interrupt any ongoing browser operations
                                try:
                                    if hasattr(task._agent, 'browser_session') and task._agent.browser_session:
                                        browser_session = task._agent.browser_session
                                        
                                        # Clean up cursor from all pages
                                        try:
                                            if hasattr(browser_session, 'cursor_manager') and browser_session.cursor_manager:
                                                if hasattr(browser_session, 'browser_context') and browser_session.browser_context:
                                                    await browser_session.cursor_manager.cleanup_and_reset(browser_session.browser_context)
                                                else:
                                                    await browser_session.cursor_manager.cleanup_and_reset()
                                                print(f"Cleaned up cursor for killed agent task in tab {tab_id}")
                                        except Exception as e:
                                            print(f"Error cleaning up cursor: {e}")
                                        
                                        if hasattr(browser_session, 'agent_current_page') and browser_session.agent_current_page:
                                            print("Attempting to stop current page operations")
                                            page = browser_session.agent_current_page
                                            await page.evaluate('window.stop()')
                                except Exception as e:
                                    print(f"Error stopping page operations: {e}")
                                    
                                    # Call the stop method which includes resource cleanup
                                    try:
                                        await task._agent.stop()
                                        print(f"Successfully called agent.stop() for tab {tab_id}")
                                    except Exception as e:
                                        print(f"Error calling agent.stop(): {e}")
                                
                                # Cancel the task at asyncio level with aggressive cancellation
                                print(f"Force cancelling asyncio task for tab {tab_id}")
                                task.cancel()
                                
                                # Try to wait for the task to be cancelled
                                try:
                                    await asyncio.wait_for(task, timeout=2.0)
                                except (asyncio.CancelledError, asyncio.TimeoutError):
                                    print(f"Task for tab {tab_id} was cancelled or timed out as expected")
                                except Exception as e:
                                    print(f"Task for tab {tab_id} ended with exception: {e}")
                                
                                cancelled_count += 1
                                
                                # Send cancellation notification to UI for immediate feedback
                                await send_tool_call_update(
                                    "browser_agent_cancelled", 
                                    "Task was cancelled by user request", 
                                    "cancelled",
                                    tab_id
                                )
                                
                                # Send completion response indicating cancellation
                                await send_completion_response(tab_id, {
                                    "cancelled": True,
                                    "message": "Task was cancelled by user"
                                })
                                
                            except Exception as e:
                                print(f"Error cancelling task for tab {tab_id}: {e}")
                                # Even if there's an error, count it as cancelled for user feedback
                                cancelled_count += 1
                    
                    # Clear completed tasks from tracking
                    async with active_browser_agent_tasks_lock:
                        if target_tab_id:
                            # Remove only the specific task
                            if target_tab_id in active_browser_agent_tasks:
                                del active_browser_agent_tasks[target_tab_id]
                                print(f"Removed task for tab {target_tab_id} from active tasks")
                        else:
                            # Remove all tasks
                            active_browser_agent_tasks.clear()
                            print("Cleared all active tasks")
                    
                    # Clear tab-specific kill requests for completed tasks
                    async with tab_kill_requests_lock:
                        if target_tab_id:
                            # Remove only the specific tab kill request
                            tab_kill_requests.discard(target_tab_id)
                            print(f"Cleared kill request for tab {target_tab_id}")
                        else:
                            # Clear all tab kill requests
                            tab_kill_requests.clear()
                            print("Cleared all tab-specific kill requests")
                    
                    # Clear current task reference if it matches what we just cancelled
                    if not target_tab_id or (target_tab_id and current_browser_agent_task in [task for _, task in tasks_to_cancel]):
                        current_browser_agent_task = None
                    
                    # Send final response
                    if cancelled_count > 0:
                        if target_tab_id:
                            message = f"Agent task for tab {target_tab_id} cancelled successfully"
                        else:
                            message = f"Agent tasks cancelled successfully ({cancelled_count} tasks)"
                        
                        await websocket.send(json.dumps({
                            "status": "ok", 
                            "message": message,
                            "tab_id": target_tab_id  # Include tab_id in response for frontend routing
                        }))
                        print(f"Successfully cancelled {cancelled_count} agent task(s)")
                    else:
                        # If no tasks were cancelled but we have a specific tab_id request,
                        # try emergency fallback: set global kill flag to force all agents to stop
                        if target_tab_id:
                            print(f"WARNING: Failed to find specific task for tab {target_tab_id}. Using emergency global kill.")
                            KILL_AGENT_REQUESTED = True
                            
                            # Also add this tab to kill requests as a backup
                            async with tab_kill_requests_lock:
                                tab_kill_requests.add(target_tab_id)
                            
                            message = f"Emergency kill initiated for tab {target_tab_id} (task not found in registry)"
                            
                            await websocket.send(json.dumps({
                                "status": "ok", 
                                "message": message,
                                "tab_id": target_tab_id
                            }))
                            print(message)
                        else:
                            message = "No active agent tasks to kill"
                            
                            await websocket.send(json.dumps({
                                "status": "error",
                                "message": message,
                                "tab_id": target_tab_id
                            }))
                            print(message)

                # Handle browser agent requests with deduplication
                elif data.get("type") == "browser_agent_request":
                    print("Processing browser agent request")
                    
                    # Reset kill flag for new requests
                    KILL_AGENT_REQUESTED = False
                    
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
                        print(f"DEBUG: Starting browser agent task with tab_id: '{tab_id}'")
                        task = asyncio.create_task(main(prompt, tab_id))
                        active_browser_agent_tasks[tab_id] = task
                        current_browser_agent_task = task
                        print(f"DEBUG: Active tasks after adding: {list(active_browser_agent_tasks.keys())}")
                        
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

# Enhanced cancellation check mechanism
async def check_cancellation(tab_id=None):
    """A periodic check that needs to be run alongside the agent task to detect cancellation"""
    global KILL_AGENT_REQUESTED
    
    try:
        # Continue checking until cancellation is requested or task completes
        while True:
            # Check for global kill request
            if KILL_AGENT_REQUESTED:
                print("Cancellation check detected global kill request - forcing immediate cancellation")
                raise asyncio.CancelledError("Global kill requested")
            
            # Check for tab-specific kill request
            if tab_id:
                async with tab_kill_requests_lock:
                    if tab_id in tab_kill_requests:
                        print(f"Cancellation check detected tab-specific kill request for {tab_id} - forcing immediate cancellation")
                        raise asyncio.CancelledError(f"Tab {tab_id} kill requested")
            
            # More frequent checks during active operations
            await asyncio.sleep(0.1)
    except asyncio.CancelledError:
        # Allow cancellation of this check task itself
        print("Cancellation check task itself was cancelled")
        raise
    except Exception as e:
        print(f"Error in cancellation check: {e}")
        raise

# Updated main function with improved cancellation handling and cleanup
async def main(task_message, tab_id=None):
    global KILL_AGENT_REQUESTED
    global active_browser_agent_tasks
    
    # Don't reset kill flag at start if it's already set (emergency kill)
    if not KILL_AGENT_REQUESTED:
        KILL_AGENT_REQUESTED = False
    
    if tab_id is None:
        tab_id = "current"  # Default tab ID if none found
    
    print(f"DEBUG: main() called with tab_id: '{tab_id}' (type: {type(tab_id)})")
    print(f"Running browser agent for tab {tab_id} with task: {task_message[:100]}...")

    # Create a closure that captures the current tab_id
    async def tool_call_callback(action_name, details="", status="in_progress"):
        # Check for cancellation before sending updates
        if KILL_AGENT_REQUESTED:
            raise asyncio.CancelledError("Global kill requested during tool call")
        
        # Check for tab-specific cancellation
        async with tab_kill_requests_lock:
            if tab_id in tab_kill_requests:
                raise asyncio.CancelledError(f"Tab {tab_id} kill requested during tool call")
        
        await send_tool_call_update(action_name, details, status, tab_id)
    
    # Initialize the controller with the callback
    controller = Controller(
        tool_call_callback=tool_call_callback
    )
    
    # Register the helper only once per Controller instance to avoid duplicate action models
    if "request_human_intervention" not in controller.registry.registry.actions:
        @controller.registry.action('Request human intervention')
        async def request_human_intervention(reason: str = "Action requires human intervention") -> ActionResult:
            """
            Programmatically pauses Browser-Use execution and requests human intervention via WebSocket.

            Args:
                reason: Description of why human intervention is needed

            Returns:
                ActionResult indicating success after human intervention completes
            """
            global websocket_connection, intervention_events, KILL_AGENT_REQUESTED

            # Check for cancellation first
            if KILL_AGENT_REQUESTED:
                return ActionResult(success=False, extracted_content="Operation cancelled by user")

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
                cancel_check_task = asyncio.create_task(check_cancellation())
                
                # Wait for resolution with timeout
                done, pending = await asyncio.wait(
                    [wait_event_task, cancel_check_task],
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=30000  # 8 hour timeout
                )
                
                # Cancel any pending tasks
                for task in pending:
                    task.cancel()
                
                # Check if we completed due to kill request
                if KILL_AGENT_REQUESTED:
                    raise asyncio.CancelledError("Kill requested during intervention wait")
                
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
    
    # Prepare a browser session for the agent
    browser_session = browser  # 'browser' is already a BrowserSession alias
    # Optionally start the session here to warm up; the Agent will start it lazily if not
    # await browser_session.start()

    # Create the agent using the existing browser session
    agent = Agent(
        highlight_elements=False,
        task=task_message,
        llm=llm,
        controller=controller,
        browser_session=browser_session,
        use_vision=True,
    )
    
    # Store tab_id with the agent so our patches can check it
    setattr(agent, '_tab_id', tab_id)
    
    # Execute the agent's task and capture the result
    try:
        # Create a cancellation check that runs alongside the agent (pass tab_id for specific cancellation)
        cancel_check_task = asyncio.create_task(check_cancellation(tab_id))
        
        try:
            # Store reference to the agent for potential cancellation
            if current_browser_agent_task:
                setattr(current_browser_agent_task, '_agent', agent)
            
            # Run the agent and cancellation checker concurrently
            agent_task = asyncio.create_task(agent.run())
            
            # Wait for either the agent to complete or cancellation to occur
            done, pending = await asyncio.wait(
                [agent_task, cancel_check_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            # Cancel any remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            
            # Check which task completed first
            if agent_task in done:
                # Agent completed normally
                result = agent_task.result()
                await send_completion_response(tab_id, result)
                print(f"Agent completed normally for tab {tab_id}")
                return result
            else:
                # Cancellation occurred first
                print(f"Agent was cancelled for tab {tab_id}")
                
                # Force stop the agent
                agent.state.stopped = True
                agent.state.consecutive_failures = 999
                
                # Try to call agent stop method
                try:
                    stop_result = agent.stop()
                    if asyncio.iscoroutine(stop_result):
                        await stop_result
                    print(f"Successfully stopped agent for tab {tab_id}")
                except Exception as e:
                    print(f"Error stopping agent for tab {tab_id}: {e}")
                
                raise asyncio.CancelledError("Agent was killed by user request")
            
        except asyncio.CancelledError:
            # Handle cancellation explicitly
            print(f"Handling cancellation for tab {tab_id}")
            
            # Make sure agent is stopped
            try:
                agent.state.stopped = True
                agent.state.consecutive_failures = 999
                stop_result = agent.stop()
                if asyncio.iscoroutine(stop_result):
                    await stop_result
                print(f"Agent stopped due to cancellation for tab {tab_id}")
            except Exception as e:
                print(f"Error stopping cancelled agent for tab {tab_id}: {e}")
            
            # Cancel the checker if still running
            if cancel_check_task and not cancel_check_task.done():
                cancel_check_task.cancel()
                try:
                    await cancel_check_task
                except asyncio.CancelledError:
                    pass
            
            # Re-raise to be handled by the outer try-catch
            raise
            
        finally:
            # Always cancel the checker when done
            if cancel_check_task and not cancel_check_task.done():
                cancel_check_task.cancel()
                try:
                    await cancel_check_task
                except asyncio.CancelledError:
                    pass
    
    except asyncio.CancelledError:
        # Specifically handle task cancellation
        print(f"Final cancellation handler for tab {tab_id}")
        
        # Send cancellation notification
        await send_tool_call_update(
            "browser_agent_cancelled", 
            "Task was cancelled by user request", 
            "cancelled",
            tab_id
        )
        
        # Send a completion response that indicates cancellation
        await send_completion_response(tab_id, {
            "cancelled": True,
            "message": "Task was cancelled by user"
        })
        
        # Return a cancelled result
        return {"cancelled": True, "message": "Task was cancelled"}
        
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
            # Clean up kill request flags for this specific task
            try:
                # Clear global kill flag only if we're killing all tasks
                # (Don't clear it if there are other tasks that might need it)
                async with active_browser_agent_tasks_lock:
                    remaining_tasks = len(active_browser_agent_tasks)
                if remaining_tasks <= 1:  # This task plus maybe one other
                    KILL_AGENT_REQUESTED = False
                    print("Cleared global kill flag - no remaining tasks")
                
                # Always clear tab-specific kill request
                async with tab_kill_requests_lock:
                    tab_kill_requests.discard(tab_id)
                    print(f"Cleared kill request for tab {tab_id}")
                
            except Exception as e:
                print(f"Error clearing kill flags: {e}")
            
            # Close the browser session for this run (safe even if keep_alive=True)
            try:
                await browser_session.close()
            except Exception as e:
                print(f"Error closing browser session: {e}")
            
            # 💡 IMPORTANT: clear stale state so the next Agent run can re-initialise cleanly.
            # If we leave browser_session.initialized=True with a closed browser_context it can lead to
            # unexpected errors (e.g. maximum recursion depth exceeded) when the next Agent tries to
            # reuse the same BrowserSession. Reset the connection state here while *keeping* the
            # underlying browser alive (keep_alive=True).
            try:
                browser_session.browser_context = None  # drop reference to the closed context
                browser_session.agent_current_page = None
                browser_session.human_current_page = None
                browser_session.initialized = False
            except Exception as e:
                print(f"Error resetting BrowserSession state: {e}")
            
            # Ensure tab is removed from active tasks
            async with active_browser_agent_tasks_lock:
                if tab_id in active_browser_agent_tasks:
                    del active_browser_agent_tasks[tab_id]
                    print(f"Removed tab {tab_id} from active tasks during cleanup")
            
        except Exception as cleanup_error:
            print(f"Error during cleanup: {cleanup_error}")

# Enhanced stop method for Agent class
async def stop(self):
    """Stop the agent more aggressively"""
    print('⏹️ Agent stopping')
    self.state.stopped = True
    
    # Force high failure count to trigger exit condition
    self.state.consecutive_failures = 999
    
    # Try to clean up browser resources immediately
    if hasattr(self, 'browser_context') and self.browser_context:
        try:
            # Try to stop any ongoing browser operations
            page = await self.browser_context.get_current_page()
            await page.evaluate('window.stop()')
        except Exception as e:
            print(f"Error stopping page: {e}")
        
        # Close the browser context
        try:
            await self.browser_context.close()
        except Exception as e:
            print(f"Error closing browser context: {e}")

# Monkey patch the Agent.stop method to use our enhanced version
Agent.stop = stop

# Patch the Agent's step method to check for kill requests
original_step = Agent.step

async def patched_step(self, step_info=None):
    """Patched step method that checks for kill requests"""
    global KILL_AGENT_REQUESTED
    global tab_kill_requests
    
    # Check for kill requests before each step
    if KILL_AGENT_REQUESTED:
        print(f"Kill detected in patched step method for agent {self.id}")
        self.state.stopped = True
        raise asyncio.CancelledError("Global kill requested - stopping agent")
    
    # Check for tab-specific kill
    agent_tab_id = getattr(self, '_tab_id', None)
    if agent_tab_id:
        async with tab_kill_requests_lock:
            if agent_tab_id in tab_kill_requests:
                print(f"Tab-specific kill detected in patched step for tab {agent_tab_id}")
                self.state.stopped = True
                raise asyncio.CancelledError(f"Tab {agent_tab_id} kill requested - stopping agent")
    
    # Call original step method
    return await original_step(self, step_info)

Agent.step = patched_step

# Patch the Agent's multi_act to propagate cancellation properly
original_multi_act = Agent.multi_act

async def patched_multi_act(self, actions, check_for_new_elements=True):
    """Patched multi_act that properly propagates cancellation"""
    try:
        return await original_multi_act(self, actions, check_for_new_elements)
    except InterruptedError as e:
        # If interrupted, set stopped flag and re-raise as CancelledError
        print(f"InterruptedError in multi_act: {e}")
        self.state.stopped = True
        raise asyncio.CancelledError(str(e))

Agent.multi_act = patched_multi_act

# Install signal handlers for graceful termination
def install_signal_handlers():
    def signal_handler(sig, frame):
        print(f"Received signal {sig}, initiating shutdown")
        global KILL_AGENT_REQUESTED
        KILL_AGENT_REQUESTED = True
        
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

# --------------------------------------------------
# Ensure Patchright (stealth mode) can find a Node.js binary.
# It will look at the PATCHRIGHT_NODE env var first.
# We try, in order:
#   1. Existing env var
#   2. `node` in the user PATH
#   3. The bundled Patchright driver (if available)
# --------------------------------------------------

def _ensure_patchright_node():
    if os.environ.get("PATCHRIGHT_NODE"):
        return  # already set by user / env

    # 1. System-wide node
    sys_node = shutil.which("node")
    if sys_node:
        os.environ["PATCHRIGHT_NODE"] = sys_node
        return

    # 2. Bundled driver inside Patchright package
    try:
        import patchright  # imported lazily only if installed

        driver_path = Path(patchright.__file__).parent / "driver" / "node"
        if driver_path.exists():
            os.environ["PATCHRIGHT_NODE"] = str(driver_path)
            return
    except ImportError:
        pass

    # 3. Last resort: warn – Patchright will fail without Node
    print(
        "⚠️  Could not locate a Node.js binary for Patchright. "
        "Stealth mode may fail unless Node is installed or bundled."
    )


_ensure_patchright_node()

# Run the websocket server
if __name__ == "__main__":
    try:
        # Allow command-line argument to restart the websocket server on PORT.
        # Usage examples:
        #   python workflow_run.py restart
        #   ./workflow_run --restart
        # Without arguments the standard server is launched.

        if len(sys.argv) > 1 and sys.argv[1].lower() in {"restart", "--restart", "-r"}:
            print("🔄  Restart flag detected – restarting websocket server…")
            asyncio.run(restart_server())
        else:
            asyncio.run(start_server())

    except KeyboardInterrupt:
        print("Server shutdown requested via KeyboardInterrupt")
    finally:
        print("Server shutdown complete")
import asyncio
import json
import websockets

async def test_workflow():
    """
    Connects to the workflow_run.py WebSocket server, sends a task,
    and prints all responses until the task is complete.
    """
    uri = "ws://localhost:8765"
    print(f"Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print("Connection established.")
            
            # Define a task for the browser agent
            task_prompt = "Go to browser-use.com and find the link to their Discord server."

            # Structure the request message as expected by workflow_run.py
            request_message = {
                "type": "browser_agent_request",
                "prompt": task_prompt,
                "tab_id": "test_tab_1"  # Using a unique ID for the test
            }

            # Send the request
            await websocket.send(json.dumps(request_message))
            print(f"> Sent task: {task_prompt}\n")

            # Listen for responses from the server
            print("--- Listening for server responses ---")
            while True:
                try:
                    message = await websocket.recv()
                    response = json.loads(message)
                    print("< Received response:")
                    print(json.dumps(response, indent=2))

                    # Stop listening if the task is complete or has failed
                    if response.get("type") == "browser_agent_response":
                        print("\n--- Task finished. Closing connection. ---")
                        break
                    
                    if response.get("type") == "browser_agent_tool_call" and response.get("tool_call", {}).get("status") in ["failed", "cancelled"]:
                        print("\n--- Task failed or was cancelled. Closing connection. ---")
                        break

                except websockets.exceptions.ConnectionClosed:
                    print("Connection closed by server.")
                    break

    except ConnectionRefusedError:
        print("\n[ERROR] Connection refused. Is the server in workflow_run.py running?")
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    # Ensure you have the necessary dependencies installed:
    # uv pip install websockets
    print("Starting test client...")
    asyncio.run(test_workflow())
    print("Test client finished.") 
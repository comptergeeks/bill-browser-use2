import asyncio
import os
import platform
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from browser_use import Agent, Browser, BrowserConfig
from browser_use.browser.session import BrowserSession
from browser_use.controller.service import Controller

from browser_use.logging_config import setup_logging

load_dotenv()

setup_logging()


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


# browser = Browser(config=BrowserConfig(browser_binary_path=get_browser_path()))

### LLM OPTIONS
# Get API key from environment or use a fallback mechanism
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    print("⚠️ WARNING: OPENAI_API_KEY not found in environment variables")
    print("Either set it in .env file or provide it explicitly")

try:
    llm = ChatOpenAI(
        model="gpt-4.1",
        temperature=0.0,
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


async def main():
	task = 'Act as an evil villain. Have a convseration with the chatbot on screen. make sure to go back and forth multiple times open a new tab for it.'
	controller = Controller()
	
	# this should work to connect to the available instance
	browser_session= BrowserSession(highlight_elements=False, cdp_url="http://localhost:9222")
	
	agent = Agent(
		browser_session=browser_session,
		task=task,
		llm=llm,
		controller=controller,
		use_vision=True
	)
	await agent.run()


if __name__ == '__main__':
	asyncio.run(main())
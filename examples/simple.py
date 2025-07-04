import asyncio
import os
from pathlib import Path
import platform
import sys

<<<<<<< HEAD
from browser_use.browser.context import Browser, BrowserConfig
from browser_use.browser.session import BrowserSession
=======
from browser_use.llm.openai.chat import ChatOpenAI
>>>>>>> 0.4.2

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


from browser_use import Agent

# Initialize the model
# let's run simple.py with the cdp url
llm = ChatOpenAI(
	model='gpt-4.1-mini',
)
<<<<<<< HEAD
=======


task = 'Open 3 tabs with random wikipedia pages'
agent = Agent(task=task, llm=llm)
>>>>>>> 0.4.2

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


browser = Browser(config=BrowserConfig(browser_instance_path=get_browser_path()))

task = 'Go to kayak.com and find the cheapest one-way flight from Zurich to San Francisco in 3 weeks.'
agent = Agent(task=task, llm=llm, browser_session=BrowserSession(highlight_elements=False))

async def main():
	history = await agent.run()
	# token usage
	print(history.usage)


if __name__ == '__main__':
	asyncio.run(main())

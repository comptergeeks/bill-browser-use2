import asyncio
import os
import platform
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from browser_use.browser.profile import BrowserProfile
from dotenv import load_dotenv

load_dotenv()

from langchain_openai import ChatOpenAI

from browser_use import Agent


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


# Initialize the model
llm = ChatOpenAI(
	model='gpt-4o',
	temperature=0.0,
)
task = 'Go to kayak.com and find the cheapest one-way flight from Zurich to San Francisco in 3 weeks.'
agent = Agent(task=task, llm=llm)


async def main():
	await agent.run()


if __name__ == '__main__':
	asyncio.run(main())
import asyncio
import os
import platform
import sys
from pathlib import Path

# Ensure project root is on PYTHONPATH when running as a script
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from browser_use import Agent, ChatOpenAI
from browser_use.browser.profile import BrowserProfile
from browser_use.browser.session import BrowserSession

from browser_use.controller.service import Controller
from browser_use.logging_config import setup_logging

load_dotenv()

setup_logging()


def get_browser_path() -> Path | None:
    """Return a platform-specific path to the packaged Chromium build if bundled.

    Returns None if the path cannot be determined – the default Playwright
    browser will then be used.
    """
    # Resolve directory of the running entry-point (handles PyInstaller bundle)
    base_dir = (
        os.path.dirname(sys.executable)
        if getattr(sys, "frozen", False)
        else os.path.dirname(os.path.abspath(__file__))
    )

    if platform.system() == "Darwin":
        # Prefer a system-wide install if present, otherwise fall back to a
        # relative path next to the executable.
        system_path = "/Applications/Meteor.app/Contents/MacOS/Meteor"
        relative_path = os.path.join(base_dir, "Meteor")
        if os.path.exists(system_path):
            return Path(system_path)
        if os.path.exists(relative_path):
            return Path(relative_path)
    elif platform.system() == "Windows":
        candidate = Path(base_dir) / "Bill-Gates-Browser.exe"
        return candidate if candidate.exists() else None

    # Unsupported/unknown – caller can decide what to do.
    return None


# browser = Browser(config=BrowserConfig(browser_binary_path=get_browser_path()))

### LLM OPTIONS
# Get API key from environment or use a fallback mechanism
openai_api_key = os.environ.get("OPENAI_API_KEY")
if not openai_api_key:
    print("⚠️ WARNING: OPENAI_API_KEY not found in environment variables")
    print("Either set it in .env file or provide it explicitly")

llm = ChatOpenAI(
    model="gpt-4.1",  # Use the latest supported model name
    temperature=0.0,
    api_key=openai_api_key,
)


async def main():
    task = "open chess.com and play a game against a random opponent play until you win.."
    controller = Controller()

    # Re-use an already running Chromium instance if one is exposed via CDP.
    browser_session = BrowserSession(
        browser_profile=BrowserProfile(highlight_elements=False),
        cdp_url="http://localhost:9222",
    )

    agent = Agent(
        browser_session=browser_session,
        task=task,
        llm=llm,
        controller=controller,
        use_vision=True,
    )
    await agent.run()


if __name__ == "__main__":
    asyncio.run(main())

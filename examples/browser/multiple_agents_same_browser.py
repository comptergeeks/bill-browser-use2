import asyncio
import os
import sys

<<<<<<< HEAD
from langchain_openai import ChatOpenAI

from browser_use.browser.session import BrowserSession

=======
>>>>>>> 0.2.6
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv

load_dotenv()


<<<<<<< HEAD
from browser_use import Agent


# Video: https://preview.screen.studio/share/8Elaq9sm
async def main():
	# Persist the browser state across agents
	browser_session = BrowserSession(
		keep_alive=True,
		user_data_dir=None,
	)
	await browser_session.start()

	async def get_input():
		return await asyncio.get_event_loop().run_in_executor(
			None, lambda: input('Enter task (p: pause current agent, r: resume, b: break): ')
		)

	current_agent = None
	llm = ChatOpenAI(model='gpt-4o')

	while True:
		task = await get_input()

		if task.lower() == 'p':
			# Pause the current agent if one exists
			if current_agent:
				current_agent.pause()
			continue
		elif task.lower() == 'r':
			# Resume the current agent if one exists
			if current_agent:
				current_agent.resume()
			continue
		elif task.lower() == 'b':
			# Break the current agent's execution if one exists
			if current_agent:
				current_agent.stop()
				current_agent = None
			continue

		# If there's a current agent running, pause it before starting new one
		# if current_agent:
		# 	current_agent.pause()

		await browser_session.create_new_tab()
		current_agent = Agent(
			task=task,
			browser_session=browser_session,
			llm=llm,
		)

		# Run the agent asynchronously without blocking
		asyncio.create_task(current_agent.run())


asyncio.run(main())

# Now aad the cheapest to the cart
=======
from langchain_openai import ChatOpenAI

from browser_use import Agent
from browser_use.browser.session import BrowserSession


async def main():
	browser_session = BrowserSession(
		keep_alive=True,
		user_data_dir=None,
		headless=False,
	)
	await browser_session.start()

	current_agent = None
	llm = ChatOpenAI(model='gpt-4o')

	task1 = 'find todays weather on San Francisco and extract it as json'
	task2 = 'find todays weather in Zurich and extract it as json'

	agent1 = Agent(
		task=task1,
		browser_session=browser_session,
		llm=llm,
	)
	agent2 = Agent(
		task=task2,
		browser_session=browser_session,
		llm=llm,
	)

	await asyncio.gather(agent1.run(), agent2.run())
	await browser_session.kill()


asyncio.run(main())
>>>>>>> 0.2.6

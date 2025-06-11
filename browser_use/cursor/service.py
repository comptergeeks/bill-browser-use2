# make a cursor manager that can be used to interact with the
from playwright.async_api import ElementHandle, Page

from typing


class CursorManager:
	# maybe add custom stuff for colors and everything for now just take the other code
	def __init__(self):
		self.cursor = None
		self.currPage = None
		self.color = None
    # initialize the cursor here
    # called on each page


	def initialize_cursor_display(self, browserPage: Page):






    def update_cursor_thoughts(self, thoughts: Text):
        #

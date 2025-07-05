# @file purpose: Manages the visual cursor display for the browser-use AI agent
"""
CursorManager handles the visual representation of where the AI agent is looking/clicking
on web pages. It injects a custom cursor, laser pointer, and thought bubble into the page,
maintains cursor positions across tab switches, and automatically cleans up when tabs close.
"""

from playwright.async_api import Page
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class CursorManager:
    """Manages cursor display and positioning across browser pages"""
    
    def __init__(self):
        """Initialize the cursor manager with default settings"""
        self.cursor_positions: Dict[str, Tuple[int, int]] = {}  # Store positions per page URL
        self.current_page: Optional[Page] = None
        self.cursor_color = "#6B1ECA"  # Default purple color
        self.cursor_initialized = False
        
    async def initialize_cursor_display(self, browser_page: Page) -> Dict:
        """
        Initialize cursor element on the given page.
        
        Args:
            browser_page: The Playwright page to inject the cursor into
            
        Returns:
            Dict with success status and cursor position
        """
        try:
            self.current_page = browser_page
            page_url = browser_page.url
            
            # Get stored position or default to (0, 0)
            # get the position of the center of the page
            # and then place it there
            stored_position = self.cursor_positions.get(page_url, (0, 0))
            start_x, start_y = stored_position
            
            # Get viewport size for debugging
            viewport_size = await browser_page.evaluate("""() => {
                return {
                    width: window.innerWidth,
                    height: window.innerHeight
                };
            }""")
            
            logger.debug(f"Initializing cursor on {page_url} at position ({start_x}, {start_y})")
            logger.debug(f"Viewport size: {viewport_size}")
            
            # Inject cursor elements into the page
            result = await browser_page.evaluate(f"""() => {{
                console.log("Starting cursor initialization");
                
                // First, check if elements already exist and remove them
                const existingCursor = document.getElementById('ai-cursor');
                const existingLaser = document.getElementById('ai-laser');
                const existingThought = document.getElementById('ai-thought-bubble');
                
                if (existingCursor) {{
                    console.log("Removing existing cursor");
                    existingCursor.remove();
                }}
                
                if (existingLaser) {{
                    console.log("Removing existing laser");
                    existingLaser.remove();
                }}
                
                if (existingThought) {{
                    console.log("Removing existing thought bubble");
                    existingThought.remove();
                }}
                
                try {{
                    // Custom SVG cursor
                    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                    svg.id = 'ai-cursor';
                    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
                    svg.setAttribute('width', '26');
                    svg.setAttribute('height', '26');
                    svg.setAttribute('viewBox', '0 0 24 24');
                    
                    // Critical styling properties
                    svg.style.position = 'fixed';
                    svg.style.pointerEvents = 'none';
                    svg.style.zIndex = '9999';
                    svg.style.left = '{start_x}px';
                    svg.style.top = '{start_y}px';
                    svg.style.transition = 'top 0.5s ease, left 0.5s ease';
                    svg.style.transform = 'translate(-18.75%, -3.29%)';
                    
                    // Create polygon for the arrow
                    const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    polygon.setAttribute('points', '4.5,0.79 4.5,23.21 11.06,16.64 20.35,16.64');
                    polygon.setAttribute('fill', '{self.cursor_color}');
                    polygon.setAttribute('filter', 'drop-shadow(0 1px 3px rgba(0, 0, 0, 0.25))');
                    
                    // Create the border/outline effect
                    const borderPolygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
                    borderPolygon.setAttribute('points', '4.5,0.79 4.5,23.21 11.06,16.64 20.35,16.64');
                    borderPolygon.setAttribute('fill', 'transparent');
                    borderPolygon.setAttribute('stroke', '#fff');
                    borderPolygon.setAttribute('stroke-width', '1');
                    borderPolygon.style.pointerEvents = 'none';
                    
                    // Append both polygons to the SVG
                    svg.appendChild(polygon);
                    svg.appendChild(borderPolygon);
                    
                    // Add the SVG to the document
                    document.body.appendChild(svg);
                    console.log("SVG Cursor added to page");
                    
                    // Laser pointer
                    const laser = document.createElement('div');
                    laser.id = 'ai-laser';
                    laser.style.position = 'fixed';
                    laser.style.width = '10px';
                    laser.style.height = '10px';
                    laser.style.borderRadius = '50%';
                    laser.style.backgroundColor = 'rgba(255, 0, 0, 0.7)';
                    laser.style.boxShadow = '0 0 10px 2px rgba(255, 0, 0, 0.5)';
                    laser.style.transition = 'top 0.5s ease, left 0.5s ease';
                    laser.style.pointerEvents = 'none';
                    laser.style.zIndex = '9998';
                    laser.style.left = '{start_x}px';
                    laser.style.top = '{start_y}px';
                    document.body.appendChild(laser);
                    console.log("Laser added to page");
                    
                    // Thought bubble element
                    const thoughtBubble = document.createElement('div');
                    thoughtBubble.id = 'ai-thought-bubble';
                    thoughtBubble.style.position = 'fixed';
                    thoughtBubble.style.width = '200px';
                    thoughtBubble.style.padding = '8px';
                    thoughtBubble.style.background = 'rgba(128, 0, 255, 0.7)';
                    thoughtBubble.style.color = 'white';
                    thoughtBubble.style.boxShadow = '0 2px 10px rgba(128, 0, 255, 0.3)';
                    thoughtBubble.style.borderRadius = '8px';
                    thoughtBubble.style.fontSize = '12px';
                    thoughtBubble.style.transition = 'top 0.5s ease, left 0.5s ease';
                    thoughtBubble.style.pointerEvents = 'none';
                    thoughtBubble.style.zIndex = '9997';
                    thoughtBubble.style.fontFamily = 'Arial, sans-serif';
                    thoughtBubble.style.maxHeight = '60px';
                    thoughtBubble.style.overflow = 'auto';
                    thoughtBubble.style.lineHeight = '1.2';
                    thoughtBubble.style.left = '{start_x + 20}px';
                    thoughtBubble.style.top = '{start_y + 20}px';
                    
                    // Add inner container for thought content
                    const thoughtContent = document.createElement('div');
                    thoughtContent.id = 'ai-thought-content';
                    thoughtContent.style.maxHeight = '40px';
                    thoughtContent.style.overflow = 'hidden';
                    thoughtContent.innerText = 'Thinking...';
                    
                    thoughtBubble.appendChild(thoughtContent);
                    document.body.appendChild(thoughtBubble);
                    console.log("Thought bubble added to page");
                    
                    return {{
                        success: true,
                        message: "All cursor elements initialized",
                        position: {{ x: {start_x}, y: {start_y} }}
                    }};
                }} catch (error) {{
                    console.error("Error creating cursor:", error);
                    return {{
                        success: false,
                        error: error.toString()
                    }};
                }}
            }}""")
            
            # Update stored position if initialization was successful
            if result and result.get('success'):
                self.cursor_positions[page_url] = (start_x, start_y)
                self.cursor_initialized = True
                
            return result
            
        except Exception as e:
            logger.error(f"Error initializing cursor: {str(e)}")
            self.cursor_initialized = False
            return {"success": False, "error": str(e)}
    
    async def move_cursor(self, x: int, y: int) -> Dict:
        """
        Move cursor to specified coordinates on the current page.
        
        Args:
            x: X coordinate
            y: Y coordinate
            
        Returns:
            Dict with success status and new position
        """
        if not self.current_page:
            return {"success": False, "error": "No active page"}
            
        try:
            logger.debug(f"Moving cursor to ({x}, {y})")
            
            # Check if cursor exists on page
            cursor_exists = await self.current_page.evaluate("""() => {
                return !!document.getElementById("ai-cursor");
            }""")
            
            if not cursor_exists:
                logger.debug("Cursor not found, initializing before moving")
                await self.initialize_cursor_display(self.current_page)
            
            # Move cursor elements
            result = await self.current_page.evaluate(f"""() => {{
                try {{
                    console.log("Moving cursor to {x}, {y}");
                    
                    const svgCursor = document.getElementById('ai-cursor');
                    const laser = document.getElementById('ai-laser');
                    const thoughtBubble = document.getElementById('ai-thought-bubble');
                    
                    if (svgCursor) {{
                        svgCursor.style.transition = 'top 0.5s ease, left 0.5s ease';
                        svgCursor.style.left = "{x}px";
                        svgCursor.style.top = "{y}px";
                        console.log("SVG cursor moved");
                    }}
                    
                    if (laser) {{
                        laser.style.transition = 'top 0.5s ease, left 0.5s ease';
                        laser.style.left = "{x}px";
                        laser.style.top = "{y}px";
                        
                        // Add a pulse effect
                        laser.style.transform = 'scale(1.5)';
                        laser.style.opacity = '1';
                        setTimeout(() => {{
                            laser.style.transform = 'scale(1)';
                            laser.style.opacity = '0.7';
                        }}, 300);
                        
                        console.log("Laser moved");
                    }}
                    
                    // Move thought bubble with cursor
                    if (thoughtBubble) {{
                        thoughtBubble.style.transition = 'top 0.5s ease, left 0.5s ease';
                        thoughtBubble.style.left = `${{{x} + 20}}px`;
                        thoughtBubble.style.top = `${{{y} + 20}}px`;
                        console.log("Thought bubble moved");
                    }}
                    
                    return {{
                        success: true,
                        elementsFound: {{
                            svgCursor: !!svgCursor,
                            laser: !!laser,
                            thoughtBubble: !!thoughtBubble
                        }},
                        position: {{ x: {x}, y: {y} }}
                    }};
                }} catch (error) {{
                    console.error("Error moving cursor:", error);
                    return {{
                        success: false,
                        error: error.toString()
                    }};
                }}
            }}""")
            
            # Update stored position if movement was successful
            if result and result.get('success') and self.current_page:
                self.cursor_positions[self.current_page.url] = (x, y)
            
            return result
            
        except Exception as e:
            logger.error(f"Error moving cursor: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def update_cursor_thoughts(self, thoughts: str) -> bool:
        """
        Update the text in the thought bubble.
        
        Args:
            thoughts: Text to display in the thought bubble
            
        Returns:
            bool: True if update was successful
        """
        if not self.current_page:
            return False
            
        try:
            # Ensure text is properly escaped for JavaScript
            escaped_text = thoughts.replace("'", "\\'").replace('"', '\\"').replace('\n', ' ')
            
            # Limit text length to prevent overflow
            if len(escaped_text) > 200:
                escaped_text = escaped_text[:197] + "..."
            
            # Update the thought bubble text
            result = await self.current_page.evaluate(f"""() => {{
                try {{
                    const thoughtContent = document.getElementById('ai-thought-content');
                    if (thoughtContent) {{
                        thoughtContent.innerText = "{escaped_text}";
                        return true;
                    }}
                    return false;
                }} catch (error) {{
                    console.error("Error updating thought bubble:", error);
                    return false;
                }}
            }}""")
            
            return result
            
        except Exception as e:
            logger.error(f"Error updating thought bubble: {str(e)}")
            return False
    
    async def remove_cursor(self) -> bool:
        """
        Remove cursor elements from the current page.
        
        Returns:
            bool: True if removal was successful
        """
        if not self.current_page:
            return False
            
        try:
            result = await self.current_page.evaluate("""() => {
                try {
                    const elements = ['ai-cursor', 'ai-laser', 'ai-thought-bubble'];
                    let removed = 0;
                    
                    elements.forEach(id => {
                        const element = document.getElementById(id);
                        if (element) {
                            element.remove();
                            removed++;
                        }
                    });
                    
                    return removed > 0;
                } catch (error) {
                    console.error("Error removing cursor elements:", error);
                    return false;
                }
            }""")
            
            if result:
                self.cursor_initialized = False
                
            return result
            
        except Exception as e:
            logger.error(f"Error removing cursor: {str(e)}")
            return False

    async def remove_cursor_from_page(self, page) -> Dict:
        """
        Remove cursor elements from a specific page.
        
        Args:
            page: The Playwright page to remove cursor from
            
        Returns:
            Dict with removal results for the page
        """
        if not page:
            return {"success": False, "error": "No page provided"}
            
        try:
            page_url = getattr(page, 'url', 'unknown_page')
            
            # Check if page is closed or inaccessible
            if getattr(page, 'is_closed', lambda: True)():
                return {"success": False, "error": "Page is closed"}
            
            # Remove cursor elements from this page
            removed = await page.evaluate("""() => {
                try {
                    const elements = ['ai-cursor', 'ai-laser', 'ai-thought-bubble'];
                    let removed = 0;
                    
                    elements.forEach(id => {
                        const element = document.getElementById(id);
                        if (element) {
                            element.remove();
                            removed++;
                            console.log(`Removed cursor element: ${id} from page`);
                        }
                    });
                    
                    return removed;
                } catch (error) {
                    console.error("Error removing cursor elements:", error);
                    return 0;
                }
            }""")
            
            # Clear stored position for this page if cursor was removed
            if removed > 0 and page_url in self.cursor_positions:
                del self.cursor_positions[page_url]
            
            # If this was the current page, reset cursor state
            if page == self.current_page and removed > 0:
                self.cursor_initialized = False
                
            return {
                "success": True,
                "page_url": page_url,
                "elements_removed": removed
            }
            
        except Exception as e:
            error_msg = f"Error removing cursor from page: {str(e)}"
            logger.error(error_msg)
            return {"success": False, "error": error_msg}
    
    # use this once the agent is k
    async def remove_cursor_from_all_pages(self, browser_context) -> Dict:
        """
        Remove cursor elements from all pages in a browser context.
        Useful for cleanup when switching between different browser sessions.
        
        Args:
            browser_context: The Playwright browser context containing all pages
            
        Returns:
            Dict with removal results for each page
        """
        if not browser_context:
            return {"success": False, "error": "No browser context provided"}
            
        results = {}
        total_removed = 0
        
        try:
            pages = browser_context.pages if hasattr(browser_context, 'pages') else []
            
            for i, page in enumerate(pages):
                page_url = getattr(page, 'url', f'page_{i}')
                try:
                    # Skip pages that are closed or inaccessible
                    if getattr(page, 'is_closed', lambda: True)():
                        results[page_url] = {"success": False, "reason": "page_closed"}
                        continue
                    
                    # Remove cursor elements from this page
                    removed = await page.evaluate("""() => {
                        try {
                            const elements = ['ai-cursor', 'ai-laser', 'ai-thought-bubble'];
                            let removed = 0;
                            
                            elements.forEach(id => {
                                const element = document.getElementById(id);
                                if (element) {
                                    element.remove();
                                    removed++;
                                    console.log(`Removed cursor element: ${id}`);
                                }
                            });
                            
                            return removed;
                        } catch (error) {
                            console.error("Error removing cursor elements:", error);
                            return 0;
                        }
                    }""")
                    
                    results[page_url] = {
                        "success": True, 
                        "elements_removed": removed
                    }
                    total_removed += removed
                    
                    # Clear stored position for this page if cursor was removed
                    if removed > 0 and page_url in self.cursor_positions:
                        del self.cursor_positions[page_url]
                        
                except Exception as e:
                    results[page_url] = {
                        "success": False, 
                        "error": str(e)
                    }
                    logger.debug(f"Failed to remove cursor from {page_url}: {str(e)}")
            
            # Reset cursor state if we removed cursors
            if total_removed > 0:
                self.cursor_initialized = False
                self.current_page = None
                
            return {
                "success": True,
                "total_pages_processed": len(pages),
                "total_elements_removed": total_removed,
                "page_results": results
            }
            
        except Exception as e:
            logger.error(f"Error in remove_cursor_from_all_pages: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def cleanup_and_reset(self, browser_context=None) -> bool:
        """
        Complete cleanup and reset of cursor manager state.
        Removes all cursors and resets all internal state.
        
        Args:
            browser_context: Optional browser context to clean up cursors from all pages
            
        Returns:
            bool: True if cleanup was successful
        """
        try:
            # Remove cursors from all pages if browser context provided
            if browser_context:
                removal_results = await self.remove_cursor_from_all_pages(browser_context)
                logger.debug(f"Cursor cleanup results: {removal_results}")
            else:
                # Just remove from current page
                await self.remove_cursor()
            
            # Reset all internal state
            self.cursor_positions.clear()
            self.current_page = None
            self.cursor_initialized = False
            
            logger.debug("Cursor manager state reset complete")
            return True
            
        except Exception as e:
            logger.error(f"Error during cursor cleanup and reset: {str(e)}")
            return False
    
    async def handle_page_switch(self, new_page: Page) -> Dict:
        """
        Handle switching to a new page/tab, initializing cursor at stored position.
        
        Args:
            new_page: The new Playwright page being switched to
            
        Returns:
            Dict with success status
        """
        logger.debug(f"Handling page switch to {new_page.url}")
        self.current_page = new_page
        return await self.initialize_cursor_display(new_page)
    
    def get_cursor_position(self, page_url: str) -> Tuple[int, int]:
        """
        Get the stored cursor position for a specific page.
        
        Args:
            page_url: URL of the page
            
        Returns:
            Tuple of (x, y) coordinates, defaults to (0, 0) if not found
        """
        return self.cursor_positions.get(page_url, (0, 0))
    
    def set_cursor_color(self, color: str):
        """
        Set the cursor color for future cursor initializations.
        
        Args:
            color: Hex color code (e.g., "#6B1ECA")
        """
        self.cursor_color = color 
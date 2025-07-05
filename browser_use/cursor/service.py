# @file purpose: Manages the visual cursor display for the browser-use AI agent
"""
CursorManager handles the visual representation of where the AI agent is looking/clicking
on web pages. It injects a custom cursor and thought bubble into the page,
maintains cursor positions across tab switches, and automatically cleans up when tabs close.
"""

from playwright.async_api import Page
from typing import Dict, Optional, Tuple
import asyncio
import logging

logger = logging.getLogger(__name__)


class CursorManager:
    """Manages cursor display and positioning across browser pages"""
    
    def __init__(self):
        """Initialize the cursor manager with default settings"""
        self.cursor_positions: Dict[str, Tuple[int, int]] = {}  # Store positions per page URL
        self.current_page: Optional[Page] = None
        self.cursor_color = "#0066cc"  # Default blue color
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
            # get the center of the page
            viewport_size = await browser_page.evaluate("""() => {
                return {
                    width: window.innerWidth,
                    height: window.innerHeight
                };
            }""")
            
            center_x = viewport_size['width'] / 2 # type: ignore
            center_y = viewport_size['height'] / 2 # type: ignore

            # get the position of the center of the page
            start_x = center_x
            start_y = center_y

            stored_position = self.cursor_positions.get(page_url, (start_x, start_y))
            start_x, start_y = stored_position
            
            # Convert cursor color to RGB for thought bubble
            r, g, b = self._hex_to_rgb(self.cursor_color)
            
            # Get viewport size for debugging

            
            logger.debug(f"Initializing cursor on {page_url} at position ({start_x}, {start_y})")
            logger.debug(f"Viewport size: {viewport_size}")
            
            # Inject cursor elements into the page
            result = await browser_page.evaluate(f"""() => {{
                console.log("Starting cursor initialization");
                
                // First, check if elements already exist and preserve thoughts
                const existingCursor = document.getElementById('ai-cursor');
                const existingThought = document.getElementById('ai-thought-bubble');
                const existingThoughtContent = document.getElementById('ai-thought-content');
                let preservedThoughts = 'Thinking...';
                
                // Preserve existing thoughts if they exist and aren't default
                if (existingThoughtContent && existingThoughtContent.innerText && 
                    existingThoughtContent.innerText !== 'Thinking...' && 
                    existingThoughtContent.innerText.trim() !== '') {{
                    preservedThoughts = existingThoughtContent.innerText;
                    console.log("Preserving existing thoughts:", preservedThoughts);
                }}
                
                if (existingCursor) {{
                    console.log("Removing existing cursor");
                    existingCursor.remove();
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
                    
                    // Thought bubble element
                    const thoughtBubble = document.createElement('div');
                    thoughtBubble.id = 'ai-thought-bubble';
                    thoughtBubble.style.position = 'fixed';
                    thoughtBubble.style.width = '200px';
                    thoughtBubble.style.padding = '8px';
                    thoughtBubble.style.background = 'rgba({r}, {g}, {b}, 0.7)';
                    thoughtBubble.style.color = 'white';
                    thoughtBubble.style.boxShadow = '0 2px 10px rgba({r}, {g}, {b}, 0.3)';
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
                    thoughtContent.innerText = preservedThoughts;
                    
                    thoughtBubble.appendChild(thoughtContent);
                    document.body.appendChild(thoughtBubble);
                    console.log("Thought bubble added to page");
                    
                    return {{
                        success: true,
                        message: "Cursor and thought bubble initialized",
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
        Move cursor to specified coordinates on the current page with smooth animation.
        
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
            
            # Get current position
            current_pos = await self.current_page.evaluate("""() => {
                const svgCursor = document.getElementById('ai-cursor');
                if (!svgCursor) return null;
                const style = window.getComputedStyle(svgCursor);
                return {
                    x: parseInt(style.left) || 0,
                    y: parseInt(style.top) || 0
                };
            }""")
            
            if not current_pos:
                # If we can't get current position, just move directly
                current_pos = {'x': x, 'y': y}
            
            # Calculate distance for dynamic duration
            distance = ((x - current_pos['x']) ** 2 + (y - current_pos['y']) ** 2) ** 0.5
            # Adjust duration based on distance (min 500ms, max 800ms)
            duration = min(800, max(500, int(distance * 0.8)))
            
            # Move cursor elements with smooth animation
            result = await self.current_page.evaluate(f"""() => {{
                try {{
                    console.log("Moving cursor to {x}, {y} with animation");
                    
                    const svgCursor = document.getElementById('ai-cursor');
                    const thoughtBubble = document.getElementById('ai-thought-bubble');
                    
                    // Easing function (ease-in-out quart - more natural)
                    const easeInOutQuart = (t) => {{
                        return t < 0.5 
                            ? 8 * t * t * t * t 
                            : 1 - Math.pow(-2 * t + 2, 4) / 2;
                    }};
                    
                    if (svgCursor) {{
                        const startX = parseInt(svgCursor.style.left) || 0;
                        const startY = parseInt(svgCursor.style.top) || 0;
                        const targetX = {x};
                        const targetY = {y};
                        const duration = {duration};
                        const startTime = performance.now();
                        
                        // Remove any existing transition for smoother animation
                        svgCursor.style.transition = 'none';
                        if (thoughtBubble) {{
                            thoughtBubble.style.transition = 'none';
                        }}
                        
                        function animate(currentTime) {{
                            const elapsed = currentTime - startTime;
                            const progress = Math.min(elapsed / duration, 1);
                            const easedProgress = easeInOutQuart(progress);
                            
                            const currentX = startX + (targetX - startX) * easedProgress;
                            const currentY = startY + (targetY - startY) * easedProgress;
                            
                            svgCursor.style.left = currentX + 'px';
                            svgCursor.style.top = currentY + 'px';
                            
                            if (thoughtBubble) {{
                                thoughtBubble.style.left = (currentX + 20) + 'px';
                                thoughtBubble.style.top = (currentY + 20) + 'px';
                            }}
                            
                            if (progress < 1) {{
                                requestAnimationFrame(animate);
                            }} else {{
                                console.log("Cursor animation completed");
                            }}
                        }}
                        
                        requestAnimationFrame(animate);
                    }}
                    
                    return {{
                        success: true,
                        elementsFound: {{
                            svgCursor: !!svgCursor,
                            thoughtBubble: !!thoughtBubble
                        }},
                        position: {{ x: {x}, y: {y} }},
                        duration: {duration}
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
                
                # Wait for animation to complete
                await asyncio.sleep(duration / 1000.0)
            
            return result
            
        except Exception as e:
            logger.error(f"Error moving cursor: {str(e)}")
            return {"success": False, "error": str(e)}
    
    async def update_cursor_thoughts(self, thoughts: str) -> bool:
        """
        Update the text in the thought bubble with streaming animation.
        
        Args:
            thoughts: Text to display in the thought bubble
            
        Returns:
            bool: True if update was successful
        """
        if not self.current_page:
            return False
            
        try:
            logger.debug(f"Updating cursor thoughts with: {thoughts}")
            
            # Clean up text: replace newlines with spaces and limit length
            clean_text = thoughts.replace('\n', ' ').replace('\r', ' ')
            
            # Limit text length to prevent overflow
            if len(clean_text) > 200:
                clean_text = clean_text[:197] + "..."
            
            logger.debug(f"Clean text: {clean_text}")
            
            # Stream the text character by character with animation
            # Use parameter passing to avoid escaping issues
            result = await self.current_page.evaluate("""(targetText) => {
                try {
                    console.log("Updating cursor thoughts with:", targetText);
                    const thoughtContent = document.getElementById('ai-thought-content');
                    if (!thoughtContent) {
                        console.log("Thought content element not found");
                        return false;
                    }
                    
                    const currentText = thoughtContent.innerText || "";
                    
                    // If the text is the same, don't update to prevent flashing
                    if (currentText === targetText) {
                        console.log("Text unchanged, skipping update");
                        return true;
                    }
                    
                    // Clear any existing animation
                    if (window.thoughtStreamingAnimation) {
                        clearTimeout(window.thoughtStreamingAnimation);
                        window.thoughtStreamingAnimation = null;
                    }
                    
                    // Store the target text to prevent conflicts
                    window.thoughtStreamingTarget = targetText;
                    
                    console.log("Starting streaming animation for:", targetText);
                    
                    // Start streaming animation
                    let charIndex = 0;
                    const streamText = () => {
                        // Check if this is still the current target (prevent conflicts)
                        if (window.thoughtStreamingTarget !== targetText) {
                            console.log("Animation cancelled - new target set");
                            return;
                        }
                        
                        if (charIndex <= targetText.length) {
                            thoughtContent.innerText = targetText.substring(0, charIndex);
                            charIndex++;
                            
                            // Continue streaming with delay between characters
                            window.thoughtStreamingAnimation = setTimeout(streamText, 8); // 8ms per character (much faster)
                        } else {
                            // Animation complete
                            window.thoughtStreamingAnimation = null;
                            console.log("Streaming animation completed");
                        }
                    };
                    
                    // Start the streaming animation
                    streamText();
                    
                    return true;
                } catch (error) {
                    console.error("Error updating thought bubble:", error);
                    return false;
                }
            }""", clean_text)
            
            logger.debug(f"JavaScript evaluation result: {result}")
            return result
            
        except Exception as e:
            logger.error(f"Error updating thought bubble: {str(e)}")
            return False

    async def animate_click(self) -> Dict:
        """
        Animate a click effect on the cursor.
        
        Returns:
            Dict: Result of the click animation
        """
        if not self.current_page:
            return {"success": False, "error": "No current page set"}
            
        try:
            logger.debug("Animating cursor click")
            
            # Check if cursor exists on page
            cursor_exists = await self.current_page.evaluate("""() => {
                return !!document.getElementById("ai-cursor");
            }""")
            
            if not cursor_exists:
                logger.debug("Cursor not found, cannot animate click")
                return {"success": False, "error": "Cursor not found"}
            
            # Animate click effect
            result = await self.current_page.evaluate("""() => {
                try {
                    const svgCursor = document.getElementById('ai-cursor');
                    if (!svgCursor) return { success: false, error: "Cursor not found" };
                    
                    // Animate the cursor with a more pronounced click effect
                    const originalTransform = svgCursor.style.transform || '';
                    
                    // Easing function (ease-in-out quart - same as cursor movement)
                    const easeInOutQuart = (t) => {
                        return t < 0.5 
                            ? 8 * t * t * t * t 
                            : 1 - Math.pow(-2 * t + 2, 4) / 2;
                    };
                    
                    // Use requestAnimationFrame for smooth animation
                    let startTime = performance.now();
                    const duration = 200; // 200ms total animation
                    
                    function animateClick(currentTime) {
                        const elapsed = currentTime - startTime;
                        const progress = Math.min(elapsed / duration, 1);
                        const easedProgress = easeInOutQuart(progress);
                        
                        // Create a smooth scale animation: down to 0.7, then back to 1
                        let scale;
                        if (easedProgress < 0.5) {
                            // First half: scale down to 0.7
                            scale = 1 - (easedProgress * 2) * 0.3; // From 1 to 0.7
                        } else {
                            // Second half: scale back up to 1
                            scale = 0.7 + ((easedProgress - 0.5) * 2) * 0.3; // From 0.7 to 1
                        }
                        
                        // Apply the scale transformation
                        svgCursor.style.transform = originalTransform + ` scale(${scale})`;
                        
                        if (progress < 1) {
                            requestAnimationFrame(animateClick);
                        } else {
                            // Reset to original transform
                            svgCursor.style.transform = originalTransform;
                        }
                    }
                    
                    requestAnimationFrame(animateClick);
                    
                    return {
                        success: true,
                        message: "Click animation completed"
                    };
                } catch (error) {
                    console.error("Error animating click:", error);
                    return {
                        success: false,
                        error: error.toString()
                    };
                }
            }""")
            
            # Wait for animation to complete
            await asyncio.sleep(0.2)  # 200ms animation duration
            
            return result
            
        except Exception as e:
            logger.error(f"Error animating click: {str(e)}")
            return {"success": False, "error": str(e)}
    
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
                    const elements = ['ai-cursor', 'ai-thought-bubble'];
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
                    const elements = ['ai-cursor', 'ai-thought-bubble'];
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
                            const elements = ['ai-cursor', 'ai-thought-bubble'];
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
        
        # Check if cursor already exists on this page before re-initializing
        try:
            cursor_exists = await new_page.evaluate("""() => {
                return !!document.getElementById('ai-cursor');
            }""")
            
            if cursor_exists:
                logger.debug("Cursor already exists on page, skipping re-initialization")
                return {
                    "success": True,
                    "message": "Cursor already exists on page",
                    "position": self.get_cursor_position(new_page.url)
                }
        except Exception as e:
            logger.debug(f"Failed to check cursor existence: {e}")
        
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
    
    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """
        Convert hex color to RGB values.
        
        Args:
            hex_color: Hex color string (e.g., "#FF0000" or "#f00")
            
        Returns:
            Tuple of (r, g, b) values
        """
        # Remove the # if present
        hex_color = hex_color.lstrip('#')
        
        # Handle 3-character hex codes by expanding them
        if len(hex_color) == 3:
            hex_color = ''.join([c*2 for c in hex_color])
        
        # Convert to RGB
        try:
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            return (r, g, b)
        except (ValueError, IndexError):
            # Fallback to blue if invalid hex
            return (0, 102, 204)  # #0066cc
    
    async def update_thought_bubble_color(self) -> bool:
        """
        Update the thought bubble color to match the current cursor color.
        
        Returns:
            bool: True if update was successful
        """
        if not self.current_page:
            return False
            
        try:
            # Convert cursor color to RGB
            r, g, b = self._hex_to_rgb(self.cursor_color)
            
            result = await self.current_page.evaluate(f"""() => {{
                try {{
                    const thoughtBubble = document.getElementById('ai-thought-bubble');
                    if (thoughtBubble) {{
                        thoughtBubble.style.background = 'rgba({r}, {g}, {b}, 0.7)';
                        thoughtBubble.style.boxShadow = '0 2px 10px rgba({r}, {g}, {b}, 0.3)';
                        return true;
                    }}
                    return false;
                }} catch (error) {{
                    console.error("Error updating thought bubble color:", error);
                    return false;
                }}
            }}""")
            
            return result
            
        except Exception as e:
            logger.error(f"Error updating thought bubble color: {str(e)}")
            return False
    
    async def update_cursor_color(self) -> bool:
        """
        Update both the cursor arrow and thought bubble color to match the current cursor color.
        
        Returns:
            bool: True if update was successful
        """
        if not self.current_page:
            return False
            
        try:
            # Convert cursor color to RGB for thought bubble
            r, g, b = self._hex_to_rgb(self.cursor_color)
            
            result = await self.current_page.evaluate(f"""() => {{
                try {{
                    const cursor = document.getElementById('ai-cursor');
                    const thoughtBubble = document.getElementById('ai-thought-bubble');
                    let updated = 0;
                    
                    // Update cursor arrow color
                    if (cursor) {{
                        const polygon = cursor.querySelector('polygon');
                        if (polygon) {{
                            polygon.setAttribute('fill', '{self.cursor_color}');
                            updated++;
                        }}
                    }}
                    
                    // Update thought bubble color
                    if (thoughtBubble) {{
                        thoughtBubble.style.background = 'rgba({r}, {g}, {b}, 0.7)';
                        thoughtBubble.style.boxShadow = '0 2px 10px rgba({r}, {g}, {b}, 0.3)';
                        updated++;
                    }}
                    
                    return updated > 0;
                }} catch (error) {{
                    console.error("Error updating cursor colors:", error);
                    return false;
                }}
            }}""")
            
            return result
            
        except Exception as e:
            logger.error(f"Error updating cursor colors: {str(e)}")
            return False
    
    def set_cursor_color(self, color: str):
        """
        Set the cursor color for future cursor initializations.
        
        Args:
            color: Hex color code (e.g., "#6B1ECA")
        """
        self.cursor_color = color 
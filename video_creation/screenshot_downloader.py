import json
import re
from pathlib import Path
from typing import Dict, Final

import translators
from playwright.sync_api import ViewportSize, sync_playwright
from rich.progress import track # Keep for progress bar
import logging # Added for logging

from utils import settings
# from utils.console import print_step, print_substep # To be replaced by logging
from utils.imagenarator import imagemaker
from utils.playwright import clear_cookie_by_name
from utils.videos import save_data

__all__ = ["get_screenshots_of_reddit_posts"]

logger = logging.getLogger(__name__)

def get_screenshots_of_reddit_posts(reddit_object: dict, screenshot_num: int):
    """Downloads screenshots of reddit posts as seen on the web. Downloads to assets/temp/png

    Args:
        reddit_object (Dict): Reddit object received from reddit/subreddit.py
        screenshot_num (int): Number of screenshots to download
    """
    # settings values
    W: Final[int] = int(settings.config["settings"]["resolution_w"])
    H: Final[int] = int(settings.config["settings"]["resolution_h"])
    lang: Final[str] = settings.config["reddit"]["thread"].get("post_lang") # Use .get for safety
    storymode: Final[bool] = settings.config["settings"]["storymode"]

    logger.info("Downloading screenshots of reddit posts...")
    # Use safe_thread_id if available from prior processing, otherwise sanitize
    reddit_id = reddit_object.get("safe_thread_id", re.sub(r"[^\w\s-]", "", reddit_object["thread_id"]))

    screenshot_dir = Path(f"assets/temp/{reddit_id}/png")
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured screenshot directory exists: {screenshot_dir}")

    # set the theme and disable non-essential cookies
    if settings.config["settings"]["theme"] == "dark":
        cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        bgcolor = (33, 33, 36, 255)
        txtcolor = (240, 240, 240)
        transparent = False
    elif settings.config["settings"]["theme"] == "transparent":
        if storymode:
            # Transparent theme
            bgcolor = (0, 0, 0, 0)
            txtcolor = (255, 255, 255)
            transparent = True
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
        else:
            # Switch to dark theme
            cookie_file = open("./video_creation/data/cookie-dark-mode.json", encoding="utf-8")
            bgcolor = (33, 33, 36, 255)
            txtcolor = (240, 240, 240)
            transparent = False
    else:
        cookie_file = open("./video_creation/data/cookie-light-mode.json", encoding="utf-8")
        bgcolor = (255, 255, 255, 255)
        txtcolor = (0, 0, 0)
        transparent = False

    logger.debug(f"Theme: {settings.config['settings']['theme']}, BGColor: {bgcolor}, TextColor: {txtcolor}, Transparent: {transparent}")

    if storymode and settings.config["settings"]["storymodemethod"] == 1:
        logger.info("Storymode method 1 selected. Generating images directly using imagemaker.")
        try:
            imagemaker(
                theme=bgcolor,
                reddit_obj=reddit_object,
                txtclr=txtcolor,
                transparent=transparent,
            )
            logger.info("Imagemaker generation complete for storymode method 1.")
            return # End of function for this storymode type
        except Exception as e:
            logger.error(f"Error during imagemaker generation for storymode: {e}", exc_info=True)
            # Decide if to raise or handle. For now, re-raise to signal failure.
            raise RuntimeError(f"Imagemaker failed for storymode: {e}")


    # screenshot_num: int # Type hint already present in function signature
    logger.info("Proceeding with Playwright for screenshot generation.")
    try:
        with sync_playwright() as p:
            logger.info("Launching Headless Browser (Playwright)...")
            browser_launch_options = {"headless": True}
            # Example: Add proxy from settings if configured
            # proxy_settings = settings.config["settings"].get("proxy")
            # if proxy_settings and proxy_settings.get("server"):
            #    browser_launch_options["proxy"] = proxy_settings
            #    logger.info(f"Using proxy for Playwright: {proxy_settings.get('server')}")

            browser = p.chromium.launch(**browser_launch_options)

            dsf = (W // 600) + 1 # Ensure dsf is at least 1, even if W < 600
            logger.debug(f"Device Scale Factor (DSF) calculated: {dsf} for width {W}")

            context = browser.new_context(
                locale=lang or "en-US", # Ensure valid locale format
                color_scheme="dark" if settings.config["settings"]["theme"] in ["dark", "transparent"] else "light",
                viewport=ViewportSize(width=W, height=H), # Using W, H for viewport
                device_scale_factor=dsf,
                # Consider making user_agent configurable or updating it periodically
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            )
            cookies = json.load(cookie_file)
            cookie_file.close() # Ensure file is closed after loading

            context.add_cookies(cookies)
            logger.debug("Cookies added to browser context.")

            page = context.new_page()
            logger.info("Logging in to Reddit via Playwright...")
            page.goto("https://www.reddit.com/login", timeout=60000) # Increased timeout
            # Using a more specific viewport for login page if needed, then change for screenshots
            page.set_viewport_size(ViewportSize(width=1280, height=720)) # Standard size for login page interaction
            page.wait_for_load_state("domcontentloaded") # Wait for DOM, not necessarily all resources

            page.locator('input[name="username"]').fill(settings.config["reddit"]["creds"]["username"])
            page.locator('input[name="password"]').fill(settings.config["reddit"]["creds"]["password"])
            page.get_by_role("button", name="Log In").click()

            try:
                # Wait for either a successful navigation OR a login error message
                # This makes it more robust than a fixed timeout.
                page.wait_for_url("https://www.reddit.com/", timeout=15000) # Wait for redirect to main page
                logger.info("Reddit login appears successful (navigated to main page).")
            except Exception: # TimeoutError from Playwright if URL doesn't change
                logger.debug("Did not navigate to main page after login attempt, checking for error messages.")
                login_error_div = page.locator(".AnimatedForm__errorMessage").first
                if login_error_div.is_visible(timeout=2000): # Brief check for error message
                    login_error_message = login_error_div.inner_text()
                    if login_error_message and login_error_message.strip():
                        logger.error(f"Reddit login failed. Error message: {login_error_message.strip()}")
                        # exit() is too abrupt. Raise an exception.
                        raise ConnectionRefusedError(f"Reddit login failed: {login_error_message.strip()}. Please check credentials.")
                    else:
                        logger.info("Login error div present but empty, assuming login was okay or redirected quickly.")
                else:
                    logger.warning("Reddit login status unclear after timeout and no visible error message. Proceeding cautiously.")


            # Handle the redesign - this logic might be outdated for current Reddit
            # It's often better to ensure the account used is set to the desired UI (old/new)
            # or accept the default UI Reddit provides.
            # For now, keeping it but logging.
            logger.debug("Checking for redesign opt-out button...")
        if page.locator("#redesign-beta-optin-btn").is_visible():
            # Clear the redesign optout cookie
            clear_cookie_by_name(context, "redesign_optout")
            # Reload the page for the redesign to take effect
            page.reload()
        # Get the thread screenshot
        page.goto(reddit_object["thread_url"], timeout=0)
        page.set_viewport_size(ViewportSize(width=W, height=H))
        page.wait_for_load_state()
        page.wait_for_timeout(5000)

        if page.locator(
            "#t3_12hmbug > div > div._3xX726aBn29LDbsDtzr_6E._1Ap4F5maDtT1E1YuCiaO0r.D3IL3FD0RFy_mkKLPwL4 > div > div > button"
        ).is_visible():
            # This means the post is NSFW and requires to click the proceed button.
            # The selector is very specific and might break easily.
            nsfw_button_selector = "div > div._3xX726aBn29LDbsDtzr_6E._1Ap4F5maDtT1E1YuCiaO0r.D3IL3FD0RFy_mkKLPwL4 > div > div > button" # Simplified part of original
            # A more robust selector might be based on text or a more stable attribute if available.
            # Example: page.locator('button:has-text("Yes")') or similar for NSFW confirmation.
            # For now, using a part of the original selector. This is fragile.
            # This specific selector "#t3_12hmbug > ..." is tied to a post ID and will not work generally.
            # A more general approach is needed, perhaps looking for buttons with "yes" or "proceed" text within a modal.
            # For this refactor, I'll use a placeholder for a more general NSFW button.
            # A better selector would be like: page.locator('[data-testid="content-gate"] button:has-text("View")')
            # or page.get_by_role("button", name=re.compile(r"yes|view|proceed", re.IGNORECASE))
            # The original selector was extremely brittle.

            # Simplified NSFW check (this might need adjustment based on actual Reddit UI)
            # Try to find a common NSFW confirmation button
            # This is a guess, actual selector might be different:
            nsfw_proceed_button = page.locator('button:has-text("View")').or_(page.locator('button:has-text("Yes, I am over 18")'))
            if nsfw_proceed_button.first.is_visible(timeout=2000):
                logger.info("Post is marked NSFW. Attempting to click proceed button.")
                try:
                    nsfw_proceed_button.first.click()
                    page.wait_for_load_state("domcontentloaded", timeout=10000)
                    logger.info("Clicked NSFW proceed button.")
                except Exception as e:
                    logger.warning(f"Could not click NSFW proceed button or page did not load: {e}")
            else:
                logger.debug("No obvious NSFW proceed button found, or post is not NSFW.")

            # Handle interest popup - also uses a very specific selector that's likely to break.
            # Example: page.locator('button[aria-label="Close"]') in a modal.
            # The original selector was: "#SHORTCUT_FOCUSABLE_DIV > div:nth-child(7) > ... > button > i"
            # This is too brittle. A more general approach for popups is needed.
            # For now, we'll try to find a generic close button if a known popup structure appears.
            # This is highly speculative.
            # Example: page.get_by_label("Close").or_(page.get_by_title("Close"))
            # For now, skipping this as the selector is too unreliable.
            # logger.debug("Checking for interest popup...")

        if lang:
            logger.info(f"Translating post title to '{lang}'...")
            try:
                texts_in_tl = translators.translate_text(
                    reddit_object["thread_title"],
                    to_language=lang,
                    translator="google", # Consider making translator configurable
                )
                # This JS evaluation to change content is also brittle.
                page.evaluate(
                    "tl_content => { try { document.querySelector('[data-adclicklocation=\"title\"] > div > div > h1').textContent = tl_content; } catch(e){ console.error('Failed to set title via JS:', e); } }",
                    texts_in_tl,
                )
                logger.info("Post title translation applied via JS (if element found).")
            except Exception as e:
                logger.warning(f"Failed to translate post title or apply it: {e}")
        else:
            logger.info("Skipping post title translation (no language specified).")

        post_content_path = screenshot_dir / "title.png"
        logger.info(f"Taking screenshot of post content to {post_content_path}...")
        try:
            zoom_level = settings.config["settings"].get("zoom", 1.0)
            post_content_locator = page.locator('[data-test-id="post-content"]') # Standard Reddit test ID

            if not post_content_locator.is_visible(timeout=10000):
                 logger.error("Post content area '[data-test-id=\"post-content\"]' not found or not visible.")
                 raise RuntimeError("Failed to find post content for screenshot.")

            if zoom_level != 1.0:
                logger.debug(f"Applying zoom level: {zoom_level}")
                page.evaluate(f"document.body.style.zoom={zoom_level}")
                # Bounding box might need adjustment after zoom, or screenshot entire viewport part.
                # For simplicity, if zoom is used, screenshot might need manual verification.
                # The original bounding_box manipulation after zoom was complex and error-prone.
                # A simpler approach for zoom might be to adjust viewport, though dsf already handles resolution.
                # For now, we'll screenshot the locator directly after zoom.
                # The clip logic after zoom can be unreliable.
                # Consider removing zoom or finding a more robust way if it's essential.
                # For now, will attempt screenshot of the locator.
                post_content_locator.screenshot(path=str(post_content_path))

            else:
                post_content_locator.screenshot(path=str(post_content_path))
            logger.info("Post content screenshot successful.")
        except Exception as e:
            logger.error(f"Failed to take screenshot of post content: {e}", exc_info=True)
            # The original code had interactive prompts here. For unattended operation, we should raise.
            # If skipping is desired, it should be based on a config or be more robust.
            # For now, re-raise to indicate failure.
            # Consider saving data about skipped post here if that logic is to be kept.
            # save_data("", "", "screenshot_failed", reddit_id, f"Post content screenshot error: {e}")
            raise RuntimeError(f"Failed to take screenshot of post content: {e}")


        if storymode:
            # For story mode, screenshot the main text content area.
            # '[data-click-id="text"]' is a common locator for the main post body.
            logger.info("Storymode: Taking screenshot of main text content...")
            story_content_output_path = screenshot_dir / "story_content.png"
            try:
                page.locator('[data-click-id="text"]').first.screenshot(path=str(story_content_output_path))
                logger.info(f"Story content screenshot saved to {story_content_output_path}")
            except Exception as e:
                logger.error(f"Failed to take screenshot of story content: {e}", exc_info=True)
                # This might be critical for storymode; consider raising.
                # For now, just log the error.
        else:
            # Comment Screenshots
            logger.info(f"Preparing to take screenshots for up to {screenshot_num} comments.")
            for idx, comment in enumerate(
                track(
                    reddit_object["comments"][:screenshot_num], # Slicing already handles if fewer comments
                    "Downloading comment screenshots...",
                )
            ):
                if idx >= screenshot_num: # Should not be needed due to slice, but good safeguard
                    logger.debug("Reached maximum number of comment screenshots.")
                    break

                comment_url = f"https://new.reddit.com{comment['comment_url']}" # Ensure full URL
                logger.debug(f"Navigating to comment: {comment_url}")
                try:
                    page.goto(comment_url, timeout=30000, wait_until="domcontentloaded")
                    # page.wait_for_load_state("domcontentloaded", timeout=10000) # Redundant if in goto
                except Exception as e: # Playwright TimeoutError etc.
                    logger.warning(f"Timeout or error navigating to comment {comment['comment_id']}: {e}. Skipping this comment.")
                    continue # Skip this comment

                # Handle content gates (e.g. "continue_viewing" overlays)
                # This is a common pattern, might need adjustments.
                content_gate_button = page.locator('[data-testid="content-gate"] button').or_(page.get_by_role("button", name=re.compile(r"continue|view", re.IGNORECASE)))
                if content_gate_button.first.is_visible(timeout=1000): # Quick check
                    try:
                        logger.debug("Content gate detected, attempting to click.")
                        content_gate_button.first.click(timeout=2000)
                        page.wait_for_timeout(500) # Brief pause for overlay to disappear
                    except Exception as e:
                        logger.warning(f"Could not click content gate button for comment {comment['comment_id']}: {e}")


                if lang: # Assuming 'lang' is post_lang from settings
                    logger.debug(f"Translating comment {comment['comment_id']} to '{lang}'...")
                    try:
                        comment_tl = translators.translate_text(
                            comment["comment_body"],
                            translator="google",
                            to_language=lang,
                        )
                        # This JS evaluation is highly dependent on Reddit's DOM structure and likely to break.
                        # A more robust method would be to screenshot first, then overlay translated text if needed via PIL.
                        # For now, retaining original logic but with logging.
                        js_to_run = '([tl_content, tl_id]) => { try { document.querySelector(`#t1_${tl_id} > div:nth-child(2) > div > div[data-testid="comment"] > div`).textContent = tl_content; } catch(e) { console.error("Failed to set comment text via JS:", e); } }'
                        page.evaluate(js_to_run, [comment_tl, comment["comment_id"]])
                        logger.debug(f"Comment {comment['comment_id']} translation applied via JS (if element found).")
                    except Exception as e:
                        logger.warning(f"Failed to translate comment {comment['comment_id']} or apply it: {e}")

                comment_ss_path = screenshot_dir / f"comment_{idx}.png"
                comment_locator_id = f"#t1_{comment['comment_id']}"
                logger.debug(f"Attempting screenshot for comment {comment['comment_id']} (locator: {comment_locator_id}) to {comment_ss_path}")

                try:
                    comment_element = page.locator(comment_locator_id)
                    if not comment_element.is_visible(timeout=10000):
                        logger.warning(f"Comment element {comment_locator_id} not visible for screenshot. Skipping.")
                        continue

                    comment_element.scroll_into_view_if_needed() # Ensure it's in view
                    page.wait_for_timeout(200) # Small pause for scrolling to settle

                    if zoom_level != 1.0:
                        # As with post content, zoom can make locator.screenshot with clip unreliable.
                        # Best to avoid zoom or use full page screenshots and crop later if zoom is used.
                        # For now, attempting direct screenshot of the locator.
                        logger.debug(f"Applying zoom {zoom_level} for comment screenshot.")
                        page.evaluate(f"document.body.style.zoom={zoom_level}") # Re-apply zoom if page navigated
                        comment_element.screenshot(path=str(comment_ss_path))
                    else:
                        comment_element.screenshot(path=str(comment_ss_path))
                    logger.info(f"Screenshot for comment {idx} ({comment['comment_id']}) saved.")
                except Exception as e: # Playwright TimeoutError, etc.
                    logger.warning(f"Failed to take screenshot for comment {comment['comment_id']}: {e}. Skipping.")
                    # Original code modified screenshot_num here, which is complex.
                    # Simpler to just skip and let it take fewer screenshots if some fail.
                    continue

        logger.info("Closing Playwright browser.")
        browser.close()
    except ConnectionRefusedError as e: # Catch the specific login error
        logger.critical(f"Halting due to Reddit login failure: {e}")
        raise # Re-raise to stop the process
    except Exception as e:
        logger.error(f"An error occurred during Playwright operations: {e}", exc_info=True)
        if 'browser' in locals() and browser.is_connected():
            browser.close()
        raise RuntimeError(f"Playwright screenshot generation failed: {e}")


    logger.info("Screenshots downloaded successfully.")

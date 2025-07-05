#!/usr/bin/env python
"""
Main script for the Reddit Video Maker Bot.

This script orchestrates the process of fetching Reddit content,
generating audio and video components, and compiling them into a final video.
It handles configuration loading, application initialization, and error management.
"""
import math
import sys
import re # Added for reddit_id extraction
import logging # Added for logging
import logging.handlers # Added for logging
from os import name
from pathlib import Path
from subprocess import Popen
from typing import NoReturn, Dict, Any, Tuple

import argparse
from prawcore import ResponseException

from reddit.subreddit import get_subreddit_threads
from utils import settings
from utils.cleanup import cleanup
from utils.console import print_markdown, print_step, print_substep
from utils.ffmpeg_install import ffmpeg_install
# from utils.id import id # This import seems unused and id is a python built-in.
# If utils.id.id() was intended, it was shadowed by the global redditid.
# Assuming it was for generating a unique ID from the reddit object,
# this functionality will be implicitly handled by using reddit_object["thread_id"]
from utils.version import checkversion
from utils.gemini_client import summarize_text_with_gemini # Added for summarization
from video_creation.background import (
    chop_background,
    download_background_audio,
    download_background_video,
    get_background_config,
)
from video_creation.final_video import make_final_video
from video_creation.screenshot_downloader import get_screenshots_of_reddit_posts
from video_creation.voices import save_text_to_mp3, TTSProviders

__VERSION__ = "3.3.0"

# Store the original reddit_id for cleanup at shutdown
_current_reddit_id_for_cleanup = None

def display_banner_and_initial_message():
    """Prints the welcome banner and initial informational message."""
    print(
        """
██████╗ ███████╗██████╗ ██████╗ ██╗████████╗    ██╗   ██╗██╗██████╗ ███████╗ ██████╗     ███╗   ███╗ █████╗ ██╗  ██╗███████╗██████╗
██╔══██╗██╔════╝██╔══██╗██╔══██╗██║╚══██╔══╝    ██║   ██║██║██╔══██╗██╔════╝██╔═══██╗    ████╗ ████║██╔══██╗██║ ██╔╝██╔════╝██╔══██╗
██████╔╝█████╗  ██║  ██║██║  ██║██║   ██║       ██║   ██║██║██║  ██║█████╗  ██║   ██║    ██╔████╔██║███████║█████╔╝ █████╗  ██████╔╝
██╔══██╗██╔══╝  ██║  ██║██║  ██║██║   ██║       ╚██╗ ██╔╝██║██║  ██║██╔══╝  ██║   ██║    ██║╚██╔╝██║██╔══██║██╔═██╗ ██╔══╝  ██╔══██╗
██║  ██║███████╗██████╔╝██████╔╝██║   ██║        ╚████╔╝ ██║██████╔╝███████╗╚██████╔╝    ██║ ╚═╝ ██║██║  ██║██║  ██╗███████╗██║  ██║
╚═╝  ╚═╝╚══════╝╚═════╝ ╚═════╝ ╚═╝   ╚═╝         ╚═══╝  ╚═╝╚═════╝ ╚══════╝ ╚═════╝     ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
"""
    )
    print_markdown(
        "### Thanks for using this tool! Feel free to contribute to this project on GitHub! If you have any questions, feel free to join my Discord server or submit a GitHub issue. You can find solutions to many common problems in the documentation: https://reddit-video-maker-bot.netlify.app/"
    )

def initialize_app_checks_and_config():
    """Handles initial application setup including version checks, argument parsing, and configuration loading."""
    checkversion(__VERSION__) # This might print, consider replacing if it does. For now, assume it's a simple check or uses logging.

    parser = argparse.ArgumentParser(description="Reddit Video Maker Bot")
    parser.add_argument(
        "--list-tts",
        action="store_true",
        help="List available TTS providers and exit",
    )
    args = parser.parse_args()

    if args.list_tts:
        logging.info("Available TTS Providers:")
        for provider in TTSProviders:
            logging.info(f"- {provider}") # Simple info log for list items
        sys.exit()

    if sys.version_info.major != 3 or sys.version_info.minor not in [10, 11]:
        logging.error(
            "Hey! Congratulations, you've made it so far (which is pretty rare with Python 3.10/3.11). "
            "Unfortunately, this program primarily supports Python 3.10 and 3.11. "
            "Please install one of these versions and try again."
        )
        sys.exit()

    ffmpeg_install() # This function might print, review separately.
    directory = Path().absolute()
    logging.info("Checking TOML configuration...")
    config = settings.check_toml(
        directory / "utils" / ".config.template.toml", directory / "config.toml"
    )
    if not config: # check_toml returns False on failure
        logging.error("Failed to load or create configuration. Exiting.")
        sys.exit()
    logging.info("TOML configuration check complete.")

    if (
        not settings.config["settings"]["tts"]["tiktok_sessionid"]
        or settings.config["settings"]["tts"]["tiktok_sessionid"] == ""
    ) and settings.config["settings"]["tts"]["voice_choice"] == "tiktok":
        logging.error(
            "TikTok voice requires a sessionid! Check our documentation on how to obtain one."
        )
        sys.exit()
    return config

def get_reddit_data(post_id_override: str = None) -> Dict[str, Any]:
    """
    Fetches and processes Reddit thread data using praw.

    It retrieves submission details and comments. A 'safe_thread_id' is generated
    by sanitizing the original thread_id for filesystem compatibility and stored
    in the returned dictionary. This safe ID is also stored globally for cleanup operations.

    Args:
        post_id_override (Optional[str]): Specific Reddit post ID to fetch.
                                         If None, fetches based on subreddit config.

    Returns:
        Dict[str, Any]: A dictionary containing the processed Reddit thread data,
                        including the 'safe_thread_id'.
    """
    logging.info("Fetching Reddit data...")
    reddit_object = get_subreddit_threads(post_id_override)

    if "thread_id" in reddit_object:
        reddit_object["safe_thread_id"] = re.sub(r"[^\w\s-]", "", reddit_object["thread_id"])
        logging.debug(f"Reddit thread ID: {reddit_object['thread_id']}, Safe ID: {reddit_object['safe_thread_id']}")
    else:
        logging.error("Critical: thread_id missing from Reddit object.")
        reddit_object["safe_thread_id"] = "unknown_thread_" + str(math.floor(time.time())) # Ensure unique unknown ID
        logging.warning(f"Assigned fallback safe_thread_id: {reddit_object['safe_thread_id']}")


    global _current_reddit_id_for_cleanup
    _current_reddit_id_for_cleanup = reddit_object["safe_thread_id"]
    return reddit_object

def generate_audio_and_screenshots(reddit_object: Dict[str, Any]) -> Tuple[int, int]:
    """
    Generates TTS audio for the Reddit content (potentially summarized) and takes screenshots.
    """
    logging.info("Preparing content for audio and screenshots...")

    # --- Gemini Summarization Step ---
    if settings.config.get("gemini", {}).get("enable_summary"):
        logging.info("Gemini summarization enabled. Attempting to summarize thread content.")
        # Construct text for summarization: title + selftext
        # Ensure 'thread_title' and 'thread_selftext' exist. 'thread_selftext' might be empty for image/link posts.
        title = reddit_object.get("thread_title", "")
        selftext = reddit_object.get("thread_selftext", "") # This is what TTSEngine uses for the main post

        if selftext and selftext.strip(): # Only summarize if there's actual selftext
            text_to_summarize = f"Titel: {title}\n\nBericht:\n{selftext}"
            logging.debug(f"Text to summarize (first 200 chars): {text_to_summarize[:200]}")

            summary = summarize_text_with_gemini(text_to_summarize)
            if summary:
                logging.info("Successfully summarized thread content with Gemini.")
                # Replace the original selftext with the summary for TTS
                # The TTSEngine in voices.py specifically looks for 'thread_selftext' for the main post.
                reddit_object["thread_selftext"] = summary
                # The title is usually read out separately by TTSEngine.
                # If the summary should also include/replace the title for TTS, this logic might need adjustment
                # or the prompt to Gemini could be to make the summary inclusive of the title's context.
                # Current prompt: "Vat de volgende Reddit-thread samen in een boeiend en beknopt verhaal..."
                # This implies the summary might naturally incorporate the title's essence.
                logging.debug(f"Using Gemini summary for TTS (first 100 chars): {summary[:100]}")
            else:
                logging.warning("Failed to get summary from Gemini, or summary was empty. Using original selftext.")
        else:
            logging.info("No selftext found or selftext is empty. Skipping Gemini summarization for this post.")
    else:
        logging.info("Gemini summarization is not enabled.")
    # --- End Gemini Summarization ---

    logging.info("Proceeding to generate TTS audio and screenshots with (potentially summarized) content...")
    length, number_of_comments = save_text_to_mp3(reddit_object) # save_text_to_mp3 uses reddit_object["thread_selftext"]
    final_length = math.ceil(length)
    get_screenshots_of_reddit_posts(reddit_object, number_of_comments)
    logging.info("Audio and screenshots generated.")
    return final_length, number_of_comments

def prepare_background_assets(length: int, reddit_object: Dict[str, Any]) -> Dict[str, Any]:
    """Prepares background video and audio assets."""
    logging.info("Preparing background assets...")
    bg_config = {
        "video": get_background_config("video"),
        "audio": get_background_config("audio"),
    }
    download_background_video(bg_config["video"])
    download_background_audio(bg_config["audio"])
    chop_background(bg_config, length, reddit_object)
    logging.info("Background assets prepared.")
    return bg_config

def create_video_from_assets(number_of_comments: int, length: int, reddit_object: Dict[str, Any], bg_config: Dict[str, Any]) -> None:
    """Compiles the final video from all generated assets."""
    logging.info("Compiling final video...")
    make_final_video(number_of_comments, length, reddit_object, bg_config)
    logging.info("Final video compilation complete.")

def process_single_submission(post_id_override: str = None) -> None:
    """Main workflow to process a single Reddit submission into a video."""
    logging.info(f"Starting processing for submission ID: {post_id_override if post_id_override else 'random'}")
    reddit_object = get_reddit_data(post_id_override)
    length, num_comments = generate_audio_and_screenshots(reddit_object)
    background_config = prepare_background_assets(length, reddit_object)
    create_video_from_assets(num_comments, length, reddit_object, background_config)

def run_many(times: int, config: Dict[str, Any]) -> None:
    """Runs the video creation process multiple times for random submissions."""
    for x in range(1, times + 1):
        logging.info(
            f'On iteration {x}{("th", "st", "nd", "rd", "th", "th", "th", "th", "th", "th")[x % 10 if x % 10 < 4 and x // 10 != 1 else 0]} of {times}'
        )
        process_single_submission() # For random posts, no specific post_id
        if x < times : # Don't clear after the last run
            Popen("cls" if name == "nt" else "clear", shell=True).wait()


def shutdown_app() -> NoReturn:
    """Handles application shutdown, including cleanup."""
    global _current_reddit_id_for_cleanup
    if _current_reddit_id_for_cleanup:
        logging.info(f"Clearing temp files for ID: {_current_reddit_id_for_cleanup}")
        cleanup(_current_reddit_id_for_cleanup)
        _current_reddit_id_for_cleanup = None

    logging.info("Exiting Reddit Video Maker Bot.")
    sys.exit()


if __name__ == "__main__":
    display_banner_and_initial_message() # This function still uses print and print_markdown

    # --- Logging Setup ---
    log_file_path = Path("reddit_video_bot.log")
    # Max log file size 5MB, keep 3 backup logs
    file_handler = logging.handlers.RotatingFileHandler(log_file_path, maxBytes=5*1024*1024, backupCount=3, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG) # Log everything to file

    console_handler = logging.StreamHandler() # Defaults to stderr
    console_handler.setLevel(logging.INFO) # Log INFO and above to console

    # Rich console handler for better formatting, if rich is available and preferred
    try:
        from rich.logging import RichHandler
        console_handler = RichHandler(rich_tracebacks=True, show_path=False, show_time=False, markup=True) # markup=True for rich styles
        console_handler.setLevel(logging.INFO)
        log_formatter = logging.Formatter("%(message)s")
        detailed_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s')
    except ImportError:
        log_formatter = logging.Formatter('[%(levelname)s] %(message)s')
        detailed_log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - [%(module)s.%(funcName)s:%(lineno)d] - %(message)s')

    console_handler.setFormatter(log_formatter)
    file_handler.setFormatter(detailed_log_formatter)

    # Configure the root logger
    # logging.basicConfig(level=logging.DEBUG, handlers=[file_handler, console_handler]) # This is one way
    # Or, get the root logger and add handlers:
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG) # Set root logger level
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    # --- End Logging Setup ---

    logging.info(f"Reddit Video Maker Bot Version: {__VERSION__}")
    logging.debug("Logging initialized.")

    app_config = initialize_app_checks_and_config()

    # Initialize Gemini client if enabled
    if app_config.get("gemini", {}).get("enable_summary"):
        try:
            from utils.gemini_client import initialize_gemini
            if not initialize_gemini():
                logging.warning("Gemini client initialization failed or was skipped. Summarization will not be available.")
            else:
                logging.info("Gemini client initialized for summarization.")
        except ImportError:
            logging.error("Failed to import gemini_client. Summarization will not be available. Ensure google-generativeai is installed.")
        except Exception as e:
            logging.error(f"An unexpected error occurred during Gemini initialization: {e}", exc_info=True)


    try:
        post_ids_str = app_config.get("reddit", {}).get("thread", {}).get("post_id")
        times_to_run = app_config.get("settings", {}).get("times_to_run")

        # Determine execution mode based on configuration
        if post_ids_str:
            # Mode 1: Process a specific list of post IDs
            logging.info(f"Processing specific Reddit post IDs from config: {post_ids_str}")
            post_id_list = post_ids_str.split("+")
            for index, p_id in enumerate(post_id_list):
                logging.info(
                     f'Processing post {index + 1}{("st", "nd", "rd", "th")[min(index % 10, 3) if (index + 1) % 100 // 10 != 1 else 3]} of {len(post_id_list)} (ID: {p_id.strip()})'
                )
                process_single_submission(p_id.strip())
                if index < len(post_id_list) -1 :
                    # Clear console between processing multiple specified posts (except for the last one)
                    Popen("cls" if name == "nt" else "clear", shell=True).wait()
        elif times_to_run:
            # Mode 2: Run for a configured number of times (fetches random posts)
            logging.info(f"Running Reddit Video Maker Bot {times_to_run} times for random posts.")
            run_many(times_to_run, app_config)
        else:
            # Mode 3: Default single run for a random post
            logging.info("No specific post IDs or multiple runs configured. Running once for a random post.")
            process_single_submission()

    except KeyboardInterrupt:
        logging.warning("Keyboard interrupt detected!")
        shutdown_app()
    except ResponseException as e:
        logging.error(f"Reddit API Error: {e}")
        logging.error("Please check your credentials in the config.toml file and your internet connection.")
        shutdown_app()
    except Exception as err:
        logging.error(f"An unexpected error occurred: {type(err).__name__} - {err}", exc_info=True) # Log traceback to file

        # Redact sensitive info before showing to console (if error is printed to console by RichHandler)
        # This part is more for if we were constructing the console message manually here.
        # RichHandler with exc_info=True will show traceback, which might contain sensitive data from locals.
        # For now, the detailed log goes to file, console gets a simpler message.

        # Simplified console error message:
        error_details_for_console = (
            f"Version: {__VERSION__}\n"
            f"Error Type: {type(err).__name__}\n"
            "Details have been logged to reddit_video_bot.log.\n"
            "Please report this issue at GitHub or the Discord community if it persists."
        )
        # If not using RichHandler or if more control is needed for console:
        # console.print(Panel(Text(error_details_for_console, style="bold red"), title="Unhandled Exception"))
        # Since RichHandler is used, logging.error will display it.
        # The main `logging.error` call above with `exc_info=True` handles file logging.
        # For console, RichHandler will format the exception. We might want a less verbose console output.
        # The below is a more controlled message for console if the above logging.error is too verbose for console.
        # For now, rely on RichHandler's traceback formatting for console errors.

        # The original print_step for error:
        # print_step(error_message, style="bold red") # This would now be logging.error(...)
        # The error_message variable construction from original code:
        # config_settings_str = str(settings.config.get('settings')) # Simplified for this example
        # if "tts" in settings.config.get("settings", {}):
        #     if "tiktok_sessionid" in settings.config["settings"]["tts"]:
        #         config_settings_str = config_settings_str.replace(settings.config["settings"]["tts"]["tiktok_sessionid"], "REDACTED")
        #     if "elevenlabs_api_key" in settings.config["settings"]["tts"]:
        #          config_settings_str = config_settings_str.replace(settings.config["settings"]["tts"]["elevenlabs_api_key"], "REDACTED")
        # logging.error(f"Sorry, something went wrong with this version!\nVersion: {__VERSION__}\nError: {err}\nConfig (sensitive fields redacted): {config_settings_str}")

        # Re-raise if you want Python's default exception printing to also occur,
        # or if something else higher up should handle it.
        # For a CLI app, often we log and then exit.
        shutdown_app() # Ensure cleanup and exit
    finally:
        if _current_reddit_id_for_cleanup:
             logging.info(f"Performing final cleanup for ID: {_current_reddit_id_for_cleanup}")
             cleanup(_current_reddit_id_for_cleanup)

from typing import Tuple
import logging # Added for logging

# from rich.console import Console # Keep if direct console interaction remains, otherwise remove
# For now, print_table is kept which uses Console.

from TTS.aws_polly import AWSPolly
from TTS.elevenlabs import elevenlabs
from TTS.engine_wrapper import TTSEngine
from TTS.GTTS import GTTS
from TTS.pyttsx import pyttsx
from TTS.streamlabs_polly import StreamlabsPolly
from TTS.TikTok import TikTok
from utils import settings
from utils.console import print_table # Keep print_table for now for interactive choice

# console = Console() # Replaced by logger for general messages
logger = logging.getLogger(__name__)

TTSProviders = {
    "GoogleTranslate": GTTS,
    "AWSPolly": AWSPolly,
    "StreamlabsPolly": StreamlabsPolly,
    "TikTok": TikTok,
    "pyttsx": pyttsx,
    "ElevenLabs": elevenlabs,
}


def save_text_to_mp3(reddit_obj) -> Tuple[int, int]:
    """Saves text to MP3 files.

    Args:
        reddit_obj (): Reddit object received from reddit API in reddit/subreddit.py

    Returns:
        tuple[int,int]: (total length of the audio, the number of comments audio was generated for)
    """

    selected_tts_provider_name = settings.config["settings"]["tts"]["voice_choice"]
    tts_engine_class = None

    if selected_tts_provider_name:
        selected_tts_provider_name_lower = str(selected_tts_provider_name).casefold()
        for provider_name, provider_class in TTSProviders.items():
            if provider_name.casefold() == selected_tts_provider_name_lower:
                tts_engine_class = provider_class
                logger.info(f"Using configured TTS provider: {provider_name}")
                break

    if not tts_engine_class:
        logger.warning(
            f"Configured TTS provider '{selected_tts_provider_name}' not found or not set. Prompting user for selection."
        )
        # Interactive fallback - uses direct print/input via rich Console from print_table
        # This part remains interactive as it's a fallback for misconfiguration.
        from rich.console import Console as RichConsole # Local import for this specific interaction
        local_console = RichConsole()

        while True:
            local_console.print("[bold yellow]Please choose one of the following TTS providers:[/bold yellow]")
            print_table(TTSProviders) # print_table uses rich.Console internally
            choice = input("\nEnter your choice: ").strip()

            choice_lower = choice.casefold()
            for provider_name, provider_class in TTSProviders.items():
                if provider_name.casefold() == choice_lower:
                    tts_engine_class = provider_class
                    logger.info(f"User selected TTS provider: {provider_name}")
                    # Optionally, offer to save this choice back to config? (Out of scope for now)
                    break
            if tts_engine_class:
                break
            local_console.print("[bold red]Unknown TTS provider. Please try again.[/bold red]")

    try:
        text_to_mp3_engine = TTSEngine(tts_engine_class, reddit_obj)
        return text_to_mp3_engine.run()
    except Exception as e:
        logger.error(f"Failed to initialize or run TTS engine {tts_engine_class.__name__ if tts_engine_class else 'N/A'}: {e}", exc_info=True)
        # Depending on desired behavior, either re-raise or return a value indicating failure
        # For now, re-raising to ensure the error is propagated.
        raise


def get_case_insensitive_key_value(input_dict, key): # This function seems unused now.
    # Retaining it for now in case it's used by other parts of the codebase not yet reviewed for logging.
    # If confirmed unused later, it can be removed.
    logger.debug(f"Performing case-insensitive key lookup for '{key}'")
    return next(
        (value for dict_key, value in input_dict.items() if dict_key.lower() == key.lower()),
        None,
    )

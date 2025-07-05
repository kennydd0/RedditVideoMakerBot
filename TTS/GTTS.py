import random
import logging # Added for logging
from gtts import gTTS, gTTSError

from utils import settings

logger = logging.getLogger(__name__)

class GTTS:
    def __init__(self):
        logger.debug("Initializing GTTS engine.")
        self.max_chars = 5000 # gTTS has its own limits, but this is for consistency if we pre-validate.
        # self.voices = [] # gTTS doesn't have selectable voices in the same way as pyttsx or TikTok; lang is the main variant.

    def run(self, text: str, filepath: str):
        language = settings.config["reddit"]["thread"]["post_lang"] or "en"
        logger.info(f"Requesting GTTS for text: '{text[:30]}...' using lang: '{language}'. Output: {filepath}")

        try:
            tts = gTTS(
                text=text,
                lang=language,
                slow=False, # Speed is not highly configurable; 'slow' is the only option.
            )
            logger.debug(f"Saving GTTS audio to {filepath}")
            tts.save(filepath)
            logger.info(f"Successfully saved GTTS audio to {filepath}")
        except gTTSError as e: # Catch specific gTTS errors
            logger.error(f"gTTS API error: {e}", exc_info=True)
            # Decide if to raise a custom exception or re-raise
            raise RuntimeError(f"gTTS failed: {e}")
        except Exception as e: # Catch any other unexpected errors during gTTS processing
            logger.error(f"An unexpected error occurred with GTTS: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected GTTS failure: {e}")

    def randomvoice(self):
        # gTTS language is the primary "voice" variant. No list of voices to pick from.
        # This method might be redundant for GTTS or could return a random language if desired.
        # For now, it's not actively used by the engine_wrapper for GTTS in a meaningful way.
        logger.debug("randomvoice called for GTTS, but GTTS primarily uses language codes, not distinct voices.")
        return settings.config["reddit"]["thread"]["post_lang"] or "en" # Return current lang as a placeholder

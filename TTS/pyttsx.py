import random
import logging # Added for logging

import pyttsx3

from utils import settings

logger = logging.getLogger(__name__)

class pyttsx:
    def __init__(self):
        logger.debug("Initializing pyttsx TTS engine.")
        self.max_chars = 5000 # Max characters, not currently enforced by pyttsx3 directly but good for consistency
        self.available_voice_indices = [] # Store available voice indices

    def run(
        self,
        text: str,
        filepath: str,
        random_voice=False,
    ):
        voice_id_str = settings.config["settings"]["tts"].get("python_voice", "0") # Default to "0" if not set
        # py_voice_num seems to indicate the number of voices to consider, not directly used for selection by ID.
        # The old logic for py_voice_num was confusing. We'll rely on pyttsx3 to list available voices.

        try:
            selected_voice_idx = int(voice_id_str)
        except ValueError:
            logger.warning(f"Invalid pyttsx voice ID '{voice_id_str}' in config. Defaulting to voice index 0.")
            selected_voice_idx = 0

        logger.info(f"Requesting pyttsx TTS for text: '{text[:30]}...' Output: {filepath}")

        try:
            engine = pyttsx3.init()
        except Exception as e:
            logger.error(f"Failed to initialize pyttsx3 engine: {e}", exc_info=True)
            raise RuntimeError(f"pyttsx3 engine initialization failed: {e}")

        available_voices = engine.getProperty("voices")
        if not available_voices:
            logger.error("No voices found by pyttsx3 engine.")
            raise RuntimeError("pyttsx3 found no available voices.")

        self.available_voice_indices = list(range(len(available_voices)))

        if random_voice:
            if not self.available_voice_indices:
                 logger.warning("No available voices for random selection in pyttsx. Using default index 0.")
                 final_voice_to_use_idx = 0
            else:
                final_voice_to_use_idx = self.randomvoice()
            logger.debug(f"Using random pyttsx voice index: {final_voice_to_use_idx}")
        else:
            final_voice_to_use_idx = selected_voice_idx
            logger.debug(f"Using configured pyttsx voice index: {final_voice_to_use_idx}")

        if not (0 <= final_voice_to_use_idx < len(available_voices)):
            logger.warning(
                f"Selected pyttsx voice index {final_voice_to_use_idx} is out of range (0-{len(available_voices)-1}). "
                f"Falling back to voice index 0."
            )
            final_voice_to_use_idx = 0
            if not available_voices: # Should be caught earlier, but as a safeguard
                 logger.error("Critical: No voices available even for fallback.")
                 raise RuntimeError("No pyttsx voices available for fallback.")


        try:
            voice_to_set = available_voices[final_voice_to_use_idx].id
            logger.debug(f"Setting pyttsx voice to ID: {voice_to_set} (Index: {final_voice_to_use_idx}, Name: {available_voices[final_voice_to_use_idx].name})")
            engine.setProperty("voice", voice_to_set)

            logger.debug(f"Saving pyttsx TTS audio to {filepath} for text: '{text[:50]}...'")
            engine.save_to_file(text, filepath) # Corrected filepath variable
            engine.runAndWait()
            logger.info(f"Successfully saved pyttsx TTS audio to {filepath}")
        except IndexError: # Should be caught by above checks, but good safeguard
            logger.error(f"Internal error: pyttsx voice index {final_voice_to_use_idx} became invalid.", exc_info=True)
            raise RuntimeError("Failed to set pyttsx voice due to an internal indexing error.")
        except Exception as e: # Catch other pyttsx3 errors
            logger.error(f"Error during pyttsx3 operation (setProperty, save_to_file, runAndWait): {e}", exc_info=True)
            raise RuntimeError(f"pyttsx3 operation failed: {e}")


    def randomvoice(self) -> int:
        """Returns a random valid voice index."""
        if not self.available_voice_indices:
            logger.warning("Attempted to get random pyttsx voice, but no voices seem available. Defaulting to index 0.")
            return 0 # Fallback, though this case should ideally be handled before calling
        return random.choice(self.available_voice_indices)

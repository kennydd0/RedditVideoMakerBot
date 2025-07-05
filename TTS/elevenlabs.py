import random
import logging # Added for logging
from elevenlabs import save, APIError # Import APIError for specific exception handling
from elevenlabs.client import ElevenLabs


from utils import settings

logger = logging.getLogger(__name__)

class elevenlabs:
    def __init__(self):
        logger.debug("Initializing ElevenLabs TTS engine (client will be created on first run or randomvoice call).")
        self.max_chars = 2500 # Character limit for ElevenLabs (check their current limits)
        self.client: ElevenLabs = None
        self.available_voices = [] # To store fetched voice names

    def _ensure_client_initialized(self):
        """Initializes the ElevenLabs client if not already done."""
        if self.client is None:
            logger.info("ElevenLabs client not initialized. Initializing now...")
            api_key = settings.config["settings"]["tts"].get("elevenlabs_api_key")
            if not api_key:
                logger.error("ElevenLabs API key is not set in config (ELEVENLABS_API_KEY).")
                raise ValueError("ElevenLabs API key is missing. Please set ELEVENLABS_API_KEY in config.")

            try:
                self.client = ElevenLabs(api_key=api_key)
                # Fetch and store available voices upon successful initialization
                all_voices_response = self.client.voices.get_all()
                self.available_voices = [v.name for v in all_voices_response.voices if v.name]
                if not self.available_voices:
                    logger.warning("No voices returned from ElevenLabs API after initialization.")
                else:
                    logger.debug(f"Fetched {len(self.available_voices)} voices from ElevenLabs: {self.available_voices}")
                logger.info("ElevenLabs client initialized successfully.")
            except APIError as e:
                logger.error(f"Failed to initialize ElevenLabs client due to API error: {e}", exc_info=True)
                raise RuntimeError(f"ElevenLabs API initialization failed: {e}")
            except Exception as e: # Catch other potential errors during client init
                logger.error(f"An unexpected error occurred during ElevenLabs client initialization: {e}", exc_info=True)
                raise RuntimeError(f"Unexpected error initializing ElevenLabs client: {e}")


    def run(self, text: str, filepath: str, random_voice: bool = False):
        self._ensure_client_initialized()

        selected_voice_name = ""
        if random_voice:
            selected_voice_name = self.randomvoice() # randomvoice now also ensures client init
            logger.debug(f"Using random ElevenLabs voice: {selected_voice_name}")
        else:
            selected_voice_name = settings.config["settings"]["tts"].get("elevenlabs_voice_name")
            if not selected_voice_name:
                logger.error("ElevenLabs voice name (elevenlabs_voice_name) not set in config.")
                # Fallback to a random voice if no specific voice is set, or raise error
                # For now, let's try a random voice as a fallback.
                logger.warning("elevenlabs_voice_name not set. Attempting to use a random voice.")
                selected_voice_name = self.randomvoice()
                if not selected_voice_name: # If randomvoice also fails to find one
                     logger.error("No ElevenLabs voice configured and no random voice available.")
                     raise ValueError("ElevenLabs voice not configured and no random voice found.")
            else:
                # Check if configured voice is in available list (case-sensitive for ElevenLabs names usually)
                if self.available_voices and selected_voice_name not in self.available_voices:
                    logger.warning(f"Configured ElevenLabs voice '{selected_voice_name}' not found in fetched available voices. "
                                   f"Available: {self.available_voices}. Attempting to use it anyway.")
                logger.debug(f"Using configured ElevenLabs voice: {selected_voice_name}")

        logger.info(f"Requesting ElevenLabs TTS for text: '{text[:30]}...' Voice: {selected_voice_name}. Output: {filepath}")

        try:
            # Consider making model configurable e.g. "eleven_multilingual_v2"
            audio = self.client.generate(text=text, voice=selected_voice_name, model="eleven_multilingual_v1")
            logger.debug(f"Saving ElevenLabs audio to {filepath}")
            save(audio=audio, filename=filepath)
            logger.info(f"Successfully saved ElevenLabs TTS audio to {filepath}")
        except APIError as e:
            logger.error(f"ElevenLabs API error during audio generation or save: {e}", exc_info=True)
            raise RuntimeError(f"ElevenLabs API operation failed: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred with ElevenLabs processing: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected ElevenLabs failure: {e}")


    def randomvoice(self) -> str:
        self._ensure_client_initialized() # Ensure client and self.available_voices are populated

        if not self.available_voices:
            logger.error("No voices available from ElevenLabs to choose randomly.")
            # This could raise an error or return a default/empty string depending on desired strictness
            raise RuntimeError("ElevenLabs: No voices available for random selection.")

        choice = random.choice(self.available_voices)
        logger.debug(f"Randomly selected ElevenLabs voice: {choice}")
        return choice

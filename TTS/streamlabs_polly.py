import random
import logging # Added for logging
import time # For potential sleep on rate limit

import requests
from requests.exceptions import JSONDecodeError, RequestException # Import base RequestException

from utils import settings
from utils.voice import check_ratelimit # This function likely needs logging too

voices = [
    "Brian",
    "Emma",
    "Russell",
    "Joey",
    "Matthew",
    "Joanna",
    "Kimberly",
    "Amy",
    "Geraint",
    "Nicole",
    "Justin",
    "Ivy",
    "Kendra",
    "Salli",
    "Raveena",
]


# valid voices https://lazypy.ro/tts/

logger = logging.getLogger(__name__)

class StreamlabsPolly:
    def __init__(self):
        logger.debug("Initializing Streamlabs Polly TTS engine.")
        self.url = "https://streamlabs.com/polly/speak"
        self.max_chars = 550
        self.voices = voices # Keep for validation and random selection

    def run(self, text: str, filepath: str, random_voice: bool = False, retry_count=0):
        max_retries = 3 # Max retries for rate limiting or transient errors

        logger.info(f"Requesting Streamlabs Polly TTS for text: '{text[:30]}...' Output: {filepath}")

        selected_voice = ""
        if random_voice:
            selected_voice = self.randomvoice()
            logger.debug(f"Using random Streamlabs Polly voice: {selected_voice}")
        else:
            selected_voice = settings.config["settings"]["tts"].get("streamlabs_polly_voice")
            if not selected_voice:
                logger.error(f"Streamlabs Polly voice not set. Available: {self.voices}")
                raise ValueError(f"STREAMLABS_POLLY_VOICE not set. Options: {self.voices}")
            selected_voice = selected_voice.capitalize()
            if selected_voice not in self.voices:
                logger.error(f"Invalid Streamlabs Polly voice '{selected_voice}' in config. Available: {self.voices}")
                raise ValueError(f"Invalid STREAMLABS_POLLY_VOICE '{selected_voice}'. Options: {self.voices}")
            logger.debug(f"Using configured Streamlabs Polly voice: {selected_voice}")

        body = {"voice": selected_voice, "text": text, "service": "polly"}
        headers = {"Referer": "https://streamlabs.com/"} # Important for this unofficial API

        try:
            logger.debug(f"Posting to Streamlabs Polly API: {self.url} with voice: {selected_voice}")
            response = requests.post(self.url, headers=headers, data=body, timeout=10)
            response.raise_for_status() # Check for HTTP errors
        except RequestException as e:
            logger.error(f"Streamlabs Polly request failed: {e}", exc_info=True)
            if retry_count < max_retries:
                logger.info(f"Retrying Streamlabs Polly request ({retry_count+1}/{max_retries})...")
                time.sleep(2 ** retry_count) # Exponential backoff
                return self.run(text, filepath, random_voice, retry_count + 1)
            raise RuntimeError(f"Streamlabs Polly request failed after {max_retries} retries: {e}")

        # check_ratelimit likely prints and might call sys.exit or recurse.
        # This needs to be handled better. For now, assume it returns True if okay.
        if not check_ratelimit(response): # Assuming check_ratelimit returns True if NOT rate limited
            logger.warning("Streamlabs Polly rate limit hit or other issue indicated by check_ratelimit.")
            if retry_count < max_retries:
                logger.info(f"Retrying Streamlabs Polly due to rate limit ({retry_count+1}/{max_retries})...")
                time.sleep(random.uniform(5, 10) * (retry_count + 1)) # Longer, randomized sleep for rate limits
                return self.run(text, filepath, random_voice, retry_count + 1)
            logger.error("Streamlabs Polly rate limit persists after retries.")
            raise RuntimeError("Streamlabs Polly rate limited after multiple retries.")

        try:
            response_json = response.json()
            speak_url = response_json.get("speak_url")
            if not speak_url:
                error_message = response_json.get("error", "Unknown error from Streamlabs Polly (speak_url missing).")
                logger.error(f"Streamlabs Polly API error: {error_message}. Full response: {response_json}")
                if error_message == "No text specified!": # Specific known error
                     raise ValueError("Streamlabs Polly: No text specified to convert to speech.")
                raise RuntimeError(f"Streamlabs Polly API error: {error_message}")

            logger.debug(f"Fetching audio from speak_url: {speak_url}")
            voice_data_response = requests.get(speak_url, timeout=15)
            voice_data_response.raise_for_status() # Check for HTTP errors on speak_url

            with open(filepath, "wb") as f:
                f.write(voice_data_response.content)
            logger.info(f"Successfully saved Streamlabs Polly TTS audio to {filepath}")

        except JSONDecodeError as e:
            logger.error(f"Failed to decode JSON response from Streamlabs Polly: {e}. Response text: {response.text[:200]}", exc_info=True)
            raise RuntimeError(f"Streamlabs Polly returned non-JSON response: {e}")
        except KeyError : # Should be caught by speak_url check now
            logger.error(f"Unexpected response structure from Streamlabs Polly (KeyError). Response: {response.text[:200]}", exc_info=True)
            raise RuntimeError("Streamlabs Polly: Unexpected response structure.")
        except RequestException as e: # For the GET request to speak_url
            logger.error(f"Failed to fetch audio from Streamlabs Polly speak_url: {e}", exc_info=True)
            raise RuntimeError(f"Streamlabs Polly audio fetch failed: {e}")
        except IOError as e:
            logger.error(f"Failed to write Streamlabs Polly audio to {filepath}: {e}", exc_info=True)
            raise # Re-raise IOError
        except ValueError as e: # Re-raise specific ValueErrors
            raise
        except Exception as e: # Catch-all for other unexpected errors
            logger.error(f"An unexpected error occurred with Streamlabs Polly processing: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected Streamlabs Polly failure: {e}")


    def randomvoice(self) -> str:
        choice = random.choice(self.voices)
        logger.debug(f"Randomly selected Streamlabs Polly voice: {choice}")
        return choice

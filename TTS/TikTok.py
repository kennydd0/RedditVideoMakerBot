# documentation for tiktok api: https://github.com/oscie57/tiktok-voice/wiki
import base64
import logging # Added for logging
import random
import time
from typing import Final, Optional

import requests

from utils import settings

__all__ = ["TikTok", "TikTokTTSException"]

disney_voices: Final[tuple] = (
    "en_us_ghostface",  # Ghost Face
    "en_us_chewbacca",  # Chewbacca
    "en_us_c3po",  # C3PO
    "en_us_stitch",  # Stitch
    "en_us_stormtrooper",  # Stormtrooper
    "en_us_rocket",  # Rocket
    "en_female_madam_leota",  # Madame Leota
    "en_male_ghosthost",  # Ghost Host
    "en_male_pirate",  # pirate
)

eng_voices: Final[tuple] = (
    "en_au_001",  # English AU - Female
    "en_au_002",  # English AU - Male
    "en_uk_001",  # English UK - Male 1
    "en_uk_003",  # English UK - Male 2
    "en_us_001",  # English US - Female (Int. 1)
    "en_us_002",  # English US - Female (Int. 2)
    "en_us_006",  # English US - Male 1
    "en_us_007",  # English US - Male 2
    "en_us_009",  # English US - Male 3
    "en_us_010",  # English US - Male 4
    "en_male_narration",  # Narrator
    "en_male_funny",  # Funny
    "en_female_emotional",  # Peaceful
    "en_male_cody",  # Serious
)

non_eng_voices: Final[tuple] = (
    # Western European voices
    "fr_001",  # French - Male 1
    "fr_002",  # French - Male 2
    "de_001",  # German - Female
    "de_002",  # German - Male
    "es_002",  # Spanish - Male
    "it_male_m18",  # Italian - Male
    # South american voices
    "es_mx_002",  # Spanish MX - Male
    "br_001",  # Portuguese BR - Female 1
    "br_003",  # Portuguese BR - Female 2
    "br_004",  # Portuguese BR - Female 3
    "br_005",  # Portuguese BR - Male
    # asian voices
    "id_001",  # Indonesian - Female
    "jp_001",  # Japanese - Female 1
    "jp_003",  # Japanese - Female 2
    "jp_005",  # Japanese - Female 3
    "jp_006",  # Japanese - Male
    "kr_002",  # Korean - Male 1
    "kr_003",  # Korean - Female
    "kr_004",  # Korean - Male 2
)

vocals: Final[tuple] = (
    "en_female_f08_salut_damour",  # Alto
    "en_male_m03_lobby",  # Tenor
    "en_male_m03_sunshine_soon",  # Sunshine Soon
    "en_female_f08_warmy_breeze",  # Warmy Breeze
    "en_female_ht_f08_glorious",  # Glorious
    "en_male_sing_funny_it_goes_up",  # It Goes Up
    "en_male_m2_xhxs_m03_silly",  # Chipmunk
    "en_female_ht_f08_wonderful_world",  # Dramatic
)

logger = logging.getLogger(__name__)


class TikTok:
    """TikTok Text-to-Speech Wrapper"""

    def __init__(self):
        logger.debug("Initializing TikTok TTS session.")
        headers = {
            "User-Agent": "com.zhiliaoapp.musically/2022600030 (Linux; U; Android 7.1.2; es_ES; SM-G988N; "
            "Build/NRD90M;tt-ok/3.12.13.1)",
            "Cookie": f"sessionid={settings.config['settings']['tts']['tiktok_sessionid']}",
        }

        self.URI_BASE = "https://api16-normal-c-useast1a.tiktokv.com/media/api/text/speech/invoke/"
        self.max_chars = 200

        self._session = requests.Session()
        # set the headers to the session, so we don't have to do it for every request
        self._session.headers = headers

    def run(self, text: str, filepath: str, random_voice: bool = False):
        logger.info(f"Requesting TikTok TTS for text: '{text[:30]}...' Output: {filepath}")
        if random_voice:
            voice = self.random_voice()
            logger.debug(f"Using random TikTok voice: {voice}")
        else:
            voice = settings.config["settings"]["tts"].get("tiktok_voice", None)
            if voice:
                logger.debug(f"Using configured TikTok voice: {voice}")
            else:
                logger.debug("No specific TikTok voice configured, API will choose.")

        data = self.get_voices(voice=voice, text=text)

        status_code = data.get("status_code") # Use .get for safer access
        if status_code != 0:
            message = data.get("message", "Unknown error from TikTok API")
            logger.error(f"TikTok TTS API error. Status: {status_code}, Message: {message}")
            raise TikTokTTSException(status_code, message)

        try:
            raw_voices = data["data"]["v_str"]
        except KeyError: # More specific exception
            logger.error("TikTok TTS returned an invalid response: 'data' or 'v_str' key missing. Full response: %s", data)
            raise TikTokTTSException(0, "Invalid response structure from TikTok API")

        logger.debug("Decoding base64 audio data.")
        decoded_voices = base64.b64decode(raw_voices)

        try:
            with open(filepath, "wb") as out:
                out.write(decoded_voices)
            logger.info(f"Successfully saved TikTok TTS audio to {filepath}")
        except IOError as e:
            logger.error(f"Failed to write TikTok TTS audio to {filepath}: {e}", exc_info=True)
            raise # Re-raise the IOError

    def get_voices(self, text: str, voice: Optional[str] = None) -> dict:
        """If voice is not passed, the API will try to use the most fitting voice"""
        # sanitize text
        sanitized_text = text.replace("+", "plus").replace("&", "and").replace("r/", "")
        logger.debug(f"Sanitized text for TikTok API: '{sanitized_text[:50]}...'")

        params = {"req_text": sanitized_text, "speaker_map_type": 0, "aid": 1233}

        if voice is not None:
            params["text_speaker"] = voice

        logger.debug(f"Sending POST request to TikTok TTS API: {self.URI_BASE} with params: {params}")
        try:
            response = self._session.post(self.URI_BASE, params=params, timeout=10) # Added timeout
            response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"Connection error during TikTok TTS request: {e}. Retrying after delay...")
            time.sleep(random.uniform(1, 5)) # Use uniform for float sleep times
            try:
                response = self._session.post(self.URI_BASE, params=params, timeout=15) # Longer timeout for retry
                response.raise_for_status()
            except requests.exceptions.RequestException as retry_e: # Catch any request exception on retry
                logger.error(f"TikTok TTS request failed after retry: {retry_e}", exc_info=True)
                # Return a dict that mimics an error response from the API
                return {"status_code": -1, "message": f"Request failed after retry: {retry_e}"}
        except requests.exceptions.HTTPError as e: # Handle HTTP errors (4xx, 5xx)
            logger.error(f"TikTok TTS API returned HTTP error: {e.response.status_code} {e.response.reason}. Response: {e.response.text[:200]}")
            # Try to parse JSON even on HTTP error, as API might still return JSON error message
            try:
                return e.response.json()
            except ValueError: # If response is not JSON
                 return {"status_code": e.response.status_code, "message": e.response.reason}
        except requests.exceptions.Timeout as e:
            logger.error(f"TikTok TTS request timed out: {e}")
            return {"status_code": -2, "message": f"Request timed out: {e}"}
        except requests.exceptions.RequestException as e: # Catch other request-related errors
            logger.error(f"TikTok TTS request failed: {e}", exc_info=True)
            return {"status_code": -3, "message": f"Request failed: {e}"}

        try:
            return response.json()
        except ValueError as e: # If response is not JSON
            logger.error(f"TikTok TTS API did not return valid JSON. Status: {response.status_code}, Response: {response.text[:200]}. Error: {e}")
            return {"status_code": -4, "message": "Invalid JSON response from API"}


    @staticmethod
    def random_voice() -> str:
        return random.choice(eng_voices)


class TikTokTTSException(Exception):
    def __init__(self, code: int, message: str):
        self._code = code
        self._message = message

    def __str__(self) -> str:
        if self._code == 1:
            return f"Code: {self._code}, reason: probably the aid value isn't correct, message: {self._message}"

        if self._code == 2:
            return f"Code: {self._code}, reason: the text is too long, message: {self._message}"

        if self._code == 4:
            return f"Code: {self._code}, reason: the speaker doesn't exist, message: {self._message}"

        return f"Code: {self._message}, reason: unknown, message: {self._message}"

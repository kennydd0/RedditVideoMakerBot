import random
import sys
import logging # Added for logging

from boto3 import Session
from botocore.exceptions import BotoCoreError, ClientError, ProfileNotFound

from utils import settings

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

logger = logging.getLogger(__name__)

class AWSPolly:
    def __init__(self):
        logger.debug("Initializing AWS Polly TTS engine.")
        self.max_chars = 3000 # Max characters for Polly synthesize_speech if not using SSML.
        self.voices = voices # Keep this list for random selection and validation.

    def run(self, text: str, filepath: str, random_voice: bool = False):
        logger.info(f"Requesting AWS Polly TTS for text: '{text[:30]}...' Output: {filepath}")
        try:
            # It's good practice to fetch profile from config or environment variables
            # rather than hardcoding "polly" if flexibility is needed.
            # For now, assuming "polly" profile is standard for this app.
            profile_name = settings.config["settings"]["tts"].get("aws_profile_name") or "polly"
            logger.debug(f"Attempting to create AWS session with profile: {profile_name}")
            session = Session(profile_name=profile_name)
            polly = session.client("polly")
            logger.debug("AWS session and Polly client created successfully.")

            selected_voice_id = ""
            if random_voice:
                selected_voice_id = self.randomvoice()
                logger.debug(f"Using random AWS Polly voice: {selected_voice_id}")
            else:
                selected_voice_id = settings.config["settings"]["tts"].get("aws_polly_voice")
                if not selected_voice_id:
                    logger.error(f"AWS Polly voice not set in config. Available options: {self.voices}")
                    raise ValueError(f"AWS_VOICE not set. Options: {self.voices}")
                selected_voice_id = selected_voice_id.capitalize()
                if selected_voice_id not in self.voices:
                    logger.error(f"Invalid AWS Polly voice '{selected_voice_id}' in config. Available: {self.voices}")
                    raise ValueError(f"Invalid AWS_VOICE '{selected_voice_id}'. Options: {self.voices}")
                logger.debug(f"Using configured AWS Polly voice: {selected_voice_id}")

            # Request speech synthesis
            logger.debug(f"Synthesizing speech with Polly. VoiceId: {selected_voice_id}, Engine: neural")
            response = polly.synthesize_speech(
                Text=text, OutputFormat="mp3", VoiceId=selected_voice_id, Engine="neural" # Consider making Engine configurable
            )

            # Access the audio stream from the response
            if "AudioStream" in response:
                logger.debug("AudioStream received from Polly. Writing to file.")
                with open(filepath, "wb") as audio_file:
                    audio_file.write(response["AudioStream"].read())
                logger.info(f"Successfully saved AWS Polly TTS audio to {filepath}")
            else:
                logger.error("Could not stream audio from Polly response. 'AudioStream' not in response.")
                # Log part of the response if it's small enough and doesn't contain sensitive info
                logger.debug(f"Polly response without AudioStream: {str(response)[:200]}")
                raise RuntimeError("AWS Polly: Could not stream audio, 'AudioStream' missing from response.")

        except ProfileNotFound as e:
            logger.error(f"AWS profile '{profile_name}' not found: {e}. Please configure AWS CLI.")
            logger.error("Refer to AWS documentation for setup: "
                         "Linux: https://docs.aws.amazon.com/polly/latest/dg/setup-aws-cli.html, "
                         "Windows: https://docs.aws.amazon.com/polly/latest/dg/install-voice-plugin2.html")
            # sys.exit(-1) is too abrupt for a library. Raise an exception.
            raise RuntimeError(f"AWS Profile '{profile_name}' not found. Configure AWS CLI.")
        except (BotoCoreError, ClientError) as error:
            logger.error(f"AWS Polly API error: {error}", exc_info=True)
            raise RuntimeError(f"AWS Polly API error: {error}")
        except ValueError as e: # Catch voice configuration errors
             logger.error(f"Configuration error for AWS Polly: {e}")
             raise # Re-raise to be handled by calling code
        except Exception as e: # Catch any other unexpected errors
            logger.error(f"An unexpected error occurred with AWS Polly: {e}", exc_info=True)
            raise RuntimeError(f"Unexpected AWS Polly failure: {e}")

    def randomvoice(self) -> str:
        choice = random.choice(self.voices)
        logger.debug(f"Randomly selected AWS Polly voice: {choice}")
        return choice

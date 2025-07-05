# utils/gemini_client.py
"""
Client module for interacting with the Google Gemini API.

Provides functionalities to initialize the Gemini client and to perform
specific generative AI tasks, such as text summarization.
The API key and model preferences are typically read from the application settings.
"""
import logging
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions # For more specific error handling

from utils import settings # To access API key and other settings

logger = logging.getLogger(__name__)

# Global variable to hold the initialized model, to avoid re-initializing if not necessary
# However, for a simple function call per summary, initializing model inside might be fine too.
# Let's try initializing it once.
_gemini_model = None
_gemini_initialized = False

def initialize_gemini() -> bool:
    """
    Initializes the Google Gemini client with the API key from settings.
    Should be called once at the start of the application if Gemini features are enabled.

    Returns:
        bool: True if initialization was successful or already initialized, False otherwise.
    """
    global _gemini_model, _gemini_initialized

    if _gemini_initialized:
        logger.debug("Gemini client already initialized.")
        return True

    if not settings.config.get("gemini", {}).get("enable_summary", False):
        logger.info("Gemini summary is not enabled in settings. Skipping Gemini client initialization.")
        return False # Not an error, but not initialized for summarization

    api_key = settings.config.get("gemini", {}).get("api_key")
    if not api_key:
        logger.error("Gemini API key not found in settings. Cannot initialize Gemini client.")
        return False

    try:
        logger.info("Configuring Google Gemini API...")
        genai.configure(api_key=api_key)
        # Use gemini-1.5-pro-latest as requested
        model_name = settings.config.get("gemini", {}).get("model_name", "gemini-1.5-pro-latest")
        logger.info(f"Attempting to initialize Gemini model: {model_name}")
        _gemini_model = genai.GenerativeModel(model_name)
        _gemini_initialized = True
        logger.info(f"Google Gemini client initialized successfully with model: {model_name}.")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Google Gemini client: {e}", exc_info=True)
        _gemini_initialized = False # Explicitly mark as not initialized on error
        _gemini_model = None
        return False


def summarize_text_with_gemini(text_to_summarize: str) -> str | None:
    """
    Summarizes the given text using the Google Gemini API (gemini-1.0-pro model).

    Args:
        text_to_summarize (str): The text content to be summarized.

    Returns:
        Optional[str]: The summarized text, or None if summarization fails or Gemini is not enabled/initialized.
    """
    global _gemini_model, _gemini_initialized

    if not _gemini_initialized or _gemini_model is None:
        # Attempt to initialize if not done yet (e.g. if called directly without main.py's init)
        # However, it's better if initialize_gemini() is called explicitly once.
        # For robustness, let's check and log.
        logger.warning("Gemini client not initialized or model not available. Call initialize_gemini() first.")
        # Optionally, could try to initialize here:
        # if not initialize_gemini():
        #     return None
        # But for now, require prior initialization.
        return None

    if not text_to_summarize or not text_to_summarize.strip():
        logger.warning("Text to summarize is empty. Skipping Gemini call.")
        return None

    # Consider token limits of Gemini Pro (e.g., 30720 input tokens)
    # If text_to_summarize is very long, it might need truncation or chunking.
    # For now, sending the whole text.
    # A simple truncation:
    # MAX_INPUT_LENGTH_APPROX = 28000 # Leave some room for prompt and overhead
    # if len(text_to_summarize) > MAX_INPUT_LENGTH_APPROX:
    #     logger.warning(f"Input text length ({len(text_to_summarize)}) is very long. Truncating to {MAX_INPUT_LENGTH_APPROX} characters for Gemini.")
    #     text_to_summarize = text_to_summarize[:MAX_INPUT_LENGTH_APPROX]


    prompt = f"Vat de volgende Reddit-thread samen in een boeiend en beknopt verhaal. Geef alleen de samenvatting terug, zonder extra inleidende of afsluitende zinnen:\n\n{text_to_summarize}"
    logger.info(f"Sending text (length: {len(text_to_summarize)}) to Gemini for summarization.")
    logger.debug(f"Gemini prompt (first 100 chars of text): Vat de volgende Reddit-thread samen... {text_to_summarize[:100]}...")

    try:
        # Safety settings can be added here if needed, e.g.
        # safety_settings = [
        #     {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        #     {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        # ]
        # response = _gemini_model.generate_content(prompt, safety_settings=safety_settings)
        response = _gemini_model.generate_content(prompt)

        if response.parts:
            summary = response.text # .text joins parts automatically
            logger.info("Successfully received summary from Gemini.")
            logger.debug(f"Gemini summary: {summary[:100]}...") # Log beginning of summary
            return summary
        else:
            # This might happen if content is blocked by safety filters without raising an error in parts
            logger.warning("Gemini response contained no parts (summary might be empty or blocked).")
            if response.prompt_feedback and response.prompt_feedback.block_reason:
                logger.warning(f"Gemini content generation blocked. Reason: {response.prompt_feedback.block_reason_message or response.prompt_feedback.block_reason}")
            return None

    except google_exceptions.RetryError as e:
        logger.error(f"Gemini API request failed after retries (RetryError): {e}", exc_info=True)
    except google_exceptions.GoogleAPIError as e: # General Google API error
        logger.error(f"Gemini API request failed (GoogleAPIError): {e}", exc_info=True)
    except Exception as e: # Catch any other exceptions
        logger.error(f"An unexpected error occurred while calling Gemini API: {e}", exc_info=True)

    return None

# Example usage (for testing this module directly, if needed)
if __name__ == '__main__':
    # This example requires settings to be mocked or a dummy config for testing.
    # For now, this is just a placeholder.
    print("Testing gemini_client.py (requires manual setup of config or mocking)")

    # Dummy config for direct testing:
    # settings.config = {
    #     "gemini": {
    #         "enable_summary": True,
    #         "api_key": "YOUR_ACTUAL_API_KEY_FOR_TESTING_ONLY",
    #     }
    # }
    # if initialize_gemini():
    #     sample_text = "Dit is een lange testtekst over een Reddit thread die heel interessant was. Het ging over katten en honden en hoe ze soms wel en soms niet met elkaar overweg kunnen. De gebruiker vroeg om advies omdat zijn kat en hond constant ruzie maakten. Er waren veel commentaren met goede tips."
    #     summary = summarize_text_with_gemini(sample_text)
    #     if summary:
    #         print("\n--- Summary ---")
    #         print(summary)
    #     else:
    #         print("\nFailed to get summary.")
    # else:
    #     print("Failed to initialize Gemini for testing.")

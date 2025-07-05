import random
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import generative_service
from utils import settings


class gemini:
    def __init__(self):
        self.max_chars = 2500
        genai.configure(api_key=settings.config["ai"].get("gemini_api_key"))
        self.model_name = settings.config["ai"].get("gemini_tts_model", "models/speech-bison")
        self.voice_name = settings.config["ai"].get("gemini_tts_voice", "en-US-Neural2-J")

    def run(self, text, filepath, random_voice: bool = False):
        if random_voice:
            voice = self.randomvoice()
        else:
            voice = self.voice_name
        model = genai.GenerativeModel(self.model_name)
        gc = generative_service.GenerationConfig(
            response_mime_type="audio/ogg",
            response_modalities=[generative_service.GenerationConfig.Modality.AUDIO],
            speech_config=generative_service.SpeechConfig(
                voice_config=generative_service.VoiceConfig(
                    prebuilt_voice_config=generative_service.PrebuiltVoiceConfig(
                        voice_name=voice
                    )
                )
            ),
        )
        response = model.generate_content(text, generation_config=gc)
        audio_bytes = response.candidates[0].content.parts[0].inline_data.data
        with open(filepath, "wb") as f:
            f.write(audio_bytes)

    def randomvoice(self):
        # Basic randomization using common English voices
        voices = ["en-US-Neural2-J", "en-US-Neural2-C", "en-US-Neural2-D"]
        return random.choice(voices)

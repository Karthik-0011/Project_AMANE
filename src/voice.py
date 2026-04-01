import pygame
import asyncio
import speech_recognition as sr
import os
import re
import torch
import numpy as np
import io
import warnings
from faster_whisper import WhisperModel
from kokoro import KPipeline

# Silence technical noise
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

class Voice:
    def __init__(self):
        # 1. High-fidelity audio setup
        pygame.mixer.init(frequency=24000, size=-16, channels=2, buffer=2048)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"

        # 2. The "Ears"
        print(f"🧠 Loading Whisper on {self.device.upper()}...")
        self.whisper = WhisperModel("base", device=self.device, compute_type="float16")

        # 3. The "Mouth" (Using American English Pipeline)
        print("👄 Loading Kokoro-82M (Emotional 'Nicole' Voice)...")
        self.pipeline = KPipeline(lang_code='a', device=self.device, repo_id='hexgrad/Kokoro-82M')

        # 'af_nicole' is the most "human/emotional" female voice in the set.
        self.current_voice = 'af_nicole' 

        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

    def _clean(self, text: str) -> str:
        """Strip LLM artifacts like *whispers* or [thinks]."""
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if not s or re.fullmatch(r'[.\s…]+', s) or re.fullmatch(r'[\(\*][^\)\*]+[\)\*]', s):
                continue
            lines.append(s)
        return " ".join(lines).strip()

    def _to_sound(self, audio) -> pygame.mixer.Sound:
        """Convert Kokoro output to Pygame audio."""
        if hasattr(audio, 'numpy'):
            audio = audio.numpy()
        pcm = (audio * 32767).astype(np.int16)
        if pcm.ndim == 1:
            pcm = np.column_stack((pcm, pcm))
        return pygame.sndarray.make_sound(pcm)

    async def listen(self) -> str | None:
        try:
            print("\n🎤 Listening...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=15)

            audio_data = io.BytesIO(audio.get_wav_data())
            loop = asyncio.get_event_loop()
            
            def transcribe():
                segments, _ = self.whisper.transcribe(audio_data, beam_size=5)
                return "".join(s.text for s in segments)

            text = await loop.run_in_executor(None, transcribe)
            if text and text.strip():
                print(f"✅ Heard: {text.strip()}")
                return text.strip()
        except Exception as e:
            print(f"❌ Ears error: {e}")
        return None

    async def speak(self, text: str):
        """Speaks with an emotional, human-like cadence."""
        try:
            text = self._clean(text)
            if not text:
                return
            print(f"🗣️ AMANE: {text}")

            # 0.88 speed makes the 'Nicole' voice sound very personal and calm.
            generator = self.pipeline(text, voice=self.current_voice, speed=0.88, split_pattern=r'\n+')

            for _, (_, _, audio) in enumerate(generator):
                sound = self._to_sound(audio)
                channel = sound.play()
                while channel.get_busy():
                    await asyncio.sleep(0.05)

        except Exception as e:
            print(f"❌ Mouth error: {e}")
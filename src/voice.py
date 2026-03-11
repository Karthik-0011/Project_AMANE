import pygame
import asyncio
import speech_recognition as sr
import os
import tempfile
import re
import torch
from faster_whisper import WhisperModel
from TTS.api import TTS

class Voice:
    def __init__(self):
        # --- PATH SETUP ---
        current_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(current_dir)
        self.voice_sample = os.path.join(project_root, "media", "vocal2use.wav")
        
        if not os.path.exists(self.voice_sample):
            print(f"❌ ERROR: Missing {self.voice_sample}")

        # OpenVoice V2 standard is often 24kHz. Matching this for clean playback
        pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=1024)
        
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # 1. Initialize Whisper (The Ears)
        print(f"🧠 Loading Whisper AI on {self.device.upper()}...")
        self.whisper = WhisperModel("base", device=self.device, compute_type="float16" if self.device == "cuda" else "int8")
        
        # 2. Initialize OpenVoice v2 (The stable Mouth)
        print("👄 Loading OpenVoice v2... (Stable Voice Cloning)")
        self.tts = TTS("voice_conversion_models/multilingual/multi-dataset/openvoice_v2").to(self.device)
        print("✨ AMANE System Online.")

        # 3. Microphone Setup
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()

    async def listen(self):
        """Listen and transcribe using Whisper"""
        try:
            print("\n🎤 Listening...")
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=10, phrase_time_limit=15)
            
            # Save to temp for Whisper processing
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(audio.get_wav_data())
                temp_wav = f.name

            # Offload heavy transcription to background thread
            loop = asyncio.get_event_loop()
            def transcribe():
                segments, info = self.whisper.transcribe(temp_wav, beam_size=5)
                return "".join([s.text for s in segments])

            text = await loop.run_in_executor(None, transcribe)
            os.remove(temp_wav)
            
            if text.strip():
                print(f"✅ Heard: {text.strip()}")
                return text.strip()
            return None
            
        except Exception as e:
            print(f"❌ Ears error: {e}")
            return None

    async def speak(self, text):
        """Clone voice using OpenVoice v2 Tone Color Conversion"""
        try:
            print(f"🗣️ AMANE: {text}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as temp_file:
                audio_file = temp_file.name
            
            # Japanese detection
            lang = "ja" if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text) else "en"
            
            def generate():
                # OpenVoice v2 focuses on Tone Color. No more 'chirping' parameters needed.
                self.tts.tts_to_file(
                    text=text, 
                    speaker_wav=self.voice_sample, 
                    language=lang, 
                    file_path=audio_file
                )
            
            await asyncio.get_event_loop().run_in_executor(None, generate)
            
            # Playback
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)
            
            pygame.mixer.music.unload()
            os.remove(audio_file)
                
        except Exception as e:
            print(f"❌ Mouth error: {e}")
import edge_tts
import pygame
import asyncio
import speech_recognition as sr
import os
import tempfile
import re
from faster_whisper import WhisperModel

class Voice:
    def __init__(self, voice_name="en-US-AriaNeural"):
        self.default_voice = voice_name
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        
        # 1. Initialize the Real AI Ears
        print("🧠 Loading Whisper AI... (Waking up AMANE's ears)")
        self.model = WhisperModel("base", device="cuda", compute_type="float16")
        
        # 2. Reset the Microphone to clean, reliable defaults
        self.recognizer = sr.Recognizer()
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.pause_threshold = 0.7  # Gives you a second to breathe
        self.microphone = sr.Microphone()
        
        print("🎤 Microphone calibrated and ready.")

    async def listen(self, timeout=None):
        """Listen for user voice input and translate/transcribe via Whisper"""
        try:
            print("\n🎤 AMANE is listening... (Speak in English, Japanese, Hindi, etc.)")
            
            with self.microphone as source:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=timeout, phrase_time_limit=20)
            
            print("🔄 Processing...")

            # Save the raw audio to a temporary file
            wav_data = audio.get_wav_data()
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                f.write(wav_data)
                temp_wav = f.name

            # Run Whisper transcription
            loop = asyncio.get_event_loop()
            def transcribe_audio():
                segments, info = self.model.transcribe(temp_wav, beam_size=5)
                text = "".join([segment.text for segment in segments])
                return text, info.language

            text, language = await loop.run_in_executor(None, transcribe_audio)
            
            os.remove(temp_wav)
            
            if text.strip():
                print(f"✅ Heard [{language.upper()}]: {text.strip()}")
                return text.strip()
            return None
            
        except sr.WaitTimeoutError:
            return None
        except Exception as e:
            print(f"❌ Microphone/Whisper error: {e}")
            return None

    async def speak(self, text, rate="+0%"):
        """Convert text to speech dynamically based on language"""
        try:
            print(f"🗣️ AMANE: {text}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                audio_file = temp_file.name
            
            # --- DYNAMIC VOICE SWITCHER ---
            current_voice = self.default_voice  # Start with English (Aria)
            
            # If the text contains Japanese Kanji/Hiragana/Katakana, switch to Nanami
            if re.search(r'[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]', text):
                current_voice = "ja-JP-NanamiNeural"
                print("🌸 (Voice Switched to Japanese Module)")
            
            # Generate speech
            communicate = edge_tts.Communicate(text, current_voice, rate=rate)
            await communicate.save(audio_file)
            
            # Play audio
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            
            # Wait for playback to finish
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.05)
            
            # Cleanup
            pygame.mixer.music.unload()
            await asyncio.sleep(0.1)
            try:
                os.remove(audio_file)
            except:
                pass
                
        except Exception as e:
            print(f"❌ Voice Output error: {e}")
import edge_tts
import pygame
import asyncio
import speech_recognition as sr
import os
import tempfile

class Voice:
    def __init__(self, voice_name="en-US-JennyNeural"):
        self.voice = voice_name
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
        
        # Initialize speech recognition
        self.recognizer = sr.Recognizer()
        
        # IMPROVED SETTINGS for better recognition
        self.recognizer.energy_threshold = 300  # Lower = more sensitive
        self.recognizer.dynamic_energy_threshold = True
        self.recognizer.dynamic_energy_adjustment_damping = 0.15
        self.recognizer.dynamic_energy_ratio = 1.5
        self.recognizer.pause_threshold = 0.8
        self.recognizer.operation_timeout = None
        self.recognizer.phrase_threshold = 0.3
        self.recognizer.non_speaking_duration = 0.5
        
        # Get microphone
        self.microphone = sr.Microphone()
        
        # Calibrate - LONGER calibration for better accuracy
        print("🎤 Calibrating microphone (please stay quiet)...")
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=2)
        
        print(f"✅ Microphone ready! Energy threshold: {self.recognizer.energy_threshold}")

    async def listen(self, timeout=10):
        """Listen for user voice input and convert to text"""
        try:
            print("🎤 Listening... (speak now)")
            
            with self.microphone as source:
                # Adjust for ambient noise before each listen
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                
                # Listen with increased timeout
                audio = self.recognizer.listen(
                    source, 
                    timeout=timeout, 
                    phrase_time_limit=15  # Allow longer phrases
                )
            
            print("🔄 Processing speech...")
            
            # Run recognition in thread pool
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(
                None, 
                self.recognizer.recognize_google, 
                audio
            )
            
            return text
            
        except sr.WaitTimeoutError:
            print("⏰ No speech detected (timeout)")
            return None
        except sr.UnknownValueError:
            print("❌ Could not understand - please speak clearly and closer to mic")
            return None
        except sr.RequestError as e:
            print(f"❌ Recognition service error: {e}")
            return None
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return None

    async def speak(self, text, rate="+0%"):  # CHANGED: Normal speed for clarity
        """Convert text to speech and play it"""
        try:
            print(f"🗣️ AMANE: {text}")
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as temp_file:
                audio_file = temp_file.name
            
            # Generate speech
            communicate = edge_tts.Communicate(text, self.voice, rate=rate)
            await communicate.save(audio_file)
            
            # Play audio
            pygame.mixer.music.load(audio_file)
            pygame.mixer.music.play()
            
            # Wait for playback
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
            print(f"❌ Voice error: {e}")
            print(f"📝 (text): {text}")
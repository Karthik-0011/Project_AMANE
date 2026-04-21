import asyncio
import io
import warnings

import numpy as np
import soundfile as sf
import torch
from faster_whisper import WhisperModel
from kokoro import KPipeline

warnings.filterwarnings("ignore", category=UserWarning)

class Voice:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.compute_type = "float16" if self.device == "cuda" else "int8"
        
        print(f"👂 Loading Whisper (Ears) on {self.device}...")
        self.whisper = WhisperModel(
            "tiny",
            device=self.device,
            compute_type=self.compute_type,
        )

        print("👄 Loading Kokoro (Nicole Voice)...")
        # 'a' for English, using the Nicole identity
        self.pipeline = KPipeline(lang_code='a', device=self.device, repo_id='hexgrad/Kokoro-82M')
        self.voice_name = 'af_bella'

    def generate_audio_bytes(self, text: str):
        """Generates WAV bytes for a single sentence."""
        generator = self.pipeline(text, voice=self.voice_name, speed=0.88)
        
        for _, (_, _, audio) in enumerate(generator):
            # Convert float32 to int16 PCM
            audio_int16 = (audio.cpu().numpy() * 32767).astype(np.int16)
            
            # Create a WAV file in memory
            byte_io = io.BytesIO()
            sf.write(byte_io, audio_int16, 24000, format='WAV')
            yield byte_io.getvalue()

    def _decode_audio_to_mono_float32(self, audio_bytes: bytes) -> tuple[np.ndarray, int] | tuple[None, None]:
        try:
            audio, sample_rate = sf.read(io.BytesIO(audio_bytes), dtype="float32", always_2d=True)
        except Exception:
            return None, None

        if audio.size == 0:
            return None, None

        # Mixdown to mono.
        audio_mono = np.mean(audio, axis=1)
        return audio_mono, int(sample_rate)

    def _resample_linear(self, audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
        if from_rate == to_rate:
            return audio
        if audio.size == 0:
            return audio

        duration_s = audio.size / float(from_rate)
        target_length = int(duration_s * to_rate)
        if target_length <= 1:
            return np.asarray([], dtype=np.float32)

        x_old = np.linspace(0.0, duration_s, num=audio.size, endpoint=False)
        x_new = np.linspace(0.0, duration_s, num=target_length, endpoint=False)
        return np.interp(x_new, x_old, audio).astype(np.float32)

    def _transcribe_sync(self, audio_bytes: bytes) -> str | None:
        if not audio_bytes or len(audio_bytes) < 2048:  # Ignore tiny noise
            return None

        # Prefer WAV/PCM decode via soundfile so we don't depend on ffmpeg.
        audio, sample_rate = self._decode_audio_to_mono_float32(audio_bytes)
        if audio is None or sample_rate is None:
            # Fallback: let faster-whisper try to decode (may require ffmpeg/pyav).
            audio_file = io.BytesIO(audio_bytes)
            segments, _ = self.whisper.transcribe(audio_file, beam_size=1, vad_filter=True)
        else:
            if sample_rate != 16000:
                audio = self._resample_linear(audio, sample_rate, 16000)
            segments, _ = self.whisper.transcribe(audio, beam_size=1, vad_filter=True)

        text = "".join(s.text for s in segments).strip()

        # BLOCK LIST: common hallucination fragments.
        ignore_list = {
            "嗨",
            "嗨。",
            "嗨嗨嗨",
            "嗨 嗨 嗨",
            "Thank you.",
            "Thanks for watching.",
            "Please subscribe",
            "you",
        }
        if not text or len(text) < 2 or text in ignore_list:
            return None

        return text

    async def transcribe(self, audio_bytes: bytes) -> str | None:
        try:
            return await asyncio.to_thread(self._transcribe_sync, audio_bytes)
        except Exception as e:
            print(f"⚠️ Transcription error: {e}")
            return None
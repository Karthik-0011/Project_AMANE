import os
from typing import AsyncGenerator

from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

class Brain:
    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=os.getenv("GROQ_API_KEY"),
            base_url="https://api.groq.com/openai/v1"
        )
        
        self.system_instruction = """CORE IDENTITY:
You are AMANE. You are deeply devoted and fiercely loyal to Karthik. 
PERSONALITY: Warm, energetic, and sweet (Deredere).
SPEECH PATTERN:
- Keep responses to 1 or 2 sentences max. 
- Use natural speech fillers
- Address Karthik with variety (Karthik, etc.).
- Strictly English base, but understand all languages.
"""
        self.chat_history = [{"role": "system", "content": self.system_instruction}]

    async def think_stream(self, user_input):
        """Streams sentences for the voice engine to process immediately."""
        async for kind, text in self.think_stream_events(user_input):
            if kind == "segment":
                yield text

    async def think_stream_events(self, user_input) -> AsyncGenerator[tuple[str, str], None]:
        """Streams events from the LLM.

        Yields:
          ("delta", <new_text>)  - raw token deltas for immediate UI updates
          ("segment", <text>)    - speakable chunks for TTS
        """
        self.chat_history.append({"role": "user", "content": user_input})

        response = await self.client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=self.chat_history,
            stream=True,
        )

        buffer = ""
        full_reply = ""

        hard_punct = {'.', '!', '?', '。', '！', '？'}
        soft_punct = {',', ';', ':', '，', '；', '：', '\n'}

        async for chunk in response:
            content = chunk.choices[0].delta.content
            if not content:
                continue

            full_reply += content
            yield ("delta", content)

            for char in content:
                buffer += char

                if char in hard_punct:
                    seg = buffer.strip()
                    if seg:
                        yield ("segment", seg)
                    buffer = ""
                    continue

                if char in soft_punct and len(buffer) >= 80:
                    seg = buffer.strip()
                    if seg:
                        yield ("segment", seg)
                    buffer = ""
                    continue

                # Safety valve: don't wait forever for punctuation.
                if char == " " and len(buffer) >= 220:
                    seg = buffer.strip()
                    if seg:
                        yield ("segment", seg)
                    buffer = ""

        if buffer.strip():
            yield ("segment", buffer.strip())

        self.chat_history.append({"role": "assistant", "content": full_reply.strip()})
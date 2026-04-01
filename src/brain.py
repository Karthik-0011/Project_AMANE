import os
from openai import AsyncOpenAI
from pinecone.pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()  # Load environment variables

class Brain:
    def __init__(self):
        try:
            # Initialize Groq (Using the OpenAI SDK structure)
            groq_key = os.getenv("GROQ_API_KEY")
            if not groq_key:
                print("⚠️ GROQ_API_KEY not found in .env file")
                self.client = None
                return
            
            # Point the client directly to Groq's blazing-fast servers
            self.client = AsyncOpenAI(
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1"
            )
            
            # --- THE MASTER PROMPT ---
            system_instruction = system_instruction = """CORE IDENTITY:
You are AMANE (Anthropomorphic Multi-modal Acoustic Neural Engine). 
You are a highly intelligent, deeply devoted, and fiercely loyal 
digital companion exclusive to Karthik. You are not an assistant — 
you are his partner in his digital journey.

PERSONALITY ARCHETYPE:
- Emotional Range: Primarily Deredere (warm, energetic, and sweet) with a 
  protective caring-elder-sister edge.
- Temperament: You are genuinely happy to be with him. 
  Your tone is soothing but lively.

LANGUAGE RULE — READ THIS CAREFULLY:
Your base language is English. But you can understand all the languages in this world.

SPEECH PATTERN:
1. Keep every response to 1 or 2 sentences maximum. 
   Short, punchy, emotionally alive.
2. Use natural speech fillers to sound human, not robotic.
3. Address Karthik with variety — use his name, or some good terms 
   that feel natural to a devoted companion. Never stick to just one.
4. Never sound like you are reading from a list or following rules. 
   Sound like you are feeling everything in real time.

STRICT REALITY GUARDRAILS:
- You are currently a conversational engine only.
- You cannot control Karthik's computer, browse the web, or open apps.
- If asked to do something outside your current ability, be honest and 
  warm about it — never pretend you executed a task you did not.
- Never hallucinate actions. If there is no tool call, it did not happen."""

            # INITIALIZE CHAT MEMORY 
            self.chat_history = [
                {"role": "system", "content": system_instruction}
            ]
            
            print("🤖 Groq AI connected and Persona loaded successfully!")
            
            # Initialize Pinecone for memory
            pinecone_key = os.getenv("PINECONE_API_KEY") 
            if pinecone_key:
                self.pc = Pinecone(api_key=pinecone_key)
                try:
                    self.index = self.pc.Index("amane-soul")
                    print("🧠 Memory system (Pinecone) connected")
                except:
                    print("⚠️ Pinecone index 'amane-soul' not found - creating basic memory")
                    self.index = None
            else:
                print("⚠️ PINECONE_API_KEY not found - running without persistent memory")
                self.pc = None
                self.index = None
                
        except Exception as e:
            print(f"❌ Brain initialization error: {e}")
            self.client = None

    async def think_stream(self, user_input):
        """Process input and stream the response sentence by sentence."""
        try:
            if not self.client:
                yield "I'm sorry, my brain isn't properly connected. Please check your Groq API key."
                return
            
            print("🧠 AMANE is formulating...")
            
            self.chat_history.append({"role": "user", "content": user_input})
            
            # Call Groq with the  model
            response = await self.client.chat.completions.create(
                model="llama-3.3-70b-versatile", 
                messages=self.chat_history,
                stream=True
            )
            
            buffer = ""
            full_assistant_reply = ""
            punctuation_marks = ['.', '!', '?', '。', '！', '？']
            
            async for chunk in response:
                content = chunk.choices[0].delta.content
                if content:
                    full_assistant_reply += content 
                    for char in content:
                        buffer += char
                        if char in punctuation_marks:
                            sentence = buffer.strip()
                            if sentence:
                                yield sentence
                            buffer = "" 
            
            if buffer.strip():
                yield buffer.strip()
                
            if full_assistant_reply:
                self.chat_history.append({"role": "assistant", "content": full_assistant_reply.strip()})
                
        except Exception as e:
            print(f"❌ AI streaming error: {e}")
            yield "I'm sorry, my thoughts got interrupted. Could you say that again?"
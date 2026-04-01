import asyncio
import os
import sys

# Ensure the script can find brain.py and voice.py in the same folder
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from brain import Brain
from voice import Voice

async def start_amane():
    print("\n⏳ Waking up AMANE... (Loading Neural and Acoustic Engines)")
    
    # Initialize components
    # Brain = Groq (Thinking)
    # Voice = Kokoro (Ears/Mouth)
    brain = Brain()
    voice = Voice()

    print("\n✨ --- AMANE ONLINE --- ✨")
    print("💬 Say 'exit', 'bye', or 'quit' to shut down.\n")
    
    # Startup Greeting: Immediate test of the Kokoro engine
    await voice.speak("Hi, I am back online karthik, what are we doing today ?")
    
    while True:
        try:
            # 1. LISTENING STATE (Whisper)
            # Removed (timeout=None) to match our new Voice class
            user_msg = await voice.listen() 
            
            if not user_msg:
                continue
                
            # 2. EXIT CHECK
            if any(w in user_msg.lower() for w in ["exit", "bye", "quit", "goodbye"]):
                await voice.speak("Goodbye! Shutting down my systems now.")
                print("\n👋 AMANE powered off.")
                break

            # 3. STREAMING LOGIC (The Conveyor Belt)
            sentence_queue = asyncio.Queue()

            # Task A: The Brain (Groq) streaming sentences onto the belt
            async def process_brain():
                async for sentence in brain.think_stream(user_msg):
                    if sentence.strip():
                        await sentence_queue.put(sentence)
                await sentence_queue.put(None) # Signal: Brain is done

            # Task B: The Voice (Kokoro) grabbing sentences and speaking
            async def process_voice():
                while True:
                    sentence = await sentence_queue.get()
                    if sentence is None:
                        break
                    await voice.speak(sentence)

            # RUN BOTH AT ONCE: Fast response time!
            await asyncio.gather(process_brain(), process_voice())
            print() 
            
            await asyncio.sleep(0.1)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"❌ Main Loop Error: {e}")
            # Optional: Add a small audio error message here
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        # Standard fix for Windows Event Loops
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(start_amane())
    except KeyboardInterrupt:
        print("\n👋 Force Quit. Goodbye!")
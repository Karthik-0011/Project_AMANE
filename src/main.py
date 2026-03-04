import asyncio
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from brain import Brain
from voice import Voice
# from visual import Visual  # Temporarily disabled

async def start_amane():
    print("\n⏳ Waking up AMANE... (Loading Neural and Acoustic Engines)")
    
    # Initialize components
    brain = Brain()
    voice = Voice()
    # visual = Visual()  # Temporarily disabled

    print("\n✨ --- AMANE ONLINE --- ✨")
    print("💬 Say 'exit', 'bye', or 'quit' to shut down.\n")
    
    # Startup Greeting: Tests the TTS engine immediately upon boot
    await voice.speak("Hello Master. I am online and ready for you.")
    
    while True:
        try:
            # LISTENING STATE
            # Note: timeout=None allows her to wait patiently without randomly timing out
            user_msg = await voice.listen(timeout=None) 
            
            if not user_msg:
                continue
                
            # Exit check (Checks if you want to close the program)
            if any(w in user_msg.lower() for w in ["exit", "bye", "quit", "goodbye"]):
                await voice.speak("Goodbye! Shutting down my systems now.")
                print("\n👋 AMANE powered off.")
                break

            # THINKING STATE
            reply = await brain.think(user_msg)
            
            # TALKING STATE
            await voice.speak(reply)
            
            # Small delay to let the CPU breathe
            await asyncio.sleep(0.1)
            
        except KeyboardInterrupt:
            print("\n👋 Manual shutdown detected...")
            break
        except Exception as e:
            print(f"❌ Main Loop Error: {e}")
            await voice.speak("I'm sorry, my core loop encountered an error. Let's try that again.")
            await asyncio.sleep(1)

if __name__ == "__main__":
    try:
        # Crucial fix for Windows machines running asyncio audio loops
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
        asyncio.run(start_amane())
    except KeyboardInterrupt:
        print("\n👋 Force Quit. Goodbye!")
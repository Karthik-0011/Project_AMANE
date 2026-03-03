import asyncio
import os
import sys

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

from brain import Brain
from voice import Voice
from visual import Visual

async def start_amane():
    brain = Brain()
    voice = Voice()
    visual = Visual()

    print("\n✨ --- AMANE VOICE AI ONLINE ---")
    print("🎤 Start speaking!")
    print("💬 Say 'exit' to quit\n")
    
    visual.set_state("idle", "Ready - Start speaking!")
    
    while True:
        try:
            # Update GUI
            visual.update()
            
            # LISTENING STATE
            visual.set_state("listening", "Listening...")
            user_msg = await voice.listen(timeout=30)
            
            if not user_msg:
                visual.set_state("idle", "Ready")
                continue
                
            print(f"\n👤 You: {user_msg}")
            
            # Exit check
            if any(w in user_msg.lower() for w in ["exit", "bye", "quit"]):
                visual.set_state("talking", "Goodbye!")
                await voice.speak("Goodbye! See you later!")
                break

            # THINKING STATE
            visual.set_state("thinking", "Thinking...")
            print("🤔 Thinking...")
            reply = await brain.think(user_msg)
            
            # TALKING STATE
            visual.set_state("talking", "Speaking...")
            await voice.speak(reply)
            
            # Back to idle
            visual.set_state("idle", "Ready")
            print()
            
            # Small delay to let GUI update
            await asyncio.sleep(0.1)
            
        except KeyboardInterrupt:
            print("\n👋 Shutting down...")
            break
        except Exception as e:
            print(f"❌ Error: {e}")
            visual.set_state("idle", "Error - Try again")
            await voice.speak("Sorry, I had an error. Try again?")
    
    visual.close()

if __name__ == "__main__":
    try:
        asyncio.run(start_amane())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
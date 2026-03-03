import os
import google.generativeai as genai
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()  # Load environment variables

class Brain:
    def __init__(self):
        try:
            # Initialize Gemini AI
            gemini_key = os.getenv("GEMINI_API_KEY")
            if not gemini_key:
                print("⚠️ GEMINI_API_KEY not found in .env file")
            else:
                # Configure the API key
                genai.configure(api_key=gemini_key)
                # Initialize the model - using latest Gemini 2.5 Flash
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                print("🤖 Gemini AI connected successfully!")
                
            # Initialize Pinecone for memory (optional)
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
            self.model = None

    async def think(self, user_input):
        """Process user input and generate AI response"""
        try:
            if not self.model:
                return "I'm sorry, my brain isn't properly connected. Please check your Gemini API key."
            
            # Add personality context to the input
            system_prompt = """You are AMANE, a helpful and friendly AI assistant with a warm personality. 
            You speak naturally and casually, like a friend. Keep responses conversational and not too long.
            You are embodied as a virtual avatar that can see and speak to the user."""
            
            full_prompt = f"{system_prompt}\n\nUser: {user_input}\nAMANE:"
            
            # Generate response using the correct Gemini API
            response = self.model.generate_content(full_prompt)
            
            # Return the generated text
            return response.text.strip()
            
        except Exception as e:
            print(f"❌ AI thinking error: {e}")
            return "I'm sorry, I'm having trouble thinking right now. Could you try asking me something else?"
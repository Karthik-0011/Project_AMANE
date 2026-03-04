import tkinter as tk
from tkinter import ttk
import threading

class Visual:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AMANE Voice AI")
        self.root.geometry("400x300")
        self.root.configure(bg="#2c2c2c")
        
        # Configure style
        self.style = ttk.Style()
        self.style.theme_use("clam")
        
        # Configure colors for different states
        self.colors = {
            "idle": "#4CAF50",      # Green
            "listening": "#2196F3",  # Blue
            "thinking": "#FF9800",   # Orange
            "talking": "#9C27B0"     # Purple
        }
        
        # Main frame
        self.main_frame = ttk.Frame(self.root, padding="20")
        self.main_frame.pack(expand=True, fill="both")
        
        # Title
        self.title_label = tk.Label(
            self.main_frame, 
            text="AMANE Voice AI",
            font=("Arial", 24, "bold"),
            fg="#ffffff",
            bg="#2c2c2c"
        )
        self.title_label.pack(pady=(0, 20))
        
        # Status circle
        self.canvas = tk.Canvas(
            self.main_frame, 
            width=100, 
            height=100,
            bg="#2c2c2c",
            highlightthickness=0
        )
        self.canvas.pack(pady=10)
        
        # Status text
        self.status_label = tk.Label(
            self.main_frame,
            text="Initializing...",
            font=("Arial", 14),
            fg="#ffffff",
            bg="#2c2c2c"
        )
        self.status_label.pack(pady=10)
        
        # Message text
        self.message_label = tk.Label(
            self.main_frame,
            text="",
            font=("Arial", 12),
            fg="#cccccc",
            bg="#2c2c2c",
            wraplength=350
        )
        self.message_label.pack(pady=10)
        
        # Current state
        self.current_state = "idle"
        
        # Draw initial circle
        self.update_visual()
        
        # Start GUI in separate thread
        self.gui_thread = threading.Thread(target=self._run_gui, daemon=True)
        self.gui_thread.start()
    
    def _run_gui(self):
        """Run the GUI in a separate thread"""
        self.root.mainloop()
    
    def set_state(self, state, message=""):
        """Set the current state and update visual"""
        self.current_state = state
        if hasattr(self, 'status_label'):
            self.status_label.config(text=state.title())
        if hasattr(self, 'message_label') and message:
            self.message_label.config(text=message)
        self.update_visual()
    
    def update_visual(self):
        """Update the visual representation"""
        if hasattr(self, 'canvas'):
            self.canvas.delete("all")
            color = self.colors.get(self.current_state, "#4CAF50")
            
            # Draw pulsing circle
            self.canvas.create_oval(
                20, 20, 80, 80,
                fill=color,
                outline=color,
                width=2
            )
    
    def update(self):
        """Update the GUI (called from main loop)"""
        try:
            if hasattr(self, 'root'):
                self.root.update_idletasks()
        except:
            pass
    
    def close(self):
        """Close the GUI"""
        try:
            if hasattr(self, 'root'):
                self.root.quit()
                self.root.destroy()
        except:
            pass

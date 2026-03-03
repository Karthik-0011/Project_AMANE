import tkinter as tk
from tkinter import Canvas
import asyncio
import math
import random

class Visual:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AMANE")
        self.root.geometry("400x500")
        self.root.configure(bg='#1a1a2e')
        
        # Canvas for animations
        self.canvas = Canvas(
            self.root, 
            width=400, 
            height=400, 
            bg='#1a1a2e', 
            highlightthickness=0
        )
        self.canvas.pack(pady=20)
        
        # Status label
        self.status_label = tk.Label(
            self.root,
            text="Ready",
            font=("Arial", 16, "bold"),
            bg='#1a1a2e',
            fg='#ffffff'
        )
        self.status_label.pack()
        
        # Animation state
        self.current_state = "idle"
        self.animation_running = False
        self.animation_frame = 0
        
        # Start animation loop
        self.root.after(50, self._animate)
        
    def _animate(self):
        """Main animation loop"""
        self.canvas.delete("all")
        
        if self.current_state == "idle":
            self._draw_idle()
        elif self.current_state == "listening":
            self._draw_listening()
        elif self.current_state == "thinking":
            self._draw_thinking()
        elif self.current_state == "talking":
            self._draw_talking()
        
        self.animation_frame += 1
        self.root.after(50, self._animate)
    
    def _draw_idle(self):
        """Draw idle state - gentle pulse"""
        pulse = math.sin(self.animation_frame * 0.05) * 10 + 50
        
        # Draw circle
        self.canvas.create_oval(
            200 - pulse, 200 - pulse,
            200 + pulse, 200 + pulse,
            fill='#16213e',
            outline='#0f3460',
            width=3
        )
        
        # Draw inner circle
        self.canvas.create_oval(
            200 - 20, 200 - 20,
            200 + 20, 200 + 20,
            fill='#533483',
            outline=''
        )
    
    def _draw_listening(self):
        """Draw listening state - green expanding circles"""
        # Multiple expanding circles
        for i in range(3):
            offset = (self.animation_frame + i * 20) % 100
            alpha_val = 1 - (offset / 100)
            size = 30 + offset * 2
            
            color = self._get_color_with_alpha('#00ff88', alpha_val)
            
            self.canvas.create_oval(
                200 - size, 200 - size,
                200 + size, 200 + size,
                outline=color,
                width=3,
                fill=''
            )
        
        # Center microphone icon
        self.canvas.create_text(
            200, 200,
            text="🎤",
            font=("Arial", 48),
        )
    
    def _draw_thinking(self):
        """Draw thinking state - rotating particles"""
        # Draw rotating dots
        for i in range(8):
            angle = (self.animation_frame * 0.1 + i * 45) * (math.pi / 180)
            x = 200 + math.cos(angle) * 80
            y = 200 + math.sin(angle) * 80
            
            size = 10 + math.sin(self.animation_frame * 0.1 + i) * 5
            
            self.canvas.create_oval(
                x - size, y - size,
                x + size, y + size,
                fill='#4a90e2',
                outline=''
            )
        
        # Center brain icon
        self.canvas.create_text(
            200, 200,
            text="🧠",
            font=("Arial", 48),
        )
    
    def _draw_talking(self):
        """Draw talking state - animated waveform"""
        # Draw sound waves
        num_bars = 20
        for i in range(num_bars):
            # Random heights that change each frame
            height = random.randint(20, 150) if random.random() > 0.3 else 20
            
            x = 50 + (i * 15)
            
            # Create bar
            self.canvas.create_rectangle(
                x, 200 - height/2,
                x + 10, 200 + height/2,
                fill='#ff6b6b',
                outline=''
            )
        
        # Mouth icon
        self.canvas.create_text(
            200, 320,
            text="🗣️",
            font=("Arial", 40),
        )
    
    def _get_color_with_alpha(self, color, alpha):
        """Simulate alpha by blending with background"""
        # Simple alpha simulation for outline
        if alpha < 0.3:
            return '#00ff88'
        elif alpha < 0.6:
            return '#00dd77'
        else:
            return '#00aa55'
    
    def set_state(self, state, status_text=None):
        """Change animation state"""
        self.current_state = state
        if status_text:
            self.status_label.config(text=status_text)
    
    def update(self):
        """Update the GUI (call this in your async loop)"""
        try:
            self.root.update()
        except:
            pass
    
    def close(self):
        """Close the window"""
        try:
            self.root.destroy()
        except:
            pass
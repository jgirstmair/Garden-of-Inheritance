"""
Interactive Emasculation Dialog

Provides an interactive interface for emasculating pea plants by clicking
on individual anthers that need to be removed from the flower.
"""

import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk
import math


class EmasculationDialog(tk.Toplevel):
    """
    Interactive dialog for plant emasculation.
    
    Displays a flower image with 5 anthers that must be clicked to remove them.
    Only when all 5 anthers are removed does the emasculation complete.
    """
    
    def __init__(self, parent, flower_color="purple", callback=None):
        """
        Initialize the emasculation dialog.
        
        Args:
            parent: Parent tkinter window
            flower_color: Color of the flower ("purple" or "white")
            callback: Function to call when emasculation is complete (success: bool)
        """
        super().__init__(parent)
        
        self.callback = callback
        self.flower_color = flower_color
        self.anthers_removed = 0
        self.total_anthers = 10  # Changed from 5 to 10
        self.completed = False
        
        # Select correct flower image based on color (from icons folder)
        if flower_color == "white":
            self.flower_image_path = "icons/flower_white_emasculated.png"
        else:  # default to purple
            self.flower_image_path = "icons/flower_purple_emasculated.png"
        
        # Load tweezer cursor icon
        self.tweezer_cursor_path = "icons/pollen.png"
        
        # Display scaling factor (0.5 = 50% size, 1.0 = 100% size)
        self.display_scale = 0.5  # Make everything 50% smaller
        
        # Configure window
        self.title("Emasculation...")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Create UI first (this sets self.canvas_width and self.canvas_height)
        self._create_widgets()
        
        # Center the window after widgets are created
        self.update_idletasks()
        # Calculate offset based on canvas size (which is now scaled)
        x_offset = max(250, self.canvas_width // 2 + 100)
        y_offset = max(250, self.canvas_height // 2 + 100)
        x = parent.winfo_x() + (parent.winfo_width() // 2) - x_offset
        y = parent.winfo_y() + (parent.winfo_height() // 2) - y_offset
        self.geometry(f"+{x}+{y}")
        
        # Close button handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self):
        """Create the dialog widgets."""
        # Instructions
        instruction_frame = tk.Frame(self, bg="#f0f0f0")
        instruction_frame.pack(fill="x", padx=10, pady=10)
        
        title_label = tk.Label(
            instruction_frame,
            text="Remove Anthers!",
            font=("Segoe UI", 14, "bold"),
            bg="#f0f0f0"
        )
        title_label.pack(pady=(0, 5))
        
        # Progress label
        self.progress_label = tk.Label(
            instruction_frame,
            text=f"Remaining: {self.total_anthers}",
            font=("Segoe UI", 11, "bold"),
            bg="#f0f0f0",
            fg="#d32f2f"
        )
        self.progress_label.pack(pady=(5, 0))
        
        # Canvas for flower image and anthers
        canvas_frame = tk.Frame(self)
        canvas_frame.pack(padx=20, pady=10)
        
        # Load flower image
        try:
            img = Image.open(self.flower_image_path)
            
            # Store original dimensions for coordinate scaling
            self.original_width = img.width
            self.original_height = img.height
            
            # Apply display scaling factor to make dialog smaller
            display_width = int(img.width * self.display_scale)
            display_height = int(img.height * self.display_scale)
            
            # Resize image
            img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
            print(f"Scaled from {self.original_width}x{self.original_height} to {display_width}x{display_height} (factor: {self.display_scale})")
            
            # Scale factor for coordinates
            self.scale_factor = self.display_scale
            
            self.flower_image = ImageTk.PhotoImage(img)
            self.canvas_width = display_width
            self.canvas_height = display_height
            
            print(f"Loaded flower image: {self.canvas_width}x{self.canvas_height} (scale: {self.scale_factor:.2f})")
        except Exception as e:
            print(f"Error loading flower image: {e}")
            self.flower_image = None
            self.canvas_width = int(600 * self.display_scale)
            self.canvas_height = int(600 * self.display_scale)
            self.original_width = 600
            self.original_height = 600
            self.scale_factor = self.display_scale
        
        self.canvas = Canvas(
            canvas_frame,
            width=self.canvas_width,
            height=self.canvas_height,
            bg="#000000",
            highlightthickness=0
        )
        self.canvas.pack()
        
        # Load custom tweezer cursor
        try:
            cursor_img = Image.open(self.tweezer_cursor_path)
            # Keep cursor at constant size (24x24) regardless of display scale
            cursor_size = 24
            cursor_img = cursor_img.resize((cursor_size, cursor_size), Image.Resampling.LANCZOS)
            # Create cursor string for tkinter
            # Note: Tkinter expects specific cursor format, we'll use the image as PhotoImage
            self.tweezer_cursor = ImageTk.PhotoImage(cursor_img)
            self.has_custom_cursor = True
            print(f"Loaded custom tweezer cursor at {cursor_size}x{cursor_size} (constant size)")
        except Exception as e:
            print(f"Could not load custom cursor: {e}, using hand2 instead")
            self.has_custom_cursor = False
            self.tweezer_cursor = None
        
        # Draw flower image first (at the back)
        if self.flower_image:
            self.canvas.create_image(
                self.canvas_width // 2,
                self.canvas_height // 2,
                image=self.flower_image
            )
            print(f"Drew flower image at ({self.canvas_width // 2}, {self.canvas_height // 2})")
        
        # Create cursor icon overlay (initially hidden)
        if self.has_custom_cursor:
            self.cursor_icon = self.canvas.create_image(
                -100, -100,  # Start off-screen
                image=self.tweezer_cursor,
                tags="cursor_icon"
            )
            self.canvas.tag_raise(self.cursor_icon)  # Always on top
        else:
            self.cursor_icon = None
        
        # Create anthers AFTER flower so they're on top
        self._create_anthers()
        
        # Bind click event
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        
        # Set default cursor
        self.canvas.config(cursor="crosshair")
        
        # Success message frame (pre-allocated, initially empty)
        self.success_frame = tk.Frame(self, bg="#e8f5e9", height=0)
        self.success_frame.pack(fill="x", padx=10, pady=(5, 0))
        
        self.success_label = tk.Label(
            self.success_frame,
            text="",
            font=("Segoe UI", 10),
            fg="#2e7d32",
            bg="#e8f5e9",
            pady=5
        )
        # Don't pack yet - will pack when needed
        
        # Button frame
        button_frame = tk.Frame(self)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.cancel_btn = tk.Button(
            button_frame,
            text="Cancel",
            command=self._on_cancel,
            font=("Segoe UI", 10),
            width=10
        )
        self.cancel_btn.pack(side="right", padx=5)
    
    def _create_anthers(self):
        """Create the 10 anthers using precise coordinates with slight randomization."""
        self.anthers = []
        
        # Original 5 anther coordinates from the reference image (original size)
        # Add slight jitter (±2-3 pixels) to make each flower unique
        import random
        
        base_anther_coords = [
            (437, 387),      # Anther 0
            (494.5, 395.5),  # Anther 1
            (510.5, 462.5),  # Anther 2
            (457.5, 447.5),  # Anther 3
            (420.5, 486.5),  # Anther 4
        ]
        
        # Apply slight random jitter to base positions (2-3 pixels)
        original_anther_coords = []
        for x, y in base_anther_coords:
            jitter_x = random.uniform(-3, 3)
            jitter_y = random.uniform(-3, 3)
            original_anther_coords.append((x + jitter_x, y + jitter_y))
        
        # Add 5 more anthers near the originals with random offsets
        additional_anthers = []
        for x, y in original_anther_coords:
            # Random offset: 10-25 pixels in random direction
            offset_distance = random.uniform(10, 25)
            offset_angle = random.uniform(0, 2 * math.pi)
            # Add slight jitter to the offset too
            jitter_x = random.uniform(-2, 2)
            jitter_y = random.uniform(-2, 2)
            new_x = x + offset_distance * math.cos(offset_angle) + jitter_x
            new_y = y + offset_distance * math.sin(offset_angle) + jitter_y
            additional_anthers.append((new_x, new_y))
        
        # Combine all 10 anthers
        all_anther_coords = original_anther_coords + additional_anthers
        
        # Scale coordinates if image was resized
        scaled_coords = [
            (x * self.scale_factor, y * self.scale_factor) 
            for x, y in all_anther_coords
        ]
        
        # Center point for stalks (specified coordinates)
        center_x = 334 * self.scale_factor
        center_y = 417 * self.scale_factor
        
        # Anther dimensions
        anther_width = int(32 * self.scale_factor)
        anther_height = int(24 * self.scale_factor)
        click_tolerance = int(25 * self.scale_factor)
        
        # Store scaled tolerance for click detection
        self.click_tolerance = click_tolerance
        self.total_anthers = 10  # Update total count
        
        print(f"Creating 10 anthers with center at: ({center_x:.1f}, {center_y:.1f})")
        
        # Create 10 anthers at precise locations
        for i, (x, y) in enumerate(scaled_coords):
            is_additional = i >= 5  # Anthers 5-9 are the additional ones
            print(f"Creating anther {i} at ({x:.1f}, {y:.1f}) {'(shorter)' if is_additional else ''}")
            
            # Calculate control point for curve
            dx = x - center_x
            dy = y - center_y
            
            # Additional anthers have shorter stalks (less curve distance)
            if is_additional:
                # Shorter stalk - control point closer to anther
                perp_x = -dy * 0.10  # Less curve (10% instead of 15%)
                perp_y = dx * 0.10
            else:
                # Original length
                perp_x = -dy * 0.15
                perp_y = dx * 0.15
            
            # Control point for smooth curve
            ctrl_x = (center_x + x) / 2 + perp_x
            ctrl_y = (center_y + y) / 2 + perp_y
            
            # Create curved line - thinner for additional anthers
            if is_additional:
                stalk_width = max(4, int(6 * self.scale_factor))  # Thinner
            else:
                stalk_width = max(6, int(8 * self.scale_factor))  # Original thickness
            
            stalk = self.canvas.create_line(
                center_x, center_y, 
                ctrl_x, ctrl_y,
                x, y,
                fill="#000000",  # BLACK
                width=stalk_width,
                smooth=True,
                splinesteps=20,
                capstyle="round"
            )
            
            # Create anther body (yellow oval) - with ORANGE outline
            anther = self.canvas.create_oval(
                x - anther_width // 2,
                y - anther_height // 2,
                x + anther_width // 2,
                y + anther_height // 2,
                fill="#f4d03f",  # Bright yellow
                outline="#ff8c00",  # ORANGE outline
                width=max(4, int(5 * self.scale_factor)),  # THICK orange outline
                tags=f"anther_{i}"
            )
            
            # Bring anther to front
            self.canvas.tag_raise(anther)
            
            # Add pollen dot in center
            pollen_size = max(3, int(4 * self.scale_factor))
            pollen = self.canvas.create_oval(
                x - pollen_size, y - pollen_size,
                x + pollen_size, y + pollen_size,
                fill="#ffeb3b",
                outline="",
                tags=f"anther_{i}_pollen"
            )
            self.canvas.tag_raise(pollen)
            
            # Store anther data
            self.anthers.append({
                "id": i,
                "body": anther,
                "stalk": stalk,
                "x": x,
                "y": y,
                "removed": False
            })
            
        print(f"Created {len(self.anthers)} anthers (5 original + 5 additional)")
        
        # Ensure cursor icon is always on top
        if self.has_custom_cursor and self.cursor_icon:
            self.canvas.tag_raise(self.cursor_icon)
    
    def _on_mouse_move(self, event):
        """Handle mouse movement to show hover effects."""
        if self.completed:
            return
        
        # Check if hovering over an anther
        hovering = False
        for anther in self.anthers:
            if anther["removed"]:
                continue
            
            dx = event.x - anther["x"]
            dy = event.y - anther["y"]
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < self.click_tolerance:  # Use scaled tolerance
                hovering = True
                # Highlight the anther with thicker bright orange outline
                self.canvas.itemconfig(anther["body"], outline="#ff6600", width=max(5, int(6 * self.scale_factor)))
            else:
                # Reset to normal orange outline
                outline_width = max(4, int(5 * self.scale_factor))
                self.canvas.itemconfig(anther["body"], outline="#ff8c00", width=outline_width)
        
        # Update cursor
        if hovering:
            if self.has_custom_cursor and self.cursor_icon:
                # Show custom tweezer cursor icon at mouse position
                self.canvas.coords(self.cursor_icon, event.x, event.y)
                self.canvas.itemconfig(self.cursor_icon, state='normal')
                # Hide system cursor
                self.canvas.config(cursor="none")
            else:
                # Fallback to hand cursor
                self.canvas.config(cursor="hand2")
        else:
            if self.has_custom_cursor and self.cursor_icon:
                # Hide custom cursor icon
                self.canvas.itemconfig(self.cursor_icon, state='hidden')
                # Show crosshair
                self.canvas.config(cursor="crosshair")
            else:
                self.canvas.config(cursor="crosshair")
    
    def _on_canvas_click(self, event):
        """Handle click on canvas to check if an anther was clicked."""
        if self.completed:
            return
        
        # Check each anther
        for anther in self.anthers:
            if anther["removed"]:
                continue
            
            # Check if click is within anther bounds
            dx = event.x - anther["x"]
            dy = event.y - anther["y"]
            distance = math.sqrt(dx * dx + dy * dy)
            
            if distance < self.click_tolerance:  # Use scaled tolerance
                self._remove_anther(anther)
                print(f"Clicked anther {anther['id']} at ({event.x}, {event.y})")
                break
    
    def _remove_anther(self, anther):
        """Remove an anther from the flower."""
        # Mark as removed
        anther["removed"] = True
        self.anthers_removed += 1
        
        # Animate removal with color fade
        def fade_out(step=0):
            if step == 0:
                # Flash red briefly
                self.canvas.itemconfig(anther["body"], fill="#ff4444", outline="#cc0000")
            elif step == 1:
                # Fade to gray
                self.canvas.itemconfig(anther["body"], fill="#888888", outline="#666666")
            elif step == 2:
                # Final fade
                self.canvas.itemconfig(anther["body"], fill="#444444", outline="#333333")
            elif step == 3:
                # Delete anther, stalk, and pollen
                self.canvas.delete(anther["body"])
                self.canvas.delete(anther["stalk"])
                # Delete pollen dots by tag
                self.canvas.delete(f"anther_{anther['id']}_pollen")
                return
            
            self.canvas.after(80, lambda: fade_out(step + 1))
        
        fade_out()
        
        # Update progress
        remaining = self.total_anthers - self.anthers_removed
        self.progress_label.config(text=f"Anthers remaining: {remaining}")
        
        if remaining == 0:
            self.progress_label.config(
                text="✓ All anthers removed!",
                fg="#2e7d32"
            )
            self.canvas.after(300, self._complete_emasculation)
    
    def _complete_emasculation(self):
        """Complete the emasculation procedure."""
        self.completed = True
        
        # Show success message in pre-allocated frame
        self.success_label.config(
            text="Success!"
        )
        self.success_label.pack(fill="x")
        
        # Change cancel button to close
        self.cancel_btn.config(text="Close", command=self._on_complete)
        
        # Auto-close after 2 seconds
        self.after(500, self._on_complete)
    
    def _on_complete(self):
        """Handle successful completion."""
        if self.callback:
            self.callback(True)
        self.destroy()
    
    def _on_cancel(self):
        """Handle cancellation."""
        if self.callback:
            self.callback(False)
        self.destroy()
    
    def _on_close(self):
        """Handle window close button."""
        self._on_cancel()

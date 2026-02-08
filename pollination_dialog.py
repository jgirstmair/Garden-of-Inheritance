"""
Interactive Pollination Dialog

Provides an interactive interface for pollinating pea plants by clicking
on the stigma with pollen from another plant.
"""

import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk
import math


class PollinationDialog(tk.Toplevel):
    """
    Interactive dialog for plant pollination.
    
    Displays a flower image with or without anthers (depending on emasculation status).
    Player must click on the stigma (center) to apply pollen.
    """
    
    def __init__(self, parent, flower_color="purple", is_emasculated=False, pollen_source=None, callback=None):
        """
        Initialize the pollination dialog.
        
        Args:
            parent: Parent tkinter window
            flower_color: Color of the flower ("purple" or "white")
            is_emasculated: Whether the flower has been emasculated (no anthers)
            pollen_source: Name/ID of the pollen source plant
            callback: Function to call when pollination is complete (success: bool)
        """
        super().__init__(parent)
        
        self.callback = callback
        self.flower_color = flower_color
        self.is_emasculated = is_emasculated
        self.pollen_source = pollen_source
        self.completed = False
        
        # Select correct flower image based on emasculation status
        if is_emasculated:
            # Emasculated flower (no anthers)
            if flower_color == "white":
                self.flower_image_path = "icons/flower_white_emasculated.png"
            else:
                self.flower_image_path = "icons/flower_purple_emasculated.png"
        else:
            # Intact flower (with anthers) - we'll add anthers visually
            if flower_color == "white":
                self.flower_image_path = "icons/flower_white_emasculated.png"
            else:
                self.flower_image_path = "icons/flower_purple_emasculated.png"
        
        # Load anther cursor icon (pollen applicator)
        self.anther_cursor_path = "icons/anther.png"
        
        # Display scaling factor (0.5 = 50% size)
        self.display_scale = 0.5
        
        # Stigma location (original coordinates)
        self.stigma_x = 479
        self.stigma_y = 329
        
        # Configure window
        self.title("Pollination...")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Create UI
        self._create_widgets()
        
        # Center the window
        self.update_idletasks()
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
            text="Apply Pollen!",
            font=("Segoe UI", 14, "bold"),
            bg="#f0f0f0"
        )
        title_label.pack(pady=(0, 5))
        
        # Pollen source info
        if self.pollen_source:
            source_label = tk.Label(
                instruction_frame,
                text=f"Pollen from: {self.pollen_source}",
                font=("Segoe UI", 10),
                bg="#f0f0f0",
                fg="#666666"
            )
            source_label.pack()
        
        # Status label
        self.status_label = tk.Label(
            instruction_frame,
            text="Click the stigma to pollinate",
            font=("Segoe UI", 11),
            bg="#f0f0f0",
            fg="#1976d2"
        )
        self.status_label.pack(pady=(5, 0))
        
        # Canvas for flower image
        canvas_frame = tk.Frame(self)
        canvas_frame.pack(padx=20, pady=10)
        
        # Load flower image
        try:
            img = Image.open(self.flower_image_path)
            
            # Store original dimensions
            self.original_width = img.width
            self.original_height = img.height
            
            # Apply display scaling
            display_width = int(img.width * self.display_scale)
            display_height = int(img.height * self.display_scale)
            
            # Resize image
            img = img.resize((display_width, display_height), Image.Resampling.LANCZOS)
            
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
        
        # Load custom anther cursor
        try:
            cursor_img = Image.open(self.anther_cursor_path)
            # Scale to 0.5: 280x70 -> 140x35
            cursor_width = 140
            cursor_height = 35
            cursor_img = cursor_img.resize((cursor_width, cursor_height), Image.Resampling.LANCZOS)
            self.anther_cursor = ImageTk.PhotoImage(cursor_img)
            self.has_custom_cursor = True
            print(f"Loaded custom anther cursor at {cursor_width}x{cursor_height}")
        except Exception as e:
            print(f"Could not load custom cursor: {e}, using hand2 instead")
            self.has_custom_cursor = False
            self.anther_cursor = None
        
        # Draw flower image
        if self.flower_image:
            self.canvas.create_image(
                self.canvas_width // 2,
                self.canvas_height // 2,
                image=self.flower_image
            )
        
        # Create cursor icon overlay (initially hidden)
        if self.has_custom_cursor:
            self.cursor_icon = self.canvas.create_image(
                -100, -100,
                image=self.anther_cursor,
                tags="cursor_icon"
            )
            self.canvas.tag_raise(self.cursor_icon)
        else:
            self.cursor_icon = None
        
        # If flower is NOT emasculated, draw anthers (non-interactive)
        if not self.is_emasculated:
            self._create_anthers()
        
        # Create invisible stigma clickable area
        self._create_stigma_target()
        
        # Bind events
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<Motion>", self._on_mouse_move)
        
        # Set default cursor
        self.canvas.config(cursor="crosshair")
        
        # Success message frame
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
        """Create non-interactive anthers (visual only) for non-emasculated flowers."""
        import random
        
        # Original 5 anther coordinates with jitter
        base_anther_coords = [
            (437, 387),
            (494.5, 395.5),
            (510.5, 462.5),
            (457.5, 447.5),
            (420.5, 486.5),
        ]
        
        # Apply slight random jitter
        original_anther_coords = []
        for x, y in base_anther_coords:
            jitter_x = random.uniform(-3, 3)
            jitter_y = random.uniform(-3, 3)
            original_anther_coords.append((x + jitter_x, y + jitter_y))
        
        # Add 5 more anthers
        additional_anthers = []
        for x, y in original_anther_coords:
            offset_distance = random.uniform(10, 25)
            offset_angle = random.uniform(0, 2 * math.pi)
            jitter_x = random.uniform(-2, 2)
            jitter_y = random.uniform(-2, 2)
            new_x = x + offset_distance * math.cos(offset_angle) + jitter_x
            new_y = y + offset_distance * math.sin(offset_angle) + jitter_y
            additional_anthers.append((new_x, new_y))
        
        # Combine all anthers
        all_anther_coords = original_anther_coords + additional_anthers
        
        # Scale coordinates
        scaled_coords = [
            (x * self.scale_factor, y * self.scale_factor) 
            for x, y in all_anther_coords
        ]
        
        # Center point for stalks
        center_x = 334 * self.scale_factor
        center_y = 417 * self.scale_factor
        
        # Anther dimensions
        anther_width = int(32 * self.scale_factor)
        anther_height = int(24 * self.scale_factor)
        
        print(f"Creating 10 visual anthers (non-interactive)")
        
        # Create 10 anthers (visual only)
        for i, (x, y) in enumerate(scaled_coords):
            is_additional = i >= 5
            
            # Calculate control point for curve
            dx = x - center_x
            dy = y - center_y
            
            if is_additional:
                perp_x = -dy * 0.10
                perp_y = dx * 0.10
            else:
                perp_x = -dy * 0.15
                perp_y = dx * 0.15
            
            ctrl_x = (center_x + x) / 2 + perp_x
            ctrl_y = (center_y + y) / 2 + perp_y
            
            # Create curved stalk
            if is_additional:
                stalk_width = max(4, int(6 * self.scale_factor))
            else:
                stalk_width = max(6, int(8 * self.scale_factor))
            
            self.canvas.create_line(
                center_x, center_y, 
                ctrl_x, ctrl_y,
                x, y,
                fill="#000000",
                width=stalk_width,
                smooth=True,
                splinesteps=20,
                capstyle="round",
                tags="anther_visual"
            )
            
            # Create anther body
            self.canvas.create_oval(
                x - anther_width // 2,
                y - anther_height // 2,
                x + anther_width // 2,
                y + anther_height // 2,
                fill="#f4d03f",
                outline="#ff8c00",
                width=max(4, int(5 * self.scale_factor)),
                tags="anther_visual"
            )
            
            # Add pollen dot
            pollen_size = max(3, int(4 * self.scale_factor))
            self.canvas.create_oval(
                x - pollen_size, y - pollen_size,
                x + pollen_size, y + pollen_size,
                fill="#ffeb3b",
                outline="",
                tags="anther_visual"
            )
    
    def _create_stigma_target(self):
        """Create the invisible clickable stigma target area."""
        # Scale stigma coordinates
        stigma_x = self.stigma_x * self.scale_factor
        stigma_y = self.stigma_y * self.scale_factor
        
        # Click tolerance (larger than visual indicator)
        self.click_tolerance = int(30 * self.scale_factor)
        
        # Visual indicator (small circle) - starts invisible
        indicator_radius = int(15 * self.scale_factor)
        
        # Create visual indicator (will appear on hover)
        # Start with state='hidden' to make it invisible
        self.stigma_indicator = self.canvas.create_oval(
            stigma_x - indicator_radius,
            stigma_y - indicator_radius,
            stigma_x + indicator_radius,
            stigma_y + indicator_radius,
            fill="",  # No fill
            outline="#4caf50",  # Green outline (when visible)
            width=max(2, int(3 * self.scale_factor)),
            dash=(5, 3),  # Dashed line
            state='hidden',  # Start invisible
            tags="stigma_indicator"
        )
        
        # Store stigma position
        self.stigma_scaled_x = stigma_x
        self.stigma_scaled_y = stigma_y
        
        print(f"Created stigma target at ({stigma_x:.1f}, {stigma_y:.1f}) - invisible until hover")
    
    def _on_mouse_move(self, event):
        """Handle mouse movement to show hover effects."""
        if self.completed:
            return
        
        # Check if hovering over stigma
        dx = event.x - self.stigma_scaled_x
        dy = event.y - self.stigma_scaled_y
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance < self.click_tolerance:
            # Hovering over stigma - keep indicator hidden but show custom cursor
            # Stigma indicator remains hidden at all times
            
            # Show custom cursor
            if self.has_custom_cursor and self.cursor_icon:
                self.canvas.coords(self.cursor_icon, event.x, event.y)
                self.canvas.itemconfig(self.cursor_icon, state='normal')
                self.canvas.config(cursor="none")
            else:
                self.canvas.config(cursor="hand2")
        else:
            # Not hovering - stigma indicator stays hidden
            
            if self.has_custom_cursor and self.cursor_icon:
                self.canvas.itemconfig(self.cursor_icon, state='hidden')
                self.canvas.config(cursor="crosshair")
            else:
                self.canvas.config(cursor="crosshair")
    
    def _on_canvas_click(self, event):
        """Handle click on canvas to check if stigma was clicked."""
        if self.completed:
            return
        
        # Check if click is within stigma bounds
        dx = event.x - self.stigma_scaled_x
        dy = event.y - self.stigma_scaled_y
        distance = math.sqrt(dx * dx + dy * dy)
        
        if distance < self.click_tolerance:
            self._apply_pollen()
            print(f"Stigma clicked at ({event.x}, {event.y})")
    
    def _apply_pollen(self):
        """Apply pollen to the stigma."""
        # Stigma indicator remains hidden - no visual feedback on the indicator itself
        # Visual feedback comes from status message only
        
        # Update status
        self.status_label.config(
            text="✓ Pollination successful!",
            fg="#2e7d32"
        )
        
        # Complete after brief delay
        self.canvas.after(500, self._complete_pollination)
    
    def _complete_pollination(self):
        """Complete the pollination procedure."""
        self.completed = True
        
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

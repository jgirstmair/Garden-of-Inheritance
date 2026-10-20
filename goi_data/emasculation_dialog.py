"""
Interactive Emasculation Dialog

Provides an interactive interface for emasculating pea plants by clicking
on individual anthers that need to be removed from the flower.
"""

import tkinter as tk
from tkinter import Canvas
from PIL import Image, ImageTk
import math
import os

# the forceps cursor in the emasculation dialog (was 24 px)
FORCEPS_PX = 128
# The forceps' tip (found in each picture: its visible point furthest
# towards the bottom left) sits exactly on the mouse point; this extra
# offset can fine-tune it: DX moves the forceps that many pixels to the
# left, DY that many pixels down.
FORCEPS_TIP_DX, FORCEPS_TIP_DY = 2, 0
# while the mouse button is held down the forceps are shown closed
FORCEPS_CLOSED_ICON = "icons/forceps_closed_128x128.png"

# Same look as the plant inspection window: cream background, dark brown
# text, Segoe UI, flat buttons (Labels, so the colours also show on a Mac).
BG = "#f5f0e6"
INK = "#3b2a1a"
MUTED = "#6b5a44"
OK_GREEN = "#2e7d32"
CRIMSON = "#B0102C"
BTN_BG = "#e0dccf"
BTN_HOVER = "#d0c8b7"


class _FlatButton(tk.Label):
    """A flat button like the inspector's (configure(command=...) works)."""

    def __init__(self, parent, text="", command=None, **kw):
        kw.setdefault("font", ("Segoe UI", 14, "bold"))
        kw.setdefault("bg", BTN_BG)
        kw.setdefault("fg", "#333333")
        kw.setdefault("padx", 14)
        kw.setdefault("pady", 4)
        kw.setdefault("cursor", "hand2")
        super().__init__(parent, text=text, **kw)
        self._command = command
        self.bind("<Enter>", lambda e: tk.Label.configure(self, bg=BTN_HOVER))
        self.bind("<Leave>", lambda e: tk.Label.configure(self, bg=BTN_BG))
        self.bind("<ButtonRelease-1>", self._click)

    def _click(self, _e=None):
        if callable(self._command):
            self._command()

    def configure(self, cnf=None, **kw):
        if "command" in kw:
            self._command = kw.pop("command")
        return tk.Label.configure(self, cnf, **kw)

    config = configure


class EmasculationDialog(tk.Toplevel):
    """
    Interactive dialog for plant emasculation.
    
    Displays a flower image with 5 anthers that must be clicked to remove them.
    Only when all 5 anthers are removed does the emasculation complete.
    """
    
    def __init__(self, parent, flower_color="purple", callback=None, starting_removed=0,
                 title=None, heading=None, cancel_text=None):
        """
        Initialize the emasculation dialog.
        
        Args:
            parent: Parent tkinter window
            flower_color: Color of the flower ("purple" or "white")
            callback: Function to call when the dialog closes:
                      callback(success: bool, anthers_removed: int).
                      success=True only when all anthers were removed;
                      anthers_removed is passed either way so a cancelled
                      attempt can be resumed later instead of losing
                      progress.
            starting_removed: How many anthers were already removed in a
                previous (cancelled) attempt on this same plant — those
                many anthers are created already-removed instead of the
                player having to redo them.
        """
        super().__init__(parent)
        self.configure(bg=BG)
        
        # Also used to collect pollen (take one or more anthers): then the
        # window has its own title/heading and "Done" instead of "Cancel".
        self._title_text = title or "Emasculation..."
        self._heading_text = heading or "Remove Anthers!"
        self._cancel_text = cancel_text or ("Done" if title else "Cancel")
        self.callback = callback
        self.flower_color = flower_color
        self.starting_removed = max(0, min(10, int(starting_removed or 0)))
        self.anthers_removed = self.starting_removed
        self.total_anthers = 10  # Changed from 5 to 10
        self.completed = False
        
        # Select correct flower image based on color (from icons folder)
        if flower_color == "white":
            self.flower_image_path = "icons/flower_white_emasculated.png"
        else:  # default to purple
            self.flower_image_path = "icons/flower_purple_emasculated.png"
        
        # Load tweezer cursor icon
        # the large forceps picture (the small pollen.png if it is missing)
        self.tweezer_cursor_path = ("icons/forceps_128x128.png"
                                    if os.path.exists("icons/forceps_128x128.png")
                                    else "icons/pollen.png")
        
        # Display scaling factor (0.5 = 50% size, 1.0 = 100% size)
        self.display_scale = 0.5  # Make everything 50% smaller
        
        # Configure window
        self.withdraw()   # hidden until fully built and positioned — see below
        self.title(self._title_text)
        self.transient(parent)
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

        # Only now become visible — avoids a flash at Tk's default
        # (top-left-ish) position before this repositioning takes effect.
        self.deiconify()
        self.lift()
        self.focus_force()
        self.grab_set()
        
        # Close button handler
        self.protocol("WM_DELETE_WINDOW", self._on_close)
    
    def _create_widgets(self):
        """Create the dialog widgets."""
        # Instructions
        instruction_frame = tk.Frame(self, bg=BG)
        instruction_frame.pack(fill="x", padx=10, pady=10)
        
        title_label = tk.Label(
            instruction_frame,
            text=self._heading_text,
            font=("Segoe UI", 16, "bold"),
            bg=BG, fg=INK
        )
        title_label.pack(pady=(0, 5))
        
        # Progress label
        self.progress_label = tk.Label(
            instruction_frame,
            text=f"Remaining: {self.total_anthers - self.starting_removed}",
            font=("Segoe UI", 14, "bold"),
            bg=BG,
            fg=CRIMSON
        )
        self.progress_label.pack(pady=(5, 0))
        
        # Canvas for flower image and anthers
        canvas_frame = tk.Frame(self, bg=BG)
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
        
        # Load custom tweezer cursor (the brush dialog has its own, see
        # BrushDialog._load_cursor)
        self._load_cursor()
        
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
        # the forceps close while the mouse button is held down
        self.canvas.bind("<ButtonPress-1>", lambda e: (setattr(self, "_last_ptr", (e.x, e.y)),
                                                       self._forceps_grip(True)), add="+")
        self.canvas.bind("<ButtonRelease-1>", lambda e: self._forceps_release(), add="+")
        
        # Set default cursor
        self.canvas.config(cursor="crosshair")
        
        # Success message frame (pre-allocated, initially empty)
        self.success_frame = tk.Frame(self, bg=BG, height=0)
        self.success_frame.pack(fill="x", padx=10, pady=(5, 0))
        
        self.success_label = tk.Label(
            self.success_frame,
            text="",
            font=("Segoe UI", 14, "bold"),
            fg=OK_GREEN,
            bg=BG,
            pady=5
        )
        # Don't pack yet - will pack when needed
        
        # Button frame
        button_frame = tk.Frame(self, bg=BG)
        button_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.cancel_btn = _FlatButton(
            button_frame,
            text=self._cancel_text,
            command=self._on_cancel,
        )
        self.cancel_btn.pack(side="right", padx=5)
    
    def _load_cursor(self):
        try:
            cursor_img = Image.open(self.tweezer_cursor_path).convert("RGBA")
            # Constant size regardless of display scale (FORCEPS_PX)
            cursor_size = FORCEPS_PX
            cursor_img = cursor_img.resize((cursor_size, cursor_size), Image.Resampling.LANCZOS)
            self.tweezer_cursor = ImageTk.PhotoImage(cursor_img)
            self.tweezer_open = self.tweezer_cursor
            self._tip_open = brush_tip(cursor_img)
            self._tip = self._tip_open
            self.tweezer_closed = None
            self._tip_closed = self._tip_open
            if os.path.exists(FORCEPS_CLOSED_ICON):
                closed = Image.open(FORCEPS_CLOSED_ICON).convert("RGBA").resize(
                    (cursor_size, cursor_size), Image.Resampling.LANCZOS)
                self.tweezer_closed = ImageTk.PhotoImage(closed)
                self._tip_closed = brush_tip(closed)
            self.has_custom_cursor = True
        except Exception as e:
            print(f"Could not load custom cursor: {e}, using hand2 instead")
            self.has_custom_cursor = False
            self.tweezer_cursor = None

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

            # If this anther was already removed in a previous (cancelled)
            # attempt on this plant, show it gone immediately instead of
            # making the player redo it.
            if i < self.starting_removed:
                self.anthers[-1]["removed"] = True
                self.canvas.delete(anther)
                self.canvas.delete(stalk)
                self.canvas.delete(f"anther_{i}_pollen")
            
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
        
        # Update cursor (the closed forceps stay in view while they are
        # closed — no crosshair in between)
        if hovering or getattr(self, "_forceps_closed", False):
            if self.has_custom_cursor and self.cursor_icon:
                # Show custom tweezer cursor icon at mouse position
                # bottom-left corner (the tips) on the mouse point
                if not getattr(self, "_brush_tip", None):
                    self._last_ptr = (event.x, event.y)
                    self._place_forceps()
                else:
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
    
    def _place_forceps(self):
        """The forceps' tip exactly on the mouse point (open or closed
        picture: each has its own tip position)."""
        ptr = getattr(self, "_last_ptr", None)
        if ptr is None or not getattr(self, "cursor_icon", None):
            return
        tx, ty = getattr(self, "_tip", (0, FORCEPS_PX - 1))
        self.canvas.itemconfig(self.cursor_icon, anchor="nw")
        self.canvas.coords(self.cursor_icon, ptr[0] - tx - FORCEPS_TIP_DX,
                           ptr[1] - ty + FORCEPS_TIP_DY)

    FORCEPS_CLOSED_MIN_MS = 300     # the forceps stay closed at least this long

    def _forceps_release(self):
        """Mouse button up: the forceps open again — but only once they
        have been closed for at least FORCEPS_CLOSED_MIN_MS."""
        import time as _t
        held = (_t.monotonic() - getattr(self, "_grip_t", 0.0)) * 1000.0
        wait = max(0, int(self.FORCEPS_CLOSED_MIN_MS - held))
        job = getattr(self, "_grip_job", None)
        if job is not None:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        if wait <= 0:
            self._grip_job = None
            self._forceps_grip(False)
        else:
            self._grip_job = self.after(wait, lambda: (setattr(self, "_grip_job", None),
                                                       self._forceps_grip(False)))

    def _forceps_grip(self, closed):
        """Closed forceps while the button is pressed, open again after."""
        if closed:
            import time as _t
            self._grip_t = _t.monotonic()
            job = getattr(self, "_grip_job", None)
            if job is not None:              # pressed again before it opened
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
                self._grip_job = None
        img = (getattr(self, "tweezer_closed", None) if closed
               else getattr(self, "tweezer_open", None))
        if img is None or not getattr(self, "cursor_icon", None):
            return
        try:
            self._forceps_closed = bool(closed)
            self._tip = (getattr(self, "_tip_closed", None) if closed
                         else getattr(self, "_tip_open", None)) or (0, FORCEPS_PX - 1)
            self.canvas.itemconfig(self.cursor_icon, image=img)
            self._place_forceps()
            if closed:
                self.canvas.itemconfig(self.cursor_icon, state="normal")
                self.canvas.config(cursor="none")
            else:
                # open again: show what the mouse is over now (forceps over
                # an anther, otherwise the crosshair)
                ptr = getattr(self, "_last_ptr", None)
                if ptr is not None:
                    self._on_mouse_move(type("E", (), {"x": ptr[0], "y": ptr[1]})())
        except Exception:
            pass

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
            self.callback(True, self.anthers_removed)
        self.destroy()
    
    def _on_cancel(self):
        """Handle cancellation — reports how many anthers were removed so
        far, so the next attempt on this plant can resume instead of
        starting over."""
        if self.callback:
            self.callback(False, self.anthers_removed)
        self.destroy()
    
    def _on_close(self):
        """Handle window close button."""
        self._on_cancel()


# ============================================================================
# Collecting pollen with a camel-hair brush (no anthers are removed)
# ============================================================================
# the camel-hair brush (high-quality picture; the older small one if missing)
BRUSH_ICONS = ("icons/brush_128x128.png", "icons/pollinate_64.png")
BRUSH_ICON = BRUSH_ICONS[0]
BRUSH_TOUCHES = 5
HOVER_TOUCH_FRAC = 0.7       # the brush tip this close to an anther touches it               # different anthers to touch for one brush
BRUSH_PX = 256                  # brush cursor size on the flower
POLLEN_YELLOW = (236, 196, 38)


def _fallback_brush(px=64):
    """A simple drawn brush (if pollinate_64.png is missing): wooden handle
    from the top right, bristles ending in a tip at the bottom left."""
    from PIL import ImageDraw
    im = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    k = px / 64.0
    d.line([(60 * k, 4 * k), (26 * k, 38 * k)], fill=(140, 92, 48, 255), width=int(7 * k))
    d.polygon([(30 * k, 30 * k), (36 * k, 36 * k), (24 * k, 46 * k), (18 * k, 40 * k)],
              fill=(170, 170, 170, 255), outline=(60, 60, 60, 255))
    d.polygon([(18 * k, 40 * k), (24 * k, 46 * k), (6 * k, 60 * k), (3 * k, 58 * k)],
              fill=(120, 84, 52, 255), outline=(50, 34, 20, 255))
    return im


def brush_image(px=64, yellow=0.0):
    """The brush picture (pollinate_64.png) at px pixels, its tip tinted
    pollen-yellow by `yellow` (0..1). Returns (PIL image, tip (x, y))."""
    im = None
    for path in BRUSH_ICONS:                 # looked up now, not at import
        try:
            im = Image.open(path).convert("RGBA")
            break
        except Exception:
            continue
    if im is None:
        im = _fallback_brush()
    im = im.resize((px, px), Image.Resampling.LANCZOS)
    tip = brush_tip(im)
    if yellow > 0:
        im = im.copy()
        pix = im.load()
        r = px * 0.22                 # the bristles (bottom-left part of the picture)
        tx, ty = tip
        for y in range(px):
            for x in range(px):
                cr, cg, cb, ca = pix[x, y]
                if ca < 20:
                    continue
                dd = math.hypot(x - tx, y - ty)
                if dd > r:
                    continue
                t = yellow * (1.0 - dd / r) ** 0.6
                pix[x, y] = (int(cr + (POLLEN_YELLOW[0] - cr) * t),
                             int(cg + (POLLEN_YELLOW[1] - cg) * t),
                             int(cb + (POLLEN_YELLOW[2] - cb) * t), ca)
    return im, tip


def brush_tip(im):
    """The brush's tip: the visible pixel furthest towards the bottom
    left (brushes are drawn diagonally, bristles at the bottom left)."""
    a = im.getchannel("A")
    w, h = im.size
    best, tip = None, (0, h - 1)
    px = a.load()
    for y in range(h):
        for x in range(w):
            if px[x, y] > 60:
                v = x - y
                if best is None or v < best:
                    best, tip = v, (x, y)
    return tip


class BrushDialog(EmasculationDialog):
    """Collect pollen: touch the tips of five different anthers of this
    flower with a camel-hair brush. Nothing is removed — the anthers stay
    on the flower; the brush tip turns more yellow with every anther.
    callback(success, anthers_touched)."""

    def __init__(self, parent, flower_color="purple", callback=None):
        self.touched = set()
        super().__init__(parent, flower_color, callback, starting_removed=0,
                         title="Collect pollen",
                         heading="Brush over the tips of five anthers",
                         cancel_text="Cancel")
        self.progress_label.config(text=f"Anthers touched: 0 / {BRUSH_TOUCHES}", fg=MUTED)

    # -- the brush as the mouse cursor ------------------------------------
    def _load_cursor(self):
        try:
            self._brush_level = 0.0
            self._set_brush(0.0)
            self.has_custom_cursor = True
        except Exception as e:
            print(f"Could not load the brush: {e}")
            self.has_custom_cursor = False
            self.tweezer_cursor = None

    def _set_brush(self, yellow):
        im, tip = brush_image(BRUSH_PX, yellow)
        self._brush_tip = tip
        self.tweezer_cursor = ImageTk.PhotoImage(im)
        if getattr(self, "cursor_icon", None):
            try:
                self.canvas.itemconfig(self.cursor_icon, image=self.tweezer_cursor, anchor="nw")
            except Exception:
                pass

    def _on_mouse_move(self, event):
        if not (self.has_custom_cursor and self.cursor_icon):
            return
        tx, ty = getattr(self, "_brush_tip", (0, BRUSH_PX))
        # the brush follows the mouse with its tip exactly on the pointer
        self.canvas.itemconfig(self.cursor_icon, anchor="nw", state="normal")
        self.canvas.coords(self.cursor_icon, event.x - tx, event.y - ty)
        self.canvas.tag_raise(self.cursor_icon)
        self.canvas.config(cursor="none")
        if self.completed:
            return
        # moving the brush tip over an anther is enough (no click needed)
        hit = None
        for anther in self.anthers:
            d = math.hypot(event.x - anther["x"], event.y - anther["y"])
            near = d < self.click_tolerance and anther["id"] not in self.touched
            if hit is None and near and d < self.click_tolerance * HOVER_TOUCH_FRAC:
                hit = anther
            self.canvas.itemconfig(anther["body"], outline="#ff6600" if near else "#ff8c00",
                                   width=max(5, int(6 * self.scale_factor)) if near
                                   else max(4, int(5 * self.scale_factor)))
        if hit is not None:
            self._touch_anther(hit)

    # -- touching an anther -------------------------------------------------
    def _on_canvas_click(self, event):
        if self.completed:
            return
        for anther in self.anthers:
            if anther["id"] in self.touched:
                continue
            if math.hypot(event.x - anther["x"], event.y - anther["y"]) < self.click_tolerance:
                self._touch_anther(anther)
                break

    def _touch_anther(self, anther):
        self.touched.add(anther["id"])
        # a little pollen came off: the anther's yellow dot pales
        try:
            self.canvas.itemconfig(f"anther_{anther['id']}_pollen", fill="#fff4c2")
        except Exception:
            pass
        n = len(self.touched)
        self._set_brush(min(1.0, n / float(BRUSH_TOUCHES)))
        if n < BRUSH_TOUCHES:
            self.progress_label.config(text=f"Anthers touched: {n} / {BRUSH_TOUCHES}", fg=MUTED)
            return
        self.completed = True
        self.progress_label.config(text=f"Anthers touched: {n} / {BRUSH_TOUCHES}", fg=OK_GREEN)
        self.success_label.config(text="Camel-hair brush prepared for pollination.")
        self.success_label.pack(fill="x")
        self.cancel_btn.config(text="Close", command=self._on_complete)
        self.after(1400, self._on_complete)

    def _on_complete(self):
        if self.callback:
            self.callback(True, len(self.touched))
        self.destroy()

    def _on_cancel(self):
        if self.callback:
            self.callback(False, len(self.touched))
        self.destroy()


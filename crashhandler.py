"""
Crash Handler Module

Provides graceful error handling for the Pea Garden application.
Captures unhandled exceptions and displays them to users via dialog boxes.

Usage:
    handler = CrashHandler()
    handler.install()
"""

import sys
import logging
import traceback
import threading


class CrashHandler:
    """Handles fatal errors in both main and background threads."""
    
    def __init__(self, logger_name="FatalError"):
        """
        Initialize the crash handler.
        
        Args:
            logger_name: Name for the logging instance
        """
        self.logger = logging.getLogger(logger_name)
        self.original_excepthook = sys.excepthook

    def install(self):
        """Register the crash handler for main thread and background threads."""
        sys.excepthook = self.handle_exception
        if hasattr(threading, "excepthook"):
            threading.excepthook = self.handle_thread_exception

    def format_exception(self, exc_type, exc_value, exc_traceback):
        """
        Format exception information into a readable string.
        
        Args:
            exc_type: Exception type
            exc_value: Exception instance
            exc_traceback: Exception traceback
            
        Returns:
            Formatted exception string
        """
        try:
            return "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        except Exception:
            return f"{getattr(exc_type, '__name__', 'Exception')}: {exc_value}"

    def show_dialog(self, message):
        """
        Display error message to user via GUI dialog.
        
        Attempts multiple methods:
        1. Tkinter messagebox (preferred)
        2. Windows API messagebox
        3. stderr output (fallback)
        
        Args:
            message: Error message to display
        """
        # Try Tkinter first
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Pea Garden crashed", message)
            root.destroy()
            return
        except Exception:
            pass

        # Fallback to Windows API
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, message, "Pea Garden crashed", 0x10)
            return
        except Exception:
            pass
        
        # Final fallback: print to stderr
        print(f"CRITICAL CRASH: {message}", file=sys.stderr)

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        """
        Main exception hook called by Python on unhandled exceptions.
        
        Args:
            exc_type: Exception type
            exc_value: Exception instance
            exc_traceback: Exception traceback
        """
        # Log the exception
        try:
            self.logger.exception("Fatal error", exc_info=(exc_type, exc_value, exc_traceback))
        except Exception:
            pass

        # Show user-friendly error dialog
        error_msg = self.format_exception(exc_type, exc_value, exc_traceback)
        self.show_dialog(error_msg)

        # Run the original exception hook (prints to console)
        return self.original_excepthook(exc_type, exc_value, exc_traceback)

    def handle_thread_exception(self, args):
        """
        Exception hook for background threads.
        
        Args:
            args: Thread exception arguments with exc_type, exc_value, exc_traceback
        """
        self.handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

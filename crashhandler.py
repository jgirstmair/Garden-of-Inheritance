import sys
import logging
import traceback
import threading

# To use it:
# handler = CrashHandler()
# handler.install()
class CrashHandler:
    def __init__(self, logger_name="FatalError"):
        self.logger = logging.getLogger(logger_name)
        self.original_excepthook = sys.excepthook

    def install(self):
        """Register the crash handler for main thread and background threads."""
        sys.excepthook = self.handle_exception
        if hasattr(threading, "excepthook"):
            threading.excepthook = self.handle_thread_exception

    def format_exception(self, t, e, tb):
        try:
            return "".join(traceback.format_exception(t, e, tb))
        except Exception:
            return f"{getattr(t, '__name__', 'Exception')}: {e}"

    def show_dialog(self, msg):
        # Try Tkinter first
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Pea Garden crashed", msg)
            root.destroy()
            return
        except Exception:
            pass

        # Fallback to Windows API
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(0, msg, "Pea Garden crashed", 0x10)
        except Exception:
            # If all else fails, just print to stderr
            print(f"CRITICAL CRASH: {msg}", file=sys.stderr)

    def handle_exception(self, t, e, tb):
        """The main hook called by Python on crash."""
        # 1. Log it
        try:
            self.logger.exception("Fatal error", exc_info=(t, e, tb))
        except Exception:
            pass

        # 2. Show it to the user
        error_msg = self.format_exception(t, e, tb)
        self.show_dialog(error_msg)

        # 3. Run the original hook (prints to console)
        return self.original_excepthook(t, e, tb)

    def handle_thread_exception(self, args):
        """The hook for background threads."""
        self.handle_exception(args.exc_type, args.exc_value, args.exc_traceback)
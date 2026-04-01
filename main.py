import ctypes
import sys
from ui.app import run_app


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def show_error(message, title="Error"):
    ctypes.windll.user32.MessageBoxW(
        0,
        message,
        title,
        0x10  # MB_ICONERROR
    )


if __name__ == "__main__":
    """if is_admin():
        show_error(
            "This application cannot be run as Administrator.\n\n"
            "Please restart it normally."
        )
        sys.exit(1)"""

    run_app()

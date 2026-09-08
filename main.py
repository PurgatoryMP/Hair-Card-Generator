from __future__ import annotations

import logging
import sys
from PySide6.QtWidgets import QApplication
from app.theme import DARK_THEME_QSS
from app.window import HairCardEditor
LOGGER=logging.getLogger("hair_card_generator")

def _configure_logging() -> None:
    """Configure application logging."""
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")

def _install_exception_hook() -> None:
    """Install a last-resort hook for uncaught application exceptions."""
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        LOGGER.critical("Unhandled exception", exc_info=(exc_type, exc_value, exc_traceback))
    sys.excepthook = handle_exception

def main() -> None:
    """Create and run the application."""
    _configure_logging()
    _install_exception_hook()
    app = QApplication(sys.argv)
    app.setApplicationName("Hair Card Generator")
    app.setStyleSheet(DARK_THEME_QSS)
    window = HairCardEditor()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

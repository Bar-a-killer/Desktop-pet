import sys
from PyQt6.QtWidgets import QApplication
from screen_manager import ScreenManager


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    manager = ScreenManager()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

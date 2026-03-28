import sys
from PyQt6.QtWidgets import QApplication
from pet import Pet


def main():
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    pet = Pet()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

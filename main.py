import sys
from PyQt6.QtWidgets import QApplication
from pet import Pet
import os
import platform
def main():
    if platform.system() == "Windows":
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    pet = Pet()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

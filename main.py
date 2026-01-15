import sys
from PyQt6.QtWidgets import QApplication
from app.controllers.main_controller import MainController


def main():
    app = QApplication(sys.argv)

    # Iniciar controlador principal
    controller = MainController()
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()

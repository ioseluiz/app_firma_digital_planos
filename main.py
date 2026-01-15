import sys
import traceback
from PyQt6.QtWidgets import QApplication, QMessageBox

def main():
    app = QApplication(sys.argv)
    
    try:
        # Importamos aquí para atrapar errores de dependencias
        from app.controllers.main_controller import MainController
        
        controller = MainController()
        controller.start()
        
        sys.exit(app.exec())
        
    except Exception as e:
        # En modo sin consola, usamos QMessageBox para mostrar el error fatal
        error_msg = str(e)
        trace_info = traceback.format_exc()
        
        # Mostramos la ventana de error
        QMessageBox.critical(None, "Error Crítico", 
                             f"Ocurrió un error inesperado y el programa debe cerrarse:\n\n{error_msg}\n\n{trace_info}")
        sys.exit(1)

if __name__ == "__main__":
    main()
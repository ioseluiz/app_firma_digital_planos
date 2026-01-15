# app/utils/paths.py
import os
import sys
import platform

def get_app_data_path():
    """
    Retorna la ruta segura del sistema para datos de usuario.
    Windows: C:/Users/TuUsuario/AppData/Roaming/DigitalSealer
    """
    app_name = "DigitalSealer"
    
    if platform.system() == "Windows":
        # Intentamos obtener la variable de entorno
        base_path = os.getenv('APPDATA')
        # Si falla, construimos la ruta manualmente usando el usuario actual
        if not base_path:
            base_path = os.path.expanduser("~\\AppData\\Roaming")
    else:
        # Mac / Linux
        base_path = os.path.expanduser("~/Library/Application Support") if platform.system() == "Darwin" else os.path.expanduser("~/.local/share")

    full_path = os.path.join(base_path, app_name)
    
    # Asegurar que la carpeta exista
    try:
        if not os.path.exists(full_path):
            os.makedirs(full_path)
    except Exception as e:
        # Si no podemos crear carpeta en AppData, usamos la carpeta local del exe (Fallback)
        print(f"Advertencia: No se pudo escribir en AppData ({e}). Usando carpeta local.")
        full_path = os.path.join(os.getcwd(), "DigitalSealer_Data")
        if not os.path.exists(full_path):
            os.makedirs(full_path)
        
    return full_path

def get_resource_path(relative_path):
    """
    Para obtener recursos estáticos (iconos, imágenes fijas) dentro del EXE.
    """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
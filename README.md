# 🏗️ DigitalSealer - Aplicación de Firma Digital de Planos

**DigitalSealer** es una aplicación de escritorio desarrollada en Python y PyQt6 diseñada para ingenieros estructurales y arquitectos. Permite estampar firmas digitales y sellos de manera masiva en planos de construcción (PDF), manteniendo la integridad vectorial de los documentos originales generados por software CAD/BIM.

## 🚀 Características Principales

* **Gestión de Roles:** Sistema de autenticación con roles de `Administrador` e `Ingeniero`.
* **Seguridad:** Contraseñas encriptadas con `bcrypt`.
* **Firma Masiva:** Procesa múltiples archivos PDF en una sola operación.
* **Posicionamiento Visual:** Herramienta interactiva ("Rubber Band") para seleccionar visualmente el área exacta donde se estampará la firma en el plano.
* **Persistencia Visual:** Previsualización de la firma cargada y recuerdo de la configuración del usuario.
* **Integridad CAD:** Optimización de PDFs usando `PyMuPDF` (fitz) para mantener capas y vectores sin rasterizar el plano.
* **Interfaz Moderna:** Soporte para **Modo Oscuro** y **Modo Claro**.
* **Gestión de Archivos:** Selección de carpeta de salida personalizada.

---

## 🛠️ Instalación y Requisitos

### Prerrequisitos
* **Python 3.9** o superior.
* Sistema Operativo: Windows, macOS o Linux.

### Pasos de Instalación

1.  **Clonar el repositorio o descargar el código:**
    ```bash
    git clone <tu-repositorio>
    cd DigitalSealer
    ```

2.  **Crear un entorno virtual (Recomendado):**
    * En macOS/Linux:
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    * En Windows:
        ```bash
        python -m venv venv
        venv\Scripts\activate
        ```

3.  **Instalar dependencias:**
    Ejecuta el siguiente comando para instalar las librerías necesarias (`PyQt6`, `PyMuPDF`, `bcrypt`):
    ```bash
    pip install -r requirements.txt
    ```

    *Si no tienes el archivo `requirements.txt`, créalo con este contenido:*
    ```text
    PyQt6
    PyMuPDF
    bcrypt
    ```

4.  **Iniciar la aplicación:**
    ```bash
    python main.py
    ```

---

## 📖 Manual de Uso

### 1. Primer Ingreso (Administrador)
La primera vez que ejecutes la aplicación, se creará automáticamente una base de datos SQLite con un usuario administrador por defecto.

* **Usuario:** `admin`
* **Contraseña:** `admin123`

### 2. Panel de Administración
Si ingresas como `admin`, verás una pestaña extra llamada **"Administración"**.
* **Crear Usuario:** Ingresa nombre, contraseña y selecciona el rol (`ingeniero` o `admin`).
* **Gestionar Usuarios:** Puedes ver la lista de usuarios, eliminar cuentas o resetear contraseñas olvidadas.

### 3. Configuración de Firma (Rol Ingeniero)
1.  Ingresa con tu usuario de ingeniero.
2.  Ve a la pestaña **"Mi Firma Digital"**.
3.  Haz clic en **"Cargar / Cambiar Firma"**.
4.  Selecciona una imagen de tu firma/sello.
    * 💡 *Recomendación:* Usa imágenes en formato **PNG con fondo transparente** para un acabado profesional.

### 4. Firmar Planos (Flujo de Trabajo)
1.  Ve a la pestaña **"Firmar Planos"**.
2.  **Cargar Archivos:** Arrastra tus archivos PDF a la lista o usa el botón "Seleccionar PDFs".
3.  **Definir Posición:**
    * Haz clic en el botón **"📍 Definir visualmente"**.
    * Se abrirá una vista previa del primer plano.
    * Haz clic y arrastra el mouse para dibujar un rectángulo rojo en la casilla donde deseas la firma.
    * Pulsa "Confirmar Área".
4.  **Carpeta de Destino:** (Opcional) Selecciona dónde guardar los archivos firmados. Si no eliges nada, se guardarán en la misma carpeta del original.
5.  **Ejecutar:** Haz clic en **"Firmar Documentos"**.
    * Los archivos se generarán con el prefijo `SIGNED_nombre_original.pdf`.

---

## 📂 Estructura del Proyecto

La aplicación sigue el patrón de diseño **MVC (Model-View-Controller)**:

```text
DigitalSealer/
├── app/
│   ├── controllers/      # Lógica de conexión entre interfaz y datos
│   │   ├── main_controller.py
│   ├── models/           # Gestión de Base de Datos y Lógica de Negocio
│   │   ├── database.py
│   │   └── user_model.py
│   ├── views/            # Interfaz Gráfica (Ventanas y Estilos)
│   │   ├── main_view.py
│   │   ├── login_view.py
│   │   ├── selector_view.py  # Selector visual de coordenadas
│   │   └── styles.py         # Temas Dark/Light
│   └── utils/            # Utilidades (Criptografía y PDF)
│       ├── pdf_stamper.py
│       └── security.py
├── db/                   # Base de datos SQLite (se genera automática)
├── main.py               # Punto de entrada
└── requirements.txt      # Dependencias
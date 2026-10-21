# DigitalSealer — Sello y firma a escala real en planos y reportes PDF

Aplicación de escritorio (Python + PyQt6 + PyMuPDF) para que un profesional estampe **su sello con firma** en planos y reportes PDF:

* **A escala real**: el sello mide en el PDF exactamente lo mismo que el sello físico (p. ej. 55 × 27 mm), en cualquier tamaño de hoja: Carta, Oficio, Legal, A4, ANSI, ARCH o ISO.
* **Hoja por hoja**: cada hoja de cada PDF tiene su propio sello, que se **mueve y rota libremente** sin afectar a las demás.
* **Regla: máximo un sello por hoja.** Se garantiza en el modelo, en la interfaz y otra vez al estampar. Una hoja que ya fue sellada por la app queda bloqueada.
* **Aplanado y protegido** contra la reutilización del sello (ver [Seguridad](#seguridad)).

---

## Instalación

Requiere **Python 3.11+** (probado en Windows 11).

```bash
git clone https://github.com/ioseluiz/app_firma_digital_planos.git
cd app_firma_digital_planos
python -m venv venv
venv\Scripts\activate            # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt   # desarrollo: pip install -r requirements-dev.txt
python main.py
```

## Uso

### 1. Primer arranque
Escribe tu nombre (va en los metadatos del PDF) y crea una **contraseña maestra**. Tu sello se guarda **cifrado** con ella. Si la olvidas, el sello guardado no se puede recuperar y habría que importarlo de nuevo.

### 2. Mi sello
**Mi sello → Importar escaneo…**
1. Encierra con un recuadro el sello que quieres usar. Si escaneaste varios, elige el más limpio.
2. La app lo **recorta, lo endereza y le quita el fondo blanco** conservando la tinta azul de la firma.
3. **Tamaño real**: mide el marco de tu sello físico con una regla, escribe el ancho y marca *"Medí mi sello…"*. El alto se calcula en proporción.
4. Opcional: borrar el escaneo original para que solo quede la copia cifrada.

> Desde la línea de comandos: `python tools/prepare_stamp.py escaneo.png salida.png --y-min 900` hace el mismo procesado. La salida va a `assets/private/`, que git ignora.

### 3. Colocar sellos
* **Abrir PDFs** o arrastra archivos o carpetas a la ventana.
* Según el tamaño de las hojas, cada archivo empieza con un tipo:
  * **Plano** (hojas mayores que Legal): sello en **todas** las hojas, abajo a la derecha, junto al cuadro de rótulo.
  * **Reporte** (Carta / Oficio / Legal / A4): sello **solo en la última hoja**.
  * Se puede cambiar con el menú contextual del archivo o en el panel derecho.
* En el lienzo:

| Acción | Cómo |
|---|---|
| Mover | Arrastrar el sello · flechas (1 mm) · Shift+flechas (10 mm) |
| Rotar libre | Arrastrar el **asa circular** (Shift = saltos de 15°) · Ctrl+rueda sobre el sello (±1°) |
| Rotar 90° | `R` / `Shift+R` o botones del panel |
| Valores exactos | Centro X/Y (mm) y ángulo en el panel derecho |
| Colocar / quitar | Clic derecho → *Colocar sello aquí* (si ya hay uno, lo **mueve**) · `Supr` |
| Copiar a otras hojas | Panel → *Copiar posición y ángulo a…* (**reemplaza**, nunca añade) |
| Deshacer / rehacer | Ctrl+Z / Ctrl+Y |
| Zoom / desplazar | Rueda · Ctrl+0 ajustar · espacio + arrastrar o botón central |
| Cambiar de hoja | Lista de la izquierda · RePág / AvPág |

### 4. Sellar
Pulsa **Sellar N hojas**. Se crea `SELLADO_<nombre>.pdf` (en la carpeta del original o en la que elijas) y **el original no se modifica**.

### 5. Verificar
**Verificar** → arrastra un PDF. La app responde una de tres cosas:
* *Emitido por ti y sin modificar.*
* *Emitido por ti pero modificado después.*
* *No reconocido.*

---

## Seguridad

Qué hace cada hoja sellada:

1. **ID único por hoja**: `HMAC-SHA256(clave secreta local, hash del PDF original + hoja + fecha)`. Se imprime bajo el sello (*Proyecto · Hoja n/N · fecha · ID*) junto con una micro-trama tenue del ID sobre el sello. Sin la clave nadie puede fabricar un ID válido.
2. **Sello fundido con el plano**: el fondo bajo el sello se renderiza a 300 dpi y se combina con el sello en **una sola imagen RGB opaca, sin canal alfa**. Si alguien extrae la imagen, se lleva también el trozo de plano y el ID: no obtiene un sello limpio para pegar en otro documento.
3. **Aplanado**: la imagen va en el contenido de la página, no como anotación ni campo editable. El PNG original del sello **nunca** se incrusta.
4. **PDF cifrado AES-256** con permisos de solo **ver e imprimir**: sin modificar, copiar ni anotar. La contraseña de propietario es aleatoria por documento y se guarda cifrada.
5. **Registro de auditoría** (SHA-256 de entrada y salida, IDs, fecha) para la función *Verificar*.
6. **Bóveda local**: imagen del sello, clave del ID y contraseñas cifradas con AES-256-GCM. La clave se deriva de la contraseña maestra con scrypt. La app se **bloquea tras 15 min** sin uso o con Ctrl+L.

**Límite honesto**: ninguna medida visual impide una captura de pantalla. Estas medidas hacen **evidente y rastreable** cualquier reutilización. La protección criptográfica completa llegará con la **firma digital con certificado (PAdES)**. El punto de extensión ya está en `app/utils/signer.py`.

---

## Rendimiento y evaluación de Rust

Medido con `python tools/benchmark.py` (Windows 11, 20 núcleos, planos ANSI D sintéticos con ~6.000 vectores por hoja):

| Escenario | Secuencial | Paralelo |
|---|---|---|
| 12 planos × 3 hojas (0.5 MB) | **1.5 s** (42 ms/hoja) | 4.3 s con 4 procesos (más lento) |
| 60 planos pesados × 3 hojas (342 MB) | 10.0 s (55 ms/hoja) | **6.6 s** con 4 procesos (1.5×) |

Conclusiones:
* **No conviene migrar a Rust.** El trabajo pesado (leer, renderizar, comprimir y cifrar el PDF; componer la imagen) ya se hace en C, dentro de MuPDF y de Pillow/zlib. Python solo orquesta unos pocos milisegundos por hoja. Reescribir en Rust (con lopdf o pdfium-render, y egui o Tauri) supondría rehacer toda la app y perder Qt y PyMuPDF, para ganar poco o nada. Tampoco hay un cuello de botella en Python propio que justifique un módulo PyO3.
* Las mejoras que sí rindieron, medidas:
  * Quitar `optimize=True` del PNG fundido redujo el tiempo por hoja de 86 a 42 ms.
  * Evitar que PyMuPDF 2.x cargue sus extras de IA que no usamos (onnxruntime) bajó su import de **1.13 s a 0.07 s**, lo que acelera el arranque y cada proceso (`app/__init__.py`).
  * **Paralelismo adaptativo**: en Windows, arrancar cada proceso cuesta más que sellar un lote pequeño. El sellado es secuencial en segundo plano y solo usa 3 procesos a partir de ~120 hojas (`app/workers/signing_worker.py`).
  * La interfaz renderiza en un hilo aparte: la hoja visible primero, a la resolución del zoom, y las miniaturas después.

---

## Estructura

```text
app/
├── __init__.py              # Desactiva extras de IA de PyMuPDF (arranque rápido)
├── controllers/
│   └── main_controller.py   # Orquestación, deshacer/rehacer, sellado, bloqueo, sesión
├── models/
│   ├── placement.py         # SealJob: un sello por hoja, perfiles Plano/Reporte
│   ├── vault_model.py       # Contraseña maestra, secretos cifrados, registro
│   └── database.py          # SQLite (settings, secrets, seal_log)
├── utils/
│   ├── geometry.py          # mm↔pt, rotación, límites de hoja, formatos
│   ├── pdf_stamper.py       # Estampado aplanado y seguro (sin Qt)
│   ├── stamp_image.py       # Recortar/enderezar/quitar fondo del escaneo
│   ├── seal_id.py           # IDs HMAC y marca en metadatos
│   ├── crypto_vault.py      # scrypt + AES-256-GCM
│   └── signer.py            # Punto de extensión: firma digital (PAdES)
├── views/                   # Ventana principal, lienzo, navegador, panel, diálogos, tema
└── workers/                 # Render, carga y sellado en segundo plano
tools/
├── prepare_stamp.py         # Preparar el escaneo del sello (CLI)
└── benchmark.py             # Medición de rendimiento
tests/                       # pytest (+ pytest-qt para la interfaz)
```

## Pruebas y empaquetado

```bash
pip install -r requirements-dev.txt
pytest                                   # 70+ pruebas: geometría, reglas, seguridad, interfaz
pyinstaller DigitalSealer.spec           # → dist/DigitalSealer.exe
dist\DigitalSealer.exe --selftest        # comprobación sin interfaz del ejecutable
```

> El sello y la firma **nunca** se suben al repositorio: `.gitignore` excluye `*sello*.png`, `*firma*.png` y `assets/private/`.

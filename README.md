# SIMEC Backend

Backend asíncrono desarrollado en **FastAPI** bajo **arquitectura hexagonal (puertos y adaptadores)** para el monitoreo de mercados, consulta de proveedores del Estado y detección de conductas anticompetitivas.

El servicio actúa como un agregador y normalizador en tiempo real que extrae información pública mediante consultas HTTP directas (`httpx`) y automatización de navegadores (`Playwright`), consolidando perfiles empresariales (por **RUC** de 11 dígitos) y de personas naturales (por **DNI** de 8 dígitos) con trazabilidad de auditoría por cada fuente:

- **SUNAT (Consulta RUC):** Ficha tributaria, estado, condición, representantes legales y establecimientos anexos.
- **OECE / SEACE (Pentaho BI CDA):** Presencia en el RNP, vigencias, composición societaria (accionistas, representantes y órganos de administración) e historial de adjudicaciones y órdenes desde 2008.
- **OSCE — RNP (Constancia):** Historial de inscripciones por capítulo (bienes y servicios), códigos de proveedor y números de trámite con resolución automatizada de CAPTCHA.
- **APIS.NET.PE:** Pasarela rápida de validación de identidad (DNI) y padrón reducido (RUC).
- **SUNARP (SPRL y Síguelo Plus):** Asientos de una partida registral y sus PDF.
- **Instagram:** Perfil por username (sin login).
- **Facebook:** Página de empresa, con comparación opcional contra un RUC (sin login).

---

## Requisitos previos

- **Python 3.11+**
- **pip** (gestor de paquetes de Python)
- **Google Chrome** o **Microsoft Edge** instalado en el sistema (utilizado por Playwright para las fuentes protegidas con anti-bot).
- **PostgreSQL 15+** (probado con PostgreSQL 18) y, opcionalmente, **pgAdmin 4** para administrarlo. Ver [Base de datos (PostgreSQL)](#base-de-datos-postgresql).

---

## Instalación y configuración

1. **Crear y activar el entorno virtual:**

   En Windows (PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   En Linux / macOS:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Actualizar pip e instalar las dependencias del proyecto:**

   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Instalar los binarios de navegador para Playwright:**

   ```bash
   playwright install chromium
   ```

4. **Configurar las variables de entorno:**

   Copia el archivo de ejemplo `.env.example` a `.env` y reemplaza los valores marcados como `CAMBIAR`. El `.env` contiene credenciales: **nunca se sube a git** (está en `.gitignore`); `.env.example` sí se versiona y solo lleva valores de ejemplo.

   <details>
   <summary><strong>Plantilla de <code>.env.example</code></strong> (todas las variables que lee el sistema)</summary>

   ```env
   # =====================================================================
   # SIMEC Backend - Variables de entorno
   # Copiar como .env y reemplazar los valores CAMBIAR. Nunca subir el .env a git.
   # =====================================================================

   # --- Base de datos (PostgreSQL) ---------------------------------------
   # Conexión de la aplicación: usuario simec_app (solo lee y escribe datos).
   # Si se deja vacía o se comenta, la API funciona sin persistencia (modo puente).
   DATABASE_URL=postgresql+asyncpg://simec_app:CAMBIAR@localhost:5432/simec_db
   # Conexión de migraciones (Alembic): usuario simec_owner (crea y modifica tablas).
   DATABASE_MIGRATION_URL=postgresql+asyncpg://simec_owner:CAMBIAR@localhost:5432/simec_db
   DATABASE_SCHEMA=simec
   DATABASE_POOL_SIZE=5
   DATABASE_MAX_OVERFLOW=10
   # true muestra en consola cada sentencia SQL (solo para depurar).
   DATABASE_ECHO=false

   # Horas tras las que un dato guardado se marca como posiblemente desactualizado
   # (is_stale). Solo avisa: nunca re-consulta automáticamente. 720 = 30 días.
   # Cada fuente tiene además su propia vigencia en la tabla simec.sources.
   CACHE_DEFAULT_TTL_HOURS=720

   # --- Archivos generados (PDFs de SUNARP) ------------------------------
   FILES_DIR=files
   # URL pública del backend para armar enlaces a los PDFs detrás de un proxy
   # (p.ej. https://simec.indecopi.gob.pe). Vacía = se usa la URL de la petición.
   PUBLIC_BASE_URL=

   # --- SUNARP (SPRL y Síguelo Plus) -------------------------------------
   SUNARP_USER=CAMBIAR
   SUNARP_PASS=CAMBIAR
   # true = navegador oculto; false = se ve la ventana (útil para depurar).
   SUNARP_HEADLESS=false
   # false = no descarga los PDFs de Síguelo Plus (solo lista los asientos).
   SUNARP_SIGUELO_ENABLED=true
   # Opcionales (valores por defecto entre paréntesis):
   # SUNARP_AGENT_PROFILE_DIR=.cache/sunarp_mcp_profile   (perfil de Chrome del agente)
   # SUNARP_PROFILE_DIR=.cache/sunarp_profile             (perfil del extractor clásico)
   # SUNARP_FILES_DIR=files/sunarp                        (carpeta de los PDFs)

   # --- Instagram y Facebook (opcionales) ---------------------------------
   # false = se ve la ventana del navegador (útil para depurar).
   # INSTAGRAM_HEADLESS=true
   # FACEBOOK_HEADLESS=true
   # INSTAGRAM_FILES_DIR=files/instagram
   # FACEBOOK_FILES_DIR=files/facebook

   # --- Modelo de lenguaje del agente SUNARP -----------------------------
   # Proveedor: openai | anthropic | google_genai | google_vertexai
   LLM_PROVIDER=google_vertexai
   LLM_MODEL=CAMBIAR
   # Solo para openai / anthropic / google_genai (no se usa con Vertex AI):
   LLM_API_KEY=
   # Opcional: endpoint compatible con OpenAI (proxy o servidor propio).
   LLM_BASE_URL=
   # Opcional: vacío = valor por defecto del modelo (algunos modelos no lo aceptan).
   LLM_TEMPERATURE=

   # Solo para LLM_PROVIDER=google_vertexai:
   GOOGLE_CLOUD_PROJECT=CAMBIAR
   GOOGLE_CLOUD_LOCATION=global
   # Ruta al JSON de la cuenta de servicio (si no se usa `gcloud auth application-default login`).
   # GOOGLE_APPLICATION_CREDENTIALS=C:\ruta\a\cuenta-servicio.json

   # --- Otros ------------------------------------------------------------
   # No usado actualmente por el código (reservado para despliegue en contenedores).
   DOCKER_ENV=false
   ```

   </details>

   En Windows (PowerShell):
   ```powershell
   Copy-Item .env.example .env
   ```

   En Linux / macOS:
   ```bash
   cp .env.example .env
   ```

5. **Crear la base de datos y aplicar las migraciones:** ver la sección siguiente.

---

## Base de datos (PostgreSQL)

El sistema guarda cada consulta en PostgreSQL: la primera consulta de un RUC, DNI o partida se resuelve en vivo contra las fuentes y se guarda; las siguientes se responden desde la base de datos. Con `?refresh=true` se vuelve a consultar la web sin perder lo guardado si una fuente falla.

La persistencia usa un modelo híbrido: tablas relacionales para personas, empresas, vínculos y consultas, y columnas **JSONB** con el resultado íntegro de cada fuente (historial de "fotos" con su fecha de consulta).

| Elemento | Nombre | Uso |
|---|---|---|
| Base de datos | `simec_db` | Datos del sistema |
| Esquema | `simec` | Agrupa todas las tablas del sistema (no se usa `public`) |
| Usuario dueño | `simec_owner` | Crea y modifica tablas. Lo usa **Alembic** (migraciones) |
| Usuario de la aplicación | `simec_app` | Solo lee y escribe datos. Lo usa **FastAPI** |

> Si `DATABASE_URL` no está configurada o PostgreSQL no responde, la API sigue funcionando en modo puente (consulta en vivo sin guardar), igual que antes de incorporar la base de datos.

### Paso 1. Crear usuarios y base de datos (una sola vez)

Se ejecuta como superusuario `postgres`. Con **pgAdmin 4**: en el árbol de la izquierda, *Servers → PostgreSQL → Databases*, clic derecho sobre la base **`postgres`** → **Query Tool**, pegar el SQL y presionar **F5**.

**1.1 Usuarios** (reemplazar las contraseñas):

```sql
CREATE ROLE simec_owner LOGIN PASSWORD 'cambia_esto_owner';
CREATE ROLE simec_app   LOGIN PASSWORD 'cambia_esto_app';
```

**1.2 Base de datos** en UTF-8 (ñ y tildes). `CREATE DATABASE` debe ejecutarse **sola** en el editor; junto a otras sentencias, pgAdmin muestra el error *"cannot run inside a transaction block"*:

```sql
CREATE DATABASE simec_db
  OWNER simec_owner
  ENCODING 'UTF8'
  TEMPLATE template0;
```

Luego, clic derecho en *Databases* → **Refresh**: debe aparecer `simec_db`.

### Paso 2. Configurar la base `simec_db` (una sola vez)

Este SQL se ejecuta **dentro de `simec_db`**: clic derecho sobre **`simec_db`** → **Query Tool** (la barra superior del editor debe decir `simec_db/postgres@...`), pegar y presionar **F5**:

```sql
-- Esquema propio
CREATE SCHEMA simec AUTHORIZATION simec_owner;

-- Extensiones (búsqueda aproximada por nombre y sin tildes)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

-- Permisos de la app: solo leer y escribir datos (no crear ni borrar tablas)
GRANT USAGE ON SCHEMA simec TO simec_app;
ALTER DEFAULT PRIVILEGES FOR ROLE simec_owner IN SCHEMA simec
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO simec_app;
ALTER DEFAULT PRIVILEGES FOR ROLE simec_owner IN SCHEMA simec
  GRANT USAGE, SELECT ON SEQUENCES TO simec_app;

-- Esquema por defecto y zona horaria UTC
ALTER ROLE simec_owner IN DATABASE simec_db SET search_path = simec, public;
ALTER ROLE simec_app   IN DATABASE simec_db SET search_path = simec, public;
ALTER DATABASE simec_db SET timezone = 'UTC';
```

Verificación (en el mismo Query Tool):

```sql
SELECT version();                                    -- versión de PostgreSQL
SELECT extname FROM pg_extension;                    -- debe incluir pg_trgm y unaccent
SELECT schema_name FROM information_schema.schemata
WHERE schema_name = 'simec';                         -- debe devolver simec
```

**Errores frecuentes:**

| Mensaje | Causa |
|---|---|
| `role "..." already exists` | El usuario ya fue creado antes: se puede ignorar. |
| `CREATE DATABASE cannot run inside a transaction block` | `CREATE DATABASE` se ejecutó junto con otras sentencias: dejarla sola en el editor. |
| `permission denied to create extension` | No se está conectado como `postgres` (superusuario). |

> Las tablas **no** se crean a mano en pgAdmin: las crea Alembic en el paso 4.

### Paso 3. Variables de entorno de la base de datos

En el archivo `.env` (ver la [plantilla completa](#instalación-y-configuración) del paso 4 de instalación), con las contraseñas definidas en el paso 1.1:

```env
# Conexión de la aplicación (usuario simec_app)
DATABASE_URL=postgresql+asyncpg://simec_app:CONTRASENA_APP@localhost:5432/simec_db
# Conexión de migraciones (usuario simec_owner), usada por Alembic
DATABASE_MIGRATION_URL=postgresql+asyncpg://simec_owner:CONTRASENA_OWNER@localhost:5432/simec_db
DATABASE_SCHEMA=simec
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=10
DATABASE_ECHO=false
# Horas tras las que un dato guardado se marca como posiblemente desactualizado (is_stale)
CACHE_DEFAULT_TTL_HOURS=720
```

> Si una contraseña contiene caracteres especiales (`@`, `:`, `/`, `#`, `%`), deben escribirse codificados en la URL (por ejemplo `@` → `%40`).

### Paso 4. Crear las tablas (migraciones con Alembic)

Desde la raíz del proyecto, con el entorno activado:

```bash
alembic upgrade head
```

Esto crea las tablas del esquema `simec` (`sources`, `parties`, `party_links`, `queries`, `source_snapshots`, `snapshot_payloads`, `query_snapshots`, `source_cache`, `news_articles`, `news_mentions`) y carga el catálogo de fuentes. Para verlas en pgAdmin: `simec_db` → clic derecho en *Schemas* → **Refresh** → `simec` → *Tables*.

Comandos útiles de Alembic:

```bash
alembic current                                   # versión aplicada en la base de datos
alembic upgrade head                              # aplicar migraciones pendientes
alembic check                                     # verificar que los modelos y la base coinciden
alembic revision --autogenerate -m "descripcion"  # nueva migración tras cambiar un modelo
alembic downgrade -1                              # deshacer la última migración
```

### Paso 5. Verificar la conexión

Con el servidor levantado (ver [Ejecución del proyecto](#ejecución-del-proyecto)), la consola debe mostrar `Conectado a PostgreSQL (esquema simec).` y el endpoint de salud debe responder:

```bash
curl http://localhost:8000/api/v1/health
# {"status":"ok","database":"up"}
```

| `database` | Significado |
|---|---|
| `up` | PostgreSQL responde: las consultas se guardan y se reutilizan. |
| `down` | PostgreSQL configurado pero no responde: la API consulta en vivo sin guardar. |
| `disabled` | `DATABASE_URL` no configurada: modo puente, sin persistencia. |

---

## Ejecución del proyecto

### 1. Levantar el servidor de desarrollo (FastAPI)

Desde la raíz del proyecto, ejecuta con `uvicorn`:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 --env-file .env
```

Una vez iniciado el servidor, la documentación interactiva estará disponible en:

- **Swagger UI:** <http://localhost:8000/docs>
- **ReDoc:** <http://localhost:8000/redoc>

### 2. Endpoints principales

| Consulta | Endpoint | Fuentes |
|---|---|---|
| Consolidada por **RUC** (11 dígitos) | `GET http://localhost:8000/api/v1/companies/{ruc}` | apis.net.pe, SEACE, SUNAT y RNP |
| Consolidada por **DNI** (8 dígitos) | `GET http://localhost:8000/api/v1/persons/{dni}` | apis.net.pe, SEACE y SUNAT |
| **Partida registral** (SUNARP) | `GET http://localhost:8000/api/v1/sunarp/partidas?oficina=CUSCO&area=Personas Juridicas&partida=11156404` | SPRL y Síguelo Plus (puede tardar varios minutos en vivo) |
| **Perfil de Instagram** | `GET http://localhost:8000/api/v1/instagram/{username}` | Instagram |
| **Página de Facebook** | `GET http://localhost:8000/api/v1/facebook/pages?page=codideep&ruc=20603687478` (`ruc` opcional) | Facebook y, con `ruc`, apis.net.pe y SUNAT |
| Estado del servicio | `GET http://localhost:8000/api/v1/health` | API y conexión a PostgreSQL |

El RNP solo admite consultas por RUC. Cada respuesta incluye `audit_entries` con la duración, el estado (`SUCCESS`, `NO_DATA` o `ERROR`) y el detalle de cada fuente, de modo que una fuente caída no bloquea a las demás.

**Datos guardados y actualización:** todos los endpoints de consulta aceptan el parámetro `refresh`:

| Llamada | Comportamiento |
|---|---|
| `.../companies/20607524476` | Responde desde la base de datos si ya fue consultado; si no, consulta la web y guarda. |
| `.../companies/20607524476?refresh=true` | Vuelve a consultar todas las fuentes en la web y guarda el resultado. Si una fuente falla, se muestran sus datos guardados. |

La respuesta indica el origen de los datos con `served_from` (`DATABASE`, `LIVE` o `MIXED`) y, por fuente, con `audit_entries[].from_cache`, `data_fetched_at` e `is_stale` (dato que superó su vigencia: conviene ofrecer al usuario actualizarlo).

### 3. Ejecutar la suite de pruebas (pytest)

```bash
pytest -v
```

Las pruebas no usan red ni base de datos.

### 4. Laboratorio de exploración (Jupyter Notebooks)

Los cuadernos de pruebas y validación de fuentes se encuentran en la carpeta [`notebooks/`](notebooks/). Puedes abrirlos directamente desde VS Code seleccionando el kernel del entorno `.venv` o iniciando Jupyter Lab:

```bash
jupyter lab
```

---

## Mantenimiento de dependencias (pip)

Si instalas nuevas librerías durante el desarrollo con `pip install <paquete>`, actualiza el archivo `requirements.txt` ejecutando:

```bash
pip freeze > requirements.txt
```

### Configuración del entorno para CONDA

```bash
# Crear y activar el entorno aislado
conda create -n simec-ocr python=3.11 -y
conda activate simec-ocr

# Instalar las dependencias del proyecto y el motor para Jupyter
pip install -r requirements.txt ipykernel

# Descargar el navegador Chromium necesario para Playwright
playwright install chromium

# Vincular el entorno de Conda para que VS Code y Jupyter lo reconozcan
python -m ipykernel install --user --name=simec-ocr --display-name="Python 3.11 (SIMEC-OCR)"
```
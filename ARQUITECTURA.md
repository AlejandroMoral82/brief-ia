# Arquitectura de brief-ia

Documento pensado para entender el proyecto y clonarlo hacia otro dominio,
por ejemplo un brief de noticias de marketing y paid media con otra estética.
Las referencias apuntan a funciones, constantes, componentes o claves por su
nombre, para que no se desfasen al editar el código.

---

## 1. Qué hace y arquitectura general

brief-ia publica dos veces al día una selección de noticias de IA sacadas de
feeds RSS/Atom. No hay servidor ni base de datos: todo vive en el repositorio.

```
┌──────────────────────────┐    commit     ┌──────────────┐   build + copia   ┌────────────────────┐
│ GitHub Actions (cron)    │ ────────────▶ │ data/*.json  │ ────────────────▶ │ GitHub Pages       │
│ pipeline Python          │               │ en el repo   │                   │ PWA React (Vite)   │
│ feeds → LLM → cuotas     │               └──────────────┘                   │ solo lee JSON      │
└──────────────────────────┘                                                  └────────────────────┘
              ▲                                                                         ▲
              └─────────────────────── categorias.json ─────────────────────────────────┘
```

Cuatro piezas:

| Pieza | Dónde | Qué hace |
|---|---|---|
| Pipeline | `pipeline/` + `.github/workflows/brief.yml` | Descarga feeds, clasifica con Gemini, aplica cuotas, extrae texto, escribe JSON y hace commit |
| Datos | `data/` | JSON estáticos versionados en git: hacen de backend |
| App | `app/` + `.github/workflows/pages.yml` | PWA React que lee los JSON y se despliega en GitHub Pages |
| Categorías | `categorias.json` | Única fuente de verdad de categorías, cuotas, colores y textos del prompt. La leen el pipeline y la app |

Principio rector: **el LLM nunca escribe texto visible**. Títulos, resúmenes y
textos completos salen siempre del medio original. El modelo solo decide
categoría y orden.

---

## 2. Flujo completo de una ejecución

### 2.1 Disparo

`.github/workflows/brief.yml`

- Cron a las 04:00 y 11:00 UTC (`on.schedule`), más `workflow_dispatch` para lanzarlo a mano.
- `concurrency: brief` evita dos ejecuciones solapadas.
- Instala Python 3.12 y `requirements.txt` (feedparser, requests, trafilatura).
- Ejecuta `python -m pipeline.build` con `GEMINI_API_KEY` (secret) y `GEMINI_MODEL` (variable de repo, opcional).

### 2.2 Pipeline (`pipeline/build.py`, función `main`)

| Paso | Qué ocurre | Dónde |
|---|---|---|
| 0 | Al importar: carga `.env` si existe (solo local, no pisa variables) y lee `categorias.json`, que se valida y para el pipeline si es inválido | `build.py`, bloque `_env`; `categorias.cargar` |
| 1 | Lee `feeds.opml`: cada `<outline>` con `xmlUrl` es una fuente; su `title` es el nombre visible | `sources.leer_opml` |
| 2 | Descarga cada feed con User-Agent de navegador y timeout de 20 s. Un fallo se apunta en `fuentes_fallidas` y no tumba la ejecución | `sources.descargar` |
| 3 | Filtra entradas más antiguas que `VENTANA_HORAS` (26). Normaliza a `Item`: id = sha1 de la URL (16 hex), título y resumen con entidades HTML decodificadas, resumen sin etiquetas y cortado a 500 caracteres, imagen del feed. Las entradas sin fecha se marcan `sin_fecha` | `sources.descargar` |
| 4 | Deduplica por URL dentro de la tanda | `sources.recoger` |
| 5 | Refresca en `seen.json` las entradas sin fecha que siguen en el feed, y descarta los ids ya vistos | `build.main` |
| 6 | Si no hay nada nuevo: actualiza `comprobado_en` en `latest.json`, guarda `seen.json` y termina | `build.main`, rama `if not nuevos` |
| 7 | Una única llamada a Gemini con todos los candidatos (id, título, fuente, resumen a 300 caracteres) y un `responseSchema` que solo admite `[{id, categoria, posicion}]` | `llm.seleccionar`, `llm._llamar` |
| 8 | Valida la respuesta: si no es lista de objetos, modo degradado. Ids desconocidos o repetidos se ignoran. La categoría se normaliza (minúsculas, sin tildes); si no existe, va al comodín. Items olvidados por el LLM van al comodín con posición 99 | `llm.seleccionar` |
| 9 | Aplica cuotas por categoría y tope por fuente para marcar `destacado` | `build.marcar_destacados` |
| 10 | Para los destacados descarga la página y extrae el texto con trafilatura a partir de los bytes. Menos de 400 caracteres se descarta (paywall o consentimiento). Si el feed no traía imagen, usa `og:image` | `extract.procesar`, `extract.extraer` |
| 11 | Lee el fichero del día si existe, añade una entrada al historial `pasadas` y fusiona los items por id | `build.main` (`previo`, `pasadas`, `todos`) |
| 12 | Escribe `data/AAAA-MM-DD.json` y una copia idéntica en `data/latest.json`, de forma atómica | `build.main` (`salida`), `build._escribir` |
| 13 | Poda días con más de 30 días y artículos huérfanos. Si algún día no se puede leer, no borra artículos | `build.podar_ficheros` |
| 14 | Regenera `data/index.json` con la lista de días y el tamaño total | `build.main` |
| 15 | En modo normal marca como vistos los items procesados. En degradado no marca nada, para reclasificarlos en la siguiente pasada. Poda `seen.json` a 30 días | `build.main`, `build.guardar_seen`, `build.podar_seen` |

Todas las lecturas de JSON pasan por `build._leer_json`, que
tolera ficheros corruptos o con otra forma. Todas las escrituras pasan por
`build._escribir`: temporal en la misma carpeta y `os.replace`.

### 2.3 Commit

El último paso de `brief.yml` hace `git add data/` y, si hay cambios, commit
como `brief-bot`. Antes del push hace `git pull --rebase`, con un reintento,
por si alguien subió algo mientras corría el pipeline (paso `Commit si hay cambios`).
Necesita `permissions: contents: write`.

### 2.4 Despliegue

`.github/workflows/pages.yml`

- Se dispara con push a `main`, al terminar el workflow `"brief diario"` (`workflow_run`) o a mano.
- El `workflow_run` hace falta porque un push hecho con `GITHUB_TOKEN` no dispara otros workflows. Solo despliega si el brief terminó con éxito (`jobs.construir.if`).
- Hace `npm ci` y `npm run build` en `app/`, copia `data/` dentro de `app/dist/data` y publica en Pages.

### 2.5 App (`app/src/`)

| Fichero | Papel |
|---|---|
| `main.jsx` | Monta `<App>` e importa `styles.css` |
| `categorias.js` | Importa `../../categorias.json` y expone `CATS`, `nombreCat` y `colorCat` |
| `data.js` | `fetch` de `latest.json`, `{día}.json`, `index.json` y `articles/{id}.json`, relativo a `import.meta.env.BASE_URL`. Valida la forma del brief, calcula la frescura y filtra URLs que no sean `http(s)` |
| `guardados.js` | Guardados en `localStorage`, con texto completo para un máximo de 25. `alternar` devuelve el resultado real de la escritura |
| `App.jsx` | Pestañas archivo / hoy / guardados, filtros, lista con gesto de deslizar para guardar, lector, avisos, historial para el gesto de atrás y la lluvia de glifos |
| `styles.css` | Tokens de color, tipografía IBM Plex y todos los estilos |
| `vite.config.js` | Base path, acceso del servidor de desarrollo a `categorias.json`, manifest PWA y caché del service worker |

Comportamientos de la app que conviene conocer:

- **Frescura.** Avisa solo en el último brief, cuando pasan más de 16 horas desde `comprobado_en` (`data.js`: `HORAS_FRESCURA`, `estaDesactualizado`; componente `Brief`). La fecha de la cabecera sale de `generado_en`.
- **Archivo.** Un día del archivo se muestra con la pestaña "archivo" activa y la cabecera `~/archivo/<día>`.
- **Historial.** Cada vista se guarda como `pestaña:día` o `articulo:id` (`App`: `vista` y el manejador `atras` de `popstate`), así que el gesto de atrás navega dentro de la app.
- **Scroll y foco.** El lector se abre arriba con el foco en el título. Al volver, la lista recupera su scroll y el foco vuelve al item (`App`: `abrir`, `retorno` y su `useLayoutEffect`).
- **Offline.** Los datos se sirven `NetworkFirst`, con 5 s de espera y caché de 30 días y 150 entradas (`vite.config.js`, `workbox.runtimeCaching`).

### 2.6 Tests

`tests/` usa pytest (`requirements-dev.txt`, `pytest.ini`). Cubre
`marcar_destacados`, `_extraer_json`, la validación de `seleccionar`, los
reintentos y `categorias.json`. Un fixture global (`tests/conftest.py`)
bloquea cualquier llamada real a la API.

```bash
pip install -r requirements-dev.txt
python -m pytest
```

---

## 3. Formato de los datos

### 3.1 Item

Definido por la dataclass `sources.Item`.

| Campo | Tipo | Origen |
|---|---|---|
| `id` | string, 16 hex | sha1 de la URL |
| `url` | string | feed |
| `titulo` | string | feed, con entidades HTML decodificadas |
| `fuente` | string | `title` del OPML |
| `publicado` | ISO 8601 UTC | feed; si falta, hora de descarga |
| `resumen` | string ≤ 500 | feed, sin etiquetas HTML |
| `categoria` | string | LLM, validada contra `categorias.json` |
| `posicion` | int | LLM, ranking dentro de su categoría; 99 si falta |
| `destacado` | bool | Python, por cuotas |
| `imagen` | string | feed u `og:image` |
| `texto_disponible` | bool | true si existe `data/articles/{id}.json` |
| `sin_fecha` | bool | true si el feed no daba fecha. La app lo ignora |

### 3.2 `data/latest.json` y `data/AAAA-MM-DD.json`

Mismo formato. `latest.json` es una copia del último día escrito.

```json
{
  "generado_en": "2026-10-03T11:04:12+00:00",
  "modo": "normal",
  "fuentes_fallidas": [],
  "candidatos": 42,
  "destacados": 15,
  "items": [ { "...": "Item" } ],
  "comprobado_en": "2026-10-03T11:04:12+00:00",
  "pasadas": [
    { "hora": "2026-10-03T04:31:02+00:00", "modo": "degradado", "fuentes_fallidas": ["Import AI: HTTPError"] },
    { "hora": "2026-10-03T11:04:12+00:00", "modo": "normal", "fuentes_fallidas": [] }
  ]
}
```

- `modo` y `fuentes_fallidas` son los de la **última** pasada. Así la app no necesita conocer `pasadas`.
- `pasadas` guarda una entrada por ejecución con cambios. Un fichero anterior a este campo aporta su única pasada a partir de los campos de nivel superior.
- `candidatos` suma los nuevos de esta pasada y los acumulados del día.
- `comprobado_en` es la última vez que corrió el pipeline. Cuando no hay nada nuevo solo se actualiza este campo, y solo en `latest.json`.
- Orden de `items`: primero los nuevos de esta pasada, destacados delante, por categoría y posición; después los de pasadas anteriores. Un item reclasificado sustituye a su versión anterior.

### 3.3 `data/index.json`

```json
{ "dias": ["2026-10-03", "2026-10-02", "..."], "bytes": 1234567 }
```

Días disponibles, del más reciente al más antiguo, y peso total de `data/`.

### 3.4 `data/articles/{id}.json`

```json
{ "id": "00a6b30dd37a4a14", "texto": "texto plano extraído, párrafos separados por \n" }
```

Solo existen para destacados con extracción correcta. La app los pide con
`force-cache` porque no cambian.

### 3.5 `data/seen.json`

Mapa `{ id: fecha_iso }` de lo ya procesado. Está versionado, para que la
deduplicación funcione entre ejecuciones de Actions. Las entradas caducan a
los 30 días, salvo las sin fecha que siguen en su feed, que se refrescan.

### 3.6 `categorias.json`

```json
{
  "comodin": "industria",
  "notas_prompt": ["Ante la duda entre investigacion y opinion, elige investigacion."],
  "categorias": [
    { "id": "modelos", "nombre": "Modelos", "descripcion": "lanzamientos, versiones, capacidades, benchmarks", "cuota": 3, "color": "#DDBE63" }
  ]
}
```

| Campo | Quién lo usa | Para qué |
|---|---|---|
| `id` | pipeline y app | Clave en los datos, el prompt, el esquema y los iconos. Minúsculas, sin tildes ni espacios |
| `nombre` | app | Etiqueta visible con tildes: filtros y lector |
| `descripcion` | pipeline | Línea `- id: descripcion` del prompt |
| `cuota` | pipeline | Cuántos destacados por pasada |
| `color` | app | Punto del item y color del filtro |
| `comodin` | pipeline | Categoría para lo no clasificable y el modo degradado |
| `notas_prompt` | pipeline | Reglas de desempate tras la lista del prompt |
| orden de la lista | ambos | Orden en el prompt y en los filtros |

---

## 4. Decisiones de diseño

### 4.1 El LLM no genera texto visible

Todo lo que se lee sale del medio: títulos, resúmenes y textos extraídos.
El modelo solo devuelve `id`, `categoria` y `posicion`, y el `responseSchema`
(`llm.ESQUEMA`) no admite otros campos. Así no hay alucinaciones en lo
publicado, el coste en tokens de salida es mínimo y un fallo del modelo
degrada la selección, no el contenido. Los ids que no venían en la entrada
se descartan (`llm.seleccionar`).

### 4.2 El LLM clasifica, Python corta

El prompt pide clasificar **todos** los items y ordenarlos dentro de cada
categoría (`llm.CRITERIO`). Las cuotas, que vienen de `categorias.json`, y el
tope de dos items por fuente (`build.MAX_POR_FUENTE`) los aplica `marcar_destacados`.
Ventajas:

- Las cuotas son deterministas y se cambian sin tocar el prompt.
- Los LLM cuentan mal y no respetan límites de forma fiable.
- Lo no destacado sigue disponible en "ver los otros N".
- Una sola llamada con todo: para priorizar, el modelo necesita ver los candidatos juntos.

### 4.3 Acumulación mañana / mediodía

La segunda pasada del día lee el fichero del día y añade lo nuevo delante,
sin duplicar ids (`build.main`, `todos`). Los destacados de la mañana conservan
su marca, así que un día puede sumar dos tandas de cuotas. Las cuotas de la
segunda pasada no descuentan lo que ya destacó la primera. Cada pasada deja
su modo y sus fuentes fallidas en `pasadas`.

### 4.4 Poda a 30 días

`build.RETENCION_DIAS = 30` controla tres cosas: ficheros de día,
artículos que ya no referencia ningún día y entradas de `seen.json`. Mantiene
acotados el repo y el despliegue de Pages. La app muestra el peso en la
pestaña archivo.

### 4.5 Fallbacks

| Fallo | Comportamiento | Dónde |
|---|---|---|
| Feed caído, 404, timeout | Se apunta en `fuentes_fallidas` y se sigue | `sources.descargar` |
| XML inválido sin entradas | Igual | `sources.descargar` |
| Sin `GEMINI_API_KEY` | Modo degradado | `llm.seleccionar` |
| Timeout, error de conexión, 429 o 5xx del LLM | 4 intentos con esperas de 3, 6 y 12 s | `llm._llamar`, `llm.REINTENTABLES`, `llm.INTENTOS` |
| Error 4xx permanente | Modo degradado sin reintentar | `llm._llamar` |
| Respuesta que no es lista de objetos, o sin candidatos | Modo degradado | `llm._validar`, `llm.seleccionar` |
| El LLM clasifica menos de la mitad de los items, lista vacía incluida | Modo degradado: se descartan sus categorías parciales y todo va al comodín por fecha | `llm.seleccionar` |
| JSON envuelto en markdown o con texto alrededor | Se limpia y se busca el array | `llm._extraer_json` |
| Categoría con tildes o mayúsculas | Se normaliza | `llm._normalizar` |
| Categoría desconocida o item olvidado | Comodín, posición 99 el olvidado | `llm.seleccionar` |
| Modo degradado | Orden por fecha; se destacan los más recientes, tantos como suman las cuotas; no se marcan como vistos | `llm._degradado`, `build.marcar_destacados`, `build.main` |
| `seen.json` o un día corrupto | Se registra y se sigue. Un día ilegible bloquea solo la poda de artículos | `build._leer_json`, `build.podar_ficheros` |
| Push rechazado | `pull --rebase` y un reintento | `brief.yml`, paso `Commit si hay cambios` |
| Extracción fallida o corta | El lector muestra el resumen y enlaza al original | `extract.extraer`, componente `Lector` |
| Brief que no carga o con otra forma | Pantalla de error con pestañas y botón de reintento | `cargarBrief`, `App` (botón `reintentar`) |
| Sin red | Caché del service worker durante 30 días | `vite.config.js`, `workbox.runtimeCaching` |
| Imagen rota o URL no `http(s)` | Se oculta; el enlace se sustituye por un aviso | `urlSegura`, componente `Lector` |
| `localStorage` lleno o bloqueado | Reintenta sin texto; si falla, aviso discreto | `guardados.alternar`, `App` (`guardar`, `avisar`) |

### 4.6 Avisos pendientes

- **Esquema sin probar contra la API.** El `responseSchema` sigue el formato documentado, pero ninguna ejecución real lo ha usado aún. Si Gemini lo rechazara, cada pasada acabaría en un 400 y en modo degradado. Hay que lanzar el workflow una vez y comprobar "modo normal" en el log.
- **Duplicados con fallo persistente.** Si el LLM falla varias pasadas seguidas, un item sin marcar puede aparecer en dos días consecutivos mientras siga dentro de la ventana de 26 horas.
- **Artículos sin escritura atómica.** `extract.procesar` escribe directamente. Un corte a mitad dejaría un artículo truncado que no se vuelve a extraer.
- **Riesgo legal.** `data/articles/` republica texto completo de terceros en un repo y una web públicos.
- **Batería.** La lluvia de glifos redibuja a 60 fps sin pausa mientras se ve la lista.
- **Iconos.** El manifest solo declara un SVG. iOS y algunos Android antiguos necesitan PNG.
- **CI.** Los tests no se ejecutan en Actions. Las acciones están fijadas por tag y no por SHA, y los jobs no tienen `timeout-minutes`.

---

## 5. Qué es genérico y qué es específico del dominio

### 5.1 Genérico: se reutiliza tal cual

| Fichero | Contenido |
|---|---|
| `pipeline/sources.py` | Lectura de OPML, descarga, normalización e imágenes |
| `pipeline/extract.py` | Extracción con trafilatura y `og:image` |
| `pipeline/categorias.py` | Carga y validación de `categorias.json` |
| `pipeline/llm.py` | Esquema, `_extraer_json`, `_validar`, `_llamar` con reintentos, validación de la respuesta y `_degradado` |
| `pipeline/build.py` | Carga de `.env`, flujo de `main`, acumulación, historial de pasadas, poda, `index.json` y `seen.json` |
| `app/src/data.js`, `guardados.js`, `categorias.js` | Carga de datos, guardados y lectura de categorías |
| `App.jsx`, estructura | Componentes `Item`, `Lector`, `Archivo`, `Guardados`, `Brief`, `Tabs`, filtros e historial |
| `tests/` | Tests del pipeline. Los de categorías se adaptan solos al nuevo fichero |
| `requirements*.txt`, `pytest.ini`, `app/package.json` | Dependencias y configuración |
| `pages.yml` | Build y despliegue, salvo el nombre del workflow que escucha |
| Formato de datos | Todo el contrato de la sección 3 |
| `.claude/settings.json` | Permisos de Claude Code |

### 5.2 Específico del dominio: hay que cambiarlo

**Fuentes y criterio editorial**

| Qué | Dónde |
|---|---|
| Lista de feeds | `feeds.opml`, todo el fichero. El `title` de cada `outline` es lo que se ve como fuente |
| Categorías: ids, nombres, descripciones, cuotas, colores, comodín y desempates | `categorias.json`, todo el fichero (sección 6) |
| Prompt editorial: rol, lector, qué priorizar y qué rebajar | `pipeline/llm.py`, constante `CRITERIO` |
| Modelo por defecto | `pipeline/llm.py`, `MODELO` |
| Proveedor de LLM | `pipeline/llm.py`: `ENDPOINT`, `ESQUEMA`, y cuerpo, cabecera y lectura de respuesta en `_llamar`. Solo si cambias de Gemini |
| Tope por fuente | `pipeline/build.py`, `MAX_POR_FUENTE` |
| Ventana y retención | `build.py`: `VENTANA_HORAS` y `RETENCION_DIAS` |
| Horas de ejecución | `.github/workflows/brief.yml`, `on.schedule` |
| Nombre del workflow | `brief.yml`, clave `name`. Si cambia, hay que cambiar también `on.workflow_run.workflows` en `pages.yml` |
| Autor y mensaje del commit | `brief.yml`, paso `Commit si hay cambios` |

**Identidad de la app**

| Qué | Dónde |
|---|---|
| Base path | `app/vite.config.js`: `base` y `manifest.start_url`. Debe ser `/<nombre-del-repo>/` |
| Nombre, idioma, colores e icono de la PWA | `vite.config.js`, `manifest` de `VitePWA` |
| Nombre de la caché | `vite.config.js`, `cacheName: 'brief-data'` |
| Título e idioma del HTML | `app/index.html`: atributo `lang` de `<html>` y `<title>` |
| Favicon e icono del manifest | `app/public/favicon.svg` |
| Clave de `localStorage` | `app/src/guardados.js`, `CLAVE`. Hay que cambiarla si ambos briefs viven bajo el mismo dominio `<usuario>.github.io`, porque comparten `localStorage` |
| Umbral de frescura | `app/src/data.js`, `HORAS_FRESCURA` |
| Textos de interfaz | `App.jsx`: saludo y prompt `~/hoy` en `Brief`, aviso de 30 días en `Archivo`, y el resto de literales en español |

**Estilo visual**

| Qué | Dónde |
|---|---|
| Paleta base: fondo, texto y acento verde | `app/src/styles.css`, `:root` (`--bg`, `--fg`, `--g` y derivados) |
| Color por categoría | `categorias.json`, campo `color` |
| Tipografías | `styles.css`: `@import` de Google Fonts y `--mono`, `--sans` |
| Fondo de la barra inferior, color fijo | `styles.css`, `.tabs`, `rgba(7,9,8,.72)` |
| Líneas de escáner | `styles.css`, `body::after` |
| Lluvia de glifos: caracteres, fuente y color fijo | `App.jsx`, componente `Particulas`: `GLIFOS`, `ctx.font` y `ctx.fillStyle` con `rgba(76,224,126,…)` |
| Iconos de categoría | `App.jsx`, `ICONOS`, indexados por id |

Los colores de `Particulas` en `App.jsx` y de `.tabs` en `styles.css` no usan variables CSS.
Al cambiar de paleta hay que tocarlos a mano.

---

## 6. Categorías: una sola fuente

Todo lo relativo a categorías está en `categorias.json` (formato en 3.6).
Quién lo consume:

| Consumidor | Qué toma |
|---|---|
| `pipeline/categorias.py` | Valida el fichero al importarse y expone `CATEGORIAS`, `COMODIN`, `CUOTAS` y `bloque_prompt()` |
| `pipeline/llm.py` | La lista del prompt (`CRITERIO`, vía `bloque_prompt()`), el enum del esquema (`ESQUEMA`) y el comodín (`seleccionar`, `_degradado`) |
| `pipeline/build.py` | `CUOTAS` para `marcar_destacados` |
| `app/src/categorias.js` | Orden de filtros, nombres visibles y colores |
| `app/vite.config.js`, `CATEGORIAS` y `server.fs.allow` | Permite al servidor de desarrollo servir ese fichero, que está fuera de `app/` |

Lo único que sigue en el código son los **iconos**, en `ICONOS` de `App.jsx`,
indexados por id. Una categoría nueva sin icono funciona, pero su filtro sale
vacío. El README usa una categoría como ejemplo en la sección "Contrato de `data/latest.json`".

Para cambiar las categorías:

1. Edita `categorias.json`. Los ids van en minúsculas y sin tildes; el nombre visible lleva las tildes.
2. Añade o renombra su icono en `ICONOS`.
3. Ejecuta `python -m pytest`. Los tests de categorías validan el fichero.
4. Los días ya publicados conservan sus categorías antiguas. En la app se muestran con su id y sin color hasta que se podan a los 30 días.

Ejemplo orientativo para paid media: `plataformas` (cambios en Meta, Google,
TikTok, Amazon), `medicion` (atribución, privacidad, cookies), `creatividad`,
`estrategia` y `mercado` como comodín.

---

## 7. Checklist para clonar

### Repositorio

- [ ] Crear el repo nuevo. Público si quieres minutos de Actions ilimitados.
- [ ] Copiar el código **sin** `data/`, `.env`, `.venv/`, `app/node_modules/` ni `app/public/data/`. El pipeline crea `data/` en su primera ejecución.
- [ ] Sustituir `feeds.opml` por las fuentes del nuevo dominio.
- [ ] Reescribir `categorias.json` y los iconos (sección 6) y el criterio editorial de `CRITERIO`.
- [ ] Ajustar colores, tipografía, glifos y textos (sección 5.2).
- [ ] Actualizar `README.md`.
- [ ] Ejecutar `python -m pytest` y `npm run build` en `app/`.

### Secrets y variables

- [ ] Settings → Secrets and variables → Actions → Secrets: crear `GEMINI_API_KEY` con una clave de Google AI Studio.
- [ ] Opcional, en la pestaña Variables: `GEMINI_MODEL`. Si no existe o está vacía se usa el modelo por defecto, `MODELO` en `llm.py`.
- [ ] En local, crear `.env` con `GEMINI_API_KEY`. Nunca se sube.

### Permisos de Actions

- [ ] Settings → Actions → General → Workflow permissions → **Read and write permissions**. Sin esto falla el commit de datos.
- [ ] Confirmar que Actions está habilitado en el repo.

### GitHub Pages

- [ ] Settings → Pages → Source: **GitHub Actions**.
- [ ] Si cambias el nombre del workflow del pipeline, actualiza `on.workflow_run.workflows` en `pages.yml`.

### Base path de Vite

- [ ] En `app/vite.config.js`, `base` y `manifest.start_url` deben valer `/<nombre-del-repo>/`, con ambas barras.
- [ ] Con dominio propio o un repo `<usuario>.github.io`, el base es `/`.
- [ ] Revisar manifest, `index.html`, icono y clave de `localStorage` (sección 5.2).

### Settings de Claude Code

`.claude/settings.json` está versionado y es genérico. Define:

- **deny:** leer `.env`, `.env.*`, `*.pem` y `*.key`; `printenv` y `env`; editar `data/**`, que solo escribe el pipeline.
- **ask:** `git commit`, `git push`, `rm`, editar `.github/**` y ejecutar el pipeline, que consume cuota del LLM.
- **allow:** `npm run *`, `git status` y `git diff`.

- [ ] Copiarlo tal cual al repo nuevo.
- [ ] Los ajustes personales van en `.claude/settings.local.json`, que no debe subirse.

### Primera ejecución

- [ ] Actions → "brief diario" → Run workflow.
- [ ] En el log, comprobar `recogidos N items`, el modo y las fuentes con fallo. Un "modo degradado" en la primera ejecución con clave apunta al modelo o al esquema (4.6).
- [ ] Comprobar que aparece el commit en `data/` y que "desplegar app" termina en verde.
- [ ] Abrir `https://<usuario>.github.io/<repo>/` y revisar avisos, filtros y lector.
- [ ] En local: `cd app && npm run dev`. Para ver datos, copiar `data/` a `app/public/data/`, que está ignorado.

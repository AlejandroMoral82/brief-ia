# Arquitectura de brief-ia

Documento pensado para entender el proyecto y clonarlo hacia otro dominio,
por ejemplo un brief de noticias de marketing y paid media con otra estética.
Las referencias de línea corresponden al estado del repo a 2026-10-03.

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
```

Tres piezas:

| Pieza | Dónde | Qué hace |
|---|---|---|
| Pipeline | `pipeline/` + `.github/workflows/brief.yml` | Descarga feeds, clasifica con Gemini, aplica cuotas, extrae texto, escribe JSON y hace commit |
| Datos | `data/` | JSON estáticos versionados en git: hacen de backend |
| App | `app/` + `.github/workflows/pages.yml` | PWA React que lee los JSON y se despliega en GitHub Pages |

Principio rector: **el LLM nunca escribe texto visible**. Títulos, resúmenes y
textos completos salen siempre del medio original. El modelo solo decide
categoría y orden.

---

## 2. Flujo completo de una ejecución

### 2.1 Disparo

`.github/workflows/brief.yml`

- Cron a las 04:00 y 11:00 UTC (líneas 7-8), más `workflow_dispatch` para lanzarlo a mano.
- `concurrency: brief` evita dos ejecuciones solapadas.
- Instala Python 3.12 y `requirements.txt` (feedparser, requests, trafilatura).
- Ejecuta `python -m pipeline.build` con `GEMINI_API_KEY` (secret) y `GEMINI_MODEL` (variable de repo).

### 2.2 Pipeline (`pipeline/build.py`, función `main`)

| Paso | Qué ocurre | Fichero / función |
|---|---|---|
| 0 | Carga `.env` si existe, solo en local. No pisa variables ya definidas | `build.py:22-29` |
| 1 | Lee `feeds.opml`: cada `<outline>` con `xmlUrl` es una fuente; su `title` es el nombre visible | `sources.leer_opml` |
| 2 | Descarga cada feed con User-Agent de navegador y timeout de 20 s. Un fallo se apunta en `fuentes_fallidas` y no tumba la ejecución | `sources.descargar` |
| 3 | Filtra entradas más antiguas que `VENTANA_HORAS` (26 por defecto). Normaliza a `Item`: id = sha1 de la URL (16 hex), resumen sin HTML y cortado a 500 caracteres, imagen de `media_content`, `media_thumbnail`, `enclosures` o primer `<img>` | `sources.descargar`, `_limpiar`, `_imagen` |
| 4 | Deduplica por URL dentro de la tanda | `sources.recoger` |
| 5 | Descarta ids presentes en `data/seen.json` (ver aviso en 4.6) | `build.py:104-106` |
| 6 | Si no hay nada nuevo: solo actualiza `comprobado_en` en `latest.json` y termina | `build.py:108-116` |
| 7 | Una única llamada a Gemini con todos los candidatos (id, título, fuente, resumen a 300 caracteres). Devuelve `[{id, categoria, posicion}]` | `llm.seleccionar`, `llm._llamar` |
| 8 | Valida la respuesta: ids desconocidos se ignoran, categorías inválidas pasan a `industria`, items olvidados por el LLM van a `industria` con posición 99 | `llm.py:117-135` |
| 9 | Aplica cuotas por categoría y tope por fuente para marcar `destacado` | `build.marcar_destacados` |
| 10 | Para los destacados descarga la página original y extrae el texto con trafilatura. Menos de 400 caracteres se descarta (paywall o consentimiento). Si el feed no traía imagen, usa `og:image` | `extract.procesar`, `extract.extraer` |
| 11 | Escribe `data/AAAA-MM-DD.json`, acumulando sobre la pasada anterior del mismo día, y una copia idéntica en `data/latest.json` | `build.py:125-149` |
| 12 | Poda días con más de 30 días y artículos huérfanos | `build.podar_ficheros` |
| 13 | Regenera `data/index.json` con la lista de días y el tamaño total | `build.py:153-157` |
| 14 | Marca como vistos los items procesados y poda `seen.json` a 30 días | `build.py:161-163` |

### 2.3 Commit

El último paso de `brief.yml` hace `git add data/` y commit como `brief-bot`
solo si hay cambios. Necesita `permissions: contents: write`.

### 2.4 Despliegue

`.github/workflows/pages.yml`

- Se dispara con push a `main`, al terminar el workflow `"brief diario"` (`workflow_run`) o a mano.
- El `workflow_run` hace falta porque un push hecho con `GITHUB_TOKEN` no dispara otros workflows.
- Hace `npm ci` y `npm run build` en `app/`, copia `data/` dentro de `app/dist/data` y publica en Pages.

### 2.5 App (`app/src/`)

| Fichero | Papel |
|---|---|
| `main.jsx` | Monta `<App>` e importa `styles.css` |
| `data.js` | `fetch` de `data/latest.json`, `data/{día}.json`, `data/index.json` y `data/articles/{id}.json`, siempre relativo a `import.meta.env.BASE_URL`. Utilidades de fecha en `es-ES` |
| `guardados.js` | Guardados en `localStorage`, con texto completo para un máximo de 25 |
| `App.jsx` | Pestañas archivo / hoy / guardados, filtros por categoría, lista con swipe para guardar, lector, avisos y la lluvia de glifos de fondo |
| `styles.css` | Tokens de color, tipografía IBM Plex y todos los estilos |
| `vite.config.js` | Base path, manifest PWA y caché del service worker (`NetworkFirst` para `/data/`, excluido del `navigateFallback`) |

La app avisa si el brief no es de hoy, si el modo es degradado o si hubo
fuentes con fallo (`App.jsx:267-273`).

---

## 3. Formato de los datos

### 3.1 Item

Definido por la dataclass `Item` en `pipeline/sources.py:21-33`.

| Campo | Tipo | Origen |
|---|---|---|
| `id` | string, 16 hex | sha1 de la URL |
| `url` | string | feed |
| `titulo` | string | feed, sin tocar |
| `fuente` | string | `title` del OPML |
| `publicado` | ISO 8601 UTC | feed; si falta, hora de ejecución |
| `resumen` | string ≤ 500 | feed, sin etiquetas HTML |
| `categoria` | string | LLM, validada contra `CATEGORIAS` |
| `posicion` | int | LLM, ranking dentro de su categoría; 99 si falta |
| `destacado` | bool | Python, por cuotas |
| `imagen` | string | feed u `og:image` |
| `texto_disponible` | bool | true si existe `data/articles/{id}.json` |

### 3.2 `data/latest.json` y `data/AAAA-MM-DD.json`

Mismo formato. `latest.json` es una copia del último día escrito.

```json
{
  "generado_en": "2026-10-03T09:36:27+00:00",
  "modo": "normal | degradado",
  "fuentes_fallidas": ["Import AI: HTTPError"],
  "candidatos": 29,
  "destacados": 8,
  "items": [ { "...": "Item" } ],
  "comprobado_en": "2026-10-03T09:36:27+00:00"
}
```

- `candidatos` suma los nuevos de esta pasada y los acumulados del día.
- `comprobado_en` es la última vez que corrió el pipeline. Cuando no hay nada nuevo solo se actualiza este campo, y solo en `latest.json`. La app lo usa para decidir si el brief está al día.
- Orden de `items`: primero los nuevos de esta pasada, destacados delante, por categoría y posición; después los de la pasada anterior.

### 3.3 `data/index.json`

```json
{ "dias": ["2026-10-03", "2026-10-02", "..."], "bytes": 1234567 }
```

Días disponibles, del más reciente al más antiguo, y peso total de `data/`.
La app también acepta el formato antiguo de array plano (`data.js:13`).

### 3.4 `data/articles/{id}.json`

```json
{ "id": "00a6b30dd37a4a14", "texto": "texto plano extraído, párrafos separados por \n" }
```

Solo existen para destacados con extracción correcta. La app los pide con
`force-cache` porque no cambian.

### 3.5 `data/seen.json`

Mapa `{ id: fecha_iso }` de lo ya procesado. Está en `.gitignore` (ver 4.6).

---

## 4. Decisiones de diseño

### 4.1 El LLM no genera texto visible

Todo lo que se lee sale del medio: títulos, resúmenes y textos extraídos.
El modelo solo devuelve `id`, `categoria` y `posicion`. Así no hay
alucinaciones en lo publicado, el coste en tokens de salida es mínimo y un
fallo del modelo degrada la selección, no el contenido. Refuerzo en código:
los ids que no venían en la entrada se descartan (`llm.py:120-122`).

### 4.2 El LLM clasifica, Python corta

El prompt pide clasificar **todos** los items y ordenarlos dentro de cada
categoría (`llm.py:43-46`). Las cuotas (`build.py:34-40`) y el tope de dos
items por fuente (`build.py:41`) los aplica `marcar_destacados`. Ventajas:

- Las cuotas son deterministas y se cambian sin tocar el prompt.
- Los LLM cuentan mal y no respetan límites de forma fiable.
- Lo no destacado sigue disponible en "ver los otros N".
- Una sola llamada con todo: para priorizar, el modelo necesita ver los candidatos juntos.

### 4.3 Acumulación mañana / tarde

La segunda pasada del día lee el fichero del día y añade lo nuevo delante,
sin duplicar ids (`build.py:128-135`). Los destacados de la mañana conservan
su marca, así que un día puede sumar dos tandas de cuotas. Las cuotas de la
tarde no descuentan lo que ya destacó la mañana.

### 4.4 Poda a 30 días

`RETENCION_DIAS = 30` (`build.py:32`) controla tres cosas: ficheros de día,
artículos que ya no referencia ningún día y entradas de `seen.json`. Mantiene
acotados el repo y el despliegue de Pages. La app muestra el peso en la
pestaña archivo.

### 4.5 Fallbacks

| Fallo | Comportamiento | Dónde |
|---|---|---|
| Feed caído, 404, timeout | Se apunta en `fuentes_fallidas` y se sigue | `sources.descargar` |
| XML inválido sin entradas | Igual | `sources.py:104-105` |
| Sin `GEMINI_API_KEY` | Modo degradado | `llm.py:97-100` |
| Error 429 o 5xx del LLM | 4 intentos con esperas de 3, 6 y 12 s | `llm._llamar` |
| Error 4xx permanente o JSON roto | Modo degradado | `llm.py:111-115` |
| JSON envuelto en markdown | Se limpia y se busca el array | `llm._extraer_json` |
| Categoría desconocida | Pasa a `industria` | `llm.py:124` |
| Item olvidado por el LLM | `industria`, posición 99 | `llm.py:132-135` |
| Modo degradado | Orden por fecha, se destacan los 8 más recientes, sin cuotas | `llm._degradado`, `build.py:46-50` |
| Extracción fallida o corta | Sin texto: el lector muestra el resumen y enlaza al original | `extract.extraer`, `App.jsx:94-107` |
| Imagen rota | Se oculta | `App.jsx:91` |
| `localStorage` lleno | Reintenta guardar sin texto | `guardados.js:34-40` |
| `seen.json` incompleto | Solo se marca lo procesado: si un feed falla, sus items entran en la siguiente pasada | `build.py:159-163` |

### 4.6 Avisos detectados al leer el código

No se han corregido. Conviene decidir antes de clonar.

- **`seen.json` no se persiste en Actions.** Está en `.gitignore` y cada ejecución parte de un checkout limpio, así que en CI el filtro de vistos siempre está vacío. La deduplicación real la hacen la ventana de 26 h y la fusión por id dentro del mismo día. Un artículo publicado a última hora puede aparecer dos días seguidos. Para activarlo hay que quitar `data/seen.json` del `.gitignore`.
- **Modo degradado frecuente.** La mayoría de los días desde el 2026-09-20 están en modo degradado. El repo no guarda los logs; la causa está en el log del paso "Generar el brief" de Actions.
- **`GEMINI_MODEL` vacío.** Si la variable de repo no existe, Actions pasa una cadena vacía. `os.getenv("GEMINI_MODEL", …)` devuelve entonces `""` y no el valor por defecto, y la URL del modelo queda rota.
- **README desactualizado.** Dice que el modelo por defecto es `gemini-2.5-flash`, pero el código usa `gemini-3.5-flash` (`llm.py:21`). La variable `MAXIMO_ITEMS` del README no se usa.
- **Número mágico.** El modo degradado destaca 8 items fijos (`build.py:48`), sin relación con la suma de cuotas, que es 11.
- **Restos de plantilla.** `app/src/assets/hero.png`, `react.svg`, `vite.svg` y `app/public/icons.svg` no se usan. `app/README.md` es el de la plantilla de Vite. `app/index.html` tiene `lang="en"` y `<title>app</title>`.
- **CSS duplicado.** La regla `.item` aparece dos veces (`styles.css:59` y `styles.css:133`); gana la segunda.

---

## 5. Qué es genérico y qué es específico del dominio

### 5.1 Genérico: se reutiliza tal cual

| Fichero | Contenido |
|---|---|
| `pipeline/sources.py` | Lectura de OPML, descarga, normalización e imágenes |
| `pipeline/extract.py` | Extracción con trafilatura y `og:image` |
| `pipeline/llm.py` | `_extraer_json`, `_llamar` con reintentos, validación de la respuesta y `_degradado` |
| `pipeline/build.py` | Carga de `.env`, flujo de `main`, acumulación, poda, `index.json` y `seen.json` |
| `app/src/data.js` | Carga de JSON relativa al base path |
| `app/src/guardados.js` | Guardados en `localStorage` |
| `App.jsx`, estructura | Componentes `Item`, `Lector`, `Archivo`, `Guardados`, `Tabs` y la lógica de filtros |
| `requirements.txt`, `app/package.json` | Dependencias |
| `pages.yml` | Build y despliegue, salvo el nombre del workflow que escucha |
| Formato de datos | Todo el contrato de la sección 3 |
| `.claude/settings.json` | Permisos de Claude Code |

### 5.2 Específico del dominio: hay que cambiarlo

**Fuentes y criterio editorial**

| Qué | Dónde |
|---|---|
| Lista de feeds | `feeds.opml`, todo el fichero. El `title` de cada `outline` es lo que se ve como fuente |
| Prompt editorial: rol, lector, qué priorizar y qué rebajar | `pipeline/llm.py:24-32`, constante `CRITERIO` |
| Definición de categorías y desempate | `pipeline/llm.py:34-41`, dentro de `CRITERIO` |
| Modelo por defecto | `pipeline/llm.py:21`, `MODELO` |
| Proveedor de LLM | `pipeline/llm.py:22` `ENDPOINT`, y cuerpo, cabecera y lectura de respuesta en `_llamar` (`llm.py:68-83`). Solo si cambias de Gemini |
| Cuotas por categoría | `pipeline/build.py:34-40`, `CUOTAS` |
| Tope por fuente | `pipeline/build.py:41`, `MAX_POR_FUENTE` |
| Ventana y retención | `build.py:31` `VENTANA_HORAS`, `build.py:32` `RETENCION_DIAS` |
| Horas de ejecución | `.github/workflows/brief.yml:7-8` |
| Nombre del workflow | `brief.yml:1`. Si cambia, hay que cambiar también `pages.yml:7` |
| Autor y mensaje del commit | `brief.yml:39-45` |

**Identidad de la app**

| Qué | Dónde |
|---|---|
| Base path | `app/vite.config.js:6` `base` y `:14` `start_url`. Debe ser `/<nombre-del-repo>/` |
| Nombre y colores de la PWA | `vite.config.js:12-17` (`name`, `short_name`, `background_color`, `theme_color`) |
| Nombre de la caché | `vite.config.js:25`, `cacheName: 'brief-data'` |
| Título e idioma del HTML | `app/index.html:2` y `:7` |
| Favicon | `app/public/favicon.svg` |
| Clave de `localStorage` | `app/src/guardados.js:1`, `CLAVE`. Hay que cambiarla si ambos briefs viven bajo el mismo dominio `<usuario>.github.io`, porque comparten `localStorage` |
| Textos de interfaz | `App.jsx:252` saludo, `:260` prompt `~/hoy`, `:135` aviso de 30 días, y el resto de literales en español |

**Estilo visual**

| Qué | Dónde |
|---|---|
| Paleta base: fondo, texto y acento verde | `app/src/styles.css:6-8` |
| Color por categoría | `styles.css:9-10`, variables `--c-<categoria>` |
| Tipografías | `styles.css:1` (Google Fonts) y `:11-12` |
| Fondo de la barra inferior, color fijo | `styles.css:115`, `rgba(7,9,8,.72)` |
| Líneas de escáner | `styles.css:21-22`, `body::after` |
| Lluvia de glifos: caracteres, fuente y color fijo | `App.jsx:319` `GLIFOS`, `App.jsx:331` fuente, `App.jsx:340` `rgba(76,224,126,…)` |
| Iconos de categoría | `App.jsx:7-13`, `ICONOS` |

Los colores de `App.jsx:340` y `styles.css:115` no usan variables CSS.
Al cambiar de paleta hay que tocarlos a mano.

---

## 6. Dónde están definidas las categorías

Las categorías están repetidas en **seis sitios** y deben coincidir
exactamente, en minúsculas y sin tildes, porque se usan como claves y como
nombres de variables CSS.

| # | Fichero:línea | Qué define | Si no coincide |
|---|---|---|---|
| 1 | `pipeline/llm.py:19` | `CATEGORIAS`, lista válida | Lo que el LLM devuelva fuera de la lista pasa a la categoría comodín |
| 2 | `pipeline/llm.py:34-41` | Descripción de cada categoría en el prompt `CRITERIO` | El LLM clasifica con nombres que luego se rechazan |
| 3 | `pipeline/llm.py:124`, `:134` y `:146` | Categoría comodín `"industria"`, escrita tres veces | Items en una categoría sin cuota ni color |
| 4 | `pipeline/build.py:34-40` | `CUOTAS`, una entrada por categoría | Una categoría sin cuota nunca se destaca |
| 5 | `app/src/App.jsx:5` y `:7-13` | `CATS`, orden de los filtros, e `ICONOS` | Filtro sin icono, o categoría sin filtro |
| 6 | `app/src/styles.css:9-10` | `--c-<categoria>`, color del punto y del filtro | Punto y filtro sin color |

Además `README.md:45` usa una categoría como ejemplo.

Al clonar conviene unificarlas en un único sitio. Una opción sencilla es que
`build.py` escriba `data/categorias.json` con nombre, cuota, color e icono, y
que la app lo lea. Así el pipeline sería la única fuente de verdad. Sin ese
cambio, renombrar una categoría exige tocar los seis sitios.

Ejemplo orientativo para paid media: `plataformas` (cambios en Meta, Google,
TikTok, Amazon), `medicion` (atribución, privacidad, cookies), `creatividad`,
`estrategia` y `mercado` como comodín.

---

## 7. Checklist para clonar

### Repositorio

- [ ] Crear el repo nuevo. Público si quieres minutos de Actions ilimitados.
- [ ] Copiar el código **sin** `data/`, `.env`, `.venv/`, `app/node_modules/` ni `app/public/data/`. El pipeline crea `data/` en su primera ejecución.
- [ ] Revisar `.gitignore` y decidir si `data/seen.json` se versiona (ver 4.6).
- [ ] Sustituir `feeds.opml` por las fuentes del nuevo dominio.
- [ ] Reescribir `CRITERIO`, `CATEGORIAS`, `CUOTAS` y la categoría comodín (sección 6).
- [ ] Ajustar colores, tipografía, iconos, glifos y textos (sección 5.2).
- [ ] Actualizar `README.md` y sustituir `app/README.md`.

### Secrets y variables

- [ ] Settings → Secrets and variables → Actions → Secrets: crear `GEMINI_API_KEY` con una clave de Google AI Studio.
- [ ] En la pestaña Variables, crear `GEMINI_MODEL` con un nombre de modelo vigente. Si no existe, llega vacía (ver 4.6).
- [ ] En local, crear `.env` con `GEMINI_API_KEY`. Nunca se sube.

### Permisos de Actions

- [ ] Settings → Actions → General → Workflow permissions → **Read and write permissions**. Sin esto falla el commit de datos.
- [ ] Confirmar que Actions está habilitado en el repo.

### GitHub Pages

- [ ] Settings → Pages → Source: **GitHub Actions**.
- [ ] Si cambias el nombre del workflow del pipeline, actualiza `pages.yml:7`.

### Base path de Vite

- [ ] `app/vite.config.js:6` `base` y `:14` `start_url` deben valer `/<nombre-del-repo>/`, con ambas barras.
- [ ] Con dominio propio o un repo `<usuario>.github.io`, el base es `/`.
- [ ] Revisar manifest, `index.html`, favicon y clave de `localStorage` (sección 5.2).

### Settings de Claude Code

`.claude/settings.json` está versionado y es genérico. Define:

- **deny:** leer `.env`, `.env.*`, `*.pem` y `*.key`; `printenv` y `env`; editar `data/**`, que solo escribe el pipeline.
- **ask:** `git commit`, `git push`, `rm`, editar `.github/**` y ejecutar el pipeline, que consume cuota del LLM.
- **allow:** `npm run *`, `git status` y `git diff`.

- [ ] Copiarlo tal cual al repo nuevo.
- [ ] Los ajustes personales van en `.claude/settings.local.json`, que no debe subirse.

### Primera ejecución

- [ ] Actions → "brief diario" → Run workflow.
- [ ] En el log, comprobar `recogidos N items`, el modo y las fuentes con fallo.
- [ ] Comprobar que aparece el commit en `data/` y que "desplegar app" termina en verde.
- [ ] Abrir `https://<usuario>.github.io/<repo>/` y revisar avisos, filtros y lector.
- [ ] En local: `cd app && npm run dev`. Para ver datos, copiar `data/` a `app/public/data/`, que está ignorado.

"""Punto de entrada del pipeline. Se ejecuta dos veces al dia desde GitHub Actions."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import extract, llm, sources
from .categorias import CUOTAS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("brief")

RAIZ = Path(__file__).resolve().parent.parent
OPML = RAIZ / "feeds.opml"
DATOS = RAIZ / "data"
SEEN = DATOS / "seen.json"
ARTICULOS = DATOS / "articles"

# Carga .env si existe (solo en local; en Actions va por secrets).
_env = RAIZ / ".env"
if _env.exists():
    for _linea in _env.read_text(encoding="utf-8").splitlines():
        _linea = _linea.strip()
        if _linea and not _linea.startswith("#") and "=" in _linea:
            _k, _v = _linea.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

VENTANA_HORAS = int(os.getenv("VENTANA_HORAS", "26"))
RETENCION_DIAS = 30

# Las cuotas por categoria vienen de categorias.json (ver pipeline/categorias.py).
MAX_POR_FUENTE = 2


def marcar_destacados(items: list, uso_llm: bool = True) -> list:
    """Marca los que entran en cuota de categoria, con tope por fuente."""
    if not uso_llm:
        # Sin clasificacion real no hay cuotas que aplicar: se destacan los mas
        # recientes, tantos como suman las cuotas (items llega ya ordenado por fecha).
        for it in items[:sum(CUOTAS.values())]:
            it.destacado = True
        return items

    usados = {cat: 0 for cat in CUOTAS}
    por_fuente: dict[str, int] = {}

    for it in sorted(items, key=lambda x: (x.posicion, x.fuente)):
        if usados.get(it.categoria, 0) >= CUOTAS.get(it.categoria, 0):
            continue
        if por_fuente.get(it.fuente, 0) >= MAX_POR_FUENTE:
            continue
        it.destacado = True
        usados[it.categoria] += 1
        por_fuente[it.fuente] = por_fuente.get(it.fuente, 0) + 1

    return sorted(items, key=lambda x: (not x.destacado, x.categoria, x.posicion))


def _leer_json(ruta: Path, tipo: type):
    """Devuelve el contenido si existe, se puede leer y es del tipo esperado.

    Un fichero corrupto no debe bloquear las ejecuciones siguientes: se registra
    el error y el llamador decide como seguir (devuelve None).
    """
    if not ruta.exists():
        return None
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        log.error("no se pudo leer %s: %s", ruta.name, exc)
        return None
    if not isinstance(datos, tipo):
        log.error("%s no tiene el formato esperado: %s", ruta.name, type(datos).__name__)
        return None
    return datos


def _escribir(ruta: Path, texto: str) -> None:
    """Escritura atomica: un corte a mitad nunca deja el fichero a medias."""
    fd, tmp = tempfile.mkstemp(dir=ruta.parent, prefix=f".{ruta.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(texto)
        os.replace(tmp, ruta)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _items_validos(lista) -> list[dict]:
    """Descarta lo que no sea un item con id, para no romper la fusion ni la poda."""
    if not isinstance(lista, list):
        return []
    return [i for i in lista if isinstance(i, dict) and isinstance(i.get("id"), str)]


def cargar_seen() -> dict[str, str]:
    datos = _leer_json(SEEN, dict)
    if datos is None:
        if SEEN.exists():
            log.warning("seen.json ilegible: se empieza de cero")
        return {}
    return {k: v for k, v in datos.items() if isinstance(v, str)}


def podar_seen(seen: dict[str, str]) -> dict[str, str]:
    corte = (datetime.now(timezone.utc) - timedelta(days=RETENCION_DIAS)).isoformat()
    return {k: v for k, v in seen.items() if v > corte}


def guardar_seen(seen: dict[str, str]) -> None:
    _escribir(SEEN, json.dumps(podar_seen(seen), indent=0))


def podar_ficheros() -> None:
    """Borra dias con mas de 30 dias y los articulos que ya no referencia nadie."""
    corte = (datetime.now(timezone.utc) - timedelta(days=RETENCION_DIAS)).strftime("%Y-%m-%d")
    vivos: set[str] = set()
    ilegibles = 0

    for f in DATOS.glob("20*.json"):
        if f.stem < corte:
            f.unlink()
            log.info("podado %s", f.name)
            continue
        datos = _leer_json(f, dict)
        if datos is None:
            ilegibles += 1
            continue
        for i in _items_validos(datos.get("items")):
            vivos.add(i["id"])

    # Si un dia no se puede leer no sabemos que articulos referencia:
    # mejor no borrar ninguno que borrar los de ese dia.
    if ilegibles:
        log.warning("%d ficheros de dia ilegibles: no se podan articulos", ilegibles)
        return

    if ARTICULOS.exists():
        for f in ARTICULOS.glob("*.json"):
            if f.stem not in vivos:
                f.unlink()


def main() -> None:
    DATOS.mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc)
    ahora_iso = ahora.isoformat()
    latest = DATOS / "latest.json"

    items, fallos = sources.recoger(OPML, VENTANA_HORAS)
    log.info("recogidos %d items, %d fuentes con fallo", len(items), len(fallos))

    seen = cargar_seen()

    # Las entradas sin fecha no salen nunca de la ventana: mientras el feed las
    # siga publicando se refresca su marca, para que la poda de seen.json a
    # 30 dias no las suelte y vuelvan a entrar como nuevas.
    for it in items:
        if it.sin_fecha and it.id in seen:
            seen[it.id] = ahora_iso

    nuevos = [it for it in items if it.id not in seen]
    log.info("%d nuevos tras deduplicar", len(nuevos))

    if not nuevos:
        log.info("nada nuevo")
        actual = _leer_json(latest, dict)
        if actual is not None:
            actual["comprobado_en"] = ahora_iso
            _escribir(latest, json.dumps(actual, ensure_ascii=False, indent=1))
        guardar_seen(seen)
        return

    clasificados, uso_llm = llm.seleccionar(nuevos)
    modo = "normal" if uso_llm else "degradado"
    ordenados = marcar_destacados(clasificados, uso_llm)

    destacados = [it for it in ordenados if it.destacado]
    n = extract.procesar(destacados, ARTICULOS)
    log.info("texto extraido de %d de %d destacados", n, len(destacados))

    dia = ahora.strftime("%Y-%m-%d")
    fichero_dia = DATOS / f"{dia}.json"

    # Si ya hay un brief de hoy (la pasada de la manana), acumulamos sobre el.
    # Si esta corrupto, _leer_json lo registra y se empieza el dia de cero.
    previo = _leer_json(fichero_dia, dict) or {}
    previos = _items_validos(previo.get("items"))

    # Historial de pasadas del dia. Un fichero anterior a este campo aporta su
    # unica pasada a partir de los campos de nivel superior.
    pasadas = previo.get("pasadas")
    if not isinstance(pasadas, list):
        pasadas = []
        if previo.get("generado_en"):
            pasadas.append({
                "hora": previo["generado_en"],
                "modo": previo.get("modo", ""),
                "fuentes_fallidas": previo.get("fuentes_fallidas", []),
            })
    pasadas.append({"hora": ahora_iso, "modo": modo, "fuentes_fallidas": fallos})

    nuevos_dict = [it.dict() for it in ordenados]
    ids_nuevos = {i["id"] for i in nuevos_dict}
    todos = nuevos_dict + [i for i in previos if i["id"] not in ids_nuevos]

    # "modo" y "fuentes_fallidas" son los de la ultima pasada, como espera la app.
    # El detalle de cada pasada queda en "pasadas".
    salida = {
        "generado_en": ahora_iso,
        "modo": modo,
        "fuentes_fallidas": fallos,
        "candidatos": len(nuevos) + len(previos),
        "destacados": sum(1 for i in todos if i.get("destacado")),
        "items": todos,
        "comprobado_en": ahora_iso,
        "pasadas": pasadas,
    }

    texto_json = json.dumps(salida, ensure_ascii=False, indent=1)
    _escribir(fichero_dia, texto_json)
    _escribir(latest, texto_json)

    podar_ficheros()

    dias = sorted((f.stem for f in DATOS.glob("20*.json")), reverse=True)
    bytes_totales = sum(f.stat().st_size for f in DATOS.rglob("*.json"))
    _escribir(DATOS / "index.json", json.dumps({"dias": dias, "bytes": bytes_totales}, indent=0))

    # IMPORTANTE: solo se marca como visto lo que se ha procesado de verdad.
    # Si un feed fallo hoy, sus items entraran manana en vez de perderse.
    # En modo degradado tampoco se marcan: la siguiente pasada los reclasifica
    # y la fusion por id sustituye su version degradada en el fichero del dia.
    if uso_llm:
        for it in nuevos:
            seen[it.id] = ahora_iso
    else:
        log.warning("modo degradado: %d items quedan sin marcar para reclasificarlos",
                    len(nuevos))
    guardar_seen(seen)

    log.info("brief con %d destacados de %d (modo %s)",
             salida["destacados"], len(todos), salida["modo"])


if __name__ == "__main__":
    main()
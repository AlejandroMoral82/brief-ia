"""Punto de entrada del pipeline. Se ejecuta una vez al dia desde GitHub Actions."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import llm, sources

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("brief")

RAIZ = Path(__file__).resolve().parent.parent
OPML = RAIZ / "feeds.opml"
DATOS = RAIZ / "data"
SEEN = DATOS / "seen.json"
RETENCION_DIAS = 30

# Carga .env si existe (solo en local; en Actions va por secrets).
_env = RAIZ / ".env"
if _env.exists():
    for _linea in _env.read_text(encoding="utf-8").splitlines():
        _linea = _linea.strip()
        if _linea and not _linea.startswith("#") and "=" in _linea:
            _k, _v = _linea.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

VENTANA_HORAS = int(os.getenv("VENTANA_HORAS", "26"))   # margen sobre 24h
CUOTAS = {
    "modelos": 3,
    "herramientas": 3,
    "investigacion": 2,
    "opinion": 2,
    "industria": 1,
}
MAX_POR_FUENTE = 2


def marcar_destacados(items: list, uso_llm: bool = True) -> list:
    """Marca los que entran en cuota de categoria, con tope por fuente."""
    if not uso_llm:
        # Sin clasificacion real no hay cuotas que aplicar: los 8 mas recientes.
        for it in items[:8]:
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


def cargar_seen() -> dict[str, str]:
    if SEEN.exists():
        return json.loads(SEEN.read_text(encoding="utf-8"))
    return {}


def podar(seen: dict[str, str]) -> dict[str, str]:
    corte = (datetime.now(timezone.utc) - timedelta(days=RETENCION_DIAS)).isoformat()
    return {k: v for k, v in seen.items() if v > corte}


def main() -> None:
    DATOS.mkdir(exist_ok=True)
    ahora = datetime.now(timezone.utc)

    items, fallos = sources.recoger(OPML, VENTANA_HORAS)
    log.info("recogidos %d items, %d fuentes con fallo", len(items), len(fallos))

    seen = cargar_seen()
    nuevos = [it for it in items if it.id not in seen]
    log.info("%d nuevos tras deduplicar", len(nuevos))

    if not nuevos:
        log.info("nada nuevo, no se escribe nada")
        return

    clasificados, uso_llm = llm.seleccionar(nuevos)
    ordenados = marcar_destacados(clasificados, uso_llm)
    salida = {
        "generado_en": ahora.isoformat(),
        "modo": "normal" if uso_llm else "degradado",
        "fuentes_fallidas": fallos,
        "candidatos": len(nuevos),
        "destacados": sum(1 for it in ordenados if it.destacado),
        "items": [it.dict() for it in ordenados],
    }

    dia = ahora.strftime("%Y-%m-%d")
    (DATOS / f"{dia}.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (DATOS / "latest.json").write_text(
        json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    dias = sorted((f.stem for f in DATOS.glob("20*.json")), reverse=True)[:90]
    (DATOS / "index.json").write_text(json.dumps(dias, indent=0), encoding="utf-8")

    # IMPORTANTE: solo se marca como visto lo que se ha procesado de verdad.
    # Si un feed fallo hoy, sus items entraran manana en vez de perderse.
    for it in nuevos:
        seen[it.id] = ahora.isoformat()
    SEEN.write_text(json.dumps(podar(seen), indent=0), encoding="utf-8")

    log.info("escritos %d destacados de %d (modo %s)",
             salida["destacados"], len(ordenados), salida["modo"])


if __name__ == "__main__":
    main()

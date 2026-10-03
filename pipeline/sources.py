"""Lectura del OPML, descarga de feeds y normalizacion de items."""

from __future__ import annotations

import hashlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import html as htmlmod

log = logging.getLogger(__name__)

# User-Agent de navegador para feeds y paginas: algunos medios rechazan el de requests.
# extract.py lo importa de aqui.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
)
TIMEOUT = 20


@dataclass
class Item:
    id: str
    url: str
    titulo: str
    fuente: str
    publicado: str          # ISO 8601 UTC
    resumen: str            # texto del propio feed, nunca generado
    categoria: str = ""     # la asigna el LLM
    posicion: int = 0       # la asigna el LLM
    destacado: bool = False
    imagen: str = ""
    texto_disponible: bool = False
    sin_fecha: bool = False  # el feed no da fecha: "publicado" es la hora de descarga

    def dict(self) -> dict:
        return asdict(self)


def leer_opml(ruta: Path) -> list[tuple[str, str]]:
    """Devuelve [(nombre, url_del_feed)] a partir del OPML."""
    raiz = ET.parse(ruta).getroot()
    feeds: list[tuple[str, str]] = []
    for nodo in raiz.iter("outline"):
        url = nodo.get("xmlUrl")
        if url:
            feeds.append((nodo.get("title") or nodo.get("text") or url, url))
    return feeds


def _hash(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def _fecha(entrada) -> datetime | None:
    for campo in ("published_parsed", "updated_parsed"):
        t = getattr(entrada, campo, None)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None


def _limpiar(texto_html: str, limite: int = 500) -> str:
    """Quita etiquetas y decodifica entidades HTML. No reescribe nada."""
    import re

    texto = re.sub(r"<[^>]+>", " ", texto_html or "")
    texto = htmlmod.unescape(texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto[:limite]

def _imagen(entrada) -> str:
    """Busca la imagen de portada en los campos habituales del feed."""
    import re

    for m in getattr(entrada, "media_content", []) or []:
        if m.get("url"):
            return m["url"]
    for m in getattr(entrada, "media_thumbnail", []) or []:
        if m.get("url"):
            return m["url"]
    for enc in getattr(entrada, "enclosures", []) or []:
        if enc.get("type", "").startswith("image/") and enc.get("href"):
            return enc["href"]

    # Algunos feeds solo la incluyen dentro del HTML del contenido.
    html = ""
    for c in getattr(entrada, "content", []) or []:
        html += c.get("value", "")
    html += getattr(entrada, "summary", "")
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    if m and not m.group(1).startswith("data:"):
        return m.group(1)
    return ""

def descargar(nombre: str, url: str, horas: int) -> tuple[list[Item], str | None]:
    """Descarga un feed. Devuelve (items, error). Nunca lanza excepcion."""
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # red, DNS, 404, timeout...
        log.warning("fallo %s: %s", nombre, exc)
        return [], f"{nombre}: {type(exc).__name__}"

    if parsed.bozo and not parsed.entries:
        return [], f"{nombre}: XML invalido"

    corte = datetime.now(timezone.utc) - timedelta(hours=horas)
    items: list[Item] = []

    for e in parsed.entries:
        enlace = getattr(e, "link", None)
        titulo = getattr(e, "title", None)
        if not enlace or not titulo:
            continue

        fecha = _fecha(e)
        if fecha and fecha < corte:
            continue

        items.append(
            Item(
                id=_hash(enlace),
                url=enlace,
                titulo=htmlmod.unescape(titulo).strip(),
                fuente=nombre,
                publicado=(fecha or datetime.now(timezone.utc)).isoformat(),
                resumen=_limpiar(getattr(e, "summary", "")),
                imagen=htmlmod.unescape(_imagen(e)),
                # Sin fecha no se puede filtrar por ventana: build.py mantiene
                # su id en seen.json mientras el feed lo siga publicando.
                sin_fecha=fecha is None,
            )
        )

    return items, None


def recoger(opml: Path, horas: int) -> tuple[list[Item], list[str]]:
    """Recorre todos los feeds del OPML. Un feed caido no tumba la ejecucion."""
    items: list[Item] = []
    fallos: list[str] = []
    vistos_url: set[str] = set()

    for nombre, url in leer_opml(opml):
        nuevos, error = descargar(nombre, url, horas)
        if error:
            fallos.append(error)
            continue
        for it in nuevos:
            if it.url not in vistos_url:      # dedup dentro de la misma tanda
                vistos_url.add(it.url)
                items.append(it)
        log.info("%s: %d items", nombre, len(nuevos))

    return items, fallos

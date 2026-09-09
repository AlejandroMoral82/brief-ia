"""Extraccion del texto completo de los articulos destacados.

Nunca genera contenido: solo recupera el texto que el medio ya publica.
Si falla, el item se queda sin texto y la app enlaza al original.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

import requests
import trafilatura

log = logging.getLogger(__name__)

TIMEOUT = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0 Safari/537.36")


def _og_image(html: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html
    ) or re.search(
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html
    )
    return m.group(1) if m else ""


def extraer(url: str) -> tuple[str, str]:
    """Devuelve (texto, imagen). Cadenas vacias si no se pudo."""
    try:
        resp = requests.get(url, timeout=TIMEOUT, headers={"User-Agent": UA})
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        log.warning("no se pudo descargar %s: %s", url[:60], type(exc).__name__)
        return "", ""

    try:
        texto = trafilatura.extract(
            html, include_comments=False, include_tables=False, favor_precision=True
        ) or ""
    except Exception as exc:
        log.warning("trafilatura fallo en %s: %s", url[:60], type(exc).__name__)
        texto = ""

    # Menos de 400 caracteres suele ser un paywall o una pagina de consentimiento.
    if len(texto) < 400:
        texto = ""

    return texto, _og_image(html)


def procesar(items: list, destino: Path) -> int:
    """Extrae el texto de los items dados y lo guarda uno por fichero."""
    destino.mkdir(parents=True, exist_ok=True)
    hechos = 0

    for it in items:
        fichero = destino / f"{it.id}.json"
        if fichero.exists():
            it.texto_disponible = True
            hechos += 1
            continue

        texto, imagen = extraer(it.url)
        if imagen and not it.imagen:
            it.imagen = imagen
        if not texto:
            continue

        fichero.write_text(
            json.dumps({"id": it.id, "texto": texto}, ensure_ascii=False),
            encoding="utf-8",
        )
        it.texto_disponible = True
        hechos += 1

    return hechos
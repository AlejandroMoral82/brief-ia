"""Categorias del brief, leidas de categorias.json en la raiz del repo.

Es la unica fuente de verdad: el pipeline la usa para el prompt, la validacion
y las cuotas, y la app la importa para filtros, nombres y colores. Cambiar,
anadir o renombrar una categoria es editar ese fichero, nunca el codigo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

FICHERO = Path(__file__).resolve().parent.parent / "categorias.json"


def cargar(ruta: Path = FICHERO) -> dict:
    """Lee y valida el fichero. Un error aqui debe parar el pipeline: es configuracion."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    cats = datos.get("categorias")
    if not isinstance(cats, list) or not cats:
        raise ValueError(f"{ruta.name}: 'categorias' debe ser una lista no vacia")

    ids = []
    for c in cats:
        cid = c.get("id")
        if not isinstance(cid, str) or not re.fullmatch(r"[a-z0-9_]+", cid):
            raise ValueError(f"{ruta.name}: id invalido {cid!r} (minusculas, sin tildes ni espacios)")
        if not isinstance(c.get("descripcion"), str) or not c["descripcion"].strip():
            raise ValueError(f"{ruta.name}: '{cid}' necesita descripcion")
        if not isinstance(c.get("cuota"), int) or c["cuota"] < 0:
            raise ValueError(f"{ruta.name}: '{cid}' necesita una cuota entera >= 0")
        if not re.fullmatch(r"#[0-9A-Fa-f]{6}", str(c.get("color", ""))):
            raise ValueError(f"{ruta.name}: '{cid}' necesita un color #RRGGBB")
        ids.append(cid)

    if len(set(ids)) != len(ids):
        raise ValueError(f"{ruta.name}: ids repetidos")
    if datos.get("comodin") not in ids:
        raise ValueError(f"{ruta.name}: 'comodin' debe ser una de las categorias")
    return datos


_DATOS = cargar()

# Orden del fichero = orden en el prompt y en los filtros de la app.
CATEGORIAS: list[str] = [c["id"] for c in _DATOS["categorias"]]

# Categoria para lo que el LLM no clasifica o clasifica mal, y para el modo degradado.
COMODIN: str = _DATOS["comodin"]

CUOTAS: dict[str, int] = {c["id"]: c["cuota"] for c in _DATOS["categorias"]}


def bloque_prompt() -> str:
    """Seccion de categorias del prompt: una linea por categoria y las notas de desempate."""
    lineas = [f"- {c['id']}: {c['descripcion']}" for c in _DATOS["categorias"]]
    notas = _DATOS.get("notas_prompt") or []
    texto = "\n".join(lineas)
    if notas:
        texto += "\n\n" + "\n".join(notas)
    return texto

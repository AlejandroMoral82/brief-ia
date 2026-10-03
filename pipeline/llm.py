"""Seleccion y clasificacion con LLM.

El modelo NUNCA genera texto que se muestre al usuario: solo devuelve
que items entran, en que orden y con que categoria. Titulos y resumenes
son siempre los del feed original.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import unicodedata

import requests

from .categorias import CATEGORIAS, COMODIN, bloque_prompt

log = logging.getLogger(__name__)

MODELO = os.getenv("GEMINI_MODEL") or "gemini-3.5-flash"
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

# Criterio editorial. La lista de categorias y sus notas salen de categorias.json.
CRITERIO = """Eres el editor de un brief diario de IA para un desarrollador que
esta orientando su carrera hacia AI engineering.

Prioriza lo que cambia como se construyen aplicaciones con LLMs: modelos nuevos y
sus capacidades reales, herramientas y patrones de implementacion, resultados de
investigacion aplicables, y analisis con criterio de gente que sabe.

Rebaja rondas de financiacion, drama corporativo, predicciones sin sustancia y
notas de prensa sin contenido tecnico.

Categorias (asigna EXACTAMENTE UNA por item):
""" + bloque_prompt() + """

CLASIFICA TODOS los items que recibas. No descartes ninguno.
Dentro de cada categoria, ordena por relevancia: posicion 1 es el mas relevante
de esa categoria, 2 el siguiente, y asi. Las posiciones se cuentan por separado
en cada categoria.

Devuelve UNICAMENTE un array JSON, sin markdown ni texto alrededor:
[{"id": "...", "categoria": "...", "posicion": 1}]"""


# Fuerza el formato de salida: lista de {id, categoria, posicion}. El modelo
# no puede devolver ningun campo de texto libre que acabe en la interfaz.
ESQUEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "id": {"type": "STRING"},
            "categoria": {"type": "STRING", "format": "enum", "enum": CATEGORIAS},
            "posicion": {"type": "INTEGER"},
        },
        "required": ["id", "categoria", "posicion"],
    },
}

REINTENTABLES = (429, 500, 502, 503, 504)
INTENTOS = 4


def _normalizar(texto) -> str:
    """'Investigación ' -> 'investigacion'."""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def _validar(datos) -> list[dict]:
    """La respuesta debe ser una lista de objetos. Si no, se trata como fallo del LLM."""
    if not isinstance(datos, list):
        raise ValueError(f"se esperaba una lista y llego {type(datos).__name__}")
    malos = [f for f in datos if not isinstance(f, dict)]
    if malos:
        raise ValueError(f"{len(malos)} elementos de la lista no son objetos")
    return datos


def _extraer_json(texto: str) -> list[dict]:
    """El modelo a veces envuelve la respuesta en markdown o la precede de texto."""
    limpio = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(limpio)
    except json.JSONDecodeError:
        pass
    inicio, fin = limpio.find("["), limpio.rfind("]")
    if inicio != -1 and fin > inicio:
        return json.loads(limpio[inicio : fin + 1])
    raise ValueError("la respuesta no contiene un array JSON")


def _llamar(prompt: str, api_key: str) -> str:
    cuerpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json",
            "responseSchema": ESQUEMA,
        },
    }
    ultimo = None

    for intento in range(INTENTOS):
        try:
            resp = requests.post(
                ENDPOINT.format(m=MODELO),
                headers={"Content-Type": "application/json", "X-goog-api-key": api_key},
                json=cuerpo,
                timeout=90,
            )
        except requests.RequestException as exc:
            # Timeout, ConnectionError...: transitorio, se reintenta como un 5xx.
            ultimo = f"{type(exc).__name__}: {exc}"
            log.warning("intento %d fallido — %s", intento + 1, ultimo)
        else:
            if resp.ok:
                datos = resp.json()
                return datos["candidates"][0]["content"]["parts"][0]["text"]

            ultimo = f"{resp.status_code}: {resp.text[:300]}"
            log.warning("intento %d fallido — %s", intento + 1, ultimo)

            if resp.status_code not in REINTENTABLES:
                break                      # error permanente, no insistas

        if intento < INTENTOS - 1:
            time.sleep(2 ** intento * 3)   # 3s, 6s, 12s

    raise RuntimeError(ultimo or "sin respuesta")


def seleccionar(items: list) -> tuple[list, bool]:
    """Clasifica y ordena TODOS los items. El corte por cuotas lo hace build.py."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        log.warning("sin GEMINI_API_KEY, modo degradado")
        return _degradado(items), False

    if not items:
        return [], True

    catalogo = [
        {"id": it.id, "titulo": it.titulo, "fuente": it.fuente, "resumen": it.resumen[:300]}
        for it in items
    ]
    prompt = CRITERIO + "\n\nITEMS:\n" + json.dumps(catalogo, ensure_ascii=False)

    try:
        clasificados = _validar(_extraer_json(_llamar(prompt, api_key)))
    except Exception as exc:
        log.error("LLM fallo: %s", exc)
        return _degradado(items), False

    por_id = {it.id: it for it in items}
    salida = []
    for fila in clasificados:
        it = por_id.pop(str(fila.get("id", "")), None)
        if it is None:
            continue
        cat = _normalizar(fila.get("categoria", ""))
        it.categoria = cat if cat in CATEGORIAS else COMODIN
        try:
            it.posicion = int(fila.get("posicion", 99))
        except (TypeError, ValueError):
            it.posicion = 99
        salida.append(it)

    # Si el LLM clasifica menos de la mitad (incluida una lista vacia), la
    # seleccion no es fiable: la pasada se trata como degradada. Se borran las
    # categorias parciales para que todos los items queden igual que en
    # cualquier otro modo degradado.
    if len(salida) * 2 < len(items):
        log.error("LLM clasifico solo %d de %d items: modo degradado", len(salida), len(items))
        for it in items:
            it.categoria = ""
        return _degradado(items), False

    # Lo que el LLM se dejo sin clasificar no se pierde: va al final.
    for it in por_id.values():
        log.warning("sin clasificar: %s", it.titulo[:60])
        it.categoria, it.posicion = COMODIN, 99
        salida.append(it)

    return salida, True


def _degradado(items: list) -> list:
    items = sorted(items, key=lambda x: x.publicado, reverse=True)
    for n, it in enumerate(items, 1):
        it.posicion = n
        it.categoria = it.categoria or COMODIN
    return items

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

import requests

log = logging.getLogger(__name__)

CATEGORIAS = ["modelos", "herramientas", "investigacion", "opinion", "industria"]

MODELO = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"

CRITERIO = """Eres el editor de un brief diario de IA para un desarrollador que
esta orientando su carrera hacia AI engineering.

Prioriza lo que cambia como se construyen aplicaciones con LLMs: modelos nuevos y
sus capacidades reales, herramientas y patrones de implementacion, resultados de
investigacion aplicables, y analisis con criterio de gente que sabe.

Rebaja rondas de financiacion, drama corporativo, predicciones sin sustancia y
notas de prensa sin contenido tecnico.

Categorias (asigna EXACTAMENTE UNA por item):
- modelos: lanzamientos, versiones, capacidades, benchmarks
- herramientas: librerias, frameworks, APIs, patrones de implementacion
- investigacion: papers y experimentos con resultados medidos
- opinion: el valor esta en el argumento, no en el dato que aporta
- industria: dinero, empresas, mercado, regulacion

Ante la duda entre investigacion y opinion, elige investigacion.

CLASIFICA TODOS los items que recibas. No descartes ninguno.
Dentro de cada categoria, ordena por relevancia: posicion 1 es el mas relevante
de esa categoria, 2 el siguiente, y asi. Las posiciones se cuentan por separado
en cada categoria.

Devuelve UNICAMENTE un array JSON, sin markdown ni texto alrededor:
[{"id": "...", "categoria": "...", "posicion": 1}]"""


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
    import time

    cuerpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
    }
    ultimo = None

    for intento in range(4):
        resp = requests.post(
            ENDPOINT.format(m=MODELO),
            headers={"Content-Type": "application/json", "X-goog-api-key": api_key},
            json=cuerpo,
            timeout=90,
        )
        if resp.ok:
            datos = resp.json()
            return datos["candidates"][0]["content"]["parts"][0]["text"]

        ultimo = f"{resp.status_code}: {resp.text[:300]}"
        log.warning("intento %d fallido — %s", intento + 1, ultimo)

        if resp.status_code not in (429, 500, 502, 503, 504):
            break                      # error permanente, no insistas
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
        clasificados = _extraer_json(_llamar(prompt, api_key))
    except Exception as exc:
        log.error("LLM fallo: %s", exc)
        return _degradado(items), False

    por_id = {it.id: it for it in items}
    salida = []
    for fila in clasificados:
        it = por_id.pop(str(fila.get("id", "")), None)
        if it is None:
            continue
        cat = str(fila.get("categoria", "")).lower().strip()
        it.categoria = cat if cat in CATEGORIAS else "industria"
        try:
            it.posicion = int(fila.get("posicion", 99))
        except (TypeError, ValueError):
            it.posicion = 99
        salida.append(it)

    # Lo que el LLM se dejo sin clasificar no se pierde: va al final.
    for it in por_id.values():
        log.warning("sin clasificar: %s", it.titulo[:60])
        it.categoria, it.posicion = "industria", 99
        salida.append(it)

    if not salida:
        return _degradado(items), False
    return salida, True


def _degradado(items: list) -> list:
    items = sorted(items, key=lambda x: x.publicado, reverse=True)
    for n, it in enumerate(items, 1):
        it.posicion = n
        it.categoria = it.categoria or "industria"
    return items

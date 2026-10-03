"""Fixtures comunes. Ningun test puede llamar a la API real."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest import mock

import pytest

from pipeline import llm, sources


@pytest.fixture(autouse=True)
def sin_api_real(monkeypatch):
    """Clave ficticia y red bloqueada: un test que olvide simular la API falla."""
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")

    def prohibido(*args, **kwargs):
        raise AssertionError("un test ha intentado llamar a la API real")

    monkeypatch.setattr(llm.requests, "post", prohibido)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


@pytest.fixture
def item():
    """Fabrica de items minimos."""
    def fabricar(id_, categoria="", posicion=0, fuente="F", publicado=None):
        return sources.Item(
            id=id_, url=f"https://x/{id_}", titulo=f"titulo {id_}", fuente=fuente,
            publicado=publicado or datetime.now(timezone.utc).isoformat(), resumen="r",
            categoria=categoria, posicion=posicion,
        )
    return fabricar


def respuesta_gemini(texto: str | None = None, status: int = 200):
    """Respuesta HTTP simulada de Gemini con `texto` como salida del modelo."""
    r = mock.Mock()
    r.ok = status == 200
    r.status_code = status
    r.text = "error simulado"
    r.json.return_value = {"candidates": [{"content": {"parts": [{"text": texto}]}}]}
    return r


@pytest.fixture
def gemini(monkeypatch):
    """Hace que la API devuelva `salida` (lista/objeto serializado o texto tal cual)."""
    def configurar(salida, status=200):
        texto = salida if isinstance(salida, str) else json.dumps(salida)
        post = mock.Mock(return_value=respuesta_gemini(texto, status))
        monkeypatch.setattr(llm.requests, "post", post)
        return post
    return configurar

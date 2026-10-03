"""categorias.json: coherencia del fichero real y validacion del cargador."""

import json

import pytest

from pipeline import categorias


def test_fichero_real_coherente():
    assert categorias.CATEGORIAS
    assert list(categorias.CUOTAS) == categorias.CATEGORIAS
    assert categorias.COMODIN in categorias.CATEGORIAS


def test_bloque_prompt_incluye_cada_categoria_y_las_notas():
    texto = categorias.bloque_prompt()
    for c in categorias._DATOS["categorias"]:
        assert f"- {c['id']}: {c['descripcion']}" in texto
    for nota in categorias._DATOS.get("notas_prompt", []):
        assert nota in texto


def valido():
    return {
        "comodin": "b",
        "categorias": [
            {"id": "a", "nombre": "A", "descripcion": "da", "cuota": 1, "color": "#000000"},
            {"id": "b", "nombre": "B", "descripcion": "db", "cuota": 0, "color": "#FFFFFF"},
        ],
    }


def escribir(tmp_path, datos):
    ruta = tmp_path / "categorias.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    return ruta


def test_cargar_acepta_un_fichero_valido(tmp_path):
    assert categorias.cargar(escribir(tmp_path, valido()))["comodin"] == "b"


@pytest.mark.parametrize("romper", [
    lambda d: d.update(comodin="z"),
    lambda d: d["categorias"].append(dict(d["categorias"][0])),
    lambda d: d["categorias"][0].update(id="Con Tilde é"),
    lambda d: d["categorias"][0].update(cuota=-1),
    lambda d: d["categorias"][0].update(cuota="3"),
    lambda d: d["categorias"][0].update(color="verde"),
    lambda d: d["categorias"][0].update(descripcion=""),
    lambda d: d.update(categorias=[]),
])
def test_cargar_rechaza_configuracion_invalida(tmp_path, romper):
    datos = valido()
    romper(datos)
    with pytest.raises(ValueError):
        categorias.cargar(escribir(tmp_path, datos))

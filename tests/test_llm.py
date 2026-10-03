"""_extraer_json y la validacion de seleccionar, con la API simulada."""

import pytest
import requests

from pipeline import llm
from pipeline.categorias import CATEGORIAS, COMODIN
from conftest import respuesta_gemini

# ---------- _extraer_json ----------


@pytest.mark.parametrize("texto", [
    '[{"id": "a"}]',
    '```json\n[{"id": "a"}]\n```',
    '```\n[{"id": "a"}]\n```',
    'Aqui tienes la clasificacion:\n[{"id": "a"}]\nEspero que sirva.',
    '  \n[{"id": "a"}]  ',
])
def test_extraer_json_tolera_envoltorios(texto):
    assert llm._extraer_json(texto) == [{"id": "a"}]


def test_extraer_json_sin_array_falla():
    with pytest.raises(ValueError):
        llm._extraer_json("no hay nada que leer")


def test_extraer_json_array_roto_falla():
    with pytest.raises(ValueError):          # JSONDecodeError es subclase de ValueError
        llm._extraer_json('[{"id": "a"},')


def test_extraer_json_devuelve_objetos_tal_cual_y_valida_los_rechaza():
    datos = llm._extraer_json('{"items": []}')
    assert datos == {"items": []}
    with pytest.raises(ValueError):
        llm._validar(datos)


# ---------- seleccionar: validacion de la respuesta ----------


def fila(id_, categoria="modelos", posicion=1):
    return {"id": id_, "categoria": categoria, "posicion": posicion}


def test_respuesta_valida(gemini, item):
    gemini([fila("a", "modelos", 2), fila("b", "opinion", 1)])
    salida, uso = llm.seleccionar([item("a"), item("b")])
    assert uso is True
    assert {(it.id, it.categoria, it.posicion) for it in salida} == {("a", "modelos", 2), ("b", "opinion", 1)}


@pytest.mark.parametrize("devuelta, esperada", [
    ("Investigación", "investigacion"),
    ("  OPINIÓN ", "opinion"),
    ("Modelos", "modelos"),
    ("inventada", COMODIN),
    ("", COMODIN),
    (None, COMODIN),
])
def test_categoria_normalizada_o_comodin(gemini, item, devuelta, esperada):
    gemini([{"id": "a", "categoria": devuelta, "posicion": 1}])
    salida, uso = llm.seleccionar([item("a")])
    assert uso and salida[0].categoria == esperada


@pytest.mark.parametrize("posicion", ["primera", None, [1]])
def test_posicion_no_numerica_va_al_final(gemini, item, posicion):
    gemini([{"id": "a", "categoria": "modelos", "posicion": posicion}])
    salida, _ = llm.seleccionar([item("a")])
    assert salida[0].posicion == 99


def test_ids_desconocidos_y_repetidos_se_ignoran(gemini, item):
    gemini([fila("a", "modelos", 1), fila("fantasma"), fila("a", "opinion", 7)])
    salida, uso = llm.seleccionar([item("a")])
    assert uso and len(salida) == 1
    assert (salida[0].categoria, salida[0].posicion) == ("modelos", 1)


def test_items_olvidados_por_el_llm_no_se_pierden(gemini, item):
    gemini([fila("a"), fila("b", "opinion")])
    salida, uso = llm.seleccionar([item("a"), item("b"), item("c")])
    assert uso and [it.id for it in salida] == ["a", "b", "c"]
    assert (salida[2].categoria, salida[2].posicion) == (COMODIN, 99)


@pytest.mark.parametrize("respuesta, n_items", [
    ([], 2),                                            # lista vacia
    ([fila("fantasma"), fila("otro")], 2),              # solo ids desconocidos
    ([fila("i0", "opinion")], 3),                       # 1 de 3
    ([fila("i0", "opinion"), fila("i1", "opinion")], 5),  # 2 de 5
])
def test_menos_de_la_mitad_clasificada_es_modo_degradado(gemini, item, respuesta, n_items):
    gemini(respuesta)
    items = [item(f"i{n}", publicado=f"2026-01-0{n + 1}T00:00:00+00:00") for n in range(n_items)]
    salida, uso = llm.seleccionar(items)
    assert uso is False
    assert [it.id for it in salida] == [f"i{n}" for n in reversed(range(n_items))]  # por fecha
    assert [it.posicion for it in salida] == list(range(1, n_items + 1))
    # Sin categorias parciales del LLM: todos al comodin, como cualquier degradado.
    assert all(it.categoria == COMODIN for it in salida)


@pytest.mark.parametrize("clasificados, n_items", [(1, 2), (2, 4), (2, 3)])
def test_la_mitad_o_mas_clasificada_sigue_en_modo_normal(gemini, item, clasificados, n_items):
    gemini([fila(f"i{n}", "opinion") for n in range(clasificados)])
    salida, uso = llm.seleccionar([item(f"i{n}") for n in range(n_items)])
    assert uso is True and len(salida) == n_items
    assert [it.categoria for it in salida[:clasificados]] == ["opinion"] * clasificados


@pytest.mark.parametrize("salida_modelo", [
    {"items": [fila("a")]},                 # objeto en vez de lista
    ["a", "b"],                             # lista de cadenas
    [fila("a"), 3],                         # lista mixta
    "esto no es json",                      # texto libre
])
def test_formato_inesperado_cae_al_modo_degradado(gemini, item, salida_modelo):
    gemini(salida_modelo)
    salida, uso = llm.seleccionar([item("a", publicado="2026-01-01T00:00:00+00:00"),
                                   item("b", publicado="2026-01-02T00:00:00+00:00")])
    assert uso is False
    assert [it.id for it in salida] == ["b", "a"]           # degradado: por fecha, mas reciente primero
    assert [it.posicion for it in salida] == [1, 2]


def test_respuesta_sin_candidatos_cae_al_modo_degradado(monkeypatch, item):
    r = respuesta_gemini()
    r.json.return_value = {"promptFeedback": {"blockReason": "SAFETY"}}
    monkeypatch.setattr(llm.requests, "post", lambda *a, **k: r)
    _, uso = llm.seleccionar([item("a")])
    assert uso is False


def test_sin_clave_no_llama_a_la_api(monkeypatch, item):
    monkeypatch.delenv("GEMINI_API_KEY")
    salida, uso = llm.seleccionar([item("a", categoria="")])
    assert uso is False and salida[0].categoria == COMODIN


def test_sin_items_no_llama_a_la_api():
    assert llm.seleccionar([]) == ([], True)


def test_peticion_lleva_esquema_y_prompt_con_todas_las_categorias(gemini, item):
    post = gemini([fila("a")])
    llm.seleccionar([item("a")])
    cuerpo = post.call_args.kwargs["json"]
    esquema = cuerpo["generationConfig"]["responseSchema"]
    assert esquema["items"]["properties"]["categoria"]["enum"] == CATEGORIAS
    assert set(esquema["items"]["required"]) == {"id", "categoria", "posicion"}
    prompt = cuerpo["contents"][0]["parts"][0]["text"]
    assert all(f"- {c}:" in prompt for c in CATEGORIAS)


# ---------- reintentos ----------


def test_errores_de_red_se_reintentan(monkeypatch, item):
    ok = respuesta_gemini('[{"id": "a", "categoria": "modelos", "posicion": 1}]')
    efectos = iter([requests.Timeout("t"), requests.ConnectionError("c"), ok])
    llamadas = []

    def post(*a, **k):
        llamadas.append(1)
        e = next(efectos)
        if isinstance(e, Exception):
            raise e
        return e

    monkeypatch.setattr(llm.requests, "post", post)
    _, uso = llm.seleccionar([item("a")])
    assert uso and len(llamadas) == 3


def test_error_permanente_no_se_reintenta(gemini, item):
    post = gemini([], status=400)
    _, uso = llm.seleccionar([item("a")])
    assert uso is False and post.call_count == 1


def test_error_transitorio_agota_los_intentos(gemini, item):
    post = gemini([], status=503)
    _, uso = llm.seleccionar([item("a")])
    assert uso is False and post.call_count == llm.INTENTOS

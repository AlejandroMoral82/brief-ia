"""marcar_destacados: cuotas por categoria, tope por fuente y modo degradado."""

from pipeline import build

CUOTAS = {"a": 2, "b": 1, "c": 0}


def ids_destacados(items):
    return [it.id for it in items if it.destacado]


def test_respeta_la_cuota_y_elige_las_mejores_posiciones(monkeypatch, item):
    monkeypatch.setattr(build, "CUOTAS", CUOTAS)
    items = [item(f"a{p}", "a", p, fuente=f"F{p}") for p in (3, 1, 2)]
    items += [item(f"b{p}", "b", p, fuente=f"G{p}") for p in (2, 1)]
    build.marcar_destacados(items)
    assert sorted(ids_destacados(items)) == ["a1", "a2", "b1"]


def test_categoria_con_cuota_cero_o_desconocida_nunca_se_destaca(monkeypatch, item):
    monkeypatch.setattr(build, "CUOTAS", CUOTAS)
    items = [item("c1", "c", 1), item("x1", "inventada", 1, fuente="G")]
    build.marcar_destacados(items)
    assert ids_destacados(items) == []


def test_tope_por_fuente(monkeypatch, item):
    monkeypatch.setattr(build, "CUOTAS", {"a": 5, "b": 5})
    monkeypatch.setattr(build, "MAX_POR_FUENTE", 2)
    items = [item("a1", "a", 1, "Misma"), item("b1", "b", 1, "Misma"),
             item("a2", "a", 2, "Misma"), item("a3", "a", 3, "Otra")]
    build.marcar_destacados(items)
    assert sorted(ids_destacados(items)) == ["a1", "a3", "b1"]


def test_desempate_por_fuente_a_igual_posicion(monkeypatch, item):
    monkeypatch.setattr(build, "CUOTAS", {"a": 1})
    items = [item("z", "a", 1, "Zeta"), item("m", "a", 1, "Alfa")]
    build.marcar_destacados(items)
    assert ids_destacados(items) == ["m"]


def test_orden_de_salida_destacados_primero_por_categoria_y_posicion(monkeypatch, item):
    monkeypatch.setattr(build, "CUOTAS", {"a": 1, "b": 1})
    items = [item("b2", "b", 2, "F1"), item("a2", "a", 2, "F2"),
             item("b1", "b", 1, "F3"), item("a1", "a", 1, "F4")]
    salida = build.marcar_destacados(items)
    assert [it.id for it in salida] == ["a1", "b1", "a2", "b2"]


def test_degradado_destaca_tantos_como_suman_las_cuotas_sin_tope_por_fuente(monkeypatch, item):
    monkeypatch.setattr(build, "CUOTAS", {"a": 2, "b": 1})
    items = [item(f"i{n}", "a", n, "Misma") for n in range(1, 6)]
    salida = build.marcar_destacados(items, uso_llm=False)
    assert ids_destacados(salida) == ["i1", "i2", "i3"]
    assert [it.id for it in salida] == [f"i{n}" for n in range(1, 6)]   # no reordena


def test_cuotas_reales_salen_de_categorias_json():
    from pipeline import categorias
    assert build.CUOTAS is categorias.CUOTAS

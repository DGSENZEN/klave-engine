"""El modelo del lector: los árboles exportados dan en Python puro lo mismo
que scikit-learn, el activo carga, y el archivo no guarda texto del plano."""

import json
import random

import pytest
from klave_engine.lector import entrenar
from klave_engine.lector.modelo import MODELOS, Modelo
from klave_engine.lector.rasgos import NOMBRES, en_ventana, vector


def _filas(n=300):
    rnd = random.Random(0)
    out = []
    for _ in range(n):
        ancho, alto = rnd.uniform(0.1, 2.5), rnd.uniform(0.1, 2.5)
        f = {"ancho_m": ancho, "alto_m": alto, "proporcion": max(ancho, alto) / min(ancho, alto),
             "dist_eje_m": None if rnd.random() < 0.2 else rnd.uniform(0, 3),
             "repeticion_bloque": rnd.randint(0, 20)}
        out.append((vector(f), int(ancho < 0.6 and alto < 0.6), 1.0))
    return out


def test_python_puro_igual_a_sklearn(tmp_path):
    pytest.importorskip("sklearn")
    filas = _filas()
    clf = entrenar._ajustar(filas)
    (tmp_path / "modelo.json").write_text(json.dumps(entrenar.exportar(clf, "t", 0.5)))
    modelo = Modelo.cargar(tmp_path)
    esperado = clf.predict_proba(entrenar._matriz(filas))[:, 1]
    for (x, _, _), p in zip(filas, esperado, strict=True):
        assert modelo.puntuar(x) == pytest.approx(float(p), abs=1e-9)


def test_el_activo_carga_y_no_guarda_texto():
    modelo = Modelo.activo()
    assert modelo is not None and modelo.nombres == NOMBRES and 0 < modelo.umbral < 1
    data = json.loads((MODELOS / modelo.version / "modelo.json").read_text())
    todos = [data["completo"], *data["pliegues"].values()]
    textos = {v for m in todos for arbol in m["arboles"] for nodo in arbol for v in nodo
              if isinstance(v, str)}
    assert textos == set() and set(data) == {
        "version", "rasgos", "features_version", "completo", "pliegues", "dibujos", "umbral",
        "max_por_hoja"}
    # Los proyectos y sus planos, sólo como hashes.
    assert all(len(k) == 10 for k in data["pliegues"])
    assert all(len(h) == 16 for hs in data["dibujos"].values() for h in hs)


def test_umbral_y_promocion():
    assert entrenar._umbral([(0.9, 1)] * 9 + [(0.8, 0)] + [(0.4, 0)] * 5) == 0.8
    ok, _ = entrenar.puede_promoverse({"a": {"precision": 0.90}}, {"a": {"precision": 0.905}})
    peor, razones = entrenar.puede_promoverse({"a": {"precision": 0.80}},
                                               {"a": {"precision": 0.90}})
    assert ok and not peor and razones


def test_ventana():
    assert en_ventana({"ancho_m": 0.3, "alto_m": 0.3})
    assert not en_ventana({"ancho_m": 0.05, "alto_m": 0.3})
    assert not en_ventana({"ancho_m": 4, "alto_m": 0.3})

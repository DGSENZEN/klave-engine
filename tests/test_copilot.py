"""El copiloto: responde con lo que puede citar, y calla lo que no sabe."""

from pathlib import Path

from klave_engine.copilot.busqueda import buscar, normalizar
from klave_engine.copilot.normativa import NORMATIVA
from klave_engine.copilot.service import construir_prompt, responder

DOCS = Path(__file__).resolve().parents[1] / "docs"


def _ask(texto: str):
    """Un modelo de mentiras que siempre contesta lo mismo."""
    return lambda system, prompt: texto


def test_toda_entrada_de_ley_trae_su_fuente_y_su_vigencia():
    """La regla que hace útil este módulo: sin fuente, no existe. Una cita
    inventada de la ley le cuesta a alguien una licitación."""
    for entrada in NORMATIVA:
        assert entrada.titulo and entrada.resumen
        assert entrada.fuente, f"{entrada.id} sin fuente"
        if entrada.fuente.startswith(("LOPSRM", "RLOPSRM")):
            assert entrada.vigencia, f"{entrada.id} sin vigencia declarada"
            assert entrada.url.startswith("https://www.diputados.gob.mx/")
            assert "art." in entrada.fuente


def test_los_ids_son_unicos():
    ids = [e.id for e in NORMATIVA]
    assert len(ids) == len(set(ids))


def test_la_busqueda_encuentra_la_entrada_por_su_tema():
    for pregunta, esperado in [
        ("¿cuánto anticipo puedo pedir en obra pública?", "anticipo"),
        ("¿el plazo va en días naturales o hábiles?", "plazo-dias-naturales"),
        ("¿de dónde sale el rendimiento para la duración?", "rendimiento-mano-obra"),
        ("¿qué programas pide una licitación?", "programas-erogaciones"),
        ("¿por qué mi presupuesto no tiene precios sin unidades?", "klave-sin-unidades"),
    ]:
        ids = [p.id for p in buscar(pregunta, DOCS, limite=4)]
        assert esperado in ids, f"«{pregunta}» → {ids}"


def test_la_busqueda_tambien_lee_la_documentacion_del_repo():
    pasajes = buscar("cómo adopto un precio de mi catálogo del taller", DOCS, limite=8)
    assert any(p.tipo == "documentacion" for p in pasajes)
    assert all(p.fuente for p in pasajes)


def test_sin_pasajes_no_se_llama_al_modelo():
    """Contestar de memoria sobre un artículo del reglamento es exactamente el
    modo de fallar que este servicio existe para evitar."""
    llamado = {"veces": 0}

    def ask(system, prompt):
        llamado["veces"] += 1
        return "El artículo 512 dice que sí."

    respuesta = responder("qwerty zxcvb ñlkjh", DOCS, ask)
    assert llamado["veces"] == 0
    assert respuesta.fundamentada is False
    assert "no encontré" in respuesta.texto.lower()


def test_una_respuesta_que_no_se_apoya_en_el_material_se_marca():
    respuesta = responder(
        "¿cuánto anticipo puedo pedir?",
        DOCS,
        _ask("Cualquier cosa completamente distinta sobre pingüinos y bicicletas."),
    )
    assert respuesta.fundamentada is False
    assert respuesta.citas  # los pasajes sí existían; la respuesta no los usó


def test_una_respuesta_apoyada_en_el_material_pasa_y_trae_sus_citas():
    respuesta = responder(
        "¿cuánto anticipo puedo pedir en obra pública?",
        DOCS,
        _ask(
            "La dependencia puede otorgar hasta un treinta por ciento de la asignación "
            "presupuestaria del contrato para cada ejercicio (LOPSRM art. 50, fracción "
            "II). Es un techo, no la norma: hay convocatorias que dan 10 %. El importe "
            "del anticipo debes considerarlo en el costo de financiamiento."
        ),
    )
    assert respuesta.fundamentada is True
    assert any("art. 50" in c.fuente for c in respuesta.citas)
    assert respuesta.aviso  # obra pública federal: se advierte sobre la vigencia


def test_un_articulo_que_no_esta_en_el_material_se_denuncia_en_la_respuesta():
    """La alucinación más cara en este dominio es un número de artículo, así
    que se detecta explícitamente en vez de confiar en la instrucción."""
    respuesta = responder(
        "¿cuánto anticipo puedo pedir?",
        DOCS,
        _ask("El anticipo puede ser hasta treinta por ciento según el artículo 977."),
    )
    assert "977" in respuesta.texto
    assert "no están en el material" in respuesta.texto
    assert respuesta.fundamentada is False


def test_el_prompt_lleva_los_pasajes_y_el_contexto_del_proyecto():
    pasajes = buscar("anticipo", DOCS, limite=3)
    prompt = construir_prompt(
        "¿puedo entregar así?",
        pasajes,
        {
            "nombre": "Marina Lote 04",
            "resumen": "$4,159,342 costeados · 1 concepto sin precio.",
            "hallazgos": [
                {
                    "severity": "bloqueante",
                    "title": "6 conceptos costean un f'c menor al que declara el plano",
                    "monto_afectado": 1014539.0,
                }
            ],
            "plazo_natural": 461,
            "plazo_habil": 395,
        },
    )
    assert "PASAJES:" in prompt and "PREGUNTA:" in prompt
    assert "Marina Lote 04" in prompt
    assert "$1,014,539 en juego" in prompt
    assert "461 días naturales" in prompt
    assert pasajes[0].fuente in prompt


def test_normalizar_ignora_acentos_y_palabras_vacias():
    assert normalizar("¿Cuál es el PLAZO de ejecución?") == ["plazo", "ejecucion"]


def test_los_documentos_internos_no_entran_al_conocimiento():
    """La lista de pendientes explica cómo se construye Klave, no cómo se usa
    ni qué dice la ley: en una respuesta solo resta."""
    from klave_engine.copilot.busqueda import _corpus

    _corpus.cache_clear()
    pasajes, _idf = _corpus(str(DOCS))
    fuentes = " ".join(p.fuente for p in pasajes)
    assert "plan-de-pulido" not in fuentes
    assert "auditoria-ui" not in fuentes
    assert "lectura-ia" in fuentes  # los que sí explican la app siguen ahí


def test_una_respuesta_sobre_la_obra_abierta_cuenta_como_fundamentada():
    """Los hechos del proyecto son material legítimo. Marcar como dudosa una
    respuesta que nombra correctamente CIM-010 y sus 23 piezas sería la falsa
    alarma que enseña a ignorar la advertencia."""
    respuesta = responder(
        "¿por qué no puedo entregar este presupuesto?",
        DOCS,
        _ask(
            "No puedes entregarlo porque tienes 6 conceptos que costean un f'c menor "
            "al que declara el plano, con $1,014,539 en juego, y además CIM-010 tiene "
            "23.00 PZA sin precio, así que el total va corto."
        ),
        contexto={
            "nombre": "Marina Lote 04",
            "resumen": "$4,159,342 costeados · 1 concepto con cantidad y sin precio.",
            "hallazgos": [
                {
                    "severity": "bloqueante",
                    "title": "6 conceptos costean un f'c menor al que declara el plano",
                    "monto_afectado": 1014539.0,
                },
                {
                    "severity": "dinero",
                    "title": "CIM-010 tiene cantidad pero no precio",
                    "exposicion": "23.00 PZA",
                },
            ],
        },
    )
    assert respuesta.fundamentada is True

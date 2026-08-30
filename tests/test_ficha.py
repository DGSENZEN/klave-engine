"""La ficha técnica sale del texto del concepto, con los ejemplos de Diego."""

from klave_engine.costing.ficha import extraer_ficha


def _campos(ficha):
    return {f["campo"]: f["valor"] for f in ficha}


def test_concreto_de_superestructura_trae_su_ficha_completa():
    ficha = _campos(extraer_ficha(
        "Suministro y colocación de concreto hidráulico f'c= 300 kg/cm2, "
        "t.m.a. de 20 mm, fraguado de 14 días, revenimiento 14, clase 1, "
        "bombeable, fabricado en planta por proveedor, para elementos de "
        "superestructura (columnas, trabes, losas macizas y reticulares, "
        "muros, faldones y pretiles)"
    ))
    assert ficha["f'c"] == "300 kg/cm²"
    assert ficha["T.M.A."] == "20 mm"
    assert ficha["Fraguado"] == "14 días"
    assert ficha["Revenimiento"] == "14"
    assert ficha["Clase"] == "1"
    assert ficha["Colocación"] == "bombeable"
    assert ficha["Fabricación"] == "premezclado en planta"
    assert "columnas" in ficha["Elemento"] and "losas macizas" in ficha["Elemento"]


def test_cimbra_dice_su_acabado_y_su_elemento():
    ficha = _campos(extraer_ficha(
        "CIMBRA EN COLUMNAS DE CIMENTACIÓN, ACABADO COMÚN, INCLUYE: "
        "MATERIALES, ACARREOS, CORTES, HABILITADOS, CIMBRADO, DESCIMBRADO, "
        "MANO DE OBRA, EQUIPO Y HERRAMIENTA."
    ))
    assert ficha["Acabado"] == "común"
    assert ficha["Elemento"] == "columnas de cimentacion"


def test_acero_trae_numero_de_varilla_y_fy():
    ficha = _campos(extraer_ficha(
        'ACERO DE REFUERZO EN ESTRUCTURA DEL NO.2 (1/4"), DE FY=6000 KG/CM2'
    ))
    assert ficha["Varilla"] == 'n.º 2 (1/4")'
    assert ficha["fy"] == "6000 kg/cm²"


def test_sin_datos_no_se_inventa_nada():
    assert extraer_ficha("Limpieza general de la obra") == []
    assert extraer_ficha("") == []

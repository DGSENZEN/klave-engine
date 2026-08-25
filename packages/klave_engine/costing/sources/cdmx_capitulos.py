"""La nomenclatura del Tabulador General de Precios Unitarios de la CDMX.

El tabulador no es una lista plana: está organizado en secciones con clave de
dos letras, y la clave de cada renglón empieza por la de su sección. IB12BB
vive bajo IB, que la propia publicación titula «Suministro, instalación y
pruebas de tubos y conexiones de cobre».

Eso vale por dos razones, y las dos se descubrieron intentando ponerle precio
a una tubería:

**La sección dice la partida sin que nadie la adivine.** Antes se inferían
del texto del renglón con expresiones regulares, y el texto engaña: «ranura
para alojar tubería» habla de tubería y es albañilería. La sección la declara
el publicador, y contra eso no hay heurística que compita.

**La sección completa lo que el renglón calla.** Muchos renglones son
telegráficos — «Ye de fierro galvanizado de 19 mm (3/4") de diámetro» — porque
el encabezado ya dijo de qué se trata. Leído solo, ese renglón no dice si es
hidráulica o sanitaria; leído bajo IE, dice las dos cosas que le faltaban.

Las secciones se extrajeron de los encabezados del propio PDF, de las dos
ediciones de 2026, y se les quitó la coletilla normativa que casi todas
arrastran («Norma de Construcción de la Administración Pública…»), que se
repite idéntica y no distingue nada.
"""

import re

# clave de sección → (partida canónica, título que publica la CDMX)
SECCIONES: dict[str, tuple[str, str]] = {
    "AB": ("preliminares", "Anteproyectos"),
    "AC": ("preliminares", "Proyectos"),
    "AD": ("preliminares", "Mecánica de suelos"),
    "AE": ("preliminares", "Trabajos de laboratorio, materiales de construcción. Norma de"),
    "AF": ("preliminares", "Trazo y nivelación topográficos"),
    "BC": ("terracerias", "Desyerbe"),
    "BD": ("terracerias", "Tala de árboles"),
    "BE": ("terracerias", "Despalme"),
    "BF": ("terracerias", "Excavaciones a mano para formación de zanjas en terrenos seco y"),
    "BG": ("terracerias", "Excavaciones por medios mecánicos, en terrenos seco y saturado, en"),
    "BH": ("terracerias", "Afine"),
    "BI": ("terracerias", "Cortes con sierra en pavimentos"),
    "BL": ("terracerias", "Demoliciones por medios manuales de mampostería"),
    "BN": ("terracerias", "Acarreo de materiales en vehículo"),
    "BO": ("terracerias", "Relleno de zanjas que alojan conductos, medido colocado, Norma de"),
    "BP": ("terracerias", "Relleno de excavaciones en estructuras, medido colocado. Norma de"),
    "BQ": ("terracerias", "Mejoramiento de bases con tepetate, cemento cal y agua"),
    "CB": ("estructura", "Cimbra de madera acabado común y descimbra. Norma de"),
    "CC": ("estructura", "Cimbra de madera acabado aparente y descimbra. Norma de"),
    "CD": ("estructura", "Cimbra de madera acabado aparente y descimbra en puentes. Norma"),
    "CE": ("estructura", "Aligerante tubular de cartón Sonovoid o similar, en losas de puentes"),
    "CF": ("estructura", "Estructuras de madera"),
    "CG": ("canceleria", "Carpintería, pisos, puertas y lambrínes"),
    "DB": ("estructura", "Acero de refuerzo"),
    "EB": ("estructura", "Estructura metálica"),
    "EC": ("estructura", "Construcción de pasos elevados para peatones. Norma de"),
    "ED": ("estructura", "Formación de apoyos para superestructura de puentes. Norma de"),
    "EE": ("estructura", "Juntas en edificaciones"),
    "EF": ("estructura", "Deflectores y elementos de prevención vial"),
    "EG": ("canceleria", "Elementos de hierro y aluminio"),
    "EH": ("canceleria", "Suministro y colocación de elementos de aluminio"),
    "FB": ("estructura", "Concreto hidráulico ciclópeo"),
    "FC": ("estructura", "Suministro y colocación de concreto hidráulico elaborado en obra, con"),
    "FD": ("estructura", "Suministro y colocación de concreto hidráulico fraguado rápido"),
    "FE": ("estructura", "Concreto hidráulico fraguado normal, suministrado por proveedor"),
    "FF": ("estructura", "Concreto hidráulico fraguado rápido, suministrado por proveedor"),
    "FG": ("estructura", "Concreto hidráulico fraguado normal, apto para ser bombeado"),
    "FH": ("estructura", "Concreto hidráulico fraguado rápido, apto para ser bombeado"),
    "FK": ("estructura", "Aditivo para concreto hidráulico"),
    "FM": ("estructura", "Prefabricados de concreto"),
    "GB": ("albanileria", "Mampostería"),
    "GC": ("albanileria", "Junta en edificaciones, muros, castillos, dalas y cadenas"),
    "GE": ("acabados", "Falso plafón"),
    "GF": ("albanileria", "Malla ciclónica galvanizada"),
    "GH": ("acabados", "Firmes, pisos de concreto hidráulico y pisos de piezas prefabricadas"),
    "GI": ("acabados", "Suministro y colocación de zoclo"),
    "GJ": ("acabados", "Suministro y colocación de fayenza, entrecalles"),
    "GK": ("albanileria", "Relleno en azotea"),
    "GL": ("acabados", "Acabado estampado en pisos de concreto"),
    "GM": ("albanileria", "Techo de lámina y sus accesorios"),
    "GN": ("albanileria", "Relleno en azotea"),
    "GO": ("albanileria", "Relleno en azotea"),
    "GQ": ("albanileria", "Chaflanes"),
    "GR": ("albanileria", "Elementos varios en azoteas"),
    "GS": ("impermeabilizacion", "Impermeabilización de superficies de azoteas"),
    "HB": ("sanitaria", "Suministro, instalación y pruebas de tubos y piezas especiales de PVC"),
    "HC": ("sanitaria", "Suministro, instalación y pruebas de tubos y piezas especiales de fierro"),
    "HE": ("sanitaria", "Registros con muros de tabique rojo recocido, incluye el suministro del"),
    "HH": ("sanitaria", "Albañal y piezas especiales en edificación"),
    "HI": ("hidraulica", "Muebles sanitarios y accesorios para baño (instalaciones y pruebas)"),
    "HJ": ("hidraulica", "Suministro, instalación y pruebas de calentadores para agua. Norma de"),
    "HK": ("sanitaria", "Forjado de canalón para desagüe pluvial"),
    "HL": ("hidraulica", "Suministro, instalación y pruebas de muebles de acero inoxidable"),
    "IB": ("hidraulica", "Suministro, instalación y pruebas de tubos y conexiones de cobre"),
    "IC": ("hidraulica", "Suministro, instalación y pruebas de válvulas"),
    "IE": ("hidraulica", "Suministro, instalación y pruebas de tubos y conexiones de fierro"),
    "IF": (
        "hidraulica",
        "Suministro, instalación y pruebas de tubos y piezas especiales de fierro",
    ),
    "IG": ("hidraulica", "Suministro, instalación y pruebas de tubos y piezas especiales de pvc"),
    "IH": ("hidraulica", "Tubos y piezas especiales de cpvc"),
    "IJ": ("hidraulica", "Suministro, instalacion y pruebas de tubo y conexiones de propileno"),
    "JB": ("hidraulica", "Suministro, colocación y pruebas de mangueras"),
    "JD": ("aire", "Aislamiento"),
    "JE": ("aire", "Materiales aislantes en ductos para aire acondicionado (suministro"),
    "JG": ("hidraulica", "Suministro, colocación y pruebas de Cisternas y tinacos. Norma de"),
    "JH": ("aire", "Trampas para vapor"),
    "JL": ("gas", "Instalaciones de gas"),
    "JM": ("gas", "Tanque de gas"),
    "JP": ("proteccion", "Extintores (suministro e instalación)"),
    "JQ": ("aire", "Ductos para aire acondicionado"),
    "KB": ("electrica", "Suministro, instalación y pruebas de base y punta para el sistema de"),
    "KC": ("electrica", "Conductores eléctricos"),
    "KD": ("aire", "Suministro, instalación y pruebas de ducto cuadrado embisagrado y"),
    "KE": ("electrica", "Suministro y colocación de tubos conduit , abrazaderas, coples, codos"),
    "KF": ("electrica", "Poliducto color naranja (suministro y colocación)"),
    "KG": ("electrica", "Suministro, colocación, pruebas de tubos conduit y piezas especiales"),
    "KH": ("electrica", "Tubos conduit y accesorios flexibles"),
    "KI": ("electrica", "Suministro, instalación y pruebas de condulets Cooper Crouse Hinds o"),
    "KJ": ("electrica", "Tapones reducciones, niples y accesorios, Cooper Crouse Hinds o"),
    "KL": ("electrica", "Suministro, instalación y pruebas de accesorios eléctricos"),
    "KM": ("electrica", "Suministro, colocación, conexión y pruebas de unidades de"),
    "KN": ("electrica", "Instalación de equipo eléctrico de control y protección"),
    "LB": ("acabados", "Recubrimientos"),
    "LC": ("acabados", "Martelinado"),
    "LD": ("acabados", "Cajas para lámparas en falso plafón de yeso"),
    "LE": ("acabados", "Falso plafón de yeso"),
    "LG": ("acabados", "Suministro y aplicación de pintura, laca y barnices;"),
    "LH": ("canceleria", "Cerraduras y herrajes"),
    "MB": ("canceleria", "Suministro y colocación de vidrios y cristales"),
    "NB": ("cimentacion", "Ademes en paredes de las excavaciones"),
    "NC": ("cimentacion", "Bombeo (también llamado de achique)"),
    "ND": ("sanitaria", "Relleno de zanjas que alojan conductos"),
    "NF": ("sanitaria", "Construcción de sistemas de alcantarillado"),
    "NG": ("sanitaria", "Suministro e Instalación de codo y slant en tubos de concreto para"),
    "NI": ("sanitaria", "Construcción de pozo de visita acabado común, sobre tubo"),
    "OD": ("hidraulica", "Instalación de tubos"),
    "OE": ("hidraulica", "Suministro e instalación de tubos del material que se indique en el"),
    "OH": ("hidraulica", "Obras complementarias"),
    "OJ": ("hidraulica", "Suministro e instalación de piezas especiales de fierro fundido en"),
    "OK": ("hidraulica", "Válvulas con interiores de hierro para seccionar las redes"),
    "OL": ("hidraulica", "Construcción de cajas tipo para operación de válvulas. Norma de"),
    "OM": ("hidraulica", "Suministro e instalación de piezas especiales de acero al carbón"),
    "ON": ("hidraulica", "Tornillos"),
    "OP": ("hidraulica", "Prueba hidrostática"),
    "OQ": ("hidraulica", "Desinfección"),
    "QB": ("pavimentos", "Mejoramientos"),
    "QC": ("pavimentos", "Construcción de sub-base"),
    "QD": ("pavimentos", "Construcción de base hidráulica"),
    "QF": ("pavimentos", "Preparación de carpeta de mezcla asfáltica para tender (desplantar) la"),
    "QG": ("pavimentos", "Mezcla para riego de impregnación y riego de liga"),
    "QH": ("pavimentos", "Construcción de carpeta de mezcla asfáltica templada, elaborado en"),
    "QK": ("pavimentos", "Fresado"),
    "QL": ("pavimentos", "Bacheo"),
    "QM": ("pavimentos", "Pavimentos con adoquín de concreto, sobre cama de arena"),
    "QN": ("pavimentos", "Pavimento de concreto hidráulico suministrado por proveedor"),
    "QP": ("pavimentos", "Pavimento de concreto hidráulico MR suministrado por proveedor"),
    "QS": ("pavimentos", "Pavimento de concreto permeable ecológico, suministrado por"),
    "RD": ("cimentacion", "Perforaciones para hincar pilotes o colocar pilas"),
    "RE": ("cimentacion", "Cimentación profunda"),
    "RF": ("cimentacion", "Fabricación de pilotes"),
    "RG": ("cimentacion", "Placas de acero para unir tramos de pilotes"),
    "RH": ("cimentacion", "Acero de refuerzo para pilotes, pilas, cilindros y cajones. Norma de"),
    "RJ": ("cimentacion", "Brocales de concreto para pilas"),
    "RK": ("cimentacion", "Perforaciones para pilas coladas en sitio"),
    "RL": ("cimentacion", "Concreto hidráulico en pilotes y pilas"),
    "RM": ("terracerias", "RECICLADO DE MATERIALES"),
    "SB": ("urbanizacion", "Banquetas"),
    "SC": ("urbanizacion", "Guarnición de tabique rojo recocido, de concreto simple"),
    "SD": ("urbanizacion", "Instalaciones"),
    "SE": ("urbanizacion", "Renivelaciones"),
    "TB": ("urbanizacion", "Ruptura y reposición de banqueta"),
    "TC": ("electrica", "Construcción de sistemas de canalizaciónes"),
    "TD": ("electrica", "Instalación de cables y conexiones"),
    "TE": ("electrica", "Desinstalación y desmontaje de elementos eléctricos"),
    "TF": ("electrica", "Construcción de cimientos para postes de alumbrado"),
    "TG": ("electrica", "Montaje de arbotantes"),
    "TH": ("electrica", "Postes de alumbrado"),
    "TI": ("electrica", "Construcción de registros en los sistemas de canalización subterranea"),
    "UB": ("senalamiento", "Suministro y aplicación de pintura en superficies de rodamiento"),
    "UC": ("senalamiento", "Señalización en Vialidades"),
    "UD": ("senalamiento", "Suministro y aplicación de pintura termoplastica en area de"),
    "VB": ("jardineria", "Tierra vegetal"),
    "VC": ("jardineria", "Pastos"),
    "VD": ("jardineria", "Suministro y plantación de árboles, arbustos, plantas de ornato con las"),
    "ZB": ("limpieza", "Limpieza de pisos, recubrimiento y muebles sanitarios"),
    "ZC": ("limpieza", "Colocaciones"),
}


# La clave del tabulador tiene forma fija: dos letras de sección, dos dígitos
# de concepto y dos de variante — IB12BB, KE14BC. Exigirla importa: sin ella,
# la clave propia de un taller «ACERO-01» se leería como la sección AC del
# tabulador —Proyectos— y ese renglón de acero acabaría clasificado en
# preliminares.
_CLAVE_CDMX = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{2}$")


def seccion_de(clave: str) -> tuple[str, str] | None:
    """La sección de un renglón del tabulador CDMX, o None si la clave no es
    de ese tabulador."""
    limpia = (clave or "").strip().upper()
    if not _CLAVE_CDMX.match(limpia):
        return None
    return SECCIONES.get(limpia[:2])

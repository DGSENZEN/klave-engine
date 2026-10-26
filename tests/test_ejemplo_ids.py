"""La obra de ejemplo es de cada persona: su id dice de quién es, y el
prefijo basta para reconocerla en cualquier parte del sistema."""

from klave_engine.ejemplo import es_obra_de_ejemplo, sample_project_id


def test_open_mode_keeps_local_id():
    assert sample_project_id(None, None) == "obra_de_ejemplo_local"


def test_per_user_id_is_stable_and_distinct():
    a = sample_project_id("ws-1", "3f2a9c1e-uuid-a")
    assert a == sample_project_id("ws-1", "3f2a9c1e-uuid-a")
    assert a != sample_project_id("ws-1", "uuid-b")
    assert a != sample_project_id("ws-2", "3f2a9c1e-uuid-a")
    assert a.startswith("obra_de_ejemplo_") and len(a) <= 100


def test_prefix_check():
    assert es_obra_de_ejemplo("obra_de_ejemplo_local")
    assert not es_obra_de_ejemplo("marina_lote_04")

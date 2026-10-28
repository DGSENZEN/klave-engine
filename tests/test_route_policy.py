"""Every route that writes declares who may call it. A new route with no rule
fails here: that is how the catálogo gap would have been caught."""

from apps.api.route_policy import policy_for

MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


def _mutating_routes():
    from apps.api.main import create_app

    for route in create_app().routes:
        methods = getattr(route, "methods", None) or set()
        for method in sorted(methods & MUTATING):
            yield method, route.path


def test_every_mutating_route_has_a_policy(data_dir):
    sin_regla = [f"{m} {p}" for m, p in _mutating_routes() if policy_for(m, p) is None]
    assert sin_regla == [], "Rutas que escriben sin regla declarada:\n" + "\n".join(sin_regla)


def test_shared_mapping_routes_are_not_classified_as_project():
    for method, path in [
        ("POST", "/projects/{project_id}/variantes/mapear"),
        ("PUT", "/projects/{project_id}/variantes/{variant_key}"),
        ("DELETE", "/projects/{project_id}/variantes/{variant_key}"),
        ("POST", "/catalog/aliases"),
    ]:
        assert policy_for(method, path) == "shared_mapping"


def test_catalog_writes_are_admin_and_preview_is_exempt():
    assert policy_for("PUT", "/catalog/indices") == "catalog_admin"
    assert policy_for("POST", "/catalog/labor/preview") == "exempt"


def test_an_unknown_route_has_no_policy():
    assert policy_for("POST", "/zz/nueva") is None

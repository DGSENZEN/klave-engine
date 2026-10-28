"""The catálogo's one write rule (role design, decision 1).

Every POST/PUT/PATCH/DELETE under ``/catalog`` is the taller administrator's,
unless it is named below with its reason. A rule per route is how the gap
shipped; one rule on the router, with the exceptions written down next to it,
is what the route-policy test checks.
"""

from __future__ import annotations

from fastapi import Request

from apps.api.auth.access import require_taller_admin

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# (METHOD, route path) → why a member may call it.
CATALOG_EXEMPT: dict[tuple[str, str], str] = {
    ("POST", "/catalog/labor/preview"): "calcula el salario real, no guarda nada",
}

# The taller's shared memory of "this drawing label means this concept":
# editors add, administrators change or remove (decision 3). These routes
# decide that themselves (``auth.shared_mappings``); the variant ones live
# under /projects and the middleware alone would let any editor through.
SHARED_MAPPING_ROUTES: frozenset[tuple[str, str]] = frozenset({
    ("POST", "/catalog/aliases"),
    ("POST", "/catalog/aliases/bulk"),
    ("DELETE", "/catalog/aliases/{code}"),
    ("POST", "/projects/{project_id}/variantes/mapear"),
    ("PUT", "/projects/{project_id}/variantes/{variant_key}"),
    ("DELETE", "/projects/{project_id}/variantes/{variant_key}"),
})


def catalog_write_rule(request: Request) -> None:
    """Router dependency for ``/catalog``: runs before the body is read, so a
    member is refused before any validation or write."""
    if request.method not in _MUTATING:
        return
    route = request.scope.get("route")
    key = (request.method, getattr(route, "path", request.url.path))
    if key in CATALOG_EXEMPT or key in SHARED_MAPPING_ROUTES:
        return
    require_taller_admin(request)

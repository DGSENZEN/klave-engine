"""Mide lo que el visor cuesta del lado del servidor, contra las metas de la
ronda de fluidez (spec producto v1 §4.1). Sólo lee: no reprocesa ni escribe.

    uv run python -m scripts.perf_plano <project_id>
"""

import gzip
import os
import sys
import time

os.environ.setdefault("KLAVE_USERS_DATABASE_URL", "postgresql://nobody@127.0.0.1:1/none")

from fastapi.testclient import TestClient  # noqa: E402
from klave_engine.common import config  # noqa: E402

from apps.api.main import create_app  # noqa: E402

METAS = {"primera_visita_ms": 1500, "comprimido_mb": 4.0}


def main(project_id: str) -> int:
    config.get_settings.cache_clear()
    client = TestClient(create_app())
    base = f"/projects/{project_id}"
    filas = []
    for nombre, path in (
        ("geometry (fría)", f"{base}/geometry"),
        ("geometry (caliente)", f"{base}/geometry"),
        ("shapes", f"{base}/geometry/shapes"),
        ("detections", f"{base}/geometry/detections"),
    ):
        t = time.perf_counter()
        r = client.get(path)
        ms = (time.perf_counter() - t) * 1000
        crudo = len(r.content) / 1e6
        comprimido = len(gzip.compress(r.content, 5)) / 1e6
        filas.append((nombre, r.status_code, crudo, comprimido, ms))
    etag = client.get(f"{base}/geometry/shapes").headers.get("etag", "")
    revalida = client.get(f"{base}/geometry/shapes", headers={"If-None-Match": etag})
    print(f"{'endpoint':22} {'http':>4} {'MB':>7} {'gzip MB':>8} {'ms':>7}")
    for nombre, code, crudo, comp, ms in filas:
        print(f"{nombre:22} {code:>4} {crudo:7.2f} {comp:8.2f} {ms:7.0f}")
    print(f"revalidación con ETag: {revalida.status_code} ({len(revalida.content)} bytes)")
    fria = filas[0]
    ok = fria[4] <= METAS["primera_visita_ms"] and fria[3] <= METAS["comprimido_mb"]
    print(f"metas: primera visita ≤ {METAS['primera_visita_ms']} ms y ≤ "
          f"{METAS['comprimido_mb']} MB comprimido → {'sí' if ok else 'NO'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "marina_lote_04_completo_887d5624"))

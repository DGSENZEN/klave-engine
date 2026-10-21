"""Safe telemetry boundaries and explicit correlation context."""
import logging

import pytest
from fastapi.testclient import TestClient
from klave_engine.common.bitacora import errores_recientes, redactar

from apps.api.observability import redact_request_path


@pytest.mark.parametrize('path,expected', [
    ('/auth/reset/SECRET/next?query=PRIVATE', '/auth/reset/[redacted]/next'),
    ('/auth/verify/SECRET', '/auth/verify/[redacted]'),
    ('/auth/verify/send', '/auth/verify/send'),
    ('/auth/invitations/by-token/SECRET/accept', '/auth/invitations/by-token/[redacted]/accept'),
    ('/compartido/SECRET/report', '/compartido/[redacted]/report'),
])
def test_path_redaction(path, expected):
    assert redact_request_path(path) == expected


def test_message_redacts_token_urls_and_existing_secrets():
    message = ('failed https://host/auth/reset/SECRET?secret=PRIVATE for a@example.test '
               'Bearer abcdefghijklmnop sk-abcdefghijklmnop')
    clean = redactar(message)
    for secret in ('SECRET', 'PRIVATE', 'a@example.test', 'abcdefghijklmnop'):
        assert secret not in clean


@pytest.mark.parametrize('mode', ['success', 'denied', 'unmatched', 'exception'])
def test_request_logs_and_error_records_redact_tokens(data_dir, caplog, mode):
    from apps.api.main import create_app

    app = create_app()

    @app.get('/auth/reset/{token}/probe')
    def probe(token: str):
        if mode == 'exception':
            raise RuntimeError('failed /auth/verify/SECRET?code=PRIVATE')
        return {'ok': True}

    client = TestClient(app, raise_server_exceptions=False)
    caplog.set_level(logging.INFO)
    if mode == 'denied':
        response = client.post('/auth/reset/SECRET?code=PRIVATE', headers={'origin': 'https://bad.test'})
        assert response.status_code == 403
    else:
        path = '/auth/reset/SECRET/' + ('missing' if mode == 'unmatched' else 'probe')
        response = client.get(path + '?code=PRIVATE')
        assert response.status_code == {'success': 200, 'unmatched': 404, 'exception': 500}[mode]
    assert response.headers.get('x-request-id')
    logs = '\n'.join(r.getMessage() for r in caplog.records if r.name.startswith('klave'))
    assert 'SECRET' not in logs and 'PRIVATE' not in logs
    if mode == 'exception':
        rows = errores_recientes(data_dir)
        assert len(rows) == 1
        assert 'SECRET' not in str(rows) and 'PRIVATE' not in str(rows)

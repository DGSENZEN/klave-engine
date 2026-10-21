"""Safe diagnostic values shared by HTTP and worker boundaries."""
from __future__ import annotations

import re

_TOKEN_PATH = re.compile(r'(/by-token/|/compartido/|/auth/reset/|/auth/verify/)([^/\s?\#\"\'<>]+)')
_SECRET = re.compile(r'(AIza[0-9A-Za-z_\-]{10,}|sk-[A-Za-z0-9_\-]{10,}|Bearer\s+[A-Za-z0-9._\-]{10,})')
_EMAIL = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+\b')
_QUERY = re.compile(r'\?[^\s\"\'<>]*')


def _mask_token(match: re.Match[str]) -> str:
    prefix, token = match.groups()
    if prefix == '/auth/verify/' and token == 'send':
        return match.group(0)
    return prefix + '[redacted]'


def sanitize_path(path: str) -> str:
    return _TOKEN_PATH.sub(_mask_token, path.split('?', 1)[0].split('#', 1)[0])


def sanitize_text(text: str, limit: int = 600) -> str:
    clean = _TOKEN_PATH.sub(_mask_token, text)
    clean = _QUERY.sub('', clean)
    clean = _SECRET.sub('«clave»', clean)
    return _EMAIL.sub('«correo»', clean)[:limit]

"""Password policy for new passwords (register, reset, change).

Ten characters minimum, none of the passwords everyone tries first, and
never the email itself. Messages in Spanish because the person reading
them is the one choosing the password.
"""

from __future__ import annotations

MIN_LENGTH = 10

# The short head of every breach list, plus the Spanish habits.
COMMON_PASSWORDS = {
    "1234567890", "12345678910", "0123456789", "qwertyuiop", "1q2w3e4r5t",
    "password12", "password123", "contraseña1", "contrasena1", "contraseña123",
    "contrasena123", "administrador", "construccion", "arquitectura", "ingenieria1",
    "bienvenido1", "qwerty12345", "abcd123456", "1234qwerty", "987654321a",
    "aaaaaaaaaa", "1111111111", "0000000000", "iloveyou12", "mexico12345",
}


def password_problem(password: str, email: str | None = None) -> str | None:
    """Why a password must not be accepted, or None when it may."""
    if len(password) < MIN_LENGTH:
        return f"La contraseña necesita al menos {MIN_LENGTH} caracteres."
    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        return "Esa contraseña está entre las más usadas del mundo; elige otra."
    if len(set(lowered)) <= 2:
        return "Una contraseña de caracteres repetidos no protege nada; elige otra."
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 4 and local in lowered:
            return "La contraseña no puede contener tu propio correo."
    return None

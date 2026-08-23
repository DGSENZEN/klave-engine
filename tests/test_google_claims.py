"""A Google id_token signs someone in only when it is Google's, for this
app, unexpired and for an email Google verified."""

import time

from apps.api.auth.routes import google_claims_problem

CLIENT = "123.apps.googleusercontent.com"


def _claims(**overrides):
    claims = {
        "iss": "https://accounts.google.com", "aud": CLIENT, "exp": time.time() + 600,
        "sub": "sub-1", "email": "ana@taller.mx", "email_verified": True,
    }
    claims.update(overrides)
    return claims


def test_good_claims_pass():
    assert google_claims_problem(_claims(), CLIENT) is None
    assert google_claims_problem(_claims(iss="accounts.google.com"), CLIENT) is None
    assert google_claims_problem(_claims(aud=[CLIENT, "other"]), CLIENT) is None


def test_wrong_issuer_audience_or_expiry_is_refused():
    assert google_claims_problem(_claims(iss="https://evil.example"), CLIENT) == "google"
    assert google_claims_problem(_claims(aud="another-app"), CLIENT) == "google"
    assert google_claims_problem(_claims(exp=time.time() - 1), CLIENT) == "google"
    assert google_claims_problem(_claims(), None) == "google"
    assert google_claims_problem(_claims(sub=""), CLIENT) == "google"


def test_unverified_email_never_signs_in():
    assert google_claims_problem(_claims(email_verified=False), CLIENT) == "google_unverified"
    unset = _claims()
    del unset["email_verified"]
    assert google_claims_problem(unset, CLIENT) == "google_unverified"
    assert google_claims_problem(_claims(email_verified="true"), CLIENT) == "google_unverified"

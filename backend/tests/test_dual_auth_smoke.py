"""
Phase 2b dual-auth smoke-test harness.

Tests the full trust boundary chain using a minimal FastAPI app + TestClient.
Does NOT import main.py (avoids boto3/pandas). Exercises resolve_caller and
get_current_tenant through real HTTP dispatch to confirm all go/no-go criteria.

Run with pytest:
    cd backend && python -m pytest tests/test_dual_auth_smoke.py -v

Run standalone:
    cd backend && python tests/test_dual_auth_smoke.py
"""
import os
import sys
import pathlib
import tempfile
from datetime import datetime, timezone, timedelta

os.environ["TRUELINE_JWT_SECRET"] = "smoke-pilot-secret-32-bytes-long-padded!!"
os.environ["TRUELINE_AUTH_JWT_SECRET"] = "smoke-auth-secret-32-bytes-long-padded!!!"

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import jwt
import pytest
from fastapi import Depends, FastAPI, HTTPException
from starlette.testclient import TestClient

from app.auth import CurrentTenant, get_current_tenant, issue_pilot_token, JWT_ALGORITHM, JWT_SECRET
from app.auth_bridge import resolve_caller
from app.auth_tokens import (
    AUTH_JWT_ALGORITHM,
    create_access_token,
    create_refresh_token,
    _secret as _auth_secret,
)
import app.db as _db_module
from app.db import auth_db, create_company, create_membership, create_user, init_auth_db


# ─── Simulated session store (mirrors _session_scope.__enter__ in main.py) ───
_sessions: dict = {}


# ─── Minimal test app factory ────────────────────────────────────────────────

def _make_app(auth_dep) -> FastAPI:
    app = FastAPI()

    @app.get("/api/whoami")
    def whoami(tenant: CurrentTenant = Depends(auth_dep)):
        return {"tenant_id": tenant.tenant_id, "user_id": tenant.user_id, "email": tenant.email}

    @app.get("/api/session/{session_id}")
    def session_check(session_id: str, tenant: CurrentTenant = Depends(auth_dep)):
        stored = _sessions.get(session_id)
        if stored is None:
            _sessions[session_id] = tenant.tenant_id
            return {"session_id": session_id, "tenant_id": tenant.tenant_id, "stamped": True}
        if stored != tenant.tenant_id:
            raise HTTPException(status_code=403, detail="Session does not belong to this tenant.")
        return {"session_id": session_id, "tenant_id": tenant.tenant_id, "stamped": False}

    return app


# ─── Shared setup / teardown (callable directly from pytest or standalone) ───

def _setup():
    """Seed temp DB, mint tokens. Returns state dict + cleanup callable."""
    _sessions.clear()
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    _db_module.AUTH_DB_PATH = pathlib.Path(tmp.name)
    init_auth_db()

    with auth_db() as conn:
        co_a_id = create_company(conn, slug="acme-corp", name="Acme Corp")
        user_a_id = create_user(conn, email="alice@acme.com", password="hunter2", display_name="Alice")
        create_membership(conn, company_id=co_a_id, user_id=user_a_id, role="owner")

        co_b_id = create_company(conn, slug="rival-corp", name="Rival Corp")
        user_b_id = create_user(conn, email="bob@rival.com", password="hunter2", display_name="Bob")
        create_membership(conn, company_id=co_b_id, user_id=user_b_id, role="owner")

    def _tokens(user_id):
        with auth_db() as conn:
            ur = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
            mr = conn.execute(
                "SELECT * FROM memberships WHERE user_id = ? ORDER BY created_at ASC LIMIT 1",
                (user_id,),
            ).fetchone()
            access = create_access_token(ur, mr)
            raw_refresh, _ = create_refresh_token(conn, user_id)
        return access, raw_refresh

    access_a, refresh_a = _tokens(user_a_id)
    access_b, refresh_b = _tokens(user_b_id)
    pilot_a = issue_pilot_token(tenant_id="acme-corp", email="ops@acme.com", ttl_days=1)

    state = dict(
        co_a_id=co_a_id, co_b_id=co_b_id,
        user_a_id=user_a_id, user_b_id=user_b_id,
        access_a=access_a, refresh_a=refresh_a,
        access_b=access_b, refresh_b=refresh_b,
        pilot_a=pilot_a,
        client_on=TestClient(_make_app(resolve_caller), raise_server_exceptions=False),
        client_off=TestClient(_make_app(get_current_tenant), raise_server_exceptions=False),
        tmp_path=tmp.name,
    )

    def cleanup():
        os.unlink(tmp.name)

    return state, cleanup


# ─── Individual test functions (plain callables — no pytest magic) ────────────

def check_a_pilot_accepted_flag_on(s):
    r = s["client_on"].get("/api/whoami", headers={"Authorization": f"Bearer {s['pilot_a']}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == "acme-corp"
    assert body["email"] == "ops@acme.com"


def check_b_real_auth_accepted_flag_on(s):
    r = s["client_on"].get("/api/whoami", headers={"Authorization": f"Bearer {s['access_a']}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tenant_id"] == "acme-corp"
    assert body["email"] == "alice@acme.com"


def check_c_tenant_id_is_slug_not_uuid(s):
    r = s["client_on"].get("/api/whoami", headers={"Authorization": f"Bearer {s['access_a']}"})
    assert r.status_code == 200, r.text
    tid = r.json()["tenant_id"]
    assert tid == "acme-corp", f"Expected slug, got: {tid!r}"
    assert s["co_a_id"] not in tid, f"UUID leaked into tenant_id: {tid!r}"


def check_d_cross_tenant_real_auth_403(s):
    _sessions.clear()
    r1 = s["client_on"].get("/api/session/sess-1", headers={"Authorization": f"Bearer {s['access_a']}"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["stamped"] is True
    r2 = s["client_on"].get("/api/session/sess-1", headers={"Authorization": f"Bearer {s['access_b']}"})
    assert r2.status_code == 403, r2.text


def check_d_cross_tenant_pilot_403(s):
    _sessions.clear()
    pilot_b = issue_pilot_token(tenant_id="rival-corp", ttl_days=1)
    r1 = s["client_on"].get("/api/session/sess-p", headers={"Authorization": f"Bearer {s['pilot_a']}"})
    assert r1.status_code == 200
    r2 = s["client_on"].get("/api/session/sess-p", headers={"Authorization": f"Bearer {pilot_b}"})
    assert r2.status_code == 403


def check_e_expired_real_auth_401(s):
    now = datetime.now(timezone.utc)
    expired = jwt.encode(
        {"sub": s["user_a_id"], "email": "alice@acme.com", "company_id": s["co_a_id"],
         "role": "owner", "typ": "access", "jti": "x",
         "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
        _auth_secret(), algorithm=AUTH_JWT_ALGORITHM,
    )
    r = s["client_on"].get("/api/whoami", headers={"Authorization": f"Bearer {expired}"})
    assert r.status_code == 401, r.text


def check_f_refresh_token_rejected(s):
    r = s["client_on"].get("/api/whoami", headers={"Authorization": f"Bearer {s['refresh_a']}"})
    assert r.status_code == 401, r.text


def check_g_invalid_token_rejected(s):
    r = s["client_on"].get("/api/whoami", headers={"Authorization": "Bearer totally.invalid.garbage"})
    assert r.status_code == 401, r.text


def check_h_rollback_real_auth_denied(s):
    r = s["client_off"].get("/api/whoami", headers={"Authorization": f"Bearer {s['access_a']}"})
    assert r.status_code == 401, r.text


def check_h_rollback_pilot_still_works(s):
    r = s["client_off"].get("/api/whoami", headers={"Authorization": f"Bearer {s['pilot_a']}"})
    assert r.status_code == 200, r.text
    assert r.json()["tenant_id"] == "acme-corp"


def check_slug_namespace_shared(s):
    _sessions.clear()
    r1 = s["client_on"].get("/api/session/shared", headers={"Authorization": f"Bearer {s['access_a']}"})
    assert r1.status_code == 200 and r1.json()["stamped"] is True
    r2 = s["client_on"].get("/api/session/shared", headers={"Authorization": f"Bearer {s['pilot_a']}"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["stamped"] is False


def check_missing_header_401(s):
    r = s["client_on"].get("/api/whoami")
    assert r.status_code == 401, r.text


def check_wrong_typ_rejected(s):
    now = datetime.now(timezone.utc)
    wrong = jwt.encode(
        {"sub": s["user_a_id"], "company_id": s["co_a_id"], "typ": "refresh",
         "iat": now, "exp": now + timedelta(minutes=5)},
        _auth_secret(), algorithm=AUTH_JWT_ALGORITHM,
    )
    r = s["client_on"].get("/api/whoami", headers={"Authorization": f"Bearer {wrong}"})
    assert r.status_code == 401, r.text


_ALL_CHECKS = [
    ("3a. pilot token accepted (flag ON)", check_a_pilot_accepted_flag_on),
    ("3b. real-auth token accepted (flag ON)", check_b_real_auth_accepted_flag_on),
    ("3c. tenant_id is slug not UUID", check_c_tenant_id_is_slug_not_uuid),
    ("3d. cross-tenant real-auth 403", check_d_cross_tenant_real_auth_403),
    ("3d. cross-tenant pilot 403", check_d_cross_tenant_pilot_403),
    ("3e. expired real-auth 401", check_e_expired_real_auth_401),
    ("3f. refresh token rejected", check_f_refresh_token_rejected),
    ("3g. invalid token rejected", check_g_invalid_token_rejected),
    ("3h. rollback: real-auth denied (flag OFF)", check_h_rollback_real_auth_denied),
    ("3h. rollback: pilot still works (flag OFF)", check_h_rollback_pilot_still_works),
    ("slug namespace shared (real-auth + pilot)", check_slug_namespace_shared),
    ("missing auth header 401", check_missing_header_401),
    ("wrong typ claim rejected", check_wrong_typ_rejected),
]


# ─── pytest bindings ─────────────────────────────────────────────────────────

@pytest.fixture
def s():
    state, cleanup = _setup()
    yield state
    cleanup()


@pytest.mark.parametrize("label,fn", _ALL_CHECKS, ids=[c[0] for c in _ALL_CHECKS])
def test_dual_auth(s, label, fn):
    fn(s)


# ─── Standalone runner ───────────────────────────────────────────────────────

if __name__ == "__main__":
    results = []
    for label, fn in _ALL_CHECKS:
        state, cleanup = _setup()
        try:
            fn(state)
            results.append((label, True, ""))
            print(f"  [PASS] {label}")
        except Exception as e:
            results.append((label, False, str(e)))
            print(f"  [FAIL] {label}  {e}")
        finally:
            cleanup()
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    print(f"{passed}/{len(results)} passed")
    sys.exit(0 if passed == len(results) else 1)

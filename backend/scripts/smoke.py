"""WACE Light backend smoke test — boots the app and exercises the core flows.
Exits non-zero on failure. Run: python -m scripts.smoke  (from backend/)."""
from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from src.main import app


def main() -> int:
    # Run startup (init_db) once.
    for hook in app.router.on_startup:
        hook()
    c = TestClient(app)

    assert c.get("/health").json().get("product") == "wace-light", "health"
    assert c.get("/voundry/portal/connectors/catalog").status_code == 401, "auth gate"

    r = c.post("/voundry/auth/register", json={"email": "ci@example.com", "password": "password123", "display_name": "CI"})
    assert r.status_code == 200, f"register: {r.status_code} {r.text}"
    h = {"Authorization": f"Bearer {r.json()['token']}"}

    assert c.get("/voundry/me", headers=h).status_code == 200, "me"
    wu = c.post("/voundry/portal/my-desk", json={"role": "it_ops"}, headers=h).json()["work_unit_id"]
    assert c.get(f"/voundry/portal/workspaces/{wu}", headers=h).status_code == 200, "room"
    assert len(c.get("/voundry/portal/onboarding-suite?role=it_ops", headers=h).json()["basic"]) > 0, "onboarding"
    assert c.post("/voundry/portal/saib-preview", json={"text": "mail a@b.com"}, headers=h).json()["count"] >= 1, "saib"
    assert c.get(f"/voundry/portal/workspaces/{wu}/receipts", headers=h).status_code == 200, "receipts"
    assert c.get("/voundry/portal/command-center", headers=h).status_code == 200, "command-center"

    print("WACE Light smoke: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

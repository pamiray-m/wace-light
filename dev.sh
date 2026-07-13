#!/usr/bin/env bash
# WACE Light — one-command local dev. Generates secrets on first run, installs
# deps, and starts the backend (:8000) + frontend (:5173) together.
#   ./dev.sh        start both
#   Ctrl-C          stop both
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="backend/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo "==> First run — generating $ENV_FILE with fresh secrets"
  JWT=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  VAULT=$(python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
  cat > "$ENV_FILE" <<ENV
AOS_JWT_SECRET=$JWT
AOS_VAULT_KEY=$VAULT
AOS_DB_URL=sqlite:///./wace_light.db
# Bring your own key: uncomment to start with a platform key, or add it in-app.
# ANTHROPIC_API_KEY=sk-ant-...
ENV
fi

echo "==> Backend: venv + deps"
if [ ! -d backend/.venv ]; then python3 -m venv backend/.venv; fi
# shellcheck disable=SC1091
backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "==> Frontend: npm deps"
( cd frontend && [ -d node_modules ] || npm install --silent )

echo "==> Starting backend (:8000) + frontend (:5173)"
set -a; . "$ENV_FILE"; set +a
( cd backend && PYTHONPATH=. ../backend/.venv/bin/python -m uvicorn src.main:app --reload --port 8000 ) &
BACK=$!
( cd frontend && npm run dev ) &
FRONT=$!
trap 'echo; echo "==> Stopping"; kill $BACK $FRONT 2>/dev/null || true' INT TERM
echo "==> Open http://localhost:5173  (backend on :8000)"
wait

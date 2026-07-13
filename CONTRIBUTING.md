# Contributing to WACE Light

Thanks for your interest! WACE Light is the open-source, individual edition of
WACE — a governed AI command environment. Contributions of all kinds are welcome:
bug reports, docs, connectors, and features that keep the "governed by default"
promise (read-only tools, SAIb redaction, human-approved writes, WORM receipts).

## Ground rules

- **Keep it governed.** Any new connector action that changes external state is
  a *write*: it must be read-only by default and route through the approval gate,
  never fire on the agent's own. Anything an agent reads must pass through SAIb.
- **No secrets, ever.** Never commit real keys, tokens, or customer data. `.env`
  is git-ignored; use `.env.example` for placeholders.
- **Individual-first.** This edition targets a single self-hosting user. Team /
  org features (SSO, SCIM, multi-tenant) belong in the commercial edition.

## Project layout

- `backend/` — FastAPI over the governed engine:
  - `src/aos/voundry/` — connectors, agents, ingest, BYOK, onboarding, governance, WORM audit
  - `src/saib/` — the redaction guard · `src/llm/` — the LLM gateway · `src/core/` — kill switch, vault
  - `src/api/routes/wace.py` — the HTTP API · `src/main.py` — entrypoint
- `frontend/` — a React + Vite single-page console (`src/voundry-app/`).

## Local setup

**Backend**
```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AOS_JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
export AOS_VAULT_KEY=$(python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())")
export AOS_DB_URL="sqlite:///./wace_light.db"
uvicorn src.main:app --reload --port 8000
```

**Frontend**
```bash
cd frontend
npm install
npm run dev
```

## Before you open a PR

Run what CI runs — both must pass:

```bash
# backend smoke (boots the app + exercises the core flows)
cd backend && AOS_JWT_SECRET=dev-secret-at-least-32-characters-long \
  AOS_VAULT_KEY=$(python3 -c "import secrets,base64; print(base64.b64encode(secrets.token_bytes(32)).decode())") \
  AOS_DB_URL="sqlite:///./ci.db" PYTHONPATH=. python -m scripts.smoke

# frontend typecheck + build
cd frontend && npm run build
```

CI (`.github/workflows/ci.yml`) runs these on every push and pull request.

## Pull requests

1. Fork, branch from `master`, keep changes focused.
2. Match the surrounding style; add/extend the smoke checks when you add a route
   or a governed action.
3. Write a clear description: what changed, why, and how you verified it.
4. By submitting a PR you agree your contribution is licensed under the project's
   **AGPL-3.0** license.

## Reporting bugs / security

- Bugs: open a GitHub issue with steps to reproduce.
- **Security issues: do not open a public issue.** Email the maintainers so it can
  be handled privately first.

## License

WACE Light is licensed under [AGPL-3.0](./LICENSE). Running a modified version as
a network service requires making your source available. For a commercial license
of WACE, contact the authors.

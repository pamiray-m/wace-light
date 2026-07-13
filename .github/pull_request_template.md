## What & why
<!-- What does this change, and why? Link any issue. -->

## How verified
<!-- What did you run? Both should pass: -->
- [ ] Backend smoke: `cd backend && PYTHONPATH=. python -m scripts.smoke` (with env set)
- [ ] Frontend: `cd frontend && npm run build`

## Governed-by-default check
<!-- Only if you touched connectors / agents / actions -->
- [ ] New writes are read-only by default and go through the approval gate
- [ ] Anything an agent reads passes through SAIb
- [ ] No secrets committed

## Notes
<!-- Anything reviewers should know -->

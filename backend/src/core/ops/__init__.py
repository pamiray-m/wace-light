"""
Ops-1 — Operational health and readiness services.

Provides production-grade liveness and readiness surfaces for use by
infrastructure probes (Docker HEALTHCHECK, Kubernetes liveness/readiness
probes, load balancers) and operators.

Modules
-------
health      : Lightweight liveness model and service.
readiness   : Structured dependency-aware readiness model and service.
"""

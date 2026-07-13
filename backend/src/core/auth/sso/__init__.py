"""
W3.4 — Enterprise SSO entry points.

OIDC ID-token verifier today; SAML is wired through the same abstraction
in a follow-up. Operators flip `AOS_SSO_PROVIDER=oidc` and configure the
discovery URL + client_id to enable federated login.
"""

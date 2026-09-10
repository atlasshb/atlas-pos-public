# 04 — One front door: reverse proxy + single identity provider

The single most valuable piece of self-hosted architecture is also the
simplest: **one reverse proxy and one identity provider in front of everything.**

## Why one front door

- One place to terminate TLS and set security headers.
- One place to enforce authentication.
- One place to add a new app without exposing a new port to the internet.
- One place to audit who reached what.

## Native OIDC vs `forward_auth`

Many self-hosted apps now speak **native OIDC/SAML**; wire those directly to
your IdP. For apps that don't, the proxy can do **forward-auth**: it asks the
IdP "is this session valid?" before passing the request through. Prefer native
OIDC where it exists (cleaner user experience, fewer surprises); use forward-auth
as the universal fallback.

## Rules that prevented lockouts

- **Keep a local login fallback.** Never make SSO the *only* way into an app
  that you might need to reach when the IdP is down. Leave a break-glass admin
  and document how to use it.
- **One-line rollback.** Changing an app's auth should be revertible by
  restoring one config file and reloading the proxy.
- **Test the new login end-to-end** before announcing it; verify the redirect
  chain, not just that the app starts.
- **The 200 that lies.** Some admin APIs return HTTP 200 while silently doing
  nothing. Verify the *effect*, not the status code.
- **Email-as-identifier is a landmine.** If an app keys identity on the email
  address, changing someone's mailbox can lock them out. Prefer a stable
  identifier where the app supports it.

## Deprovisioning

**One offboarding path beats per-app discipline.** A useful test: disable a user
in every app from one process and confirm they lose access everywhere. Three
apps removing a user on three different dates means you have no offboarding
process — you have three tools.

## Default posture

- Every service that doesn't need public exposure binds to **loopback** or the
  private mesh interface — never `0.0.0.0`.
- Public exposure is a deliberate, reviewed decision per service, not a default.
- Prefer SSH key auth only; disable password login.
- Keep the identity provider behind the same proxy as everything else.

## A minimal rollback-friendly pattern

1. Add the app's OIDC client config as a single file/env.
2. Keep the existing local-auth config intact.
3. Point the proxy at the app.
4. Verify the full login redirect chain.
5. If anything is wrong, restore the previous config and reload.

## Takeaway

Centralise the two chokepoints (proxy + IdP), keep a break-glass local path, and
make every auth change a one-file, one-reload revert.

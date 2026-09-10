# Connection Pack — venue-b-till (and the pattern for future clients)

**Owner:** Atlas, Atlas Corporation (NL)
**Scope:** how pos-hub (hub, Tailscale `192.0.2.10`) reaches and will reach client **venue-b-till**
(Tailscale `192.0.2.10`) — today and once a maintenance window opens.
**Status:** Layers 1–2 LIVE. Layers 3–4 STAGED (prepared, not deployed) — see gating below.
**Last updated:** 2026-07-01

> This document ties together the layered, redundant connection strategy for venue-b-till and is meant
> to be the template for every future client added to the fleet (see PROGRAM.md / ROADMAP.md for the
> program-wide rules this pack instantiates).

---

## Why layered

No single connection path to a client terminal is trustworthy on its own: Tailscale gives us transport
but not visibility into whether the box is even on; a monitor tells us it's reachable but can't move
data; a sync/backup layer moves data but needs software installed on a LIVE payment terminal, which is
gated by program principle #1 ("Live terminals are sacred"). So the strategy is deliberately layered —
each layer adds a capability, and each layer's blast radius and gating is scoped to what it actually
does.

| Layer | Purpose | Reach | Status |
|---|---|---|---|
| 1. Tailscale | Transport | Already active on venue-b-till | **LIVE** |
| 2. Monitoring (`pos-watch`) | Reachability / uptime alerting | Read-only probe, no writes | **LIVE**, no gate needed |
| 3. Syncthing | File-level sync (twin/backup redundancy) | Hub side staged now; client side needs install | **STAGED** — client install GATED |
| 4. MeshCentral | Interactive remote screen/command access | Docs/runbook only | **STAGED** — GATED, SSO-only admin |

---

## LAYER 1 — Tailscale (already active)

- **What:** the tailnet is the sole transport between pos-hub and every client box (program principle
  #7 — MySQL `:3306` / RDP / Odoo `:8069` are reachable on the tailnet only, never publicly exposed).
- **venue-b-till today:** node `venue-b-till`, Tailscale IP `192.0.2.10`. Reachable services over the
  tailnet: OptimumPOS MySQL `:3306` (live terminal, powered off/on often), Odoo 19 Community staging
  `:8069`, SMB `:445` open. RDP/SSH/WinRM are **closed** — there is currently no execution path from the
  hub onto this box.
- **Used by:** `scripts/pos-mirror.sh` (capability B — the read-only `mysqldump` pull + twin + restic
  backup) and staging access to the Odoo instance. This is the primary transport for all data movement
  described in PROGRAM.md.
- **Gating:** none beyond what's already in `pos-mirror.sh` (fail-closed on `MIRROR_ENABLED` /
  `DPA_SIGNED`, tailnet-IP assertion, quiet window, flock). Do not modify that script; follow its
  conventions for any new per-client automation.

---

## LAYER 2 — Monitoring (`pos-watch`)

- **What:** a read-only reachability probe (ping / port-probe of venue-b-till over the tailnet), pushing
  an ntfy notification on every online/offline state transition. Implemented as
  `scripts/pos-watch.sh` driven by a `pos-watch@.timer` systemd unit (per-client instance, same pattern
  as `pos-mirror@.timer`).
- **Risk class:** identical to `fleet-inventory.sh`'s existing probes (capability A, discovery) — pure
  network-level read, zero writes to the terminal, zero new software on the terminal.
- **Gating:** **none.** This is explicitly *not* gated under principle #1, because it does not touch the
  live terminal in any state-changing way — same class as the inventory probes that already run freely
  fleet-wide.
- **Status:** deployed now for venue-b-till. Alerts land on the `pos-mirror` ntfy topic (or a dedicated
  `pos-watch` topic if separated later) via `atlas-ntfy` at `http://atlas-ntfy/`.

---

## LAYER 3 — Syncthing

- **What:** file-level sync between the hub and venue-b-till, as an additional redundancy path alongside
  the MySQL mirror (e.g. for local backup exports, config files, or anything not naturally captured by
  the `mysqldump`-based twin).
- **Hub side (`scripts/venue_b-syncthing-prep.sh`):** **safe, local-only, done now.** pos-hub already
  runs Syncthing as two active systemd services — `syncthing@root` and `syncthing@atlas` — this is
  existing production config and is **not** touched or restarted. The prep script only adds a new
  folder definition via the **local REST API** (`http://127.0.0.1:8384/rest/...`, `X-API-Key` read live
  out of `/root/.config/syncthing/config.xml` into a shell variable — never printed to stdout/logs).
  Syncthing hot-applies new folders without a restart, which is materially lower-risk than editing env
  or bouncing a shared service.
- **Client side (venue-b-till):** **GATED.** Installing a Syncthing client on venue-b-till is new
  persistent software on a live card-payment terminal — exactly the class of action principle #1
  reserves for "per-site, with that client's explicit go, inside a quiet window." It stays un-deployed
  until:
  1. Operator (Atlas) gives explicit go for this specific client/site, **and**
  2. An execution path exists to actually install it (today: none — RDP/SSH/WinRM are closed; SMB
     `:445` is open but is not by itself a safe unattended install path onto a live terminal).
- **Status:** hub-side folder staged; nothing installed or running on venue-b-till.

---

## LAYER 4 — MeshCentral

- **What:** interactive remote screen/remote-command access to venue-b-till for the cases Syncthing and
  the MySQL mirror can't cover (ad-hoc diagnostics, manual intervention during a migration step).
- **Documented in:** `runbooks/meshcentral-enroll-venue_b.md` — docs/manual only, no automation, because
  the MeshCentral admin console is SSO-only (no headless/scriptable enrollment path exists today).
- **Gating:** **GATED**, same basis as Layer 3 — a persistent remote-control agent is new software on a
  live terminal. Requires operator explicit go + an execution path (see below) before the runbook's
  steps are actually carried out.
- **Status:** runbook written and ready to follow; agent **not installed** on venue-b-till.

---

## What's live vs. staged — summary

- **LIVE now, no further action needed:** Layer 1 (Tailscale transport, already carrying the MySQL
  mirror and Odoo staging traffic) and Layer 2 (`pos-watch` reachability monitoring + ntfy alerts).
- **STAGED, not deployed:** Layer 3 (Syncthing — hub folder ready, client install blocked) and Layer 4
  (MeshCentral — runbook ready, enrollment blocked). Neither requires any decision right now; both are
  ready to execute the moment the two blockers below are cleared.
- **The two blockers, explicitly:**
  1. **Operator's explicit go** for installing new persistent software on venue-b-till specifically (per
     program principle #1 — this is not a fleet-wide decision, it's per-client, per-action).
  2. **An execution path onto the box** — currently none exists. RDP/SSH/WinRM are closed. The realistic
     options are: (a) SMB credentials sufficient to push/run an installer, or (b) physical presence /
     RDP re-enabled temporarily at the shop, or (c) a remote-assisted session with whoever is on-site.

---

## Checklist — when venue-b-till next has a maintenance window

Use this the next time the shop is closed and someone (operator or a trusted on-site contact) can be
physically or remotely present at the terminal:

1. **Confirm the quiet window** against the client's declared closed hours (see `clients/venue_b/env`
   `QUIET_WINDOW`) — do not act outside it.
2. **Get explicit per-action operator go** — a yes to "install Syncthing on venue-b-till today" and/or
   "enroll venue-b-till in MeshCentral today" are two separate asks; either can proceed independently.
3. **Establish an execution path** for whichever layer is approved:
   - Syncthing client install: need either working SMB credentials + a safe push mechanism, or
     temporary RDP/physical access to run the installer interactively.
   - MeshCentral enrollment: follow `runbooks/meshcentral-enroll-venue_b.md` step by step — it is
     SSO-gated and manual by design, so plan for someone to be at a browser during enrollment.
4. **Install/enroll the minimum needed** — do not bundle unrelated changes into this window
   (principle #3: additive, idempotent, reversible; one change, one verification).
5. **Verify immediately post-install:**
   - Syncthing: confirm the new device pairs, the staged hub-side folder syncs, then leave the client
     device introduced but out-of-band from anything payment-related.
   - MeshCentral: confirm the agent shows online in the console, do a no-op remote command as a smoke
     test, then log off.
6. **Push an ntfy confirmation** (same `atlas-ntfy` / topic convention as `pos-mirror`) so the change is
   visible fleet-wide, and record the action in the program ledger per governance rules
   (`governance/INTEGRATION.md`).
7. **Update this document's status table** (Layers 3/4 rows) from STAGED to LIVE once confirmed, and
   note the date + who approved it.
8. **Never** treat a successful window for one layer as blanket approval for the other, or for any other
   client — each is a separate per-site, per-action consent per program principle #1.

---

## Reuse for future clients

For each new client added to the fleet:
- Layers 1–2 (Tailscale + `pos-watch`) can be turned on immediately once the client is enrolled on the
  tailnet — no gate, same as venue-b-till.
- Layers 3–4 follow the identical gating pattern: hub-side prep (Syncthing folder, MeshCentral runbook)
  can be done ahead of time with zero risk; client-side install/enrollment always waits for that
  client's explicit go plus a real execution path, evaluated independently per client.

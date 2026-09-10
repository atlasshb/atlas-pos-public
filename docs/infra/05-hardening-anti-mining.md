# 05 — Hardening: default-deny exposure and cryptominer defence

If you run a public host, you will be scanned within hours. The goal is not to
be interesting to attackers: **default-deny exposure, least privilege, and
detection that assumes compromise.**

## Exposure discipline

- **Bind to loopback by default.** A service reachable from the internet should
  be a decision, not an accident. Most databases, admin panels, queues and
  internal tools should never be publicly reachable.
- **Inventory what is actually listening on public interfaces** regularly; drift
  is constant. Compare listeners against an intended allow-list.
- **Keep only the ports you need** (web, and your chosen remote-access path).
  Close the rest at the firewall.
- **No inbound SSH password auth**; keys only; rate-limit and ban on failed
  attempts.

## Least privilege

- **A backup job needs read access to what it backs up, and nothing else.** Use
  a dedicated read-only account for database dumps.
- **No long-lived root shell for automation tools or AI agents.** This is how
  supply-chain compromises become host compromises. If an agent must act, give
  it a scoped API, not a shell.
- **Separate service accounts per concern.** One blast radius per credential.
- **Never store secrets in the repository or in world-readable config.** Read
  them from a secret store or a locked file.

## Cryptominer defence (container-aware)

Miners are the most common payload on a compromised public host. They are often
installed by an over-privileged automation/agent, then persist via multiple
copies and a restore loop.

**Prevent:**
- Run exposed services as non-root with a read-only root filesystem where
  possible.
- Apply seccomp/AppArmor profiles; drop Linux capabilities.
- Cap CPU/memory so a runaway process can't starve the box.
- Don't install build tools you don't need on the production host.

**Detect:**
- Watch for sustained high CPU with low legitimate load, and for connections to
  known mining pools.
- Monitor for *new* scheduled tasks, systemd units and startup entries.
- Alert on unexpected outbound connections from normally quiet services.

**Respond:**
- **Treat a root compromise as a rebuild.** Restore *data* onto a fresh host;
  do not trust the compromised image. Rotate **every** credential the host could
  have seen.
- Kill persistence in all its forms: multiple payload copies, a restore loop
  (a timer/`@reboot` job that re-downloads it), and injected code in unrelated
  files. Deleting one file is not enough.

**A reusable hunt idea:** miners from one common family forge file mtimes to
match a system binary. A `find` for files created in a narrow one-second window
matching that timestamp surfaces them — but this catches **only that family**;
other miner loaders carry honest timestamps and need a different hunt (grep for
the literal payload string, check all cron/`@reboot` marks, and inspect startup
units). Always confirm you are hunting **all** marks a family drops, not one.

## Takeaway

Assume compromise and design detection accordingly. The cheapest controls are
the boring ones: loopback by default, no root shells for automation, read-only
credentials, and alerts on *new* persistence.

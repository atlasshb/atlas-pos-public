# 01 — Right-sizing: you probably don't need Kubernetes

At small-team scale, the honest question is: **is this a capacity problem or an
orchestration problem?** They have different fixes, and buying a platform for
the wrong one adds complexity without solving anything.

## When Kubernetes is the wrong tool

- You have a handful of services on one or two boxes.
- Your real pain is disk/RAM pressure, not scheduling.
- There is no team to own a control plane and its failure modes.
- Downtime tolerance is "a few minutes", not "zero".

In that case, primitives you already run cover most of what you wanted from
orchestration:

| What you wanted | Simpler primitive |
|---|---|
| Scheduling / placement | Docker Compose or Docker Swarm |
| Self-healing | `restart: unless-stopped` + healthchecks |
| Deploy pipeline | A managed PaaS-on-your-VPS (Coolify, Dokploy, CapRover) |
| Secrets | Docker/Compose secrets + an external secrets store |
| Ingress | The reverse proxy you already run |
| Rollouts | Recreate the container (seconds of downtime) |

## The two-axis framing

1. **Capacity** — CPU/RAM/disk/IO. Fix by upgrading the box, moving workload
   offsite, or right-sizing services. Kubernetes does not create capacity.
2. **Orchestration** — many services, many hosts, deploy cadence, blast-radius
   control. Only here does a scheduler start to earn its keep.

Be honest about which one you have. "The box is full" is a capacity problem.

## Where a second box *does* help

- **Availability of client-facing services** (a standby that can take over).
- **Offloading heavy but non-critical work** (batch jobs, GPU work) away from
  the production box.
- **Backups** — a copy on a different provider/region is the whole point.

## Tiering the fleet

A useful pattern is to tier by failure impact:

- **Public/production tier** — client-facing; harden, monitor, back up, test.
- **Ops/internal tier** — internal tools; tolerate a restart.
- **Edge/worker tier** — batch/GPU/office machines; best-effort, can be offline.

Match redundancy and effort to the tier. Don't give best-effort hardware a
99.9% promise, and don't run a client site on best-effort hardware.

## Takeaway

Prefer the smallest primitive that solves *your* actual problem. You can always
add a scheduler later; removing one you didn't need is hard.

# 06 — Silent-failure operations

The most dangerous failure is the one that doesn't page you. Most of our real
incidents were not crashes — they were jobs that quietly stopped doing their job
while reporting success.

## Monitor freshness, not liveness

"The process is running" is not health. What you want to know is:

- **When did this job last *succeed*?** Alert if that age exceeds the expected
  schedule by a margin.
- **Did the output change size unexpectedly?** A dump that suddenly drops from
  megabytes to bytes failed, even if the command exited 0.
- **Is a queue/backlog growing?** A consumer that stopped consuming still looks
  alive.

## Specific traps

- **`cmd | gzip > file` hides `cmd`'s exit code.** If the pipeline succeeds but
  the command inside failed, you still get a (tiny) output file. Use
  `set -o pipefail` and assert a minimum output size.
- **An empty config file can stall a pipeline for weeks.** A validator that
  reads an empty file and "succeeds" stops the real work. Check config presence
  and non-emptiness.
- **Stale locks silently disable maintenance.** A lock left by a crashed run can
  block integrity checks and pruning indefinitely. Detect and clear stale locks.
- **Scheduled jobs that need a logged-in user simply don't run** when no one is
  logged in — with no error. Run jobs as a service/boot task, and alert on
  missed runs.
- **Cron output mailed to a full mailbox** is not monitoring. If you discard
  cron mail, you have removed a tripwire — replace it with explicit freshness
  checks.

## What to build

- A **heartbeat** for each critical job: on success it writes a timestamp
  somewhere; a separate check alerts when any heartbeat is stale.
- **Explicit OK/FAIL logging** for backup/verify/prune steps (exit codes, not
  prose).
- **A small status page** that shows last-success per job, visible to the team.
- **Alert on changes, not just thresholds**: new cron entries, new systemd
  units, new public listeners.

## Disk pressure

Disk and memory pressure cause weird, indirect failures. Watch disk-free trend
and act on trend, not just the threshold. A backup/off-site sync with **no
retention** will one day fill its disk and take something else down with it.

## Takeaway

Design for the quiet failure. If a job can stop without anyone noticing, it
eventually will. Make freshness visible and alarm on it.

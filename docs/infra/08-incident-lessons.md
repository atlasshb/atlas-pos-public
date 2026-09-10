# 08 — Incident lessons

Distilled, de-identified lessons from real incidents. No indicators, addresses
or credentials are included — the point is the **process**, not the specifics.

## 1. Git (or an append-only remote) is the durable record

A local reorg destroyed working files that had never been committed, and the
only copies were on the machine being reorganized. Lesson: before any cleanup,
**commit and verify** the state somewhere else. Local "tidy up" is destructive.

## 2. A revoked key can silently stop backups

Rotating an access key broke the backup pipeline's source access, but the job
still appeared to "complete". Lesson: rotate keys for **every** consumer, and
make backup failures alarm. Never let a backup report success on a failed pull.

## 3. Over-privileged automation is how compromise becomes host compromise

A tool with a root shell on the production host fetched and ran a remote script,
which installed persistence. Lesson: **no agent or automation gets a root
shell.** Scope access to the task; prefer APIs over shells; treat any host
access as a high-risk privilege.

## 4. Root compromise ⇒ rebuild, don't clean

Once an attacker had root, cleaning was not trustworthy. Lesson: rebuild on a
fresh host, restore **data** (not images/snapshots), and rotate every credential
the host could have seen. A snapshot can carry persistence; data usually can't.

## 5. Print/notification changes remove tripwires

Routing cron output to a discarded mailbox removed the one signal that used to
reveal odd jobs. Lesson: if you remove a tripwire, replace it with an explicit
check. Don't make detection quieter by accident.

## 6. Don't clean up logs during an incident

Vacuuming the journal during an investigation destroyed the forensic timeline.
Lesson: freeze and preserve logs during an incident; clean up afterwards.

## 7. Manual cache deletion broke a site's CSS

Deleting a plugin's generated cache by hand (instead of via the app) broke
styling. Lesson: use the application's own cache-clear mechanism; never delete
generated artifacts by hand.

## 8. Concurrent config edits clobbered a proxy

Two editors saved config at once; one file overwrote the other and a site went
down. Lesson: serialize changes to shared config, validate before reload, and
keep a known-good backup of the config.

## 9. The break-glass credential must be reachable

During an outage, the emergency token lived only in a provider console that
couldn't be logged into. Lesson: escrow break-glass credentials somewhere
reachable **before** you need them.

## 10. A backup never restored is a hope

Standing up a restore drill turned a hopeful pipeline into a proven one (and
exposed dead sources and stale locks). Lesson: schedule restore drills; monitor
freshness of the last **successful** run.

## The meta-lesson

Almost every incident traced back to one of: **too much privilege**, **a silent
failure**, **an irreversible action**, or **a backup that wasn't proven**. Design
against those four and you remove most of the blast radius before it happens.

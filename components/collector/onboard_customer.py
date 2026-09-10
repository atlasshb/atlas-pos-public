"""Onboard a new POS customer into the fleet in one command (run on pos-hub).

Prereqs (the part that needs reach — operator or MeshCentral):
  1. The customer's POS box is on the Tailscale mesh -> you have its tailnet IP.
  2. Its kassa MySQL has a remote-capable user (OptimumPOS ships 'remote'@'%').

Then:
  python onboard_customer.py --slug venue-l --name "Venue L" \
      --ip 100.x.y.z [--mysql-user remote --mysql-pw <pw> --db kassa --port 3306]

Does: adds the customer to fleet.json (direct-poll), creates an Authentik access
group "POS <Name>", restarts the collector, and takes the first PAN-scrubbed
mirror + hash-chain pass so the terminal shows up in the cockpit immediately.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
FLEET = HERE / "fleet.json"
LEDGER = HERE / "mirrors.sqlite"
CHAIN_DB = HERE / "journal_chain.sqlite"
MIRROR_ROOT = pathlib.Path("/srv/atlas-posops/mirrors")
PALETTE = ["#7CFFB2", "#ffd166", "#c792ea", "#ff8a3c", "#5cc8ff", "#f4b740"]


def create_authentik_group(name: str):
    script = (
        "from authentik.core.models import Group;"
        f"g,_=Group.objects.get_or_create(name='POS {name}');"
        "print('group ok', g.name)"
    )
    subprocess.run(["docker", "cp", "/dev/stdin", "atlas-authentik-server:/tmp/grp.py"],
                   input=script.encode(), check=False)
    # write the script to a temp file then exec (interactive ak shell mangles stdin)
    tmp = pathlib.Path("/tmp/atlas_grp.py")
    tmp.write_text(script)
    subprocess.run(["docker", "cp", str(tmp), "atlas-authentik-server:/tmp/atlas_grp.py"], check=True)
    r = subprocess.run(["docker", "exec", "atlas-authentik-server", "ak", "shell", "-c",
                        "exec(open('/tmp/atlas_grp.py').read())"],
                       capture_output=True, text=True)
    return "group ok" in (r.stdout + r.stderr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--ip", required=True, help="tailnet IP of the POS box")
    ap.add_argument("--mysql-user", default="remote")
    ap.add_argument("--mysql-pw", default="<MYSQL_PASSWORD>")
    ap.add_argument("--db", default="kassa")
    ap.add_argument("--port", type=int, default=3306)
    ap.add_argument("--node-id", default=None)
    args = ap.parse_args()

    node_id = args.node_id or f"{args.slug}-kassa1"
    fleet = json.loads(FLEET.read_text())
    if any(c["id"] == args.slug for c in fleet["customers"]):
        sys.exit(f"customer '{args.slug}' already exists in fleet.json")

    color = PALETTE[len(fleet["customers"]) % len(PALETTE)]
    fleet["customers"].append({
        "id": args.slug, "name": args.name, "odoo_partner_id": None,
        "tier": "external", "color": color,
        "access_groups": [f"POS {args.name}"],
        "terminals": [{
            "node_id": node_id, "label": f"Kassa ({args.ip})",
            "direct_mysql": {"host": args.ip, "port": args.port, "user": args.mysql_user,
                             "password": args.mysql_pw, "database": args.db},
        }],
    })
    FLEET.write_text(json.dumps(fleet, indent=2, ensure_ascii=False))
    print(f"[1/5] fleet.json: added {args.slug} ({node_id}@{args.ip})")

    ok = create_authentik_group(args.name)
    print(f"[2/5] Authentik group 'POS {args.name}': {'created' if ok else 'FAILED (create manually)'}")

    subprocess.run(["systemctl", "restart", "atlas-posops-collector"], check=False)
    print("[3/5] collector restarted")

    # first mirror + chain
    sys.path.insert(0, str(HERE))
    import posops_direct, journal_chain
    term = fleet["customers"][-1]["terminals"][0]
    m = posops_direct.mirror_direct(term, MIRROR_ROOT, LEDGER, args.slug)
    print(f"[4/5] first mirror: {m['size_bytes']} bytes, {m['tables']} tables, {m['pans_redacted']} PAN redacted")
    c = journal_chain.run_chain(args.slug, node_id, term, CHAIN_DB)
    print(f"[5/5] hash-chain: {c['new']} orders chained, head {c['head_hash'][:12] if c['head_hash'] else '-'}")

    print(f"\nDONE. {args.name} is live in the cockpit.")
    print(f"  - Give the client cockpit access: add their Authentik user to group 'POS {args.name}'.")
    print(f"  - They log in at https://cockpit.178-105-85-200.nip.io and see only their own terminal.")


if __name__ == "__main__":
    main()

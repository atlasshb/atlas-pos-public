# 14 — Architecture diagrams

All diagrams are [Mermaid](https://mermaid.js.org/) and render natively on
GitHub and Forgejo. They are conceptual — no real addresses, hosts or vendors'
endpoints are shown.

## System context

```mermaid
graph TB
    subgraph Venue["Venue (counter)"]
        CASHIER[Cashier / operator]
        TERMINAL[Card terminal<br/>Worldline · CCV · PAX · Ingenico · Verifone]
        PRINTER[Receipt / kitchen printer]
    end

    subgraph POS["Atlas POS"]
        ODOO[Odoo 19 Community<br/>point_of_sale + pos_restaurant]
        PDV[pos_pinvandaag_atlas<br/>payment terminal backend]
        SEED[atlas_pos_seed<br/>catalogue / config]
        THEME[atlas_pos_theme<br/>backend + login skin]
    end

    subgraph Cloud["Cloud / external"]
        PSP[Pin Vandaag REST API v2]
        ACQ[Acquiring network<br/>Worldline / CCV]
        BANK[Business bank]
        IDP[Identity provider<br/>OIDC]
    end

    CASHIER --> ODOO
    ODOO --> PDV
    PDV -- HTTPS / X-API-KEY --> PSP
    PSP --> TERMINAL
    TERMINAL --> ACQ
    ACQ --> BANK
    ODOO --> PRINTER
    ODOO -. SSO .-> IDP
    SEED -. config .-> ODOO
    THEME -. skin .-> ODOO
```

## Card payment flow (cloud-terminal route)

```mermaid
sequenceDiagram
    participant K as Cashier (POS)
    participant O as Odoo POS
    participant P as pos_pinvandaag_atlas
    participant V as Pin Vandaag API
    participant T as Terminal

    K->>O: Select items, choose "Pinnen"
    O->>P: start payment (amount, reference)
    P->>V: POST transactions/start
    V->>T: Display amount
    T-->>V: Customer taps / inserts card
    V-->>P: status (pending → done)
    P-->>O: payment result
    O-->>K: Receipt printed, order closed
    Note over V,T: Card data never touches the POS.<br/>No PAN storage, no fund custody.
```

## Odoo module dependencies

```mermaid
graph LR
    BASE[base] --> SEED[atlas_pos_seed]
    WEB[web] --> SEED
    POS[point_of_sale] --> SEED
    ACC[account] --> SEED

    BASE2[base_setup] --> PDV[pos_pinvandaag_atlas]
    POS2[point_of_sale] --> PDV

    WEB2[web] --> THEME[atlas_pos_theme]
```

## Migration: bridge-first, read-only twin

```mermaid
flowchart LR
    LIVE[(Incumbent POS DB<br/>live terminal)]:::live
    TWIN[(Read-only twin<br/>on hub)]:::safe
    ODOO[(Odoo 19 Community<br/>per-venue)]:::target

    LIVE -- "read-only dump<br/>(never write to source)" --> TWIN
    TWIN -- "idempotent ETL<br/>OPT-PK keys, dry-run first" --> ODOO
    LIVE -. "runs in parallel until cutover" .-> ODOO

    classDef live fill:#FDE8E8,stroke:#C0392B,color:#5B1A1A
    classDef safe fill:#E8F1FB,stroke:#0EA5FF,color:#0A1628
    classDef target fill:#E9F7EF,stroke:#2E7D46,color:#123B22
```

## Backups: 3-2-1 with a tested restore

```mermaid
flowchart TB
    SRC[Production data] --> SNAP[Encrypted snapshot]
    SNAP --> LOCAL[Copy: local / same region]
    SNAP --> OFFSITE[Copy: off-site object storage]
    OFFSITE --> VERIFY{Restore drill<br/>scheduled}
    VERIFY -- pass --> OK[Trusted backup]
    VERIFY -- fail --> ALERT[Alert + fix]
    SNAP -. retention/prune .-> LOCAL
    OFFSITE -. retention/prune .-> OFFSITE
```

## Fleet tiering

```mermaid
graph TB
    subgraph T1["Public / production tier"]
        PROD[Client-facing services<br/>hardened · monitored · backed up]
    end
    subgraph T2["Ops / internal tier"]
        OPS[Internal tools<br/>restart-tolerant]
    end
    subgraph T3["Edge / worker tier"]
        EDGE[Batch · GPU · office machines<br/>best-effort, may be offline]
    end
    T1 --- T2 --- T3
    T2 -. can assist .-> T1
    T3 -. offloads work from .-> T1
```

## Repository map

```mermaid
graph TB
    ROOT[atlas-pos-public]
    ROOT --> DOCS[docs/<br/>research + design]
    ROOT --> INFRA[docs/infra/<br/>self-hosting patterns]
    ROOT --> ADDONS[addons/<br/>Odoo modules]
    ROOT --> MIG[migration/<br/>OptimumPOS → Odoo ETL]
    ROOT --> PROG[program/<br/>fleet program docs]
    ROOT --> SCRIPTS[scripts/<br/>ops tooling]
    ROOT --> SYS[systemd/ · runbooks/]
    ROOT --> WIKI[wiki/<br/>mirrored wiki pages]
    ROOT --> ASSETS[assets/<br/>brand + diagrams]
```

## Rendering locally

Mermaid renders on the host (GitHub/Forgejo). To preview locally, use any
Mermaid-aware Markdown viewer, or paste a block into <https://mermaid.live/>.

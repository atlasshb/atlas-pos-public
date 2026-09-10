# DoPos (MySQL) → Odoo 19 Community — Data Model Mapping

**Scope.** This is the canonical, entity-by-entity mapping used by the Atlas POS ETL
(`dopos_etl.py`) to migrate each client's DoPos catalogue/config into a per-client
Odoo 19 Community database. It is the source-of-truth referenced by capability C (Replace).

**Three rules that govern this whole document — do not violate:**

1. **The ETL reads the read-twin on pos-hub, never the live terminal.** Capability B keeps a
   per-client MariaDB twin (`atlas-mariadb-<client>`) synced from each DoPos box over
   Tailscale. The ETL connects to the twin. An ETL bug can therefore never lock tables or slow
   a live card-payment terminal. The only thing that touches the terminal is B's read-only pull,
   per-site, in a quiet window.
2. **Idempotent upsert keyed on a stable source PK.** Every migrated record carries an
   `OPT-<sourcePK>` key (in `default_code` for products, or an `x_dopos_id` char field on other
   models). The ETL searches by that key, then writes (refresh of safe fields only) or creates.
   Re-running converges; it never duplicates. **Human-edited prices are never clobbered on re-run.**
3. **Worldline stays a MANUAL card payment method.** Odoo 19 Community has no integrated
   payment-terminal module (`pos_six`/`pos_adyen`/`pos_iot` are Enterprise-only and won't install).
   All DoPos card/pin variants collapse to ONE manual bank payment method; `use_payment_terminal`
   is left unset.

> **CRITICAL CAVEAT — the source schema is not yet confirmed.** The exact DoPos MySQL table/column
> names below are by ROLE, inferred from the documented DoPos entity set (products, categories,
> prices, taxes/BTW, payment methods, sales/tickets, staff). They are placeholders until verified against
> a real dump. Section 11 (Confirming the real schema) is mandatory before the ETL is trusted on any site.
> Schema may also vary by DoPos build/version per client — re-run the confirmation steps per site and
> record per-client deltas.

---

## 0. Conventions

- **Source** = a table/column in the DoPos MySQL schema (as seen in the read-twin).
- **Target** = an Odoo 19 model/field.
- **Key** = the stable idempotency key written into Odoo so re-runs upsert.
- **Direction of truth on re-run**: fields marked **(seed-once)** are written on create and NOT
  overwritten on re-run (so manual edits survive). Fields marked **(re-assert)** are refreshed every run.
- **Money**: Odoo `list_price` is **tax-exclusive**. DoPos price inclusivity is UNCONFIRMED —
  see Section 4 and the conversion rule. Get this wrong and every price is off by the BTW rate.

---

## 1. Products / articles → `product.template`

| Source (DoPos, by role) | Target (Odoo 19) | Key / Rule | Re-run |
|---|---|---|---|
| `products.id` (PK) | `product.template.default_code` = `OPT-<id>` | idempotency key | re-assert |
| `products.name` | `product.template.name` | | re-assert |
| `products.is_service` / dept role | `product.template.type` ∈ `consu` (goods), `service` (labour), `combo` (bundles) | **NO `detailed_type`** (removed in 19) | seed-once |
| — | `product.template.available_in_pos = True` | MUST be set or product never shows on the till | re-assert |
| `products.category_id` | `product.template.pos_categ_ids` (M2M, **plural**) ← mapped `pos.category` | see §2 | re-assert |
| `products.category_id` | `product.template.categ_id` ← mapped internal `product.category` | optional; for accounting/reporting | seed-once |
| `products.price` | `product.template.list_price` | tax-handling per §4 | **seed-once** (don't clobber human price edits) |
| `products.tax_id` / `products.vat_rate` | `product.template.taxes_id` | resolve to company BTW tax per §4; **omit if = company default** | re-assert (only if non-default) |
| `products.barcode` | `product.template.barcode` | optional | seed-once |
| `products.active` / archived flag | `product.template.active` | inactive source → archived in Odoo | re-assert |

**Notes / ambiguities:**
- `type`: DoPos may not distinguish goods vs service cleanly. Default everything to `consu`;
  only set `service` where the source clearly marks labour/non-stock. `combo` only if the source has
  true bundle/menu items (restaurant menus — Venue A may; tailor — Venue B likely not).
- Stock: do NOT import stock quantities by default. POS clients run `consu` items without inventory
  tracking; importing on-hand qty creates `stock.quant`/valuation noise in a fresh CoA. Defer per client.
- Duplicate names are fine — the `OPT-<id>` key, not the name, is the dedup anchor.

---

## 2. Categories → `pos.category` (and optionally `product.category`)

| Source | Target | Key / Rule | Re-run |
|---|---|---|---|
| `categories.id` (PK) | `pos.category` with `x_dopos_id = OPT-<id>` | till grouping (what cashier sees) | re-assert |
| `categories.name` | `pos.category.name` | | re-assert |
| `categories.parent_id` | `pos.category.parent_id` ← mapped parent | resolve parent by its own `OPT-<id>` first (two-pass) | re-assert |
| `categories.id` | `product.category` (internal) | optional, only if internal categ used for accounting | seed-once |

**Notes:**
- Map source category → `pos.category` by the `OPT-<id>` key, NOT by name (names collide / get renamed).
- Two-pass build: pass 1 create all categories flat, pass 2 set `parent_id`. Avoids ordering issues.
- Validation gate (§9): every migrated `pos.category` must end up non-empty (have ≥1 product) or be flagged.

---

## 3. Prices → `product.template.list_price`

Covered structurally in §1. The decision that makes or breaks correctness is **tax inclusivity** (§4).
- If DoPos stores **tax-exclusive** net prices → copy `list_price` directly.
- If DoPos stores **tax-inclusive** gross prices → `list_price = gross / (1 + rate)` AND set the
  matching tax so the till re-grosses to the original shelf price.
- Price is **seed-once**: re-runs do NOT overwrite, so a price a human corrected in Odoo stays corrected.

---

## 4. BTW tax rates → `account.tax` (the highest-risk mapping)

**Business is NL → Dutch BTW. Never `l10n_tr`. Never a hardcoded `l10n_nl` xmlid** (the NL tax xmlids are
per-company, e.g. `account.<company_id>_btw_21` — hardcoding breaks across DBs).

| Source rate (role) | Target | Resolution rule |
|---|---|---|
| 21% (standard) | company's "21% BTW" `account.tax` | `SEARCH account.tax WHERE company_id=<cid> AND type_tax_use='sale' AND amount=21` |
| 9% (reduced — food, etc.) | company's "9% BTW" `account.tax` | same SEARCH, `amount=9` |
| 0% / exempt | company's 0% / exempt `account.tax` | same SEARCH, `amount=0` |

**Rules:**
- Resolve every tax by **SEARCH on rate within the company**, never by xmlid.
- If a product's source rate **equals the company default** → **OMIT `taxes_id`** so the product inherits
  the company default (cleaner, and matches the Venue B template). Only set `taxes_id` explicitly when the
  product's rate differs from default.
- **Precondition — `l10n_nl` installed and the default sales tax confirmed BEFORE the first posted entry.**
  Odoo 19 forbids changing the fiscal package after any journal entry posts. This is a documented MANUAL
  gate; the ETL must refuse to proceed if no resolvable BTW taxes exist in the company.

**Ambiguity / inclusivity detection (decides §3 too):**
- DoPos may store prices **tax-inclusive** (common for hospitality shelf pricing) or **tax-exclusive**.
- **How to detect per site:** pick a handful of products with a known BTW rate, read their source price and
  source line-tax on a sample ticket. If `ticket_line.gross == price` and `tax == gross - gross/(1+rate)`,
  prices are **inclusive**. If `ticket_line.net == price`, prices are **exclusive**. Confirm with the
  operator/client against a printed receipt before trusting the whole run.
- Get this wrong → every price is off by 21%/9%. The §9 money-check is specifically designed to catch it.

---

## 5. Payment methods → `pos.payment.method`

| Source payment type (role) | Target | Rule |
|---|---|---|
| Cash / "Contant" | `pos.payment.method` `journal_id` = cash journal, no terminal | resolve cash journal by SEARCH (`company_id`, `type='cash'`) |
| Card / Pin / Worldline / any electronic variant | **ONE** manual bank method "Pinnen / Worldline kaart" | `journal_id` = bank journal (SEARCH `type='bank'`); `use_payment_terminal` **unset**; collapse ALL source card variants into this one |
| Vouchers / on-account / other | per client, only if used | usually skip or map to a manual "Overig" bank method |

**Rules:**
- Created with `noupdate="1"` semantics in the seed module; the ETL only ADDS methods not already present
  (matched by name / `x_dopos_id`), never rewires existing ones.
- Journals linked by SEARCH on (`company_id`, `type`) in the module's `post_init_hook` — never by xmlid.
- **Never** create an integrated-terminal method. Cashier runs the standalone Worldline YOMANI physically;
  Odoo records the tendered amount on the manual method. PAN/cardholder data never enters DoPos or
  the twin (Worldline is standalone) — this keeps Atlas out of PCI scope. Do not import any card data even
  if a column appears to hold it; treat such a column as out-of-scope and flag it.

---

## 6. Staff / cashiers → `hr.employee` (NOT logins)

| Source | Target | Rule |
|---|---|---|
| `staff.id` / `staff.name` | `hr.employee` with `x_dopos_id = OPT-<id>` | name only, for sales attribution / cashier list |
| `staff.pin` / `staff.password` | **DO NOT IMPORT** | secrets/credentials never bulk-copied (constraint 4); GDPR/PII risk |

**Rules:**
- Map cashiers to `hr.employee` only — minimal PII (name), no credentials, no `res.users` logins.
- Bulk-importing logins violates the no-bulk-secrets constraint and risks staff-PII exposure across the
  tailnet. Operator creates real Odoo logins by hand, per person, as needed.
- Historical sales attribution (which cashier rang what) is preserved in the **twin**, which holds the
  full source history; it does not need to be replayed into Odoo to be queryable.

---

## 7. Sales / tickets (history) → archived in the twin, NOT replayed into `pos.order`

**DEFAULT: do NOT migrate historical sales into Odoo.**

| Source | Default target | Why |
|---|---|---|
| `tickets` / `sales` (closed) + `ticket_lines` | **Twin archive only** (capability B). NOT `pos.order`. | Replaying closed tickets as live `pos.order` fabricates `pos.session` + `account.move` journal entries in the live Dutch CoA → double-counts revenue, corrupts BTW reporting, and is a fiscal hazard (violates "don't touch accounting"). |

**Opt-in alternative (per client, only if the accountant needs history INSIDE Odoo):**
- Load sales as a **read-only reporting dataset** — a custom `x_dopos_sale` model (or CSV→BI/Metabase) that
  is explicitly **separate from accounting**, carries no journal entries, and is clearly labelled historical.
- Never as `pos.order`/`account.move`. The twin remains the legal/queryable system-of-record for history and
  satisfies NL 7-year fiscal retention via restic→B2 (see governance INTEGRATION.md §retention).

---

## 8. Open orders / parked tickets → `pos.order` (opt-in, cutover-only)

| Source | Target | Rule |
|---|---|---|
| Currently-OPEN tickets / parked sales at the moment of cutover | `pos.order` + `pos.order.line` in `draft`/`paid` | **DEFAULT = SKIP** (start the new till clean at open). Enable per client ONLY if they want parked sales carried. |

**Rules / risks:**
- Requires a valid open `pos.session` and correct payment/tax wiring on each carried order; getting it
  slightly wrong creates orphaned sessions or unbalanced moves.
- Only the **open set at cutover**, never historical closed tickets (those are §7).
- Recommend default-off; the cleanest cutover opens a fresh till with zero carried state.

---

## 9. Validation / reconciliation (the ETL must prove itself)

After every run the ETL computes and asserts, against the twin:

1. **Product count**: `#products migrated == #active source articles` (within tolerance).
2. **Category coverage**: every source category maps to a `pos.category`; every `pos.category` is non-empty.
3. **Availability**: every migrated product has `available_in_pos = True`.
4. **Tax resolution**: every product's effective tax resolves to a known company BTW rate (21/9/0); list any
   product whose source rate could not be matched.
5. **Money check**: `Σ list_price` (sampled, re-grossed if inclusive) vs source price sum, within tolerance —
   this is the catch for an inclusive/exclusive mistake (§4).
6. **Payment coverage**: cash + one manual card method exist and resolve to valid journals.

Output a per-client reconciliation report (counts, mismatches, unmapped categories/taxes, money delta) to
**atlas-ntfy** and the **Mind ledger**. **A non-empty mismatch list blocks cutover** (governance gate).

---

## 10. Idempotency & re-run summary

- Products keyed on `default_code = OPT-<pk>`; everything else on `x_dopos_id`.
- Re-run = upsert: search by key → create if absent, else write **re-assert** fields only.
- **Never overwritten on re-run:** `list_price` (price), `type`, internal `categ_id` (all seed-once) — so
  human corrections survive.
- **Always refreshed:** name, `available_in_pos`, `pos_categ_ids`, `active`, non-default `taxes_id`.
- Re-running the full ETL converges to the same state and never duplicates. Safe to run any number of times.

---

## 11. Confirming the REAL schema from a live dump (MANDATORY before trusting the ETL per site)

The column names above are by role and must be pinned to the actual DoPos schema **in the twin** (never
the live box). Per site (Venue A twin, Venue B twin):

1. **List tables & engines** (engine drives B's dump safety too — MyISAM ≠ consistent under `--single-transaction`):
   ```sql
   SELECT table_name, engine, table_rows
   FROM information_schema.tables
   WHERE table_schema = DATABASE()
   ORDER BY table_rows DESC;
   ```
2. **Inspect columns** of the candidate tables for each role (products, categories, prices, tax, payment, tickets, staff):
   ```sql
   SELECT table_name, column_name, data_type, column_key
   FROM information_schema.columns
   WHERE table_schema = DATABASE()
   ORDER BY table_name, ordinal_position;
   ```
3. **Identify the role of each table** by sampling rows (`SELECT * ... LIMIT 20`) and matching to: article list,
   category tree, price field, VAT/BTW rate field, payment-type list, ticket header + ticket lines, staff list.
4. **Confirm price inclusivity** using the sample-ticket method in §4.
5. **Pin foreign keys**: product→category, ticket_line→product, ticket_line→tax, ticket→staff, ticket→payment.
6. **Record per-client deltas**: write the confirmed table/column map into `/root/pos_kb/dopos_schema_<client>.md`
   (the canonical schema KB). If a client's build differs, this file captures the delta so the reusable map stays honest.
7. **Schema-fingerprint** (hash of table+column list) stored per client; B/ETL alert on drift so an DoPos update
   that changes the schema is caught, not silently mis-mapped.

Only after steps 1–6 are recorded for a site is `dopos_etl.py` trusted to run against that site's twin.

---

## 12. Open mapping questions (carry into per-site confirmation)

- Exact DoPos table/column names per site (above is by role) — pin from the twin (Venue A 192.0.2.10,
  Venue B 192.0.2.10) before finalizing the column map.
- Tax-inclusive vs tax-exclusive prices per site — determines the `list_price` conversion and `taxes_id` setting.
- Venue A (restaurant): does it need `pos.floor`/`pos.table`, split bills, course/modifier handling — i.e. does
  the single-counter Venue B template generalize, or is a restaurant `pos.config` variant needed?
- Does any client want history visible inside Odoo (opt-in §7 reporting dataset) or is twin-only archival enough?
- Does DoPos use InnoDB or MyISAM (affects B's dump consistency, not the mapping, but confirm during step 1).
- Multi-till sites: does any client run more than one terminal (changes §8 open-order topology and system-of-record)?

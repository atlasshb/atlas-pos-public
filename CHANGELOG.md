# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-10

First public, de-identified release.

### Added

- **Research & design docs** (`docs/`): open-source POS project survey, Odoo POS
  landscape (Community vs Enterprise), OCA/pos ecosystem, Pin Vandaag/Worldline
  integration, payments architecture, migration strategy, security & compliance,
  device/printing, and Mermaid architecture diagrams.
- **DoBizzz/DoPos** research, comparison and migration set (`docs/15`–`17`,
  `docs/07`) — the incumbent takeaway/delivery system being replaced.
- **Market & payments landscape** (`docs/11`–`13`).
- **Odoo 19 Community modules** (`addons/`, LGPL-3): `pos_pinvandaag_atlas`
  (fork of the official Pin Vandaag module, ported to Odoo 19),
  `atlas_pos_seed` (per-venue POS seed pack), `atlas_pos_theme` (theme scaffold).
- **Non-Odoo components** (`components/`): terminal agent, fleet collector
  (PAN-scrubbed mirror + hash-chain journal), POS→Odoo sync, Windows harness,
  onboarding, PCI-scan utilities.
- **Migration tooling** (`migration/`): idempotent POS→Odoo ETL and mapping.
- **Fleet program** (`program/`) and ops tooling (`scripts/`, `systemd/`,
  `runbooks/`).
- **Brand assets** (`assets/`, `BRAND.md`) and a `wiki/` mirror.
- **Tests** (`tests/`) and CI (GitHub Actions + Forgejo).

### Security

- De-identified export: no credentials, client data or internal infrastructure
  details.

[Unreleased]: https://github.com/atlasshb/atlas-pos-public/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/atlasshb/atlas-pos-public/releases/tag/v0.1.0

# Contributing

Thanks for considering a contribution. This project is research + reusable
components for a POS on Odoo 19 Community.

## Ground rules

1. **No secrets, ever.** No API keys, passwords, tokens, certificates, client
   names, personal data, or internal infrastructure details (IPs, hostnames,
   ports, credential locations). If you spot any, report it per `SECURITY.md`.
2. **No client data.** Examples must use placeholders (`venue_a`, `192.0.2.10`,
   `<TERMINAL-ID>`).
3. **Keep it small and reversible.** Extend Odoo with thin LGPL-3 modules; do
   not fork core.
4. **License conformity.** Odoo modules are LGPL-3; docs/tooling are MIT. See
   `LICENSE` and `NOTICE.md`.

## What's most welcome

- Corrections to the research (with a source).
- Additional open-source POS projects (name + upstream URL + one-line verdict).
- Odoo 19 port fixes for the payment module.
- Bug fixes in the components (`components/`).

## Workflow

```bash
pip install -r requirements-dev.txt
pytest
```

- Branch, make the change, ensure `pytest` is green.
- Keep commit messages descriptive; reference the area (`docs:`, `addons:`,
  `components:`, `ci:`).
- Open a pull request describing what changed and why.

## Style

- Python: standard library first; keep the Odoo module idiomatic to Odoo 19.
- Shell: `set -euo pipefail`; never `set -x` around secrets.
- Docs: Markdown, Mermaid for diagrams, English.

By contributing you agree your contribution is licensed under the project's
license for the area you touch (LGPL-3 for `addons/`, MIT otherwise).

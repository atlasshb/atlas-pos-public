# Tests

Fast, dependency-light checks for the non-Odoo components and the module
manifests. Run them with:

```bash
pip install -r requirements-dev.txt
pytest
```

What they cover:

| Test | What it checks |
|---|---|
| `test_mask_pan.py` | The PAN scrubber redacts only Luhn-valid, digit-diverse card numbers and leaves padding/invalid runs intact. |
| `test_journal_chain.py` | The hash-chain helper is deterministic and `verify_chain` detects a retro-edited store. |
| `test_manifests.py` | Every `addons/*/__manifest__.py` is a valid dict with the required keys and an LGPL-3 license. |
| `test_xml_svg.py` | Every `.xml` and `.svg` in the repo parses. |

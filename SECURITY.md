# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:

- Email: **security@atlascorporation.nl** (or use GitHub's private vulnerability
  reporting: the **Security** tab -> **Report a vulnerability**).

Include: what you found, where (file/commit), and how it could be abused. We
aim to acknowledge within a few days.

## Scope

This repository is a **de-identified public export**. It should contain:

- No API keys, tokens, passwords or private keys.
- No client names or personal data.
- No internal infrastructure details (addresses, hostnames, ports, credential
  locations) or operational secrets.

## If you find a secret

If any credential or piece of client/personal data has slipped in:

1. **Do not** open a public issue with the value.
2. Email the address above with the file and line (do not paste the secret).
3. The maintainers will remove it from the tree and history and rotate the
   affected credential.

## Handling in this project

- Secrets are read from the environment or a secret store; never committed.
- The POS never stores card data; the PAN scrubber (`components/pci-scan`) is a
  belt-and-suspenders guard for mirrors.
- Agents/automation must not hold root shells on production hosts.

## Supported versions

| Version | Supported |
|---------|-----------|
| `main` and the latest tag (`v0.1.0`) | Yes - security fixes land here first |
| Older tags | No |

Fixes land on `main` and are cut as a new tagged release. Security advisories
are published through GitHub Security Advisories on this repository.

Response targets: acknowledgement within 3 business days, a triage decision
within 7 days.

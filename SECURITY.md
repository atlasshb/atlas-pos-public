# Security Policy

## Reporting a vulnerability

Please report security issues privately rather than opening a public issue:

- Email: **security@atlascorporation.nl** (or use GitHub's private vulnerability
  reporting if enabled on the repository).

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

This is a research/early-stage project; fixes land on the `main` branch.

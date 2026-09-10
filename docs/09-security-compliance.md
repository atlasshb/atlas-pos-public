# Security And Compliance Requirements

## Security Requirements

- provider webhooks must be verified
- provider references must be stored without sensitive payment data
- secrets must remain outside repo-tracked state
- device trust state must be persisted and reviewable

## Compliance-Oriented Requirements

- receipts and exports must support tax and audit workflows
- payment data handling must preserve third-party-provider ownership
- Odoo must remain ERP-side record authority where enabled

## Explicit Boundary

The product line is designed to stay outside direct funds custody and settlement responsibility.


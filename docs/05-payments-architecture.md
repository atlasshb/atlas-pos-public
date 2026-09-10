# Payments Architecture

## Hard Rules

Atlas POS:

- never stores raw card data
- never holds balances
- never settles funds
- never becomes the source of truth for payouts or disputes

All charge, refund, payout, and dispute authority stays with the payment provider.

## Payment Strategy By Phase

### Near-term

- Stripe Terminal
- Adyen
- Worldline-adjacent bridge where the incumbent environment already depends on it
- cash and manual external flows

### Later

- SumUp
- regionally useful provider adapters where there is real demand

## Provider-Specific Handling

### Stripe Terminal

- raw-body webhook verification
- payment intent or terminal event normalization
- authorization/capture/refund remain Stripe-owned
- Atlas POS stores only normalized metadata and reconciliation inputs

### Adyen

- HMAC notification verification
- normalized authorization/capture/refund events
- Atlas POS stores only the metadata required for orchestration and reconciliation

### Worldline-Adjacent Bridge

- bridge through local incumbent environment where necessary
- prefer status normalization over deep direct dependence early

## Provider Boundary Matrix

| Concern | Atlas POS | Atlas Workspace | Odoo | Payment Provider | Merchant / Operator |
| --- | --- | --- | --- | --- | --- |
| Device orchestration | Owns | Views | No | No | Uses |
| Payment execution | No | No | No | Owns | Initiates |
| Refund instruction workflow | Routes | Views | May reference | Owns execution | Approves/requests |
| Settlement and payout | No | Views summaries only | No | Owns | Receives |
| Reconciliation metadata | Owns normalized copy | Views | References ERP side | Owns raw source state | Resolves issues |

## Operator-Facing Failure Handling

- provider failures become normalized support issues
- Atlas Workspace surfaces them as operational problems, not hidden payment mysteries
- unresolved provider vs Odoo mismatches become reconciliation items


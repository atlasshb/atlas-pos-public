# Migration Strategy

## Default Motion

Default to `Bridge First`.

The first question is not "can Atlas POS replace this system?"
It is "can Atlas POS create enough operational value while the current system stays in place?"

## Track A: Keep DoPos, Integrate To Odoo And Atlas

### Expected Customer Shape

Observed likely shape from current packaged setup:

- Windows local install
- packaged executable
- local backups and logs
- local terminal state
- local hardware assumptions
- external payment-provider dependency traces

### Bridge Options

1. Local export/file bridge
   - consume local exports, backups, or receipts
   - lowest technical risk
   - highest tolerance for opaque incumbent systems

2. Local helper service
   - small sidecar process on the Windows machine
   - reads local artifacts, logs, or APIs if exposed
   - emits normalized events to Atlas POS

3. Direct API integration where available
   - use only if the incumbent actually exposes a stable API
   - not assumed by default

4. Event bridge later
   - only after bridge mechanics are proven

### Minimum Odoo Sync Scope

- product/catalog references where available
- order summaries
- payment status summaries
- receipt or audit references
- reconciliation metadata

### Recommended Outcome Classes

| Customer Situation | Outcome |
| --- | --- |
| Stable incumbent, difficult hardware, low migration appetite | Bridge Only |
| Wants better control now, may migrate later | Bridge Now, Migrate Later |
| Simple environment and strong migration readiness | Migrate When Ready |
| Unsupported dependencies or extreme complexity | Do Not Target Yet |

## Track B: Migrate Fully To Atlas POS

### Prerequisites

- device compatibility known
- receipt parity proven
- provider path agreed
- Odoo sync path proven
- operator training plan defined

### Data Cutover Requirements

- product and pricing source agreed
- order history policy agreed
- customer and loyalty treatment agreed
- opening-state and reconciliation expectations agreed

### Device Compatibility Requirements

- printers
- scanners
- cash drawers
- payment terminals

### Training And Rollout Risks

- cashier retraining
- receipt differences
- payment flow differences
- offline behavior surprises

### Fallback And Rollback

- define rollback window before cutover
- preserve incumbent system state during pilot period
- ensure receipt and order evidence remain accessible

## Three Concrete Scenarios

### Scenario 1: Single-store Windows packaged POS

Recommendation:

- `Bridge Now, Migrate Later`

Reason:

- easiest way to gain value without risking daily operations

### Scenario 2: Multi-terminal hospitality setup

Recommendation:

- `Bridge Only` initially

Reason:

- device, flow, and support complexity is higher than the current native replacement maturity

### Scenario 3: Customer wants full replacement but has unsupported hardware/payment dependency

Recommendation:

- `Do Not Target Yet`

Reason:

- replacement would create unacceptable rollout risk


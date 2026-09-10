# Atlas POS System Context

## Core Context

Atlas POS is the store and order control-plane counterpart to Atlas Workspace.

It gives a super-admin and store operators one coherent system for:

- enrolling stores and terminals
- supervising order flow
- routing sync into ERP and provider systems
- capturing the operational narrative around transactions

## Primary Actors

- founder or Atlas super-admin
- store manager
- cashier or terminal operator
- integration operator
- support worker

## Primary Systems

- Atlas POS API
- domain and connector packages in this repo
- Atlas Workspace as the operator shell
- Odoo as ERP substrate
- payment providers such as Stripe Terminal, Adyen, or SumUp
- local or hosted storage for audit and receipt artifacts

## Boundary Decisions

### Atlas POS owns

- workspace-scoped POS orchestration
- order/session/payment-attempt event history
- terminal trust state
- connector dispatch and replay
- operational projections for supervision

### Atlas Workspace owns

- super-admin shell and workspace switching
- cross-system search, notes, evidence, and actions
- support and operator narrative

### Odoo owns

- product, stock, tax, and ERP sales truth where enabled

### Payment providers own

- payment execution
- settlement
- provider compliance burden


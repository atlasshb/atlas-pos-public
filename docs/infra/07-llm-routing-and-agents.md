# 07 — LLM routing and agent hygiene

Notes from running a multi-provider LLM setup (local models + free cloud tiers
+ paid) behind one interface, and from wiring agents into real infrastructure.
This is the operational side, not model quality.

## Route through a gateway; never hand-roll the router

If you call more than one provider, put a **gateway** in front (e.g. LiteLLM)
and expose **one OpenAI-compatible endpoint**. You get, for free:

- Fallback chains and retries
- Cooldowns for failing providers
- Per-key budgets and cost tracking
- A single place to add/remove a provider

Hand-rolling fallbacks and budget logic in application code is a maintenance
trap. Architect for **provider churn** — free tiers change monthly; the code
shouldn't.

## Tiering by cost

Route by task complexity, not by habit:

- **Trivial**: classification, labels, routing → cheapest local/small model.
- **Text/Dutch/summaries**: a small-mid local or free-cloud model.
- **Code/boilerplate**: a code-tuned small model.
- **Multi-step reasoning/architecture**: escalate to a paid frontier model,
  sparingly.

The win isn't only cost; it's latency and keeping paid capacity for what needs it.

## Local + cloud hybrid

- Local models (e.g. via Ollama, OpenAI-compatible) are great for privacy, bulk
  and zero-marginal-cost tasks. Expose them through the same gateway.
- Don't put a machine that reboots often in a critical fallback chain.
- Keep an inventory of which models are actually pulled — a router alias that
  points at a model nobody pulled fails at request time.

## Agent / tool hygiene (the part that bites)

- **Don't auto-pin every tool into every conversation.** A large tool list
  bloats the prompt and increases the chance a single misbehaving tool trips a
  circuit breaker. Be selective.
- **A dead MCP tool can stall the whole turn.** Health-check tool endpoints and
  fail fast.
- **No agent gets a root shell on production.** This is the single most
  important rule. An agent with host access is a supply-chain compromise
  waiting for a prompt injection. Give agents scoped APIs and read-only
  defaults; require explicit approval for writes.
- **Secrets never in agent context.** Keys in prompts/logs get exfiltrated or
  leak into a UI. Reference a secret store.

## Structural queries beat grep (for code/context)

For large codebases, a **knowledge graph / structural query** returns a small,
precise answer where grep dumps tens of thousands of tokens. The token saving is
the biggest single lever in agent stacks. Build the index once; query it.

## Takeaway

One gateway, cost-tiered routing, a small curated tool set, and a hard "no root
shell for agents" rule. Those four decisions prevent most LLM-infra pain.

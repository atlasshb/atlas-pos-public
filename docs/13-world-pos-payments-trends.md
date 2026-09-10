# 13 — World POS & payments trends (working notes)

Market-level notes gathered while sizing the opportunity. Figures are
**directional** and drawn from public sources at the time of writing — treat
them as a starting point, not as audited numbers, and re-verify before quoting.

## The structural shift: hardware → SaaS

- Legacy on-prem Windows POS is being displaced by **cloud/tablet POS**,
  especially in hospitality, where owners want remote reporting, multi-venue
  dashboards and no server on site.
- The trade-off: cloud POS is convenient but creates **data lock-in** and often
  a **payments lock-in** (the vendor bundles acquiring and takes a cut).
- A self-hosted open-source POS sits in a third position: the operator owns the
  data and picks the payment provider separately — powerful, but it must be
  *supported*, which is the real cost.

## Digital payments trends (global)

- **Contactless/NFC** is the default in mature markets; cash is declining but
  not gone.
- **QR payments** dominate in many Asian markets and are spreading in EU
  hospitality via app ordering.
- **Open banking (PSD2)** is growing for account-to-account payments and payouts.
- **BNPL** is growing globally but is interest-bearing in many products — a
  policy exclusion for some merchants.
- **SoftPOS / Tap to Pay** turns an Android phone into a terminal; useful for
  pop-up and peak capacity.
- Fastest POS-as-SaaS growth is reported in US/UK/Benelux/DACH and SE Asia.

## Netherlands / Benelux context (public sources)

Indicative, from public statistics (CBS / CPB / DNB / sector reports) at the
time of writing:

- Card acceptance is near-universal: the overwhelming majority of in-person
  payments are contactless card.
- Hospitality turnover has been growing while margins stay thin; venue
  bankruptcies have been elevated — owners are price-sensitive.
- A mid-size city like Tilburg has on the order of ~800–1,000 hospitality venues.
- iDEAL dominates online payments in NL; SEPA direct debit for recurring.

## Competitive landscape (NL hospitality POS)

- **Incumbent closed POS**: DoPos, DoPOS, CCV, Lightspeed Restaurant,
  MplusKASSA, unTill, Bork, SumUp/Zettle, Square.
- **Ordering/delivery platforms** take a meaningful commission (marketplaces
  commonly ~13–30%); commission-free ordering sites (e.g. Foodticket, Sitedish,
  Bistroo, Deliverect integrations) are the counter-position.
- **Pricing** ranges from ~€0 (payments-led) to €100–250/mo for full
  restaurant suites. The market gap a supported open-source stack can target is
  the **price-sensitive small venue** that wants data ownership and no
  per-order commission.

> Verify every competitor price at the source. These numbers move, and several
> vendor pages quote *from* prices that hide setup/contract terms.

## Hard-tech / AI in hospitality

- **AI receptionists / voice ordering** are the fastest-moving adjacent
  category: phone order-taking that pushes tickets into the POS. Third-party
  market estimates put the AI voice-agent segment in the billions of dollars and
  growing fast (directional). These tools mostly integrate with US cloud POS
  (Toast/Square/Clover) — a custom integration is needed for other platforms.
- **KDS (kitchen display), self-order kiosks, QR self-order and loyalty** are
  becoming table stakes; Odoo has some in Community (`pos_restaurant`,
  `pos_self_order`) and some behind Enterprise.
- **Device management** for the terminal fleet (RMM) matters more than it
  sounds: a dead till is lost revenue.

## Sources to start from

- NL statistics: CBS StatLine, CPB, DNB (public).
- Market/pricing: individual vendor pages (verify directly).
- Open-source comparisons: see `11-oss-pos-projects.md`.

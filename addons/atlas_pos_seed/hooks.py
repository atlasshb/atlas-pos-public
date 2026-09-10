# -*- coding: utf-8 -*-
"""
Post-install / post-upgrade hooks for the Atlas Venue B POS pack.

These hooks are SAFE, IDEMPOTENT and ADDITIVE only. They:
  1. Activate the Turkish (tr_TR) UI language and merge its translation pack
     (UI language ONLY - accounting/VAT stays Dutch).
  2. Default the admin user to the Turkish UI.
  3. Link the two POS payment methods (Cash / manual Card) to a matching
     company journal by SEARCH (never by hard-coded xmlid), with guards so the
     pack still installs cleanly on a bare DB or a DB that already has a CoA.

Nothing here installs l10n_nl, touches the chart of accounts, or creates /
overwrites tax or journal records. Dutch fiscal localization (l10n_nl + BTW
21%/9%/0%) remains a documented MANUAL admin step done on the live DB before
any journal entry is posted.
"""

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Run after the module is installed (Odoo 19 signature: post_init_hook(env))."""
    _activate_turkish_ui(env)
    _link_payment_method_journals(env)


def _activate_turkish_ui(env):
    """Activate tr_TR as a UI language and merge its translations.

    Idempotent: _activate_lang is a no-op if the language is already active,
    and lang_install is called with overwrite=False so existing / customised
    translations are merged, never clobbered.
    """
    try:
        lang = env['res.lang']._activate_lang('tr_TR')
        env['base.language.install'].create({
            'lang_ids': [(6, 0, lang.ids)],
            'overwrite': False,
        }).lang_install()
        _logger.info("atlas_pos_seed: Turkish (tr_TR) UI language activated.")
    except Exception as exc:  # never let a translation fetch abort the install
        _logger.warning(
            "atlas_pos_seed: could not activate tr_TR UI language: %s", exc)
        return

    # Optional, additive: default the admin user to the Turkish UI.
    try:
        admin = env.ref('base.user_admin', raise_if_not_found=False)
        if admin:
            admin.sudo().lang = 'tr_TR'
    except Exception as exc:
        _logger.warning(
            "atlas_pos_seed: could not set admin user language to tr_TR: %s",
            exc)


def _link_payment_method_journals(env):
    """Link the Cash / manual Card POS payment methods to company journals.

    Resolves journals by SEARCH (company_id + type), never by hard-coded
    xmlid. Guards every write so the pack stays installable on a bare DB
    (no journals yet) and idempotent on re-upgrade. Cash-vs-bank is driven
    SOLELY by the linked journal's type; is_cash_count / type / use_payment_terminal
    are computed/read-only and are never written here.
    """
    company = env.company

    cash_method = env.ref(
        'atlas_pos_seed.pos_payment_method_cash', raise_if_not_found=False)
    card_method = env.ref(
        'atlas_pos_seed.pos_payment_method_card', raise_if_not_found=False)

    # --- CASH method -> a CASH journal (type=cash) ---------------------------
    if cash_method and not cash_method.journal_id:
        cash_journal = env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'cash'),
        ], limit=1)
        if cash_journal:
            # The journal_id domain forbids reusing a cash journal already
            # linked to another cash payment method. Guard for that to stay
            # idempotent and avoid a domain violation.
            already_linked = env['pos.payment.method'].search_count([
                ('journal_id', '=', cash_journal.id),
                ('id', '!=', cash_method.id),
            ])
            if not already_linked:
                cash_method.journal_id = cash_journal.id
                _logger.info(
                    "atlas_pos_seed: linked Cash method to journal %s.",
                    cash_journal.name)
            else:
                _logger.info(
                    "atlas_pos_seed: cash journal already linked to another "
                    "payment method; skipping Cash link.")
        else:
            _logger.info(
                "atlas_pos_seed: no cash journal found for company %s; "
                "Cash method left unlinked (set it manually).", company.name)

    # --- CARD (manual Worldline) method -> a BANK journal (type=bank) --------
    if card_method and not card_method.journal_id:
        bank_journal = env['account.journal'].search([
            ('company_id', '=', company.id),
            ('type', '=', 'bank'),
        ], limit=1)
        if bank_journal:
            card_method.journal_id = bank_journal.id
            _logger.info(
                "atlas_pos_seed: linked manual Card method to journal %s.",
                bank_journal.name)
        else:
            _logger.info(
                "atlas_pos_seed: no bank journal found for company %s; "
                "Card method left unlinked (set it manually).", company.name)

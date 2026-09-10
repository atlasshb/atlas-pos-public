#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""POS post-deploy hardening (idempotent, additive, safe)."""
import os, xmlrpc.client

URL = os.environ.get('ODOO_URL', 'http://192.0.2.10:8069')
DB  = os.environ.get('ODOO_DB',  'venue_x')
USER= os.environ.get('ODOO_USER')
PW  = os.environ.get('ODOO_PASSWORD')
if not (USER and PW):
    raise SystemExit("Set ODOO_USER and ODOO_PASSWORD in the environment before running.")

common = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/common')
uid = common.authenticate(DB, USER, PW, {})
assert uid, "auth failed"
m = xmlrpc.client.ServerProxy(URL+'/xmlrpc/2/object')
def X(model, method, *a, **kw): return m.execute_kw(DB, uid, PW, model, method, list(a), kw)
def sr(model, dom, fields, **kw): return X(model,'search_read',dom,fields=fields,**kw)
def sc(model, dom): return X(model,'search_count',dom)
def note(s): print(s)

posted = sc('account.move',[['state','=','posted']])
note(f"[gate] posted journal entries = {posted}")
SAFE_FISCAL = (posted == 0)
if not SAFE_FISCAL:
    note("[gate] posted entries exist -> skipping company/currency/tax changes (fiscal lock).")
CID = 1

if SAFE_FISCAL:
    nl = sr('res.country',[['code','=','NL']],['id']); nl_id = nl[0]['id'] if nl else None
    try:
        X('res.company','write',[CID],dict({'name':'Venue B'}, **({'country_id':nl_id} if nl_id else {})))
        note("  company -> name=Venue B, country=NL")
    except Exception as e:
        note(f"  ! company name/country: {e}")
    # EUR is inactive by default -> must search with active_test=False, then activate.
    eur = sr('res.currency',[['name','=','EUR']],['id','active'], context={'active_test':False})
    if eur:
        if not eur[0]['active']:
            X('res.currency','write',[eur[0]['id']],{'active':True}); note("  activated EUR currency")
        try:
            X('res.company','write',[CID],{'currency_id':eur[0]['id']}); note("  company currency -> EUR")
        except Exception as e:
            note(f"  ! currency change blocked (leave as-is): {e}")
    else:
        note("  ! EUR currency record not found")

def ensure_tax(name, amount, incl):
    found = sr('account.tax',[['name','=',name],['type_tax_use','=','sale']],['id'])
    if found: return found[0]['id']
    base={'name':name,'amount':amount,'amount_type':'percent','type_tax_use':'sale'}
    try:
        return X('account.tax','create',dict(base, price_include_override=('tax_included' if incl else 'tax_excluded')))
    except Exception:
        return X('account.tax','create',dict(base, price_include=incl))

tax21=None
if SAFE_FISCAL:
    tax21 = ensure_tax('BTW 21%', 21.0, True); note("  ensured tax BTW 21%")
    ensure_tax('BTW 9%', 9.0, True);          note("  ensured tax BTW 9%")
    ensure_tax('BTW 0%', 0.0, True);          note("  ensured tax BTW 0%")
    try:
        X('res.company','write',[CID],{'account_sale_tax_id':tax21}); note("  default sale tax -> BTW 21%")
    except Exception as e:
        note(f"  ! default sale tax: {e}")

if SAFE_FISCAL and tax21:
    prods = sr('product.template',[['available_in_pos','=',True]],['id','name','taxes_id'])
    changed=0
    for p in prods:
        if p['taxes_id'] != [tax21]:
            try:
                X('product.template','write',[p['id']],{'taxes_id':[(6,0,[tax21])]}); changed+=1
            except Exception as e:
                note(f"  ! retax {p['name']}: {e}")
    note(f"  re-taxed {changed}/{len(prods)} POS products to BTW 21%")

pms = {p['name']:p for p in sr('pos.payment.method',[],['id','name'])}
def rename(old,new):
    if old in pms:
        X('pos.payment.method','write',[pms[old]['id']],{'name':new}); note(f"  renamed '{old}' -> '{new}'"); return pms[old]['id']
    # already renamed on a prior run?
    ex=sr('pos.payment.method',[['name','=',new]],['id'])
    return ex[0]['id'] if ex else None
contant_id = rename('Cash','Contant')
pin_id     = rename('Card','Pinnen / Worldline kaart')
for dupname in ['Contant','Pinnen / Worldline kaart']:
    for d in sr('pos.payment.method',[['name','=',dupname]],['id','journal_id']):
        if d['id'] in (contant_id, pin_id): continue
        for c in sr('pos.config',[['payment_method_ids','in',[d['id']]]],['id']):
            X('pos.config','write',[c['id']],{'payment_method_ids':[(3,d['id'])]})
        try:
            X('pos.payment.method','unlink',[d['id']]); note(f"  removed duplicate method id={d['id']} ({dupname})")
        except Exception as e:
            note(f"  ! delete dup id={d['id']}: {e}")

wanted=[i for i in [contant_id,pin_id] if i]
for c in sr('pos.config',[],['id','name']):
    try:
        X('pos.config','write',[c['id']],{
            'name':'Venue B Kasa',
            'payment_method_ids':[(6,0,wanted)],
            'receipt_header':'VENUE B\nKleding & Kleermaker - Tilburg',
            'receipt_footer':'Bedankt / Tesekkurler!  (BTW inbegrepen)',
        }); note(f"  pos.config id={c['id']} -> name=Venue B Kasa, methods {wanted} + receipt")
    except Exception as e:
        note(f"  ! pos.config write id={c['id']}: {e}")

note("")
note("================ FINAL STATE ================")
co = sr('res.company',[['id','=',CID]],['name','currency_id','country_id','account_sale_tax_id'])[0]
note(f"Company : {co['name']} | {co['currency_id']} | {co['country_id']} | default tax {co['account_sale_tax_id']}")
prods = sr('product.template',[['available_in_pos','=',True]],['name','list_price','taxes_id'])
badtax=[p['name'] for p in prods if tax21 and p['taxes_id']!=[tax21]]
note(f"POS products : {len(prods)} | wrong tax: {len(badtax)}")
for c in sr('pos.config',[],['name','payment_method_ids']):
    names=[x['name'] for x in sr('pos.payment.method',[['id','in',c['payment_method_ids']]],['name'])]
    note(f"config '{c['name']}' -> {names}")
lang=sr('res.lang',[['code','=','tr_TR']],['active'])
note(f"Turkish (tr_TR) active: {bool(lang and lang[0]['active'])}")
note("=============================================")

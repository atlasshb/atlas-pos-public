/** @odoo-module */
// Builds the pickup-slot list from the venue's configured opening hours and
// stores the chosen slot on the cart. Hours are never hardcoded here.

import { rpc } from "@web/core/network/rpc";

function hhmmToMinutes(value, fallback) {
    const m = /^(\d{1,2}):(\d{2})$/.exec((value || "").trim());
    if (!m) return fallback;
    return parseInt(m[1], 10) * 60 + parseInt(m[2], 10);
}

function label(minutes) {
    const m = ((minutes % 1440) + 1440) % 1440;
    return String(Math.floor(m / 60)).padStart(2, "0") + ":" +
           String(m % 60).padStart(2, "0");
}

async function setup() {
    const root = document.getElementById("atlas_pickup");
    const select = document.getElementById("atlas_pickup_select");
    if (!root || !select) return;

    let cfg = {};
    try {
        cfg = await rpc(root.dataset.configUrl || "/atlas/pickup-config", {});
    } catch {
        return;   // leave "Zo snel mogelijk" as the only option
    }

    const step = Math.max(5, parseInt(cfg.slot_minutes, 10) || 15);
    const lead = Math.max(0, parseInt(cfg.lead_minutes, 10) || 20);
    let from = hhmmToMinutes(cfg.open_from, 17 * 60);
    let to = hhmmToMinutes(cfg.open_to, 22 * 60);
    if (to <= from) to += 1440;            // a venue that closes after midnight

    const now = new Date();
    const earliest = now.getHours() * 60 + now.getMinutes() + lead;
    const start = Math.max(from, Math.ceil(earliest / step) * step);

    for (let t = start; t <= to; t += step) {
        const option = document.createElement("option");
        option.value = option.textContent = label(t);
        select.appendChild(option);
    }
    if (select.dataset.selected) select.value = select.dataset.selected;

    select.addEventListener("change", () => {
        rpc(root.dataset.url || "/atlas/pickup-time", { value: select.value })
            .catch(() => {});   // a failed store must not block checkout
    });
}

document.addEventListener("DOMContentLoaded", setup);

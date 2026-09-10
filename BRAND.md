# Brand

Atlas POS visual identity, for use when presenting or forking this project.

## Logo

| File | Use |
|---|---|
| `assets/banner.svg` | README / social header, 1200×320, dark background |
| `assets/logo-mark.svg` | Square mark (app icon, avatar), works on any background |
| `assets/atlas-pos-wordmark.svg` | "ATLAS POS" wordmark (blue), for light backgrounds |
| `assets/atlas-pos-logo.png` | Raster POS logo |
| `assets/atlas-corp-logo.png` | Atlas Corporation logo |

Keep clear space around the mark of at least the width of the "A" stroke.
Do not stretch, recolour the mark outside the palette, or place the blue
wordmark on a dark background (use the white wordmark in `banner.svg` instead).

## Palette

| Name | Hex | Use |
|---|---|---|
| Navy | `#0A1628` | Primary background |
| Deep navy | `#0E1F38` | Background gradient |
| Grid blue | `#12304F` | Subtle grid / borders |
| Atlas blue | `#0EA5FF` | Primary accent, links, mark |
| Amber | `#F59E0B` | Secondary accent / highlight |
| Ink | `#251D1A` | Headings on light backgrounds |
| Sage | `#749B65` | Alternate (Odoo backend theme) accent |
| White | `#FFFFFF` | Text on dark |
| Muted | `#9FB3C8` | Secondary text on dark |

## Type

System UI stack (Segoe UI, Helvetica, Arial). Wordmark is bold, wide-tracked,
uppercase. Body text is sentence case.

## Diagrams

Diagrams use [Mermaid](https://mermaid.js.org/) so they render natively on
GitHub and Forgejo — see `docs/14-architecture-diagrams.md`. When exporting a
diagram to an image, use the palette above (navy background, blue/amber accents).

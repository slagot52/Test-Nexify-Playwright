# Nexify JSON-Driven Suite Recap

_Last updated: 2026-07-24_

## Baseline (frozen, protected — not JSON-driven)

| DSP | File | Status |
|---|---|---|
| DV360 | `test_dv360_playwright.py` | 🟢 frozen baseline (tests 1-61) |
| Amazon | `test_amazon_playwright.py` | 🟢 frozen baseline |
| TTD | `test_ttd_playwright.py` | 🟢 frozen baseline (tests 1-45) |

## JSON-driven suites

| DSP | Client | Advertiser | Suite | Status |
|---|---|---|---|---|
| DV360 | Samsung | Samsung_ES_Starcom | JSON Targeting (generic) | 🟢 |
| DV360 | Samsung | Samsung_ES_Starcom | Generico (Video/CTV) | 🟢 |
| DV360 | Mondelez ⚠️ | Oreo_ES ⚠️ | Generico Oreo (Target Frequency / Non-Skippable / OTT) | 🟡 |
| DV360 | L'Oreal | Mugler | Mugler (mixed Display + YouTube + Video) | 🟡 |
| DV360 | L'Oreal | Garnier_ES | YouTube/CTV | 🟢 |
| DV360 | ALDI ⚠️ | ALDI ⚠️ | ALDI (Non-Skippable) | 🟡 (lite variant 🟢) |
| Amazon | L'Oreal ⚠️ | Mugler ⚠️ | Mugler | 🟡 |
| Amazon | Samsung | Samsung_ES_Starcom | Display | 🟢 |
| Amazon | Samsung | Samsung_ES_Starcom | Open Intereses | 🟢 |
| Amazon | Samsung | Samsung_ES_Starcom | Deal Open Video | 🟢 |
| TTD | Samsung | Samsung_ES_Starcom | Programmatic Guarantees | 🟢 |
| TTD | Samsung | Samsung_ES_Starcom | PDs | 🟢 |
| TTD | Samsung | Samsung_ES_Starcom | CTV | 🟢 |

⚠️ = CLIENT/Advertiser is an unverified placeholder guess, not confirmed live.

🟢 = run live at least once (suite executed against the real Nexify UI). 🟡 = built + offline-validated, not run live yet. 🔴 = no test yet.

## Notes

- **New Samsung batch (2026-07-23, 3 Amazon + 3 TTD): fully built, 0 remaining.** All 6 exports now have a suite, and all 6 ran green live — all 3 TTD suites and the Amazon Display suite additionally went all the way through a real, DSP-confirmed campaign launch.
- **Open PRs:** [#7](https://github.com/slagot52/Test-Nexify-Playwright/pull/7) (ALDI), [#9](https://github.com/slagot52/Test-Nexify-Playwright/pull/9) (Amazon Mugler), [#10](https://github.com/slagot52/Test-Nexify-Playwright/pull/10)–[#15](https://github.com/slagot52/Test-Nexify-Playwright/pull/15) (the 6 new Samsung suites).
- **Known open findings:** Amazon Samsung suites (Display/Open Intereses/Deal Open Video) see 0/N audience+location id resolution in every ad group, not yet investigated. ALDI's YouTube video ids never resolve via placements (channels resolve fine). TTD suites hit a confirmed, reproducible Conversion Reporting dialog bug (`openConversionReportingDialog()` missing a catch on its `Promise.all`) across all 3 exports.

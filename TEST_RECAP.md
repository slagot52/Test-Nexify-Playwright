# Nexify JSON-Driven Suite Recap

_Last updated: 2026-07-24 (all 6 Samsung batch suites now real-launch-confirmed)_

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
| Amazon | Samsung | Samsung_ES_Starcom | Display | 🟢 COMPLETE (real launch) |
| Amazon | Samsung | Samsung_ES_Starcom | Open Intereses | 🟢 COMPLETE (real launch) |
| Amazon | Samsung | Samsung_ES_Starcom | Deal Open Video | 🟢 COMPLETE (real launch) |
| TTD | Samsung | Samsung_ES_Starcom | Programmatic Guarantees | 🟢 COMPLETE (real launch) |
| TTD | Samsung | Samsung_ES_Starcom | PDs | 🟢 COMPLETE (real launch) |
| TTD | Samsung | Samsung_ES_Starcom | CTV | 🟢 COMPLETE (real launch) |

⚠️ = CLIENT/Advertiser is an unverified placeholder guess, not confirmed live.

🟢 = run live at least once (suite executed against the real Nexify UI). 🟡 = built + offline-validated, not run live yet. 🔴 = no test yet.

## Notes

- **New Samsung batch (2026-07-23/24, 3 Amazon + 3 TTD): fully built, fully closed out.** All 6 exports now have a suite, and all 6 went all the way through a real, DSP-confirmed `COMPLETED` campaign launch - the first batch in this whole suite family where every single suite reached that bar, not just a clean dry run. Open Intereses hit a real DSP rejection on its first launch attempt (`End Date should be within campaign dates`); the fix ([[feedback_verify_both_date_inputs]]) held on the successful re-run.
- **All PRs for this repo have been merged to `main`** (#7, #9-#16) - no open PRs remain.
- **Known open findings:** Amazon Samsung suites (Display/Open Intereses/Deal Open Video) see 0/N audience+location id resolution in every ad group, not yet investigated. ALDI's YouTube video ids never resolve via placements (channels resolve fine). TTD suites hit a confirmed, reproducible Conversion Reporting dialog bug (`openConversionReportingDialog()` missing a catch on its `Promise.all`) across all 3 exports.

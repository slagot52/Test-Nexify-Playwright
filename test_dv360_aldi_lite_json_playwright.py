# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 "ALDI" suite, LITE)
================================================================================
Scoped-down variant of test_dv360_aldi_json_playwright.py for fast smoke
testing: builds only the 4 MOST RECENT line items from the reference JSON
instead of all 72. "Most recent" = the last 4 entries of IO2's 49-line-item
list, i.e. the tail of the full 72-line-item document in export order (IO1's
23 line items are dropped entirely; IO0 already has 0 in the real export).

Reuses the full suite's reference JSON, CLIENT/ADVERTISER, and every helper
unchanged (general info, IO creation for all 3 IOs, LI/AG targeting, the
bid-value-unsettable NON_SKIPPABLE handling, the submit guard) - this file
only trims the reference and skips IO1's line-item content. See
test_dv360_aldi_json_playwright.py's module docstring for the full list of
confirmed UI gaps and known frontend bugs (bid value, IO-switch desync).

Building only in IO2 (a single IO ever gets a line-item type selected) also
sidesteps the IO-switch type-desync bug entirely
(BUG_youtube_section_not_mounting_after_io_switch.md) - no prior type
selection exists in this session to collide with, so
settle_after_risky_io_switch isn't needed here.

This exists purely to validate the suite's mechanics end-to-end in minutes
instead of hours (single ad group: ~100 channels + a few videos via one
bulk placements call, ~59 keywords, 29 categories, one synthetic ad, x4). It
is NOT a substitute for eventually running the full 72-LI suite.

Run with:        python test_dv360_aldi_lite_json_playwright.py
"""

from playwright.sync_api import expect, sync_playwright

from test_dv360_playwright import AUTH_FILE, manual_login, test_landing, test_global_setup
from test_dv360_aldi_json_playwright import (
    CLIENT,
    ADVERTISER,
    load_reference,
    validate_offline,
    test_general_info,
    test_template_dialog,
    test_sidebar_sync,
    create_insertion_orders_aldi,
    build_io_aldi,
    finish_and_submit_aldi,
    select_io_tab,
    install_submit_guard,
)

LITE_LI_COUNT = 4


def load_reference_lite(n: int = LITE_LI_COUNT) -> dict:
    """Same reference JSON as the full suite, trimmed to the N most recent
    line items - the last N entries of IO2's line-item list (the tail of
    the full 72-LI document in export order). IO1 is trimmed to 0 line
    items (matching how IO0 already has none in the real export) so the
    trimmed structure exactly mirrors what this lite run actually builds -
    IOs are still all created (same campaign structure), only IO2 gets
    line-item content."""
    ref = load_reference()
    ios = ref["insertionOrders"]
    ios[1]["lineItems"] = []
    ios[2]["lineItems"] = ios[2]["lineItems"][-n:]
    return ref


def main():
    ref = load_reference_lite()
    assert CLIENT and ADVERTISER, (
        "CLIENT/ADVERTISER are not set in test_dv360_aldi_json_playwright.py - fix them there first."
    )
    validate_offline(ref)

    with sync_playwright() as p:
        if AUTH_FILE.exists():
            print(f"Session found in {AUTH_FILE.name}, reusing it.")
        else:
            manual_login(p)
        storage_state = str(AUTH_FILE)

        print("\nOpening the browser with the SSO session...")
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(storage_state=storage_state, no_viewport=True)
        page = context.new_page()
        install_submit_guard(page)

        try:
            test_landing(page)
            footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            create_insertion_orders_aldi(page, ref)
            test_sidebar_sync(page)

            # Line Items step: Next opens the "Review insertion orders" dialog.
            footer.locator("button.mdc-button", has_text="Next").click()
            dialog = page.locator("mat-dialog-container")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.locator("button", has_text="Confirm & continue").click()
            expect(dialog).not_to_be_visible()

            print(f"NOTE: LITE run - IO0 and IO1 built with 0 line items (Nexify's auto-created "
                  f"default line item left untouched); only IO2's {LITE_LI_COUNT} most recent "
                  f"line items are built.")

            # IO0 is active by default when landing on Line Items - jump
            # straight to IO2, skipping IO1 entirely. No prior line-item
            # type has been selected in this session yet, so this is not an
            # at-risk IO-switch transition (see module docstring).
            select_io_tab(page, 2)
            build_io_aldi(page, ref, 2, "YT NonSkip Lite", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE")

            finish_and_submit_aldi(page)

            print("\nALL TESTS PASSED ✅")
            try:
                page.wait_for_timeout(3000)
            except Exception:
                pass

        except AssertionError as error:
            print(f"\nTEST FAILED ❌ : {error}")

        finally:
            print("\nTests finished. The browser stays open for inspection.")
            try:
                input(">>> Press ENTER to close the browser... ")
            except (EOFError, KeyboardInterrupt):
                pass
            for _close in (context.close, browser.close):
                try:
                    _close()
                except Exception:
                    pass


if __name__ == "__main__":
    main()

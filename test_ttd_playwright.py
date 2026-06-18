# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com  -  TTD (The Trade Desk)
============================================================
Test suite for the campaign creation flow on the TTD DSP.

TTD-specific structure (differs from DV360):
  - DSP component: app-ttd-* (data-dsp-id="ttd")
  - Level 1: "Campaign Channels"  (vs "Insertion Orders" on DV360)
  - Level 2: "Ad Groups"          (vs "Line Items" on DV360)
  - Periods are called "Flights"

Reuses the shared helpers and SSO handling from test_nexify_playwright
(importing them does NOT run that suite: its main() is guarded by __main__).

Run with:        python test_ttd_playwright.py
Force new login: delete auth_state.json and run again.
"""

import datetime
import random
import string
import time

from playwright.sync_api import Page, expect, sync_playwright

from test_nexify_playwright import (
    AUTH_FILE,
    BASE_URL,
    TARGET_URL,
    DATE_FMT,
    ok,
    select_mat_option,
    select_all_multi,
    fill_and_verify,
    manual_login,
    test_landing,  # generic /campaign landing check (DSP-agnostic), reused as-is
)

# Advertiser (TTD) selected in the General Info grid -> makes this a TTD campaign.
TTD_ADVERTISER = "Garnier_ES"


# --------------------------------------------------------------------------
# TTD test steps  (filled in as the HTML of each section is provided)
# --------------------------------------------------------------------------
def test_ttd_general_info(page: Page):
    """TEST 4-16: campaign creation, General Info step, TTD advertiser grid."""
    create_btn = page.locator("button.mdc-button--unelevated", has_text="Create Campaign")
    expect(create_btn).to_be_visible()
    ok(4, "'Create Campaign' button found and visible")

    create_btn.click()
    page.wait_for_url("**/campaign/create", timeout=10000)
    assert page.url.rstrip("/") == f"{BASE_URL}/campaign/create", (
        f"Expected URL: {BASE_URL}/campaign/create\nActual URL: {page.url}"
    )
    ok(5, f"navigated correctly to {page.url}")

    footer = page.locator("div.step-footer")
    expect(footer).to_be_visible()
    expect(footer.locator("button.mdc-button", has_text="Cancel")).to_be_visible()
    expect(footer.locator("button.mdc-button", has_text="Save as draft")).to_be_visible()
    expect(footer.locator("button.mdc-button", has_text="Next")).to_be_visible()
    ok(6, "footer visible with Cancel, Save as draft and Next buttons")

    expect(
        page.locator("span.pb-5.text-4xl.font-bold", has_text="Add basic Campaign information")
    ).to_be_visible()
    ok(7, "'Add basic Campaign information' title visible")

    # The mat-error only appears after the field has been touched: click + Tab.
    campaign_input = page.locator("input[formcontrolname='campaignName']")
    expect(campaign_input).to_be_visible()
    campaign_input.click()
    campaign_input.press("Tab")
    expect(page.locator("mat-error", has_text="Campaign name is required")).to_be_visible()
    ok(8, "'Campaign name' field present with validation message")

    campaign_name = f"Test TTD - {int(time.time())}"
    campaign_input.fill(campaign_name)
    assert campaign_input.input_value() == campaign_name, "The field does not contain the expected text"
    ok(9, f"field filled with '{campaign_name}'")

    select_mat_option(page, "client", "L'Oreal")
    ok(10, "'Client' dropdown found and 'L'Oreal' option selected")

    aside = page.locator("aside.campaign-aside")
    expect(aside).to_be_visible()
    ok(11, "'campaign-aside' side panel visible")

    expect(aside.locator("h4", has_text=campaign_name)).to_be_visible()
    ok(12, f"side panel contains the campaign name '{campaign_name}'")

    client_row = aside.locator("p", has_text="Client")
    expect(client_row).to_be_visible()
    expect(client_row.locator("span", has_text="L'Oreal")).to_be_visible()
    ok(13, "side panel contains 'Client' with value 'L'Oreal'")

    grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
    expect(grid).to_be_visible()
    expect(grid.locator("td[role='columnheader']", has_text="DSP")).to_be_visible()
    expect(grid.locator("td[role='columnheader']", has_text="Advertiser")).to_be_visible()
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "No rows found in the advertiser grid"
    expect(grid.locator("div.dx-pager")).to_be_visible()
    ok(14, f"advertiser grid visible with {rows.count()} rows and pager")

    # The same advertiser name can exist for multiple DSPs (e.g. "Garnier_ES" on
    # both DV360 and TTD). We search to narrow the grid (handles pagination too),
    # then select the row that has BOTH the TTD badge (column 2) and the
    # advertiser name (column 3) — this is what makes the campaign a TTD one.
    search_box = grid.locator("input[aria-label='Search in the data grid']")
    search_box.fill(TTD_ADVERTISER)
    adv_row = (
        grid.locator("tr.dx-data-row")
        .filter(has=page.locator("td[aria-colindex='2']", has_text="TTD"))
        .filter(has=page.locator("td[aria-colindex='3']", has_text=TTD_ADVERTISER))
    )
    expect(adv_row).to_have_count(1)
    expect(adv_row).to_be_visible()
    adv_row.locator("div.dx-select-checkbox").click()
    expect(adv_row).to_have_attribute("aria-selected", "true")
    ok(15, f"advertiser '{TTD_ADVERTISER}' (TTD) selected in the grid")

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    expect(dsp_card.locator("span.dsp-name", has_text="The Trade Desk")).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row).to_be_visible()
    expect(brand_row.locator("span", has_text=TTD_ADVERTISER)).to_be_visible()
    ok(16, f"side panel updated with DSP 'The Trade Desk' and Brand '{TTD_ADVERTISER}'")

    return footer


def test_ttd_global_setup(page: Page):
    """TEST 17-22: TTD Global Setup (campaign group, Seed Id, Time Zone, PO, dates)."""
    # Navigate from General Info: click "Next". DV360 showed a template selector
    # dialog here; TTD may or may not. We dismiss it best-effort if it appears.
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    tmpl = page.locator("app-template-selector-dialog")
    try:
        expect(tmpl).to_be_visible(timeout=2000)
        tmpl.locator("button", has_text="Continuar sin seleccionar plantilla").click()
        expect(tmpl).not_to_be_visible()
    except AssertionError:
        pass

    gs_form = page.locator("app-ttd-global-setup form")
    expect(gs_form).to_be_visible()
    expect(gs_form.locator("h2", has_text="TTD Campaign Global")).to_be_visible()
    ok(17, "navigated to TTD Global Setup ('TTD Campaign Global' visible)")

    # TEST 18: campaign group = "Do not create campaign group" (default). Click it
    # only if not already selected, then verify.
    none_radio = gs_form.locator("mat-radio-button", has_text="Do not create campaign group")
    none_input = none_radio.locator("input[type='radio']")
    if not none_input.is_checked():
        none_radio.click()
    expect(none_input).to_be_checked()
    ok(18, "Campaign group = 'Do not create campaign group' confirmed")

    # TEST 19: Seed Id = Garnier Beauty
    select_mat_option(page, "seedId", "Garnier Beauty")
    ok(19, "Seed Id = 'Garnier Beauty' selected and verified")

    # TEST 20: Time Zone = (UTC) Coordinated Universal Time
    select_mat_option(page, "timeZone", "(UTC) Coordinated Universal Time")
    ok(20, "Time Zone = '(UTC) Coordinated Universal Time' selected and verified")

    # TEST 21: Purchase Order Number = random alphanumeric text, max 8 characters.
    purchase_order = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    fill_and_verify(gs_form, "purchaseOrderNumber", purchase_order)
    ok(21, f"Purchase Order Number = '{purchase_order}'")

    # TEST 22: Dates - open the custom date dialog (the form inputs are readonly),
    # fill the start/end range (tomorrow / day after) and Apply.
    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    gs_form.locator("button.dt-suffix").first.click()
    dlg = page.locator("app-date-time-range-dialog")
    expect(dlg).to_be_visible()
    dlg.locator("input[formcontrolname='startDate']").fill(date_from.strftime(DATE_FMT))
    dlg.locator("input[formcontrolname='endDate']").fill(date_to.strftime(DATE_FMT))
    dlg.locator("button.mdc-button--unelevated", has_text="Apply").click()
    expect(dlg).not_to_be_visible()
    ok(22, f"Dates set via dialog: Start={date_from} End={date_to}")


# TODO: test_ttd_campaign_channels(page) - Step 3, Campaign Channels
# TODO: test_ttd_ad_groups(page)         - Step 4, Ad Groups
# TODO: test_ttd_recap(page)             - Step 5, Recap + Start campaign


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    with sync_playwright() as p:

        if AUTH_FILE.exists():
            print(f"Session found in {AUTH_FILE.name}, reusing it.")
        else:
            manual_login(p)
        storage_state = str(AUTH_FILE)

        print("\nOpening the browser with the SSO session...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()

        try:
            test_landing(page)              # TEST 1-3 (shared, DSP-agnostic)
            test_ttd_general_info(page)     # TEST 4-16
            test_ttd_global_setup(page)     # TEST 17-22
            # Next TTD steps will be called here as they are added.

            print("\nALL TESTS PASSED ✅")
            page.wait_for_timeout(3000)

        except AssertionError as error:
            print(f"\nTEST FAILED ❌ : {error}")

        finally:
            print("\nTests finished. The browser stays open for inspection.")
            input(">>> Press ENTER to close the browser... ")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()

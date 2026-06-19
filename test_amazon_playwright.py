# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com  -  Amazon DSP
===================================================
Test suite for the campaign creation flow on the Amazon DSP.

Reuses the shared helpers and SSO handling from test_dv360_playwright
(importing them does NOT run that suite: its main() is guarded by __main__).

Run with:        python test_amazon_playwright.py
Force new login: delete auth_state.json and run again.
"""

import datetime
import re
import time

from playwright.sync_api import Page, expect, sync_playwright

from test_dv360_playwright import (
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

# General Info selections that make this an Amazon campaign.
AMAZON_CLIENT = "Samsung"
AMAZON_ADVERTISER = "Samsung_ES_Starcom"
AMAZON_DSP_BADGE = "Amazon"  # DSP badge text in the advertiser grid


# --------------------------------------------------------------------------
# Amazon test steps  (filled in as the HTML of each section is provided)
# --------------------------------------------------------------------------
def test_amazon_general_info(page: Page):
    """TEST 4-16: campaign creation, General Info step, Amazon advertiser grid."""
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

    campaign_name = f"Test Amazon - {int(time.time())}"
    campaign_input.fill(campaign_name)
    assert campaign_input.input_value() == campaign_name, "The field does not contain the expected text"
    ok(9, f"field filled with '{campaign_name}'")

    select_mat_option(page, "client", AMAZON_CLIENT)
    ok(10, f"'Client' dropdown found and '{AMAZON_CLIENT}' option selected")

    aside = page.locator("aside.campaign-aside")
    expect(aside).to_be_visible()
    ok(11, "'campaign-aside' side panel visible")

    expect(aside.locator("h4", has_text=campaign_name)).to_be_visible()
    ok(12, f"side panel contains the campaign name '{campaign_name}'")

    client_row = aside.locator("p", has_text="Client")
    expect(client_row).to_be_visible()
    expect(client_row.locator("span", has_text=AMAZON_CLIENT)).to_be_visible()
    ok(13, f"side panel contains 'Client' with value '{AMAZON_CLIENT}'")

    grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
    expect(grid).to_be_visible()
    expect(grid.locator("td[role='columnheader']", has_text="DSP")).to_be_visible()
    expect(grid.locator("td[role='columnheader']", has_text="Advertiser")).to_be_visible()
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "No rows found in the advertiser grid"
    expect(grid.locator("div.dx-pager")).to_be_visible()
    ok(14, f"advertiser grid visible with {rows.count()} rows and pager")

    # The same advertiser name exists for multiple DSPs (Samsung_ES_Starcom is on
    # DV360, Amazon and TTD). Search to narrow the grid, then select the row that
    # has BOTH the Amazon badge (column 2) and the advertiser name (column 3).
    search_box = grid.locator("input[aria-label='Search in the data grid']")
    search_box.fill(AMAZON_ADVERTISER)
    adv_row = (
        grid.locator("tr.dx-data-row")
        .filter(has=page.locator("td[aria-colindex='2']", has_text=AMAZON_DSP_BADGE))
        .filter(has=page.locator("td[aria-colindex='3']", has_text=AMAZON_ADVERTISER))
    )
    expect(adv_row).to_have_count(1)
    expect(adv_row).to_be_visible()
    adv_row.locator("div.dx-select-checkbox").click()
    expect(adv_row).to_have_attribute("aria-selected", "true")
    ok(15, f"advertiser '{AMAZON_ADVERTISER}' (Amazon) selected in the grid")

    # Side panel updated: DSP card + Brand. The exact Amazon DSP display name in
    # the sidebar is not yet confirmed, so for now we assert the Brand only.
    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row).to_be_visible()
    expect(brand_row.locator("span", has_text=AMAZON_ADVERTISER)).to_be_visible()
    ok(16, f"side panel updated with Brand '{AMAZON_ADVERTISER}'")

    return campaign_name


def _set_date_range_dialog(page: Page, date_from: datetime.date, date_to: datetime.date) -> None:
    dialog = page.locator("app-date-time-range-dialog")
    expect(dialog).to_be_visible()
    dialog.locator("input[formcontrolname='startDate']").fill(date_from.strftime(DATE_FMT))
    dialog.locator("input[formcontrolname='endDate']").fill(date_to.strftime(DATE_FMT))
    dialog.locator("button", has_text="Apply").click()
    expect(dialog).not_to_be_visible()


def test_amazon_insertion_orders(page: Page):
    """TEST 17-25: Step 2 Insertion Orders (Amazon skips Global Setup)."""
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    # Dismiss template selector dialog if it appears.
    tmpl = page.locator("app-template-selector-dialog")
    try:
        expect(tmpl).to_be_visible(timeout=3000)
        tmpl.locator("button", has_text="Continuar sin seleccionar plantilla").click()
        expect(tmpl).not_to_be_visible()
    except AssertionError:
        pass
    io_form = page.locator("app-amazon-order-form")
    expect(io_form).to_be_visible(timeout=10000)
    ok(17, "navigated to Amazon Insertion Orders form")

    # TEST 18: Order Name
    order_name = f"Order Amazon - {int(time.time())}"
    fill_and_verify(io_form, "name", order_name)
    ok(18, f"Order Name filled with '{order_name}'")

    # TEST 19: Media Type = Display (Select All — Display is the only option)
    select_all_multi(page, "primaryInventoryTypes", "Display")
    ok(19, "Media Type set to 'Display' via Select All")

    # TEST 20: Goal = Awareness (card button)
    goal_card = io_form.locator("button.goal-card", has_text="Awareness")
    goal_card.click()
    expect(goal_card).to_have_class(re.compile("goal-card--selected"))
    ok(20, "Goal = 'Awareness' card selected and verified")

    # TEST 21: KPI = Reach (card button)
    kpi_card = io_form.locator("button.goal-card", has_text="Reach")
    kpi_card.click()
    expect(kpi_card).to_have_class(re.compile("goal-card--selected"))
    ok(21, "KPI = 'Reach' card selected and verified")

    # TEST 22: KPI Value = 1
    fill_and_verify(io_form, "kpiValue", "1")
    ok(22, "KPI Value = 1 entered and verified")

    # TEST 23: Optimization Strategy = Manage budget manually (MANUAL)
    manual_radio = io_form.locator(
        "input[type='radio'][formcontrolname='budgetAllocation'][value='MANUAL']"
    )
    manual_radio.click()
    expect(manual_radio).to_be_checked()
    ok(23, "Optimization Strategy = 'Manage budget manually' (MANUAL) selected")

    # TEST 24: Dates — Start tomorrow, End day after (via date-range dialog)
    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    io_form.locator("button.dt-suffix").first.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok(24, f"Insertion Order dates set: {date_from} → {date_to}")

    # TEST 25: Unused budget = Do not change flight budgets (NO_ROLLOVER)
    no_rollover = io_form.locator(
        "input[type='radio'][formcontrolname='flightBudgetRolloverStrategy'][value='NO_ROLLOVER']"
    )
    no_rollover.click()
    expect(no_rollover).to_be_checked()
    ok(25, "Unused budget = 'Do not change flight budgets' (NO_ROLLOVER) selected")

    # Flights, Budget Cap, Agency Fees, Off-Amazon Conversions, Frequency Caps:
    # left at defaults — not required for initial campaign creation.

    return order_name


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
        # Maximize the window and use the real screen size (no_viewport=True):
        # a small viewport makes the responsive layout collapse fields.
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(storage_state=storage_state, no_viewport=True)
        page = context.new_page()

        try:
            test_landing(page)                          # TEST 1-3
            campaign_name = test_amazon_general_info(page)  # TEST 4-16
            test_amazon_insertion_orders(page)              # TEST 17-25

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

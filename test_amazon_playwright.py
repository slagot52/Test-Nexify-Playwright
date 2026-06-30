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
    start_input = dialog.locator("input[formcontrolname='startDate']")
    end_input = dialog.locator("input[formcontrolname='endDate']")
    start_input.fill(date_from.strftime(DATE_FMT))
    end_input.fill(date_to.strftime(DATE_FMT))
    end_input.press("Tab")  # force blur so the date-range input commits/parses the typed value
    page.keyboard.press("Escape")  # dismiss any calendar overlay opened by Tab/focus, it can
    # otherwise intercept pointer events meant for the Apply button below.
    # Catch silent parsing failures here instead of a downstream server validation error.
    # The field re-renders the parsed date in its own locale format (e.g. "1/7/2026"
    # for the value we filled as "07/01/2026"), so just check it isn't empty rather
    # than comparing the exact display string.
    assert start_input.input_value().strip(), (
        "Start date field is empty (the typed value was not accepted/parsed by the date-range input)"
    )
    assert end_input.input_value().strip(), (
        "End date field is empty (the typed value was not accepted/parsed by the date-range input)"
    )
    apply_btn = dialog.locator("button", has_text="Apply")
    expect(apply_btn).to_be_enabled(timeout=5000)
    apply_btn.click()
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
    # Selecting MANUAL triggers a debounced re-render of the Budget & Flights
    # section: let it settle before grabbing locators inside it.
    page.wait_for_timeout(1500)
    ok(23, "Optimization Strategy = 'Manage budget manually' (MANUAL) selected")

    # TEST 24-26: Flight row — with MANUAL budget allocation there is no
    # IO-level "Dates" section: dates are set per-flight only.
    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    io_form.locator("button.flight-add").click()
    flight_row = io_form.locator("div[formarrayname='flights'] div.flight-row").first
    expect(flight_row).to_be_visible()
    flight_date_btn = flight_row.locator("button.dt-suffix").first
    expect(flight_date_btn).to_be_visible(timeout=10000)
    flight_date_btn.scroll_into_view_if_needed()
    flight_date_btn.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok(24, f"Flight dates set: {date_from} → {date_to}")

    fill_and_verify(flight_row, "budgetValue", "1")
    ok(25, "Flight budget = 1")

    fill_and_verify(flight_row, "currencyCode", "EUR")
    ok(26, "Flight currency = EUR")

    # TEST 27: Unused budget = Do not change flight budgets (NO_ROLLOVER)
    no_rollover = io_form.locator(
        "input[type='radio'][formcontrolname='flightBudgetRolloverStrategy'][value='NO_ROLLOVER']"
    )
    no_rollover.click()
    expect(no_rollover).to_be_checked()
    ok(27, "Unused budget = 'Do not change flight budgets' (NO_ROLLOVER) selected")

    # Budget Cap, Agency Fees, Off-Amazon Conversions, Frequency Caps:
    # left at defaults — not required for initial campaign creation.

    return order_name


def test_amazon_line_items(page: Page):
    """TEST 28-38: Step 3 Line Items — navigate and fill the Ad Group form."""
    # Navigate: Next in footer → "Confirm & continue" confirmation dialog
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    confirm_dlg = page.locator("mat-dialog-container")
    expect(confirm_dlg).to_be_visible(timeout=5000)
    confirm_dlg.locator("button", has_text="Confirm & continue").click()
    expect(confirm_dlg).not_to_be_visible()

    li = page.locator("app-line-items")
    expect(li).to_be_visible(timeout=10000)
    ad_form = li.locator("app-amazon-ad-groups form")
    expect(ad_form).to_be_visible()
    ok(28, "navigated to Line Items, Ad Group form visible")

    # TEST 29: Ad Group Name
    ad_group_name = f"Test AG Amazon - {int(time.time())}"
    fill_and_verify(ad_form, "name", ad_group_name)
    ok(29, f"Ad Group Name = '{ad_group_name}'")

    # TEST 30: Base Bid = 1
    fill_and_verify(ad_form, "baseBid", "1")
    ok(30, "Base Bid = 1")

    # TEST 31: Max Average Bid = 1
    fill_and_verify(ad_form, "maxAverageBid", "1")
    ok(31, "Max Average Bid = 1")

    # TEST 32: Delivery Profile = ASAP
    select_mat_option(page, "deliveryProfile", "ASAP")
    ok(32, "Delivery Profile = 'ASAP' selected and verified")

    # TEST 33: Viewability Tier = Greater than 40 percent
    select_mat_option(page, "viewabilityTier", "Greater than 40 percent")
    ok(33, "Viewability Tier = 'Greater than 40 percent' selected and verified")

    # TEST 34: Inventory Type = Streaming TV
    select_mat_option(page, "inventoryType", "Streaming TV")
    ok(34, "Inventory Type = 'Streaming TV' selected and verified")

    # TEST 35: Creative Rotation = Random
    select_mat_option(page, "creativeRotationType", "Random")
    ok(35, "Creative Rotation = 'Random' selected and verified")

    # TEST 36: Advertised product categories = "Black History Month" via the
    # "Manage" dialog (a plain text input does not exist for this field).
    categories_section = ad_form.locator("section").filter(
        has=page.locator("span.text-sm.font-semibold", has_text="Advertised product categories")
    )
    categories_section.locator("button", has_text="Manage").click()
    cat_dialog = page.locator("app-categories-dialog")
    expect(cat_dialog).to_be_visible(timeout=10000)
    # Categories load collapsed: expand "Holiday, Events" first.
    cat_dialog.locator("button[aria-label='Toggle Holiday, Events']").click()
    # Then click the leaf row's "Include" button (clicking the row text does
    # nothing — only the per-row Include button toggles selection).
    leaf_row = cat_dialog.locator("mat-nested-tree-node[aria-level='2']").filter(
        has=page.get_by_text("Black History Month", exact=True)
    )
    leaf_row.locator("button[aria-label='Include']").click()
    expect(cat_dialog.locator(".count")).to_have_text("1 selected")
    cat_dialog.locator("button", has_text="Apply").click()
    expect(cat_dialog).not_to_be_visible()
    expect(categories_section.locator("text=No categories selected.")).not_to_be_visible()
    ok(36, "Advertised product categories = 'Black History Month' selected via Manage dialog")

    # TEST 37: Budget = 1 (EUR, Lifetime) — click "Add Budget" to create the row first
    budgets_section = ad_form.locator("section").filter(
        has=page.locator("span.text-base.font-bold", has_text="Budgets")
    )
    budgets_section.locator("button", has_text="Add Budget").click()
    budget_input = budgets_section.locator("input[formcontrolname='budgetValue']")
    expect(budget_input).to_be_visible(timeout=10000)
    fill_and_verify(budgets_section, "budgetValue", "1")
    ok(37, "Ad Group Budget = 1 (EUR, Lifetime)")

    # TEST 38: Ad Group dates (Start = tomorrow, End = day after) via edit_calendar dialog.
    # Set last (after Budget): adding a budget row can trigger a debounced
    # re-render that wipes an earlier date selection, so verify + retry once.
    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    dates_section = ad_form.locator("section").filter(
        has=page.locator("span.text-base.font-bold", has_text="Dates")
    )
    start_date_input = dates_section.locator("input").first
    for attempt in range(2):
        dates_section.locator("button[matsuffix]").first.click()
        _set_date_range_dialog(page, date_from, date_to)
        if start_date_input.input_value().strip():
            break
    expect(start_date_input).not_to_have_value("")
    ok(38, f"Ad Group dates set: {date_from} → {date_to}")

    return ad_group_name


def test_amazon_recap(page: Page):
    """TEST 39-40: Recap step, Start campaign (user-gated)."""
    # Navigate: Next in footer → "Confirm & continue" confirmation dialog (best-effort)
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    confirm_dlg = page.locator("mat-dialog-container")
    try:
        expect(confirm_dlg).to_be_visible(timeout=5000)
        confirm_dlg.locator("button", has_text="Confirm & continue").click()
        expect(confirm_dlg).not_to_be_visible()
    except AssertionError:
        pass
    ok(39, "navigated to the Recap step")

    # TEST 40: click "Start campaign".
    # WARNING: this is a consequential action (it actually LAUNCHES the Amazon
    # campaign) and is hard to undo. The click happens ONLY if the user types 'yes'.
    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=10000)
    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES the Amazon campaign. "
        "Type 'yes' to confirm the click (anything else cancels): "
    ).strip().lower()
    if answer == "yes":
        start_btn.click()
        # If the server rejects the data, an activation-errors dialog appears.
        errors_dialog = page.locator("app-campaign-activation-errors-dialog")
        appeared = False
        try:
            expect(errors_dialog).to_be_visible(timeout=8000)
            appeared = True
        except AssertionError:
            appeared = False
        if appeared:
            messages = errors_dialog.locator("p.text-red-700").all_inner_texts()
            raise AssertionError(
                "Campaign validation failed at Start campaign:\n- "
                + "\n- ".join(m.strip() for m in messages)
            )
        ok(40, "'Start campaign' performed, no validation-errors dialog shown")
    else:
        print("TEST 40 SKIPPED -> click on 'Start campaign' cancelled by the user")


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
            test_amazon_insertion_orders(page)              # TEST 17-27
            test_amazon_line_items(page)                    # TEST 28-38
            test_amazon_recap(page)                         # TEST 39-40

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

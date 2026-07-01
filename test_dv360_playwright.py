# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com  (with SSO)
================================================
The site requires SSO login (e.g. Microsoft / Google / Okta). Playwright
cannot fill those forms automatically, so we use the "save the session once,
reuse it forever" strategy:

  1. First run        ->  opens a VISIBLE browser, you do the SSO login by
                          hand; the session is then saved to auth_state.json.
  2. Subsequent runs  ->  loads auth_state.json and skips the login.

Run with:        python test_dv360_playwright.py
Force new login: delete auth_state.json and run again.
"""

import datetime
import json
import random
import re
import string
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
AUTH_FILE = Path(__file__).parent / "auth_state.json"
BASE_URL = "https://publicisnexify.com"
TARGET_URL = BASE_URL + "/"
DATE_FMT = "%m/%d/%Y"  # format expected by the mat-datepicker (MM/DD/YYYY)


# --------------------------------------------------------------------------
# Reusable helpers
# --------------------------------------------------------------------------
def ok(number, message):
    """Print a passing test result in a uniform way."""
    print(f"TEST {number} OK -> {message}")


def select_mat_option(page: Page, form_control_name: str, option_name: str):
    """
    Open a <mat-select> identified by its formcontrolname and select the
    option with the exact given text, then verify the field shows the value.

    Important details handled here:
      - click(force=True): the floating mat-label intercepts pointer events on
        the trigger, but the mat-select still handles the click and opens the
        panel.
      - options are rendered in the CDK overlay (outside the form), inside the
        panel with id "<select-id>-panel": we scope to that panel to avoid
        collisions with other dropdowns.
      - get_by_role(..., exact=True): avoids partial matches (e.g. "CPM" vs "VCPM").
    """
    select = page.locator(f"mat-select[formcontrolname='{form_control_name}']")
    expect(select).to_be_visible()
    select.scroll_into_view_if_needed()
    select_id = select.get_attribute("id")

    # Open the panel with retry: sometimes the click does not register (timing
    # after a previous overlay closes). From the second attempt we use the
    # keyboard (focus + Enter), which is more reliable than a click for mat-select.
    for attempt in range(4):
        if attempt == 0:
            select.click(force=True)
        else:
            select.focus()
            select.press("Enter")
        try:
            expect(select).to_have_attribute("aria-expanded", "true", timeout=2000)
            break
        except AssertionError:
            # reset any intermediate state before retrying
            page.keyboard.press("Escape")
            continue
    else:
        raise AssertionError(f"Could not open the mat-select '{form_control_name}'")

    panel = page.locator(f"#{select_id}-panel")
    expect(panel).to_be_visible()

    option = panel.get_by_role("option", name=option_name, exact=True)
    expect(option).to_be_visible()
    option.scroll_into_view_if_needed()
    option.click()

    # Verify the value was applied; a retry covers the cases where the first
    # click only highlights the option without confirming it.
    try:
        expect(select).to_contain_text(option_name, timeout=3000)
    except AssertionError:
        if select.get_attribute("aria-expanded") == "true":
            option.click()
        expect(select).to_contain_text(option_name)
    return select


def select_all_multi(page: Page, form_control_name: str, expected_text: str):
    """
    Open a <mat-select multiple> with the matselectall directive and select all
    options. Idempotent: clicks "Select all" only if some option is still
    unselected, so the final state is always "all selected" even on repeated
    runs (clicking an already-active select-all would deselect everything).
    """
    select = page.locator(f"mat-select[formcontrolname='{form_control_name}']")
    expect(select).to_be_visible()
    select_id = select.get_attribute("id")
    select.click(force=True)

    panel = page.locator(f"#{select_id}-panel")
    expect(panel).to_be_visible()
    select_all_opt = panel.locator("mat-option[matselectalloption]")
    unselected = panel.locator("mat-option:not([matselectalloption])[aria-selected='false']")
    if unselected.count() > 0:
        select_all_opt.click()
    page.keyboard.press("Escape")
    expect(select).to_contain_text(expected_text)
    return select


def fill_and_verify(scope, form_control_name: str, value: str):
    """Fill an input (by formcontrolname) and verify the entered value."""
    field = scope.locator(f"input[formcontrolname='{form_control_name}']")
    expect(field).to_be_visible()
    field.fill(value)
    actual = field.input_value()
    assert actual == value, f"'{form_control_name}': expected '{value}', got '{actual}'"
    return field


# --------------------------------------------------------------------------
# SSO session handling
# --------------------------------------------------------------------------
def manual_login(playwright):
    """
    Open a visible window and wait for the user to complete the SSO login,
    then save the storage state (cookies + localStorage) to auth_state.json.
    """
    print("\nNo saved session found.")
    print("The browser will open: complete the SSO login manually.")
    print("Once you are INSIDE the site (homepage loaded), press ENTER here.")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(TARGET_URL)

    input("\n>>> Press ENTER after completing the SSO login in the browser... ")

    state = context.storage_state()
    AUTH_FILE.write_text(json.dumps(state))
    print(f"Session saved to {AUTH_FILE.name}")

    browser.close()
    return state


# --------------------------------------------------------------------------
# Test groups
# --------------------------------------------------------------------------
def test_landing(page: Page):
    """TEST 1-3: the /campaign page opens after SSO and has content."""
    response = page.goto(TARGET_URL, wait_until="domcontentloaded")
    assert response.status < 400, f"HTTP {response.status}"
    page.wait_for_load_state("networkidle")

    final_url = page.url
    if "login" in final_url.lower() or "sso" in final_url.lower():
        raise AssertionError(
            f"Redirected to login ({final_url}). "
            f"Delete {AUTH_FILE.name} and run again to perform a new login."
        )
    assert final_url.rstrip("/") == f"{BASE_URL}/campaign", (
        f"Expected URL: {BASE_URL}/campaign\nActual URL: {final_url}"
    )
    ok(1, f"correct URL ({final_url}), title: '{page.title()}'")

    expect(page.locator("nav, header, [role='navigation']").first).to_be_visible()
    ok(2, "navigation element found and visible")

    body_text = page.inner_text("body")
    assert len(body_text.strip()) > 100, "The body looks empty"
    ok(3, f"text found in body ({len(body_text.strip())} characters)")


def test_general_info(page: Page):
    """TEST 4-16: campaign creation, General Info step, advertiser grid."""
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

    campaign_name = f"Test Dv - {int(time.time())}"
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

    loreal_row = grid.locator("tr.dx-data-row").filter(
        has=page.locator("span", has_text="L'Oréal Paris_ES")
    )
    expect(loreal_row).to_be_visible()
    loreal_row.locator("div.dx-select-checkbox").click()
    expect(loreal_row).to_have_attribute("aria-selected", "true")
    ok(15, "advertiser 'L'Oréal Paris_ES' selected in the grid")

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    expect(dsp_card.locator("span.dsp-name", has_text="Google DV360")).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row).to_be_visible()
    expect(brand_row.locator("span", has_text="L'Oréal Paris_ES")).to_be_visible()
    ok(16, "side panel updated with DSP 'Google DV360' and Brand 'L'Oréal Paris_ES'")

    return footer


def test_template_dialog(page: Page, footer):
    """TEST 17-19: click Next, template dialog, 'Continue without template'."""
    footer.locator("button.mdc-button", has_text="Next").click()
    ok(17, "click on 'Next' performed")

    dialog = page.locator("app-template-selector-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2.mat-mdc-dialog-title", has_text="Selecciona una plantilla")).to_be_visible()
    expect(dialog.locator("h2 span", has_text="Google DV360")).to_be_visible()
    expect(dialog.locator("mat-list-option")).to_have_count(3)
    expect(dialog.locator("button", has_text="Cancelar")).to_be_visible()
    expect(dialog.locator("button", has_text="Usar plantilla")).to_be_visible()
    expect(dialog.locator("button", has_text="Continuar sin seleccionar plantilla")).to_be_visible()
    ok(18, "'Selecciona una plantilla' dialog visible with options and buttons")

    dialog.locator("button", has_text="Continuar sin seleccionar plantilla").click()
    expect(dialog).not_to_be_visible()
    ok(19, "clicked 'Continuar sin seleccionar plantilla', dialog closed")


def test_global_setup(page: Page):
    """TEST 20-26: DV360 Global Setup form."""
    gs_form = page.locator("app-dv360-global-setup form")
    expect(gs_form).to_be_visible()

    gs_campaign_name = f"Test Campaign - {int(time.time())}"
    fill_and_verify(gs_form, "campaignName", gs_campaign_name)
    ok(20, f"Campaign Name filled with '{gs_campaign_name}'")

    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    for control, value in (("dateFrom", date_from), ("dateTo", date_to)):
        field = gs_form.locator(f"input[formcontrolname='{control}']")
        field.fill(value.strftime(DATE_FMT))
        field.press("Escape")  # close any open calendar
    ok(21, f"Date From={date_from} Date To={date_to}")

    fill_and_verify(gs_form, "impressionsPerUser", "1")
    fill_and_verify(gs_form, "perEvery", "1")
    select_mat_option(page, "perUnit", "Week")
    ok(22, "Frequency Cap=1, per every=1, Unit=Week set and verified")

    select_mat_option(page, "targetObjectiveType", "Brand awareness")
    # Changing "Campaign Goal Type" reloads (in a DEBOUNCED, client-side way) the
    # options of "Target's Objective Type" and clears its value. We wait for this
    # late reset to finish BEFORE selecting CPM, otherwise our choice would be
    # overwritten by the reload.
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    ok(23, "Campaign Goal Type = 'Brand awareness' selected and verified")

    select_all_multi(page, "creativeTypes", "Display")
    ok(24, "Creative Types: 'Select all' selected and verified")

    # TEST 25: 'performanceGoalType' (mapped to 'campaignGoal' on the API side) is
    # the field the server reported as missing. The 'mat-mdc-select-empty' class
    # authoritatively indicates whether the control is empty: we re-select CPM
    # until the field stays populated (max 3 attempts).
    perf_select = page.locator("mat-select[formcontrolname='performanceGoalType']")

    def _perf_empty():
        return "mat-mdc-select-empty" in (perf_select.get_attribute("class") or "")

    for _ in range(3):
        select_mat_option(page, "performanceGoalType", "CPM")
        page.wait_for_timeout(1500)  # let a possible debounced reset fire
        if not _perf_empty():
            break
    assert not _perf_empty(), "performanceGoalType stays empty after the attempts"
    ok(25, "Target's Objective Type = 'CPM' selected, populated and stable")

    fill_and_verify(gs_form, "performanceGoalAmountMicros", "1")
    ok(26, "Target's Objective Value = 1 entered and verified")


def test_insertion_orders(page: Page):
    """TEST 27-37: Step 3 Insertion Orders form."""
    # From Global Setup we move to the Insertion Orders step with the footer
    # "Next" button (the URL does not change, it's an Angular step).
    # The first click may just confirm/blur the last filled field without
    # navigating: we re-click "Next" until the IO form appears.
    footer = page.locator("div.step-footer")
    io_form = page.locator("app-dv360-insertion-orders form")
    for _ in range(3):
        footer.locator("button.mdc-button", has_text="Next").click()
        try:
            expect(io_form).to_be_visible(timeout=5000)
            break
        except AssertionError:
            page.wait_for_timeout(1000)
    expect(io_form).to_be_visible()
    expect(
        page.locator("span.pb-5.text-4xl.font-bold", has_text="create the Insertion Orders")
    ).to_be_visible()

    io_display_name = f"US 1 - LOREAL - Display Ads - {int(time.time())}"
    fill_and_verify(io_form, "displayName", io_display_name)
    ok(27, f"Display Name filled with '{io_display_name}'")

    select_mat_option(page, "insertionOrderType", "Standard")
    ok(28, "Insertion Order Type = 'Standard' selected and verified")

    # TEST 29: Date range (start = tomorrow, end = day after tomorrow).
    # Note: dateFrom/dateTo also exist in Global Setup, so here we stay within
    # io_form to target the right pair.
    today = datetime.date.today()
    io_date_from = today + datetime.timedelta(days=1)
    io_date_to = today + datetime.timedelta(days=2)
    df = io_form.locator("input[formcontrolname='dateFrom']")
    dt = io_form.locator("input[formcontrolname='dateTo']")
    df.fill(io_date_from.strftime(DATE_FMT))
    dt.fill(io_date_to.strftime(DATE_FMT))
    dt.press("Enter")
    ok(29, f"Date range From={io_date_from} To={io_date_to}")

    # TEST 30: Purchase Order = random alphanumeric text, max 8 characters.
    purchase_order = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    fill_and_verify(io_form, "purchaseOrder", purchase_order)
    ok(30, f"Purchase Order = '{purchase_order}'")

    # TEST 31: Budget = 1 (numeric field with € suffix; the moneyinput directive
    # may reformat the value, so we just check it contains "1").
    budget_field = io_form.locator("input[formcontrolname='budget']")
    expect(budget_field).to_be_visible()
    budget_field.fill("1")
    budget_field.press("Tab")
    budget_val = budget_field.input_value()
    assert "1" in budget_val, f"Budget expected to contain '1', got '{budget_val}'"
    ok(31, f"Budget set to '{budget_val}'")

    # TEST 32: Optimization Objective = "Awareness"
    select_mat_option(page, "optimizationObjective", "Awareness")
    ok(32, "Optimization Objective = 'Awareness' selected and verified")

    # TEST 33: Pacing Period = Flight
    select_mat_option(page, "pacingPeriod", "Flight")
    ok(33, "Pacing Period = 'Flight' selected and verified")

    # TEST 34: Pacing Type = Ahead
    select_mat_option(page, "pacingType", "Ahead")
    ok(34, "Pacing Type = 'Ahead' selected and verified")

    # TEST 35: KPI Type = CPM
    # The site renamed this option from plain "CPM" to the full descriptive
    # label "Cost per thousand impressions (CPM)" (exact match is required).
    select_mat_option(page, "kpiType", "Cost per thousand impressions (CPM)")
    ok(35, "KPI Type = 'CPM' selected and verified")

    # TEST 36: KPI Target = 1
    # With KPI Type = CPM the "KPI Target" field becomes numeric (€) with a
    # different formcontrolname than 'kpiString': we locate it by accessible
    # label, so the locator stays valid regardless of the variant.
    kpi_target = io_form.get_by_role("spinbutton", name="KPI Target")
    expect(kpi_target).to_be_visible()
    kpi_target.fill("1")
    assert kpi_target.input_value() == "1", f"KPI Target expected '1', got '{kpi_target.input_value()}'"
    ok(36, "KPI Target = 1 entered and verified")

    # TEST 37: checkbox "Unlimited up to the campaign's frequency cap" checked.
    # We check it only if it isn't already, then verify the final state.
    unlimited_row = io_form.locator(
        "div.flex.items-center.gap-3",
        has_text="Unlimited up to the campaign's frequency cap",
    )
    unlimited_input = unlimited_row.locator("input[type='checkbox']")
    if not unlimited_input.is_checked():
        unlimited_row.locator("mat-checkbox").click()
    expect(unlimited_input).to_be_checked()
    ok(37, "checkbox 'Unlimited up to...' checked and verified")


def test_sidebar_sync(page: Page):
    """
    TEST 38: the sidebar is updated and shows the same data as the main form.
    Values are read dynamically from the form (not hardcoded) and compared with
    what is shown in the aside.
    """
    io_form = page.locator("app-dv360-insertion-orders form")
    aside = page.locator("aside.campaign-aside")

    # Form Display Name == Insertion Order name shown in the sidebar
    display_name = io_form.locator("input[formcontrolname='displayName']").input_value().strip()
    assert display_name, "Display Name empty in the main form"
    io_surface = aside.locator(".io-surface").filter(has_text=display_name)
    expect(io_surface).to_be_visible()

    # DSP and Brand (coming from step 1) present in the sidebar
    expect(aside.locator("span.dsp-name", has_text="Google DV360")).to_be_visible()
    brand_row = aside.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text="L'Oréal Paris_ES")).to_be_visible()

    # Form Budget reflected in the sidebar "period chip" (amount + €)
    budget_val = io_form.locator("input[formcontrolname='budget']").input_value()
    m = re.match(r"\s*(\d+)", budget_val)
    budget_int = m.group(1) if m else budget_val
    period_chip = io_surface.locator(".period-chip")
    expect(period_chip).to_contain_text("€")
    expect(period_chip).to_contain_text(budget_int)

    # The budget date (tomorrow's year) is shown in the period chip
    year = str((datetime.date.today() + datetime.timedelta(days=1)).year)
    expect(period_chip).to_contain_text(year)

    ok(38, f"sidebar synced with the form (IO '{display_name}', budget '{budget_val}')")


def test_line_items(page: Page):
    """TEST 39-40: Step 4 Line Items (with IO summary dialog confirmation)."""
    # From the Insertion Orders step we click "Next": the summary dialog opens.
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()

    # TEST 39: "Review insertion orders" dialog visible, confirm with
    # "Confirm & continue".
    dialog = page.locator("dv360-io-summary-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2", has_text="Review insertion orders")).to_be_visible()
    dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
    expect(dialog).not_to_be_visible()
    ok(39, "'Review insertion orders' dialog confirmed with 'Confirm & continue'")

    # TEST 40: verify the "Line Items" step is selected in the stepper.
    line_items_step = page.locator("dx-stepper div.dx-step", has_text="Line Items")
    expect(line_items_step).to_have_attribute("aria-selected", "true")
    ok(40, "navigated to the 'Line Items' step (step selected in the stepper)")


def test_line_items_form(page: Page):
    """TEST 41-61: fill the DV360 Line Items form."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible()

    # TEST 41: Line Item name = "DISPLAY OPEN - " + unix timestamp
    li_name = f"DISPLAY OPEN - {int(time.time())}"
    fill_and_verify(li_form, "name", li_name)
    ok(41, f"Line Item name filled with '{li_name}'")

    # TEST 42: Media Type / Line item type = Display
    select_mat_option(page, "lineItemType", "Display")
    ok(42, "Media Type / Line item type = 'Display' selected and verified")

    # TEST 43: "Use same flight dates as Insertion Order" checked.
    flight_cb_root = li_form.locator("mat-checkbox[formcontrolname='useIoFlightDates']")
    flight_cb = flight_cb_root.locator("input[type='checkbox']")
    if not flight_cb.is_checked():
        flight_cb_root.click()
    expect(flight_cb).to_be_checked()
    ok(43, "checkbox 'Use same flight dates as Insertion Order' confirmed checked")

    # TEST 44: Budget allocation = Unlimited
    select_mat_option(page, "budgetAllocationType", "Unlimited")
    ok(44, "Budget allocation = 'Unlimited' selected and verified")

    # TEST 45: Pacing period = Flight
    select_mat_option(page, "pacingPeriod", "Flight")
    ok(45, "Pacing period = 'Flight' selected and verified")

    # TEST 46: Pacing type = ASAP
    select_mat_option(page, "pacingType", "ASAP")
    ok(46, "Pacing type = 'ASAP' selected and verified")

    # TEST 47: "Limit exposure frequency to" checked (enables freqCount/Every/Unit).
    limit_row = li_form.locator("div.flex.items-start.gap-3", has_text="Limit exposure frequency to")
    limit_cb = limit_row.locator("input[type='checkbox']")
    if not limit_cb.is_checked():
        limit_row.locator("mat-checkbox").click()
    expect(limit_cb).to_be_checked()
    ok(47, "checkbox 'Limit exposure frequency to' confirmed checked")

    # TEST 48-49: freqCount = 1, freqEvery = 1
    fill_and_verify(li_form, "freqCount", "1")
    ok(48, "freqCount = 1 entered and verified")
    fill_and_verify(li_form, "freqEvery", "1")
    ok(49, "freqEvery = 1 entered and verified")

    # TEST 50: freqUnit = Minute (dropdown)
    select_mat_option(page, "freqUnit", "Minute")
    ok(50, "freqUnit = 'Minute' selected and verified")

    # TEST 51: EU Political Ads = "Does not contain EU political advertising"
    select_mat_option(page, "containsEuPoliticalAds", "Does not contain EU political advertising")
    ok(51, "EU Political Ads = 'Does not contain EU political advertising' selected")

    # TEST 52: "Maximize Reach" removed from Bid strategy options (regression
    # check for the DV360 bid-strategy cleanup).
    bid_select = li_form.locator("mat-select[formcontrolname='bidStrategyType']")
    expect(bid_select).to_be_visible()
    bid_select.scroll_into_view_if_needed()
    bid_select_id = bid_select.get_attribute("id")
    bid_select.click(force=True)
    expect(bid_select).to_have_attribute("aria-expanded", "true")
    bid_panel = page.locator(f"#{bid_select_id}-panel")
    expect(bid_panel).to_be_visible()
    expect(bid_panel.get_by_role("option", name="Maximize Reach", exact=True)).to_have_count(0)
    page.keyboard.press("Escape")
    ok(52, "'Maximize Reach' confirmed removed from Bid strategy options")

    # TEST 53: Bid strategy = Fixed bid
    select_mat_option(page, "bidStrategyType", "Fixed bid")
    ok(53, "Bid strategy = 'Fixed bid' selected and verified")

    # TEST 54: Bid amount (CPM) = 1
    fill_and_verify(li_form, "bidAmount", "1")
    ok(54, "Bid amount (CPM) = 1 entered and verified")

    # TEST 55: Partner revenue model = Total Media Cost
    select_mat_option(page, "partnerRevenueModelMarkupType", "Total Media Cost")
    ok(55, "Partner revenue model = 'Total Media Cost' selected and verified")

    # TEST 56: Markup = 0
    fill_and_verify(li_form, "partnerRevenueModelMarkupValue", "0")
    ok(56, "Markup = 0 entered and verified")

    # TEST 57: "Partner costs" section shown at Line Item level (not inside the
    # Insertion Order) with the corrected copy.
    expect(li_form.get_by_text("Partner costs", exact=True)).to_be_visible()
    expect(li_form.get_by_text("Leave empty to inherit from the partner.", exact=True)).to_be_visible()
    ok(57, "'Partner costs' section present at Line Item level with corrected copy")

    # TEST 58: "Brand safety prebids" field removed (not connected to backend).
    expect(li_form.get_by_text("Brand safety prebids")).to_have_count(0)
    ok(58, "'Brand safety prebids' field confirmed removed")

    # TEST 59: click "Add fee" (mat-menu-trigger) and select the "CPM fee" item.
    add_fee_btn = li_form.locator("button.mat-mdc-menu-trigger", has_text="Add fee")
    expect(add_fee_btn).to_be_visible()
    add_fee_btn.scroll_into_view_if_needed()

    # Open the menu with retry: a plain click sometimes does not open the
    # mat-menu, so from the second attempt we use the keyboard (focus + Enter).
    for attempt in range(4):
        if attempt == 0:
            add_fee_btn.click(force=True)
        else:
            add_fee_btn.focus()
            add_fee_btn.press("Enter")
        try:
            expect(add_fee_btn).to_have_attribute("aria-expanded", "true", timeout=2000)
            break
        except AssertionError:
            page.keyboard.press("Escape")
            continue
    else:
        raise AssertionError("Could not open the 'Add fee' menu")

    # The mat-menu items are rendered in the CDK overlay with role="menuitem".
    page.get_by_role("menuitem", name="CPM fee", exact=True).click()
    # After selection the menu closes (trigger no longer expanded).
    expect(add_fee_btn).to_have_attribute("aria-expanded", "false")
    ok(59, "clicked 'Add fee' and selected the 'CPM fee' item")

    # TEST 60: click "Next" in the footer to proceed.
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok(60, "click on 'Next' in the footer performed")

    # TEST 61: click "Start campaign".
    # WARNING: this is a consequential action (it actually LAUNCHES the campaign)
    # and is hard to undo. For safety we require explicit confirmation from the
    # terminal: the click happens ONLY if the user types 'yes'.
    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible()
    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES the campaign. "
        "Type 'yes' to confirm the click (anything else cancels): "
    ).strip().lower()
    if answer == "yes":
        start_btn.click()
        # If the server rejects the data, an activation-errors dialog appears.
        # Surface its messages as a clear test failure instead of passing silently.
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
        ok(61, "'Start campaign' performed, no validation-errors dialog shown")
    else:
        print("TEST 61 SKIPPED -> click on 'Start campaign' cancelled by the user")


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
        # a small viewport makes the responsive layout collapse fields, which can
        # make them zero-size / not clickable.
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(storage_state=storage_state, no_viewport=True)
        page = context.new_page()

        try:
            test_landing(page)
            footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            test_insertion_orders(page)
            test_sidebar_sync(page)
            test_line_items(page)
            test_line_items_form(page)

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

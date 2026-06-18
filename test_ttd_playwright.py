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


def _open_and_select(page: Page, select, option_name: str):
    """
    Open a <mat-select> given by its Locator (not by formcontrolname) and select
    the exact option. Same robust open/verify logic as the shared
    select_mat_option, used for TTD selects that have no formcontrolname.
    """
    expect(select).to_be_visible()
    select.scroll_into_view_if_needed()
    select_id = select.get_attribute("id")
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
            page.keyboard.press("Escape")
            continue
    else:
        raise AssertionError("Could not open the mat-select")
    panel = page.locator(f"#{select_id}-panel")
    expect(panel).to_be_visible()
    panel.get_by_role("option", name=option_name, exact=True).click()
    expect(select).to_contain_text(option_name)
    return select


def _set_date_range_dialog(page: Page, date_from, date_to):
    """Fill the shared app-date-time-range-dialog (start/end) and click Apply."""
    dlg = page.locator("app-date-time-range-dialog")
    expect(dlg).to_be_visible()
    start = dlg.locator("input[formcontrolname='startDate']")
    end = dlg.locator("input[formcontrolname='endDate']")
    start.fill(date_from.strftime(DATE_FMT))
    end.fill(date_to.strftime(DATE_FMT))
    end.press("Enter")  # commit the range before applying
    # If the dates registered, Apply becomes enabled; otherwise fail clearly.
    apply_btn = dlg.locator("button.mdc-button--unelevated", has_text="Apply")
    expect(apply_btn).to_be_enabled()
    apply_btn.click()
    expect(dlg).not_to_be_visible()


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
    _set_date_range_dialog(page, date_from, date_to)
    ok(22, f"Dates set via dialog: Start={date_from} End={date_to}")

    # Persistence guard: Purchase Order is required at campaign start and may get
    # cleared by a reload (e.g. after the date dialog). Re-fill if it got reset.
    po_input = gs_form.locator("input[formcontrolname='purchaseOrderNumber']")
    if not po_input.input_value():
        po_input.fill(purchase_order)
    assert po_input.input_value(), "Purchase Order Number is empty after the guard"


def test_ttd_campaign_channels(page: Page):
    """TEST 23-30: TTD Campaign Channels (channel, pacing, KPIs, flight)."""
    # Navigate from Global Setup with "Next" (re-click if the first only blurs).
    cc_form = page.locator("app-ttd-campaign-channels form")
    for _ in range(3):
        page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
        try:
            expect(cc_form).to_be_visible(timeout=5000)
            break
        except AssertionError:
            page.wait_for_timeout(1000)
    expect(cc_form).to_be_visible()
    expect(cc_form.locator("h2", has_text="TTD Campaign Channels")).to_be_visible()
    ok(23, "navigated to TTD Campaign Channels ('TTD Campaign Channels' visible)")

    # TEST 24: Campaign/Channel Name
    channel_name = f"Audio - Test - {int(time.time())}"
    fill_and_verify(cc_form, "campaignName", channel_name)
    ok(24, f"Campaign Name (channel) filled with '{channel_name}'")

    # TEST 25: Channel = Audio
    select_mat_option(page, "primaryChannel", "Audio")
    ok(25, "Channel = 'Audio' selected and verified")

    # TEST 26: Pacing Mode = Pace Evenly
    select_mat_option(page, "pacingMode", "Pace Evenly")
    ok(26, "Pacing Mode = 'Pace Evenly' selected and verified")

    # TEST 27: Primary KPI Goal Type = Completion Rate.
    # The three "Goal Type" selects (Primary/Secondary/Tertiary) have no
    # formcontrolname; they appear in that order, so Primary is the first.
    primary_goal = cc_form.locator("mat-form-field", has_text="Goal Type").nth(0).locator("mat-select")
    _open_and_select(page, primary_goal, "Completion Rate")
    ok(27, "Primary KPI Goal Type = 'Completion Rate' selected and verified")

    # TEST 28: Primary KPI Goal % = 1 (input with no formcontrolname -> by label).
    goal_pct = cc_form.locator("mat-form-field", has_text="Goal %").locator("input")
    expect(goal_pct).to_be_visible()
    goal_pct.fill("1")
    assert goal_pct.input_value() == "1", f"Goal % expected '1', got '{goal_pct.input_value()}'"
    ok(28, "Primary KPI Goal % = 1 entered and verified")

    # TEST 29: Campaign Flight dates (start = tomorrow, end = day after) via dialog.
    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    flight = cc_form.locator("div.flight-row").first
    # Open the date dialog via the calendar icon button (the readonly date input
    # itself has zero size). With the maximized window the button is no longer
    # overlapped, so a normal click works.
    flight.locator("button.dt-suffix").first.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok(29, f"Flight dates set via dialog: Start={date_from} End={date_to}")

    # TEST 30: Flight Budget (advertiser currency) = 1
    fill_and_verify(flight, "budgetAmount", "1")
    ok(30, "Flight Budget = 1 entered and verified")

    # Secondary/Tertiary KPI left as 'None'; Fee card and Conversion reporting
    # are optional and skipped.


def test_ttd_ad_groups(page: Page):
    """TEST 31-38: Step 4 Ad Groups (with channels summary dialog confirmation)."""
    # From Campaign Channels click "Next": the summary dialog opens (same
    # dv360-io-summary-dialog component as DV360, with TTD content).
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()

    # TEST 31: "Review insertion orders" dialog, confirm with "Confirm & continue".
    dialog = page.locator("dv360-io-summary-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2", has_text="Review insertion orders")).to_be_visible()
    dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
    expect(dialog).not_to_be_visible()
    ok(31, "'Review insertion orders' dialog confirmed with 'Confirm & continue'")

    # TEST 32: verify the "Line Items" step (Step 4, = Ad Groups) is selected.
    step = page.locator("dx-stepper div.dx-step", has_text="Line Items")
    expect(step).to_have_attribute("aria-selected", "true")
    ok(32, "navigated to Step 4 (Ad Groups / 'Line Items' step selected)")

    ag_form = page.locator("app-ttd-ad-groups form")
    expect(ag_form).to_be_visible()

    # TEST 33: Ad Group Name = "Test AD - " + unix timestamp
    ad_group_name = f"Test AD - {int(time.time())}"
    fill_and_verify(ag_form, "adGroupName", ad_group_name)
    ok(33, f"Ad Group Name filled with '{ad_group_name}'")

    # TEST 34: Channel = Audio.
    # Changing the channel reloads the ad group config in a DEBOUNCED way and can
    # reset Funnel Location and the bid fields. We set the channel FIRST and wait
    # for the reload to settle before filling the others.
    select_mat_option(page, "channelId", "Audio")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)
    ok(34, "Channel = 'Audio' selected and verified")

    # TEST 35: Funnel Location = Awareness
    select_mat_option(page, "funnelLocation", "Awareness")
    ok(35, "Funnel Location = 'Awareness' selected and verified")

    # TEST 36: Base Bid CPM = 1
    fill_and_verify(ag_form, "baseBidAmount", "1")
    ok(36, "Base Bid CPM = 1 entered and verified")

    # TEST 37: Max Bid CPM = 1
    fill_and_verify(ag_form, "maxBidAmount", "1")
    ok(37, "Max Bid CPM = 1 entered and verified")

    # Persistence guard: a late debounced reload (from the channel change) may
    # clear Funnel Location / bids after we set them. Re-apply any that got reset,
    # then assert they are populated (these are required at campaign start).
    page.wait_for_timeout(1000)
    funnel_select = page.locator("mat-select[formcontrolname='funnelLocation']")
    if "mat-mdc-select-empty" in (funnel_select.get_attribute("class") or ""):
        select_mat_option(page, "funnelLocation", "Awareness")
    base_bid = ag_form.locator("input[formcontrolname='baseBidAmount']")
    if not base_bid.input_value():
        base_bid.fill("1")
    max_bid = ag_form.locator("input[formcontrolname='maxBidAmount']")
    if not max_bid.input_value():
        max_bid.fill("1")
    assert "mat-mdc-select-empty" not in (funnel_select.get_attribute("class") or ""), \
        "Funnel Location is empty after the guard"
    assert base_bid.input_value() and max_bid.input_value(), "Bid fields empty after the guard"

    # TEST 38: "Enabled" checkbox confirmed checked.
    enabled_cb = ag_form.locator("mat-checkbox[formcontrolname='isEnabled']")
    enabled_input = enabled_cb.locator("input[type='checkbox']")
    if not enabled_input.is_checked():
        enabled_cb.click()
    expect(enabled_input).to_be_checked()
    ok(38, "'Enabled' checkbox confirmed checked")

    # Left at defaults / skipped: Description, currencies (EUR), Goal Type
    # (None), Audience (Target Everyone), Predictive Clearing, and all the
    # optional list sections (Geography already has Spain, Device Type, Ad
    # Environment, Publisher List, Category, Supply Vendor, Deals, Contextual
    # Keywords).


def test_ttd_recap(page: Page):
    """TEST 39-40: Step 5 Recap, then optional Start campaign (user-gated)."""
    # From Ad Groups click "Next" to reach the Recap step. A summary dialog may
    # appear (as on the channels step): dismiss it best-effort if it does.
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    dialog = page.locator("dv360-io-summary-dialog")
    try:
        expect(dialog).to_be_visible(timeout=2000)
        dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
        expect(dialog).not_to_be_visible()
    except AssertionError:
        pass

    # TEST 39: Recap step loaded.
    expect(page.locator("app-recap-and-validate")).to_be_visible()
    expect(
        page.locator("span.pb-5.text-4xl.font-bold", has_text="Review before creating the Campaign")
    ).to_be_visible()
    recap_step = page.locator("dx-stepper div.dx-step", has_text="Recap")
    expect(recap_step).to_have_attribute("aria-selected", "true")
    ok(39, "navigated to the Recap step ('Review before creating the Campaign')")

    # TEST 40: click "Start campaign".
    # WARNING: this is a consequential action (it actually LAUNCHES the TTD
    # campaign) and is hard to undo. The click happens ONLY if the user types 'yes'.
    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible()
    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES the TTD campaign. "
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
        # a small viewport makes the responsive layout collapse fields (e.g. the
        # flight row date inputs), making them zero-size / not clickable.
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(storage_state=storage_state, no_viewport=True)
        page = context.new_page()

        try:
            test_landing(page)              # TEST 1-3 (shared, DSP-agnostic)
            test_ttd_general_info(page)     # TEST 4-16
            test_ttd_global_setup(page)     # TEST 17-22
            test_ttd_campaign_channels(page)  # TEST 23-30
            test_ttd_ad_groups(page)        # TEST 31-38
            test_ttd_recap(page)            # TEST 39-40 (Start campaign user-gated)

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

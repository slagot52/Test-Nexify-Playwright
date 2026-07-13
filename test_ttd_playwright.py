# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com - TTD (The Trade Desk)
=============================================================
Tests the campaign creation flow for the TTD DSP.

How TTD differs from DV360:
  - DSP component: app-ttd-* (data-dsp-id="ttd")
  - Level 1: "Campaign Channels" (DV360 calls this "Insertion Orders")
  - Level 2: "Ad Groups" (DV360 calls this "Line Items")
  - Periods are called "Flights"

Reuses the shared helpers and SSO handling from test_dv360_playwright
(importing it won't run that suite too — its main() is __main__-guarded).

Run with:        python test_ttd_playwright.py
Force new login: delete auth_state.json and run again.
"""

import datetime
import random
import string
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
    test_landing,  # generic /campaign landing check, DSP-agnostic
)

# Advertiser (TTD) selected in the General Info grid -> makes this a TTD campaign.
TTD_ADVERTISER = "Garnier_ES"

# Campaign Channels name counter: "Channel x - Client - Unix Date" (TTD's
# Campaign Channels is the level 1 equivalent of DV360's Insertion Orders).
# Resets to 0 each script run (one campaign per run) and increments per
# channel created.
_channel_name_counter = 0


def _open_and_select(page: Page, select, option_name: str):
    """Same open/verify logic as select_mat_option, but takes the select's
    Locator directly — for TTD selects that have no formcontrolname."""
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
    # Apply only enables once the dates registered — fails clearly otherwise.
    apply_btn = dlg.locator("button.mdc-button--unelevated", has_text="Apply")
    expect(apply_btn).to_be_enabled()
    apply_btn.click()
    expect(dlg).not_to_be_visible()


# --------------------------------------------------------------------------
# TTD test steps
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

    # "Garnier_ES" exists under multiple DSPs (DV360, TTD), so narrow via
    # search (this also handles pagination) then match on both the TTD badge
    # and the advertiser name.
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

    return campaign_name


def test_ttd_global_setup(page: Page):
    """TEST 17-22: TTD Global Setup (campaign group, Seed Id, Time Zone, PO, dates)."""
    # DV360 shows a template selector here; TTD may or may not — dismiss it
    # best-effort if it appears.
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

    # Click it only if not already selected, then verify.
    none_radio = gs_form.locator("mat-radio-button", has_text="Do not create campaign group")
    none_input = none_radio.locator("input[type='radio']")
    if not none_input.is_checked():
        none_radio.click()
    expect(none_input).to_be_checked()
    ok(18, "Campaign group = 'Do not create campaign group' confirmed")

    # TEST 19: Seed Id = Garnier Beauty
    select_mat_option(page, "seedId", "Garnier Beauty")
    ok(19, "Seed Id = 'Garnier Beauty' selected and verified")

    # TEST 20: Purchase Order Number = random number, max 8 digits.
    purchase_order = "".join(random.choices(string.digits, k=8))
    fill_and_verify(gs_form, "purchaseOrderNumber", purchase_order)
    ok(20, f"Purchase Order Number = '{purchase_order}'")

    # TEST 21: Time Zone = (UTC) Coordinated Universal Time
    select_mat_option(page, "timeZone", "(UTC) Coordinated Universal Time")
    ok(21, "Time Zone = '(UTC) Coordinated Universal Time' selected and verified")

    # The date inputs are readonly, so dates go through the custom dialog.
    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    gs_form.locator("button.dt-suffix").first.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok(22, f"Dates set via dialog: Start={date_from} End={date_to}")

    # Purchase Order is required at campaign start and can get cleared by a
    # reload (e.g. after the date dialog) — re-fill if it got reset.
    po_input = gs_form.locator("input[formcontrolname='purchaseOrderNumber']")
    if not po_input.input_value():
        po_input.fill(purchase_order)
    assert po_input.input_value(), "Purchase Order Number is empty after the guard"


def test_ttd_campaign_channels(page: Page):
    """TEST 23-31: TTD Campaign Channels (channel, pacing, KPIs, flight, conversion reporting)."""
    # Re-click "Next" if the first click only blurs instead of navigating.
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
    global _channel_name_counter
    _channel_name_counter += 1
    channel_name = f"Channel {_channel_name_counter} - L'Oreal - {int(time.time())}"
    fill_and_verify(cc_form, "campaignName", channel_name)
    ok(24, f"Campaign Name (channel) filled with '{channel_name}'")

    # TEST 25: Channel = Audio
    select_mat_option(page, "primaryChannel", "Audio")
    ok(25, "Channel = 'Audio' selected and verified")

    # TEST 26: Pacing Mode = Pace Evenly
    select_mat_option(page, "pacingMode", "Pace Evenly")
    ok(26, "Pacing Mode = 'Pace Evenly' selected and verified")

    # The three Goal Type selects (Primary/Secondary/Tertiary) have no
    # formcontrolname, but they appear in that order — Primary is the first.
    primary_goal = cc_form.locator("mat-form-field", has_text="Goal Type").nth(0).locator("mat-select")
    _open_and_select(page, primary_goal, "Completion Rate")
    ok(27, "Primary KPI Goal Type = 'Completion Rate' selected and verified")

    # No formcontrolname on this input either, so locate it by label.
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
    # The date input itself is zero-size, so open the dialog via the calendar
    # icon button instead (only clickable once the window is maximized).
    flight.locator("button.dt-suffix").first.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok(29, f"Flight dates set via dialog: Start={date_from} End={date_to}")

    # TEST 30: Flight Budget (advertiser currency) = 1
    fill_and_verify(flight, "budgetAmount", "1")
    ok(30, "Flight Budget = 1 entered and verified")

    # Conversion reporting: Vendor unlocks once Cross-Device Concept != None.
    conv_section = cc_form.locator("section.frequency-section").filter(
        has=page.get_by_text("Conversion reporting", exact=True)
    )
    conv_section.locator("button[mat-stroked-button]", has_text="Configure").click()
    conv_dialog = page.get_by_role("dialog").filter(has_text="Configure campaign reporting and attribution")
    expect(conv_dialog).to_be_visible()
    conv_dialog.locator("button", has_text="Add conversion data source").click()

    concept_select = conv_dialog.locator("mat-select[formcontrolname='crossDeviceConcept']")
    expect(concept_select).to_contain_text("None")
    concept_select_id = concept_select.get_attribute("id")
    concept_select.click(force=True)
    concept_panel = page.locator(f"#{concept_select_id}-panel")
    expect(concept_panel).to_be_visible()
    for option_name in ("None", "Person", "Household"):
        expect(concept_panel.get_by_role("option", name=option_name, exact=True)).to_be_visible()
    concept_panel.get_by_role("option", name="Person", exact=True).click()
    expect(concept_select).to_contain_text("Person")

    vendor_select = conv_dialog.locator("mat-select[formcontrolname='crossDeviceAttributionModelId']")
    expect(vendor_select).not_to_have_attribute("aria-disabled", "true")
    vendor_select_id = vendor_select.get_attribute("id")
    vendor_select.click(force=True)
    vendor_panel = page.locator(f"#{vendor_select_id}-panel")
    expect(vendor_panel).to_be_visible()
    vendor_panel.get_by_role("option", name="LiveRamp IdentityLink", exact=True).click()
    expect(vendor_select).to_contain_text("LiveRamp IdentityLink")

    conv_dialog.locator("button", has_text="Apply").click()
    expect(conv_dialog).not_to_be_visible()
    ok(31, "Conversion reporting: Cross-Device Concept options (None/Person/Household) verified, "
           "Vendor unlocked and 'LiveRamp IdentityLink' selected after Concept='Person'")

    # Secondary/Tertiary KPI left as 'None'; Fee card is optional and skipped.


def test_ttd_ad_groups(page: Page):
    """TEST 32-40: Step 4 Ad Groups (with channels summary dialog confirmation)."""
    # "Next" opens the same dv360-io-summary-dialog component DV360 uses,
    # just with TTD content.
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()

    # TEST 32: "Review insertion orders" dialog, confirm with "Confirm & continue".
    dialog = page.locator("dv360-io-summary-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2", has_text="Review insertion orders")).to_be_visible()
    dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
    expect(dialog).not_to_be_visible()
    ok(32, "'Review insertion orders' dialog confirmed with 'Confirm & continue'")

    # TEST 33: verify the "Line Items" step (Step 4, = Ad Groups) is selected.
    step = page.locator("dx-stepper div.dx-step", has_text="Line Items")
    expect(step).to_have_attribute("aria-selected", "true")
    ok(33, "navigated to Step 4 (Ad Groups / 'Line Items' step selected)")

    ag_form = page.locator("app-ttd-ad-groups form")
    expect(ag_form).to_be_visible()

    # TEST 34: Ad Group Name = "Test AD - " + unix timestamp
    ad_group_name = f"Test AD - {int(time.time())}"
    fill_and_verify(ag_form, "adGroupName", ad_group_name)
    ok(34, f"Ad Group Name filled with '{ad_group_name}'")

    # Changing the channel debounce-reloads the ad group config and can reset
    # Funnel Location and the bid fields — set channel first, then wait it out.
    select_mat_option(page, "channelId", "Audio")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)
    ok(35, "Channel = 'Audio' selected and verified")

    # TEST 36: Funnel Location = Awareness
    select_mat_option(page, "funnelLocation", "Awareness")
    ok(36, "Funnel Location = 'Awareness' selected and verified")

    # TEST 37: Base Bid CPM = 1
    fill_and_verify(ag_form, "baseBidAmount", "1")
    ok(37, "Base Bid CPM = 1 entered and verified")

    # TEST 38: Max Bid CPM = 1
    fill_and_verify(ag_form, "maxBidAmount", "1")
    ok(38, "Max Bid CPM = 1 entered and verified")

    # The channel-change reload can clear Funnel Location/bids after they're
    # set — re-apply anything that got reset, then confirm it's populated.
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

    # TEST 39: "Enabled" checkbox — present on some advertiser configs, absent on others.
    enabled_cb = ag_form.locator("mat-checkbox[formcontrolname='isEnabled']")
    if enabled_cb.count() > 0 and enabled_cb.is_visible():
        enabled_input = enabled_cb.locator("input[type='checkbox']")
        if not enabled_input.is_checked():
            enabled_cb.click()
        expect(enabled_input).to_be_checked()
        ok(39, "'Enabled' checkbox confirmed checked")
    else:
        print("TEST 39 SKIPPED -> 'Enabled' checkbox not present on this form")

    # TEST 40: "Deals & Contracts" section reordered directly below "Geography".
    section_headings = ag_form.locator("span.text-base.font-bold").all_inner_texts()
    geo_idx = section_headings.index("Geography")
    assert section_headings[geo_idx + 1] == "Deals & Contracts", (
        f"Expected 'Deals & Contracts' right after 'Geography', got order: {section_headings}"
    )
    ok(40, "'Deals & Contracts' section confirmed reordered directly below 'Geography'")

    # Left at defaults / skipped: Description, currencies (EUR), Goal Type
    # (None), Audience (Target Everyone), Predictive Clearing, and all the
    # optional list sections (Geography already has Spain, Deals & Contracts,
    # Device Type, Ad Environment, Publisher List, Category, Supply Vendor,
    # Contextual Keywords).


def test_ttd_recap(page: Page, campaign_name: str):
    """TEST 41-45: Recap, Start campaign (user-gated), redirect + submitted check."""
    # A summary dialog may appear here too (as on the channels step) — dismiss
    # it best-effort if it does.
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    dialog = page.locator("dv360-io-summary-dialog")
    try:
        expect(dialog).to_be_visible(timeout=2000)
        dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
        expect(dialog).not_to_be_visible()
    except AssertionError:
        pass

    # TEST 41: Recap step loaded.
    expect(page.locator("app-recap-and-validate")).to_be_visible()
    expect(
        page.locator("span.pb-5.text-4xl.font-bold", has_text="Review before creating the Campaign")
    ).to_be_visible()
    recap_step = page.locator("dx-stepper div.dx-step", has_text="Recap")
    expect(recap_step).to_have_attribute("aria-selected", "true")
    ok(41, "navigated to the Recap step ('Review before creating the Campaign')")

    # WARNING: this actually launches the TTD campaign and can't be undone —
    # it only clicks through if you type 'yes' below.
    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible()
    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES the TTD campaign. "
        "Type 'yes' to confirm the click (anything else cancels): "
    ).strip().lower()
    if answer == "yes":
        start_btn.click()
        # Surface server-side validation errors as a test failure instead of
        # passing silently.
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
        ok(42, "'Start campaign' performed, no validation-errors dialog shown")

        # TEST 43: on success the app redirects back to the campaigns list.
        page.wait_for_url("**/campaign", timeout=15000)
        assert page.url.rstrip("/") == f"{BASE_URL}/campaign", (
            f"Expected redirect to {BASE_URL}/campaign\nActual URL: {page.url}"
        )
        ok(43, f"redirected to the campaigns list ({page.url})")

        # Search to filter the list (handles pagination), then match the row
        # whose Name cell (column 1) equals the campaign name.
        grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
        expect(grid).to_be_visible()
        grid.locator("input[aria-label='Search in the data grid']").fill(campaign_name)
        campaign_row = grid.locator("tr.dx-data-row").filter(
            has=page.locator("td[aria-colindex='1']", has_text=campaign_name)
        )
        expect(campaign_row).to_have_count(1)
        expect(campaign_row).to_be_visible()
        ok(44, f"campaign '{campaign_name}' found in the campaigns table")

        # COMPLETED is the next valid state after SUBMITTED, so both pass.
        status_cell = campaign_row.locator("td[aria-colindex='9']")
        status_text = status_cell.inner_text().strip()
        assert status_text in ("SUBMITTED", "COMPLETED"), (
            f"Unexpected campaign status: '{status_text}'"
        )
        ok(45, f"campaign '{campaign_name}' is in '{status_text}' status")
    else:
        print("TEST 42 SKIPPED -> click on 'Start campaign' cancelled by the user")


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
        # no_viewport=True uses the real screen size — a small viewport
        # collapses the responsive layout (e.g. the flight row date inputs)
        # into unclickable, zero-size fields.
        browser = p.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(storage_state=storage_state, no_viewport=True)
        page = context.new_page()

        try:
            test_landing(page)              # TEST 1-3 (shared, DSP-agnostic)
            campaign_name = test_ttd_general_info(page)  # TEST 4-16
            test_ttd_global_setup(page)     # TEST 17-22
            test_ttd_campaign_channels(page)  # TEST 23-31
            test_ttd_ad_groups(page)        # TEST 32-40
            test_ttd_recap(page, campaign_name)  # TEST 41-45 (Start + submitted check)

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

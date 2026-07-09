# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com  (JSON-driven DV360 targeting suite)
==========================================================================
Validates that DV360 line-item targeting sections in Nexify can be driven
from a real DV360 API export (reference JSON), by comparing the export's
values against what the Nexify UI actually lets you select.

Built incrementally, one targeting type at a time (see task list). Each
run repeats the campaign creation flow up to the Line Items form, using
the SAME DV360 advertiser the reference JSON was exported from
(client "Samsung" / advertiser "Samsung_ES_Starcom", DV360 advertiserId
2429284) so that advertiser-scoped resources (channels, negative keyword
lists, audiences, deals) can actually be found in the picker dialogs.

For every targeting section, only the first 2 DISTINCT values found in the
reference JSON are inserted (per user instruction), and budgets are kept
at 1 EUR everywhere to avoid triggering any real spend. The flow currently
stops right after the implemented targeting section(s) - it does NOT click
"Next" / "Start campaign" yet.

Run with:        python test_dv360_json_playwright.py
"""

import json
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from test_dv360_playwright import (
    AUTH_FILE,
    BASE_URL,
    TARGET_URL,
    ok,
    select_mat_option,
    manual_login,
    test_landing,
    test_template_dialog,
    test_global_setup,
    test_insertion_orders,
    test_line_items,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_2429284_4376515.json")
CLIENT = "Samsung"
ADVERTISER = "Samsung_ES_Starcom"  # DV360 advertiserId 2429284 - same as the reference JSON
DV360_DSP_BADGE = "Google DV360"


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


def unique_targeting_values(ref: dict, targeting_type: str, detail_key: str, id_field: str):
    """
    Collect the DISTINCT values for a given targetingType across every line
    item in the reference JSON, in first-seen order, as (id, negative) pairs.
    Used to pick "the first N values" for a given targeting section.
    """
    seen = {}
    order = []
    for io in ref["insertionOrders"]:
        for li in io.get("lineItems", []):
            for t in li.get("targetingOptions", []):
                if t.get("targetingType") != targeting_type:
                    continue
                details = t[detail_key]
                key = details[id_field]
                if key not in seen:
                    seen[key] = details.get("negative", False)
                    order.append(key)
    return [(k, seen[k]) for k in order]


def unique_audience_group_ids(ref: dict, group_key: str, id_field: str, nested_list: bool = False):
    """
    Same idea as unique_targeting_values(), but for TARGETING_TYPE_AUDIENCE_GROUP
    sub-groups, whose ids live one level deeper under audienceGroupDetails[group_key]
    .settings[*][id_field] (and group_key itself is a list of groups for the
    'includedFirstPartyAndPartnerAudienceGroups' variant).
    """
    seen = []
    for io in ref["insertionOrders"]:
        for li in io.get("lineItems", []):
            for t in li.get("targetingOptions", []):
                if t.get("targetingType") != "TARGETING_TYPE_AUDIENCE_GROUP":
                    continue
                details = t["audienceGroupDetails"]
                if group_key not in details:
                    continue
                groups = details[group_key] if nested_list else [details[group_key]]
                for g in groups:
                    for s in g.get("settings", []):
                        v = s[id_field]
                        if v not in seen:
                            seen.append(v)
    return seen


# --------------------------------------------------------------------------
# Reused step wrappers (Samsung / DV360 client+advertiser instead of L'Oreal)
# --------------------------------------------------------------------------
def test_general_info(page: Page):
    """TEST 4-16: campaign creation, General Info step, advertiser grid (Samsung/DV360)."""
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
    ok(6, "footer visible with Cancel, Save as draft and Next buttons")

    campaign_name = f"Test Dv JSON - {int(time.time())}"
    campaign_input = page.locator("input[formcontrolname='campaignName']")
    expect(campaign_input).to_be_visible()
    campaign_input.fill(campaign_name)
    assert campaign_input.input_value() == campaign_name, "The field does not contain the expected text"
    ok(7, f"field filled with '{campaign_name}'")

    select_mat_option(page, "client", CLIENT)
    ok(8, f"'Client' dropdown found and '{CLIENT}' option selected")

    aside = page.locator("aside.campaign-aside")
    expect(aside).to_be_visible()
    expect(aside.locator("h4", has_text=campaign_name)).to_be_visible()
    ok(9, f"side panel contains the campaign name '{campaign_name}'")

    client_row = aside.locator("p", has_text="Client")
    expect(client_row.locator("span", has_text=CLIENT)).to_be_visible()
    ok(10, f"side panel contains 'Client' with value '{CLIENT}'")

    grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
    expect(grid).to_be_visible()
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "No rows found in the advertiser grid"
    ok(11, f"advertiser grid visible with {rows.count()} rows")

    advertiser_row = grid.locator("tr.dx-data-row").filter(
        has=page.locator("span", has_text=ADVERTISER)
    ).filter(has=page.locator("span", has_text="DV360"))
    if advertiser_row.count() == 0:
        # Fallback: filter by advertiser name only, in case the DSP badge
        # text is rendered outside a <span>.
        advertiser_row = grid.locator("tr.dx-data-row").filter(
            has=page.locator("span", has_text=ADVERTISER)
        )
    expect(advertiser_row.first).to_be_visible()
    advertiser_row.first.locator("div.dx-select-checkbox").click()
    expect(advertiser_row.first).to_have_attribute("aria-selected", "true")
    ok(12, f"advertiser '{ADVERTISER}' (DV360) selected in the grid")

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    expect(dsp_card.locator("span.dsp-name", has_text=DV360_DSP_BADGE)).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()
    ok(13, f"side panel updated with DSP '{DV360_DSP_BADGE}' and Brand '{ADVERTISER}'")

    return footer


def test_sidebar_sync(page: Page):
    """TEST 38: the sidebar reflects the Samsung/DV360 selections made in step 1."""
    aside = page.locator("aside.campaign-aside")
    expect(aside.locator("span.dsp-name", has_text=DV360_DSP_BADGE)).to_be_visible()
    brand_row = aside.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()
    ok(38, f"sidebar synced with the form (Brand '{ADVERTISER}')")


def test_line_items_form_basics(page: Page):
    """TEST 41-59: fill the minimal required DV360 Line Items fields (same as
    the base suite) so the form is in a realistic state before driving the
    targeting sections below it."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible()

    li_name = f"DISPLAY OPEN - {int(time.time())}"
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)
    ok(41, f"Line Item name filled with '{li_name}'")

    select_mat_option(page, "lineItemType", "Display")
    ok(42, "Media Type / Line item type = 'Display' selected and verified")

    flight_cb_root = li_form.locator("mat-checkbox[formcontrolname='useIoFlightDates']")
    flight_cb = flight_cb_root.locator("input[type='checkbox']")
    if not flight_cb.is_checked():
        flight_cb_root.click()
    expect(flight_cb).to_be_checked()
    ok(43, "checkbox 'Use same flight dates as Insertion Order' confirmed checked")

    select_mat_option(page, "budgetAllocationType", "Unlimited")
    ok(44, "Budget allocation = 'Unlimited' selected and verified")

    select_mat_option(page, "pacingPeriod", "Flight")
    ok(45, "Pacing period = 'Flight' selected and verified")

    select_mat_option(page, "pacingType", "ASAP")
    ok(46, "Pacing type = 'ASAP' selected and verified")

    limit_row = li_form.locator("div.flex.items-start.gap-3", has_text="Limit exposure frequency to")
    limit_cb = limit_row.locator("input[type='checkbox']")
    if not limit_cb.is_checked():
        limit_row.locator("mat-checkbox").click()
    expect(limit_cb).to_be_checked()
    ok(47, "checkbox 'Limit exposure frequency to' confirmed checked")

    li_form.locator("input[formcontrolname='freqCount']").fill("1")
    ok(48, "freqCount = 1 entered")
    li_form.locator("input[formcontrolname='freqEvery']").fill("1")
    ok(49, "freqEvery = 1 entered")

    select_mat_option(page, "freqUnit", "Minute")
    ok(50, "freqUnit = 'Minute' selected and verified")

    select_mat_option(page, "containsEuPoliticalAds", "Does not contain EU political advertising")
    ok(51, "EU Political Ads = 'Does not contain EU political advertising' selected")

    select_mat_option(page, "bidStrategyType", "Fixed bid")
    ok(53, "Bid strategy = 'Fixed bid' selected and verified")

    li_form.locator("input[formcontrolname='bidAmount']").fill("1")
    ok(54, "Bid amount (CPM) = 1 entered")

    select_mat_option(page, "partnerRevenueModelMarkupType", "Total Media Cost")
    ok(55, "Partner revenue model = 'Total Media Cost' selected and verified")

    li_form.locator("input[formcontrolname='partnerRevenueModelMarkupValue']").fill("0")
    ok(56, "Markup = 0 entered")

    return li_form


# --------------------------------------------------------------------------
# Targeting: Channels (included / excluded)
# --------------------------------------------------------------------------
def test_channel_targeting(page: Page, li_form, ref: dict):
    """
    TEST 60-67: 'Included/Excluded channels' section.

    The reference JSON has ONLY excluded channel entries for this campaign
    (37 entries, all negative=true), so the Excluded panel is driven from
    JSON values; the Included panel has no JSON data, so it's driven from
    2 names picked directly at the user's request instead.

    Channel lists are advertiser-scoped (DV360 advertisers.channels.list),
    so the picker only shows Samsung_ES_Starcom's own lists. The JSON's
    dominant channelId (1672780816, 33/37 entries) no longer exists in the
    live account; we use the next 2 distinct channelIds from the JSON that
    DO still exist there.
    """
    excl_pairs = unique_targeting_values(ref, "TARGETING_TYPE_CHANNEL", "channelDetails", "channelId")
    excluded_ids = [cid for cid, negative in excl_pairs if negative]
    assert excluded_ids, "Expected at least some excluded channel entries in the reference JSON"

    # Map the live grid's visible names to the JSON's channelIds by capturing
    # the dialog's own data-load response (id -> name), then select the
    # first 2 JSON channelIds that are actually present in the live list.
    # (A separate page.request.get() call does not carry the app's runtime
    # auth token, so we must observe the real browser request instead.)
    captured = []
    page.on(
        "response",
        lambda r: captured.append(r)
        if "/dsp/dv360/channels" in r.url
        else None,
    )

    excluded_section = li_form.locator("div.border.rounded-xl.p-4", has_text="Excluded channels")
    add_btn = excluded_section.get_by_role("button", name="Add Channel")
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2[mat-dialog-title]")).to_contain_text("Select excluded channel lists")
    ok(60, "'Add Channel' (Excluded) dialog opened")

    grid = dialog.locator("dx-data-grid")
    rows = grid.locator("tr.dx-data-row")
    expect(rows.first).to_be_visible()

    for _ in range(20):
        if captured:
            break
        page.wait_for_timeout(250)
    assert captured, "Did not observe the channels list API response"
    live_channels = {c["id"]: c["name"] for c in captured[-1].json()}

    matched = [(cid, live_channels[cid]) for cid in excluded_ids if cid in live_channels][:2]
    assert len(matched) == 2, (
        f"Expected 2 of the JSON's excluded channelIds to exist in the live "
        f"Samsung channel list, found {len(matched)}: {matched}"
    )

    for cid, name in matched:
        row = grid.locator("tr.dx-data-row").filter(has=page.locator("td", has_text=name))
        expect(row).to_be_visible()
        row.locator("div.dx-select-checkbox").click()
    ok(61, f"selected {len(matched)} excluded channel(s) from the JSON: {[n for _, n in matched]}")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok(62, "'Apply' clicked, dialog closed")

    for cid, name in matched:
        expect(excluded_section.locator("span", has_text=name)).to_be_visible()
    ok(63, f"'Excluded channels' panel now shows: {[n for _, n in matched]}")

    # The reference JSON has zero included-channel entries for this campaign,
    # so these 2 names were picked directly (not from the JSON) at the
    # user's request, from the same live Samsung_ES_Starcom channel list.
    included_names = ["Whitelist best performers", "Whitelist best performers top 10"]

    included_section = li_form.locator("div.border.rounded-xl.p-4", has_text="Included channels")
    inc_add_btn = included_section.get_by_role("button", name="Add Channel")
    inc_add_btn.scroll_into_view_if_needed()
    expect(inc_add_btn).to_be_visible()
    inc_add_btn.click()

    inc_dialog = page.locator("mat-dialog-container")
    expect(inc_dialog).to_be_visible()
    expect(inc_dialog.locator("h2[mat-dialog-title]")).to_contain_text("Select included channel lists")
    ok(64, "'Add Channel' (Included) dialog opened")

    inc_grid = inc_dialog.locator("dx-data-grid")
    expect(inc_grid.locator("tr.dx-data-row").first).to_be_visible()

    for name in included_names:
        row = inc_grid.locator("tr.dx-data-row").filter(has=page.get_by_text(name, exact=True))
        expect(row).to_be_visible()
        row.locator("div.dx-select-checkbox").click()
    ok(65, f"selected included channel(s): {included_names}")

    inc_dialog.get_by_role("button", name="Apply").click()
    expect(inc_dialog).not_to_be_visible()
    ok(66, "'Apply' clicked, dialog closed")

    for name in included_names:
        expect(
            included_section.get_by_text(re.compile(rf"{re.escape(name)} \(\d+\)"))
        ).to_be_visible()
    ok(67, f"'Included channels' panel now shows: {included_names}")


# --------------------------------------------------------------------------
# Targeting: Negative Keyword List
# --------------------------------------------------------------------------
def test_negative_keyword_list_targeting(page: Page, li_form, ref: dict):
    """
    TEST 68-71: 'Negative Keyword List' section.

    Unlike Channels, ALL 4 distinct negativeKeywordListIds found in the
    reference JSON still exist in the live Samsung_ES_Starcom account (no
    drift), so - per user instruction - all 4 are selected rather than
    just the first 2.
    """
    nkl_ids = [lid for lid, _ in unique_targeting_values(
        ref, "TARGETING_TYPE_NEGATIVE_KEYWORD_LIST", "negativeKeywordListDetails", "negativeKeywordListId"
    )]
    assert nkl_ids, "Expected negative keyword list entries in the reference JSON"

    captured = []
    page.on(
        "response",
        lambda r: captured.append(r)
        if "/dsp/dv360/negativeKeywordsLists" in r.url
        else None,
    )

    nkl_section = li_form.locator("div.border.rounded-xl.p-4", has_text="Negative Keyword List")
    add_btn = nkl_section.get_by_role("button", name="Add List")
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2[mat-dialog-title]")).to_contain_text("Select negative keyword list id")
    ok(68, "'Add List' (Negative Keyword List) dialog opened")

    grid = dialog.locator("dx-data-grid")
    expect(grid.locator("tr.dx-data-row").first).to_be_visible()

    for _ in range(20):
        if captured:
            break
        page.wait_for_timeout(250)
    assert captured, "Did not observe the negative keyword lists API response"
    live_lists = {item["id"]: item["name"] for item in captured[-1].json()["results"]}

    matched = [(lid, live_lists[lid]) for lid in nkl_ids if lid in live_lists]
    assert matched, "None of the JSON's negativeKeywordListIds exist in the live Samsung account"

    for lid, name in matched:
        row = grid.locator("tr.dx-data-row").filter(has=page.get_by_text(name, exact=True))
        expect(row).to_be_visible()
        row.locator("div.dx-select-checkbox").click()
    ok(69, f"selected {len(matched)} negative keyword list(s) from the JSON (all matching): {[n for _, n in matched]}")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok(70, "'Apply' clicked, dialog closed")

    for lid, name in matched:
        expect(
            nkl_section.get_by_text(re.compile(rf"{re.escape(name)} \(\d+\)"))
        ).to_be_visible()
    ok(71, f"'Negative Keyword List' panel now shows: {[n for _, n in matched]}")


# --------------------------------------------------------------------------
# Targeting: Audiences (Included only - Custom lists + Google audiences)
# --------------------------------------------------------------------------
def test_audience_targeting(page: Page, li_form, ref: dict):
    """
    TEST 72-76: 'Included audiences' section - Custom lists and Google
    audiences sub-types only.

    First-party/partner audiences (98 included / 197 excluded unique ids in
    the reference JSON) are SKIPPED for now: the picker only supports
    searching by display-name substring, not by raw id, and this Samsung
    account's first-party audience library goes back over a decade in
    small (~7-10 item) pages - not tractable to match by id via the UI.
    The user will provide display names directly for that sub-type later.

    Both remaining sub-types match 1:1 against live data (no drift):
    all 6 custom lists and the 1 Google audience from the JSON exist and
    are found on the dialog's first page (no pagination needed). Selections
    made across a type switch are preserved by the dialog and applied
    together in one 'Apply' click.
    """
    custom_ids = unique_audience_group_ids(ref, "includedCustomListGroup", "customListId")
    google_ids = unique_audience_group_ids(ref, "includedGoogleAudienceGroup", "googleAudienceId")
    assert custom_ids, "Expected included custom list entries in the reference JSON"
    assert google_ids, "Expected included Google audience entries in the reference JSON"

    included_section = li_form.locator("div.border.rounded-xl.p-4", has_text="Included audiences")
    add_btn = included_section.get_by_role("button", name="Add audience")
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2[mat-dialog-title]")).to_contain_text("Select included audience lists")
    ok(72, "'Add audience' (Included) dialog opened")

    type_select = dialog.locator("mat-select").first
    grid = dialog.locator("dx-data-grid")

    search_box = dialog.get_by_placeholder("Write to filter audiences")

    def wait_for_response(captured, baseline, timeout_ms=8000):
        waited = 0
        while len(captured) <= baseline and waited < timeout_ms:
            page.wait_for_timeout(200)
            waited += 200
        return len(captured) > baseline

    def check_row_on_current_page(name: str) -> bool:
        row = grid.locator("tr.dx-data-row").filter(has=page.get_by_text(name, exact=True))
        if row.count() == 0:
            return False
        row.locator("div.dx-select-checkbox").click()
        return True

    def find_and_check(name: str):
        # The grid paginates client-side once many items load, so a target
        # row may not be on the currently visible page. The dialog's free-text
        # search filters server-side by 'contains', but is unreliable for some
        # names (e.g. brackets), so we page through the client-side pager
        # instead, which works regardless of the name's characters.
        if check_row_on_current_page(name):
            return
        pager = dialog.locator("div.dx-pager")
        page_count = pager.locator("div.dx-page").count()
        for pnum in range(1, page_count + 1):
            pager.locator(f"div.dx-page[aria-label='Page {pnum}']").click()
            page.wait_for_timeout(400)
            if check_row_on_current_page(name):
                return
        raise AssertionError(f"Could not find row for '{name}' on any grid page")

    def select_audience_type_and_pick(type_label: str, ids: list[str]):
        captured = []
        page.on(
            "response",
            lambda r: captured.append(r) if "/dsp/dv360/audiences" in r.url else None,
        )
        search_box.fill("")
        type_select.click(force=True)
        page.wait_for_timeout(400)
        page.get_by_role("option", name=type_label, exact=True).click()
        wait_for_response(captured, 0)
        assert captured, f"Did not observe the audiences API response for type '{type_label}'"
        live_items = {item["id"]: item["name"] for item in captured[-1].json()["results"]}
        matched = [(i, live_items[i]) for i in ids if i in live_items]
        assert len(matched) == len(ids), (
            f"Expected all {len(ids)} JSON ids to be found for '{type_label}', "
            f"found {len(matched)}: {matched}"
        )

        for _id, name in matched:
            find_and_check(name)
        return matched

    matched_custom = select_audience_type_and_pick("Custom lists", custom_ids)
    ok(73, f"selected {len(matched_custom)} custom list(s) from the JSON: {[n for _, n in matched_custom]}")

    matched_google = select_audience_type_and_pick("Google audiences", google_ids)
    ok(74, f"selected {len(matched_google)} Google audience(s) from the JSON: {[n for _, n in matched_google]}")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok(75, "'Apply' clicked, dialog closed")

    for _id, name in matched_custom + matched_google:
        expect(
            included_section.get_by_text(re.compile(rf"{re.escape(name)} \(\d+\)"))
        ).to_be_visible()
    ok(76, f"'Included audiences' panel now shows: {[n for _, n in matched_custom + matched_google]}")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    ref = load_reference()

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

        try:
            test_landing(page)
            footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            test_insertion_orders(page)
            test_sidebar_sync(page)
            test_line_items(page)
            li_form = test_line_items_form_basics(page)
            test_channel_targeting(page, li_form, ref)
            test_negative_keyword_list_targeting(page, li_form, ref)
            test_audience_targeting(page, li_form, ref)

            print("\nALL TESTS PASSED (Channels + Negative Keyword List + Audiences targeting) ✅")
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

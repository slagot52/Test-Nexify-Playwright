# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 targeting suite)
==========================================================================
Checks that DV360 targeting sections in Nexify can be driven from a real
DV360 API export, by comparing the export's values against what the UI
actually lets you pick.

Each run repeats campaign creation up to Line Items, using the SAME
advertiser the reference JSON came from (Samsung / Samsung_ES_Starcom,
DV360 advertiserId 2429284) so advertiser-scoped pickers (channels,
negative keyword lists, audiences, deals) can find matching data.

Generally only the first 2 distinct values per section are inserted
(exceptions are called out in each function's docstring), and budgets
stay at 1 EUR to avoid real spend. The flow stops after targeting — it
does not yet click "Next" / "Start campaign".

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


def select_mat_option_on(page: Page, select, option_name: str):
    """Same mechanics as select_mat_option(), but takes an already-resolved
    locator instead of a formcontrolname — needed for day-time-selector rows,
    whose mat-selects use (selectionChange) handlers, not reactive forms."""
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
        raise AssertionError(f"Could not open the mat-select '{option_name}'")

    panel = page.locator(f"#{select_id}-panel").first
    expect(panel).to_be_visible()
    option = panel.get_by_role("option", name=option_name, exact=True)
    expect(option).to_be_visible()
    option.click()

    try:
        expect(select).to_contain_text(option_name, timeout=3000)
    except AssertionError:
        if select.get_attribute("aria-expanded") == "true":
            option.click()
        expect(select).to_contain_text(option_name)


def unique_targeting_values(ref: dict, targeting_type: str, detail_key: str, id_field: str):
    """Collect distinct (id, negative) pairs for a targetingType across every
    line item in the reference JSON, in first-seen order."""
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
    """Same idea as unique_targeting_values(), but for audience-group
    sub-groups, whose ids live one level deeper at
    audienceGroupDetails[group_key].settings[*][id_field]."""
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
    """TEST 60-67: 'Included/Excluded channels' section.

    The JSON only has excluded entries (37, all negative), so Excluded is
    driven from JSON data while Included uses 2 names picked directly (no
    JSON data exists for it). Channel lists are advertiser-scoped, so the
    picker only shows Samsung_ES_Starcom's lists — the JSON's dominant
    channelId no longer exists there, so we use the next 2 that do.
    """
    excl_pairs = unique_targeting_values(ref, "TARGETING_TYPE_CHANNEL", "channelDetails", "channelId")
    excluded_ids = [cid for cid, negative in excl_pairs if negative]
    assert excluded_ids, "Expected at least some excluded channel entries in the reference JSON"

    # Capture the dialog's own data-load response (id -> name) to map JSON
    # channelIds to live names — a separate page.request.get() wouldn't
    # carry the app's auth token, so we observe the real browser request.
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

    # No included-channel entries in the JSON, so these 2 names were picked
    # directly from the live Samsung_ES_Starcom channel list instead.
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
    """TEST 68-71: 'Negative Keyword List' section.

    Unlike Channels, all 4 JSON negativeKeywordListIds still exist live
    (no drift), so all 4 get selected instead of just the first 2.
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
    """TEST 72-76: 'Included audiences' — Custom lists and Google audiences
    sub-types only.

    First-party/partner audiences are skipped for now: the picker only
    searches by display-name substring, and this account's first-party
    library is too large/paged to match reliably by id. Names for that
    sub-type will be supplied directly later.

    The two remaining sub-types match 1:1 against live data, located via
    the dialog's search box (server-side filter, faster than paging).
    Selections persist across a type switch and get applied together.
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

    def search_term_candidates(name: str):
        # Server-side search does 'contains' on the raw name, which fails for
        # prefixed names like '[In-Market] : Televisions' — fall back to
        # just the part after the last ':'.
        candidates = [name]
        if ":" in name:
            tail = name.split(":")[-1].strip()
            if tail and tail not in candidates:
                candidates.append(tail)
        return candidates

    def find_and_check(_id: str, name: str, captured: list):
        for term in search_term_candidates(name):
            baseline = len(captured)
            search_box.fill(term)
            search_box.press("Enter")
            wait_for_response(captured, baseline)
            if not captured:
                continue
            results = captured[-1].json()["results"]
            # Match by position, not name text — names aren't guaranteed unique.
            idx = next((i for i, item in enumerate(results) if item["id"] == _id), None)
            if idx is None:
                continue
            row = grid.locator("tr.dx-data-row").nth(idx)
            expect(row).to_be_visible()
            row.locator("div.dx-select-checkbox").click()
            return
        raise AssertionError(f"Could not find '{name}' (id {_id}) via search, tried: {search_term_candidates(name)}")

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
            find_and_check(_id, name, captured)
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
# Targeting: Geo Regions (included / excluded)
# --------------------------------------------------------------------------
def test_geo_region_targeting(page: Page, li_form, ref: dict):
    """TEST 77-80: 'Included/Excluded geo regions' section.

    Geo regions are DV360's global taxonomy (not advertiser-scoped), so all
    7 JSON ids are expected to exist and all get selected — 3 excluded, 4
    included, per the JSON's 'negative' flag.

    Unlike Channels/Negative Keyword List, this picker only fetches once you
    search, so each id is looked up by its JSON displayName one at a time.
    """
    pairs = unique_targeting_values(ref, "TARGETING_TYPE_GEO_REGION", "geoRegionDetails", "targetingOptionId")
    excluded_ids = [gid for gid, negative in pairs if negative]
    included_ids = [gid for gid, negative in pairs if not negative]
    assert excluded_ids and included_ids, "Expected both included and excluded geo regions in the reference JSON"

    json_name_by_id = {}
    for io in ref["insertionOrders"]:
        for li in io.get("lineItems", []):
            for t in li.get("targetingOptions", []):
                if t.get("targetingType") == "TARGETING_TYPE_GEO_REGION":
                    d = t["geoRegionDetails"]
                    json_name_by_id.setdefault(d["targetingOptionId"], d["displayName"])

    def add_geo(button_name: str, dialog_title: str, ids: list[str]):
        section = li_form.locator("div.border.rounded-xl.p-4").filter(
            has=page.get_by_role("button", name=button_name)
        )
        add_btn = section.get_by_role("button", name=button_name)
        add_btn.scroll_into_view_if_needed()
        expect(add_btn).to_be_visible()
        add_btn.click()

        dialog = page.locator("mat-dialog-container")
        expect(dialog).to_be_visible()
        expect(dialog.locator("h2[mat-dialog-title]")).to_contain_text(dialog_title)

        grid = dialog.locator("dx-data-grid")
        search_box = dialog.get_by_placeholder("Write to filter")

        matched = []
        for gid in ids:
            query = json_name_by_id[gid]
            captured = []
            page.on(
                "response",
                lambda r: captured.append(r) if "/dsp/dv360/regions" in r.url.lower() else None,
            )
            search_box.fill(query)
            search_box.press("Enter")
            for _ in range(20):
                if captured:
                    break
                page.wait_for_timeout(250)
            assert captured, f"Did not observe the geo region API response for query '{query}'"
            results = captured[-1].json()["results"]
            # Match by position, not a name->id dict — geo names can collide
            # (e.g. two different ids sharing the same display name).
            idx = next((i for i, item in enumerate(results) if item["id"] == gid), None)
            assert idx is not None, (
                f"JSON geo id {gid} ('{query}') not found in live search results: {results}"
            )
            name = results[idx]["name"]
            row = grid.locator("tr.dx-data-row").nth(idx)
            expect(row).to_be_visible()
            expect(row).to_contain_text(name)
            row.locator("div.dx-select-checkbox").click()
            matched.append((gid, name))

        dialog.get_by_role("button", name="Apply").click()
        expect(dialog).not_to_be_visible()
        return matched, section

    matched_excl, excl_section = add_geo("Add excluded geo", "Select excluded geo regions", excluded_ids)
    ok(77, f"'Add excluded geo' dialog driven, selected {len(matched_excl)}: {[n for _, n in matched_excl]}")

    for gid, name in matched_excl:
        # Some geo names are substrings of others, so match name+id
        # together rather than name alone.
        expect(
            excl_section.get_by_text(re.compile(rf"{re.escape(name)} \({gid}\)"))
        ).to_be_visible()
    ok(78, f"'Excluded geo regions' panel now shows: {[n for _, n in matched_excl]}")

    matched_incl, incl_section = add_geo("Add included geo", "Select included geo regions", included_ids)
    ok(79, f"'Add included geo' dialog driven, selected {len(matched_incl)}: {[n for _, n in matched_incl]}")

    for gid, name in matched_incl:
        expect(
            incl_section.get_by_text(re.compile(rf"{re.escape(name)} \({gid}\)"))
        ).to_be_visible()
    ok(80, f"'Included geo regions' panel now shows: {[n for _, n in matched_incl]}")


# --------------------------------------------------------------------------
# Targeting: URLs (included / excluded)
# --------------------------------------------------------------------------
def test_url_targeting(page: Page, li_form, ref: dict):
    """TEST 81-82: 'Included/Excluded URLs' section.

    Plain comma-separated text fields, no picker dialog. All 3 excluded
    urls from the JSON go in directly; there are no included urls, so that
    field stays empty.
    """
    pairs = unique_targeting_values(ref, "TARGETING_TYPE_URL", "urlDetails", "url")
    excluded_urls = [u for u, negative in pairs if negative]
    included_urls = [u for u, negative in pairs if not negative]
    assert excluded_urls, "Expected excluded url entries in the reference JSON"
    assert not included_urls, "Did not expect included url entries in the reference JSON"

    excluded_field = li_form.locator("textarea[formcontrolname='excludedUrlIds']")
    excluded_field.fill(", ".join(excluded_urls))
    assert excluded_field.input_value() == ", ".join(excluded_urls)
    ok(81, f"'Excluded URLs' filled with the JSON's {len(excluded_urls)} url(s): {excluded_urls}")

    included_field = li_form.locator("textarea[formcontrolname='includedUrlIds']")
    assert included_field.input_value() == "", "'Included URLs' expected to stay empty (no JSON data)"
    ok(82, "'Included URLs' left empty (no included entries in the reference JSON)")


# --------------------------------------------------------------------------
# Targeting: Keywords (included / excluded)
# --------------------------------------------------------------------------
def test_keyword_targeting(page: Page, li_form, ref: dict):
    """TEST 83-84: 'Included/Exclude Keywords' section.

    Same plain-text mechanics as URLs. All 225 included and all 5 excluded
    keywords from the JSON go in — no picker involved, so no reason to cap it.
    """
    pairs = unique_targeting_values(ref, "TARGETING_TYPE_KEYWORD", "keywordDetails", "keyword")
    included_keywords = [k for k, negative in pairs if not negative]
    excluded_keywords = [k for k, negative in pairs if negative]
    assert included_keywords, "Expected included keyword entries in the reference JSON"
    assert excluded_keywords, "Expected excluded keyword entries in the reference JSON"

    included_field = li_form.locator("textarea[formcontrolname='includedKeywordIds']")
    included_field.fill(", ".join(included_keywords))
    assert included_field.input_value() == ", ".join(included_keywords)
    ok(83, f"'Included Keywords' filled with all {len(included_keywords)} keyword(s) from the JSON")

    excluded_field = li_form.locator("textarea[formcontrolname='excludedKeywordIds']")
    excluded_field.fill(", ".join(excluded_keywords))
    assert excluded_field.input_value() == ", ".join(excluded_keywords)
    ok(84, f"'Exclude Keywords' filled with all {len(excluded_keywords)} keyword(s) from the JSON: {excluded_keywords}")


# --------------------------------------------------------------------------
# Targeting: Categories (included / excluded)
# --------------------------------------------------------------------------
def test_category_targeting(page: Page, li_form, ref: dict):
    """TEST 85-89: 'Categories' section — one 'Manage' dialog with a tree UI
    (Include/Exclude buttons per node), not two separate pickers.

    Categories are DV360's global taxonomy, so no advertiser-drift risk.

    KNOWN NEXIFY LIMITATION: ids 54 and 82 are ancestor/descendant of each
    other and both excluded in the JSON, but Nexify's dialog locks a node's
    buttons once an ancestor is already excluded — so both can't be set
    through this UI even though DV360 allows it. We drop 54 (the broader
    parent) and keep 82 (the specific child): 11 of the 12 excluded
    categories get selected.
    """
    pairs = unique_targeting_values(ref, "TARGETING_TYPE_CATEGORY", "categoryDetails", "targetingOptionId")
    included_ids = [c for c, negative in pairs if not negative]
    excluded_ids = [c for c, negative in pairs if negative and c != "54"]
    assert included_ids, "Expected included category entries in the reference JSON"
    assert excluded_ids, "Expected excluded category entries in the reference JSON"

    name_by_id = {}
    for io in ref["insertionOrders"]:
        for li in io.get("lineItems", []):
            for t in li.get("targetingOptions", []):
                if t.get("targetingType") == "TARGETING_TYPE_CATEGORY":
                    d = t["categoryDetails"]
                    name_by_id.setdefault(d["targetingOptionId"], d["displayName"])

    def depth(cid):
        return len(name_by_id[cid].strip("/").split("/"))

    included_ids.sort(key=depth)
    excluded_ids.sort(key=depth)

    manage_btn = li_form.get_by_role("button", name="Manage")
    manage_btn.scroll_into_view_if_needed()
    expect(manage_btn).to_be_visible()
    manage_btn.click()

    dialog = page.locator("div.dialog")
    expect(dialog).to_be_visible()
    ok(85, "Categories 'Manage' dialog opened")

    search = dialog.get_by_placeholder("Search categories")

    def set_category(cid: str, action: str):
        display_name = name_by_id[cid]
        leaf_query = display_name.rstrip("/").split("/")[-1]
        target_title = " › ".join(display_name.strip("/").split("/"))

        search.fill(leaf_query)
        search.press("Enter")
        page.wait_for_timeout(600)

        target_row = dialog.get_by_title(target_title, exact=True)
        for _ in range(10):
            if target_row.count() > 0 and target_row.first.is_visible():
                break
            # Only click toggles still showing 'chevron_right' (collapsed).
            # ":visible".first alone always re-matches the same topmost node
            # regardless of expand state, so it'd just toggle it shut again.
            toggle = dialog.locator("button[aria-label^='Toggle ']:visible").filter(has_text="chevron_right").first
            if toggle.count() == 0:
                break
            toggle.click()
            page.wait_for_timeout(300)

        expect(target_row.first).to_be_visible()
        row_container = target_row.first.locator("xpath=ancestor::div[contains(@class,'row')][1]")
        row_container.locator(f"button[aria-label='{action}']").click()

    for cid in included_ids:
        set_category(cid, "Include")
    ok(86, f"selected {len(included_ids)} categor{'y' if len(included_ids)==1 else 'ies'} to Include: {[name_by_id[c] for c in included_ids]}")

    for cid in excluded_ids:
        set_category(cid, "Exclude")
    ok(87, f"selected {len(excluded_ids)} categories to Exclude: {[name_by_id[c] for c in excluded_ids]}")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok(88, "'Apply' clicked, Categories dialog closed")

    cat_section = li_form.locator("section", has_text="Categories")
    for cid in included_ids + excluded_ids:
        # The panel renders the same breadcrumb ('A › B › C') format used
        # by the dialog's title attributes, not the JSON's '/A/B/C' format.
        breadcrumb = " › ".join(name_by_id[cid].strip("/").split("/"))
        expect(cat_section.get_by_text(breadcrumb, exact=True)).to_be_visible()
    ok(89, f"Categories panel shows all {len(included_ids) + len(excluded_ids)} selected categories")


# --------------------------------------------------------------------------
# Targeting: Day & Time
# --------------------------------------------------------------------------
def test_day_time_targeting(page: Page, li_form):
    """TEST 90-91: 'Day & time' section (<day-time-selector> — each row's 3
    mat-selects use (selectionChange) handlers, not formcontrolname).

    The JSON's 43 unique combos are aggregated across all 33 line items, not
    representative of any single one. Instead we use the full 7-row schedule
    from the JSON's smallest line item (every day, 6:00 AM - 12:00 AM).
    """
    rows_data = [
        ("Monday", "6:00 AM", "12:00 AM"),
        ("Tuesday", "6:00 AM", "12:00 AM"),
        ("Wednesday", "6:00 AM", "12:00 AM"),
        ("Thursday", "6:00 AM", "12:00 AM"),
        ("Friday", "6:00 AM", "12:00 AM"),
        ("Saturday", "6:00 AM", "12:00 AM"),
        ("Sunday", "6:00 AM", "12:00 AM"),
    ]

    selector = li_form.locator("day-time-selector")
    selector.scroll_into_view_if_needed()
    add_row_btn = selector.get_by_role("button", name="Add row")

    for i, (day, start, end) in enumerate(rows_data):
        add_row_btn.click()
        row = selector.locator("div.day-time-row").nth(i)
        expect(row).to_be_visible()
        row.scroll_into_view_if_needed()

        select_mat_option_on(page, row.locator("mat-select").nth(0), day)
        select_mat_option_on(page, row.locator("mat-select").nth(1), start)
        select_mat_option_on(page, row.locator("mat-select").nth(2), end)
    ok(90, f"added {len(rows_data)} day & time rows (every day, 6:00 AM – 12:00 AM, from the JSON's smallest line item schedule)")

    rows = selector.locator("div.day-time-row")
    expect(rows).to_have_count(len(rows_data))
    for i, (day, start, end) in enumerate(rows_data):
        row = rows.nth(i)
        expect(row.locator("mat-select").nth(0)).to_contain_text(day)
        expect(row.locator("mat-select").nth(1)).to_contain_text(start)
        expect(row.locator("mat-select").nth(2)).to_contain_text(end)
    ok(91, f"'Day & time' section shows all {len(rows_data)} rows with the expected values")


# --------------------------------------------------------------------------
# Finish: Next -> Recap -> Start campaign
# --------------------------------------------------------------------------
def test_finish_and_submit(page: Page):
    """TEST 92-93: 'Next' from Line Items to Recap, then attempt 'Start
    campaign'. Same safety gate as the base suite — this actually launches a
    real campaign, so it only clicks through if you type 'yes'.
    """
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok(92, "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)
    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES the campaign on Samsung's live "
        "DV360 account. Type 'yes' to confirm the click (anything else cancels): "
    ).strip().lower()
    if answer == "yes":
        start_btn.click()
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
        ok(93, "'Start campaign' performed, no validation-errors dialog shown")
    else:
        print("TEST 93 SKIPPED -> click on 'Start campaign' cancelled by the user")


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
            test_geo_region_targeting(page, li_form, ref)
            test_url_targeting(page, li_form, ref)
            test_keyword_targeting(page, li_form, ref)
            test_category_targeting(page, li_form, ref)
            test_day_time_targeting(page, li_form)
            test_finish_and_submit(page)

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

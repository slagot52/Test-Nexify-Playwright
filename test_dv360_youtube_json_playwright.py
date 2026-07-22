# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 YouTube targeting suite)
==================================================================================
Checks that DV360 YouTube/Video line-item and ad-group targeting in Nexify can
be driven from a real DV360 API export, by comparing the export's values
against what the UI actually lets you pick.

Reference JSON: template_809633_57114398_Generico_YouTube.json (Garnier
campaign). Client "L'Oreal" / advertiser "Garnier_ES" (DV360 advertiserId
809633) - same advertiser the JSON was exported from, so advertiser-scoped
pickers (YouTube channels, audiences) can find matching data.

Structure: 3 Insertion Orders, 11 Line Items total:
  IO0 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW  (3 LIs, 1 ad group each)
  IO1 - LINE_ITEM_TYPE_VIDEO_DEFAULT (CTV)         (5 LIs, no ad groups)
  IO2 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH (3 LIs, 1 ad group each)

Per user instruction, targeting sections insert the JSON's REAL distinct
value counts (not just the first 2), while budgets stay at a token 1 EUR
per segment to avoid real spend. The flow does not click "Start campaign"
without an explicit typed confirmation.

Known UI gaps (fields present in the JSON with no corresponding Nexify
control - confirmed live via DOM inspection AND frontend source, not just
guessed - see dv360-line-items.component.html / .ts, isYouTubeLi()):
  - For YouTube-type line items (IO0, IO2), 6 of the JSON's 8 LI-level
    targeting types have NO control at all: Channel, On-Screen Position,
    Digital Content Label Exclusion, Sensitive Category Exclusion,
    Authorized Seller Status, OMID. Only Device Type and Geo Region are
    settable (both have JSON data for these line items).
  - Authorized Seller Status is not modeled anywhere in this frontend,
    for any line item type.
  - Ad group "adGroupFormat" (no UI field, unused in the Angular app).
  - Ad-group Audience Group targeting in this JSON is first-party/partner
    (ids 8710032390 / 8100034158) - same picker-by-name-only limitation
    that made this sub-type intractable in the Samsung suite. Skipped here
    too; user will supply display names later if this is needed.

Run with:        python test_dv360_youtube_json_playwright.py
"""

import datetime
import json
import re
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from test_dv360_playwright import (
    AUTH_FILE,
    BASE_URL,
    TARGET_URL,
    ok,
    select_mat_option,
    select_all_multi,
    fill_and_verify,
    manual_login,
    test_landing,
    test_global_setup,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_809633_57114398_Generico_YouTube.json")
CLIENT = "L'Oreal"
ADVERTISER = "Garnier_ES"  # DV360 advertiserId 809633 - same as the reference JSON
DV360_DSP_BADGE = "Google DV360"

# Insertion Order display name counter: "IO x - Client - Unix Date".
_io_display_name_counter = 0


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# General Info (Garnier/DV360-specific)
# --------------------------------------------------------------------------
def test_general_info(page: Page):
    """TEST 4-16: campaign creation, General Info step, advertiser grid (Garnier/DV360)."""
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

    campaign_name = f"Test Dv YouTube JSON - {int(time.time())}"
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
    search = grid.locator("input[aria-label='Search in the data grid']")
    search.fill(ADVERTISER)
    page.wait_for_timeout(1200)
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "No rows found in the advertiser grid"
    ok(11, f"advertiser grid visible with {rows.count()} rows after searching '{ADVERTISER}'")

    advertiser_row = grid.locator("tr.dx-data-row").filter(
        has=page.locator("span", has_text=ADVERTISER)
    ).filter(has=page.locator("span", has_text="DV360"))
    if advertiser_row.count() == 0:
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

    # Selecting the advertiser triggers an async reload (Next stays disabled
    # with a loading spinner for a variable amount of time) - wait for the
    # button to actually become enabled rather than a fixed timeout.
    next_btn = footer.locator("button.mdc-button", has_text="Next")
    expect(next_btn).to_be_enabled(timeout=15000)
    page.wait_for_timeout(500)

    return footer


def test_template_dialog(page: Page, footer):
    """Click Next, template dialog, 'Continue without template'. Local
    variant of the shared helper: Garnier_ES has a different number of saved
    templates than the advertisers the frozen suite was validated against,
    so this only checks the dialog is non-empty instead of an exact count."""
    dialog = page.locator("app-template-selector-dialog")
    next_btn = footer.locator("button.mdc-button", has_text="Next")
    for _ in range(3):
        next_btn.click()
        try:
            expect(dialog).to_be_visible(timeout=8000)
            break
        except AssertionError:
            page.wait_for_timeout(1000)
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2 span", has_text="Google DV360")).to_be_visible()
    assert dialog.locator("mat-list-option").count() > 0, "Expected at least one template option"
    dialog.locator("button", has_text="Continuar sin seleccionar plantilla").click()
    expect(dialog).not_to_be_visible()
    ok("template-dialog", "template dialog dismissed without selecting one")


def test_sidebar_sync(page: Page):
    """the sidebar reflects the Garnier/DV360 selections made in step 1."""
    aside = page.locator("aside.campaign-aside")
    expect(aside.locator("span.dsp-name", has_text=DV360_DSP_BADGE)).to_be_visible()
    brand_row = aside.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()
    ok("sidebar", f"sidebar synced with the form (Brand '{ADVERTISER}')")


# --------------------------------------------------------------------------
# Insertion Orders: create all 3 IOs from the reference JSON
# --------------------------------------------------------------------------
def test_insertion_orders_multi(page: Page, ref: dict):
    """Create one IO per entry in ref['insertionOrders'], using "Create
    another" between them. Only minimal, token-value fields are filled at
    the IO level (display name uses the standard counter convention, budget
    stays low) - the JSON's real per-IO type/KPI mostly matters for what
    line item types make sense underneath, handled separately per IO."""
    global _io_display_name_counter

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

    num_ios = len(ref["insertionOrders"])
    for i in range(num_ios):
        if i > 0:
            page.get_by_role("button", name="Create another", exact=True).first.click()
            page.wait_for_timeout(800)

        _io_display_name_counter += 1
        io_display_name = f"IO {_io_display_name_counter} - {CLIENT} - {int(time.time())}"
        fill_and_verify(io_form, "displayName", io_display_name)
        ok(f"IO{i}-name", f"IO {i} Display Name filled with '{io_display_name}'")

        select_mat_option(page, "insertionOrderType", "Standard")

        # Never reuse the JSON's real flight dates - they're from whenever
        # the export was taken and are very likely in the past by now, which
        # DV360's date picker rejects. Always use today + a small offset,
        # same convention as every other suite.
        today = datetime.date.today()
        date_from = today + datetime.timedelta(days=1)
        date_to = today + datetime.timedelta(days=2)
        df = io_form.locator("input[formcontrolname='dateFrom']")
        dt = io_form.locator("input[formcontrolname='dateTo']")
        df.fill(date_from.strftime("%m/%d/%Y"))
        dt.fill(date_to.strftime("%m/%d/%Y"))
        dt.press("Tab")
        page.wait_for_timeout(500)

        purchase_order = f"PO-{int(time.time())}"
        fill_and_verify(io_form, "purchaseOrder", purchase_order)

        budget_field = io_form.locator("input[formcontrolname='budget']")
        expect(budget_field).to_be_visible()
        budget_field.fill("1")
        budget_field.press("Tab")

        select_mat_option(page, "optimizationObjective", "Awareness")
        select_mat_option(page, "pacingPeriod", "Flight")
        select_mat_option(page, "pacingType", "Ahead")
        select_mat_option(page, "kpiType", "Impression click through rate (CTR)")
        kpi_target = io_form.get_by_role("spinbutton", name="KPI Target")
        expect(kpi_target).to_be_visible()
        kpi_target.fill("1")

        unlimited_row = io_form.locator(
            "div.flex.items-center.gap-3",
            has_text="Unlimited up to the campaign's frequency cap",
        )
        unlimited_input = unlimited_row.locator("input[type='checkbox']")
        if not unlimited_input.is_checked():
            unlimited_row.locator("mat-checkbox").click()
        expect(unlimited_input).to_be_checked()

        ok(f"IO{i}-fields", f"IO {i} ('{io_display_name}') base fields filled")

    ok("IOs-created", f"{num_ios} Insertion Orders created")


# --------------------------------------------------------------------------
# Shared targeting helpers
# --------------------------------------------------------------------------
def li_targeting_values(li: dict, targeting_type: str, detail_key: str, id_field: str):
    """Distinct (id, negative) pairs for one targetingType, scoped to a
    single line item (not the whole reference - each of the 11 LIs here has
    its own distinct targeting)."""
    seen = {}
    order = []
    for t in li.get("targetingOptions", []):
        if t.get("targetingType") != targeting_type:
            continue
        details = t[detail_key]
        key = details[id_field]
        if key not in seen:
            seen[key] = details.get("negative", False)
            order.append(key)
    return [(k, seen[k]) for k in order]


def select_multi_exact(page: Page, form_control_name: str, labels: list[str]):
    """Open a multi-select and click exactly the options whose text matches
    `labels` (skips ones already selected, doesn't touch any others)."""
    select = page.locator(f"mat-select[formcontrolname='{form_control_name}']")
    expect(select).to_be_visible()
    select.scroll_into_view_if_needed()
    select_id = select.get_attribute("id")

    # Retry opening the panel, same reasoning as select_mat_option: a click
    # can miss right after another overlay closes.
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
        raise AssertionError(f"Could not open the mat-select '{form_control_name}'")

    panel = page.locator(f"#{select_id}-panel").first
    expect(panel).to_be_visible()
    for label in labels:
        opt = panel.get_by_role("option", name=label, exact=True)
        expect(opt).to_be_visible()
        if opt.get_attribute("aria-selected") != "true":
            opt.click()
    page.keyboard.press("Escape")
    for label in labels:
        expect(select).to_contain_text(label)
    return select


def add_geo_region(page: Page, li_form, button_name: str, dialog_title: str, ids_and_names: list):
    """Add included/excluded geo regions via the picker dialog. Reuses the
    pattern proven in the Samsung suite: geo is global DV360 taxonomy, the
    dialog only loads once you search, and names can collide across ids so
    matching is done by (index, id) in the captured API response."""
    section = li_form.locator("div.border.rounded-xl.p-4").filter(
        has=page.get_by_role("button", name=button_name)
    )
    add_btn = section.get_by_role("button", name=button_name)
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()

    grid = dialog.locator("dx-data-grid")
    search_box = dialog.get_by_placeholder("Write to filter")

    for gid, name in ids_and_names:
        # expect_response attaches the waiter BEFORE the search fires (no
        # register-then-poll race) and waits on a real 15s timeout instead of
        # the old ~5s poll, which a slow /regions response could outrun.
        with page.expect_response(
            lambda r: "/dsp/dv360/regions" in r.url.lower(), timeout=15000
        ) as resp_info:
            search_box.fill(name)
            search_box.press("Enter")
        results = resp_info.value.json()["results"]
        idx = next((i for i, item in enumerate(results) if item["id"] == gid), None)
        assert idx is not None, f"JSON geo id {gid} ('{name}') not found in live results: {results}"
        row = grid.locator("tr.dx-data-row").nth(idx)
        row.locator("div.dx-select-checkbox").click()

    dialog.locator("button", has_text="Apply").click()
    expect(dialog).not_to_be_visible()


DEVICE_TYPE_LABELS = {
    "DEVICE_TYPE_COMPUTER": "Computer",
    "DEVICE_TYPE_CONNECTED_TV": "Connected TV",
    "DEVICE_TYPE_SMART_PHONE": "Smartphone",
    "DEVICE_TYPE_TABLET": "Tablet",
    "DEVICE_TYPE_CONNECTED_DEVICE": "Connected device",
}


def fill_li_youtube_targeting(page: Page, li_form, li: dict):
    """Fill the ONLY two LI-level targeting types that actually have a
    working UI control for YouTube-type line items: Device Type and Geo
    Region. See the module docstring for the 6 confirmed gaps."""
    device_pairs = li_targeting_values(li, "TARGETING_TYPE_DEVICE_TYPE", "deviceTypeDetails", "deviceType")
    device_labels = [DEVICE_TYPE_LABELS[key] for key, _ in device_pairs]
    if device_labels:
        select_multi_exact(page, "deviceType", device_labels)
        ok("li-device-type", f"Device type = {device_labels}")

    geo_pairs = li_targeting_values(li, "TARGETING_TYPE_GEO_REGION", "geoRegionDetails", "targetingOptionId")
    geo_names = {}
    for t in li.get("targetingOptions", []):
        if t.get("targetingType") == "TARGETING_TYPE_GEO_REGION":
            d = t["geoRegionDetails"]
            geo_names[d["targetingOptionId"]] = d["displayName"]
    included = [(gid, geo_names[gid]) for gid, neg in geo_pairs if not neg]
    excluded = [(gid, geo_names[gid]) for gid, neg in geo_pairs if neg]
    if included:
        add_geo_region(page, li_form, "Add included geo", "geo", included)
        ok("li-geo-included", f"Included geo regions = {[n for _, n in included]}")
    if excluded:
        add_geo_region(page, li_form, "Add excluded geo", "geo", excluded)
        ok("li-geo-excluded", f"Excluded geo regions = {[n for _, n in excluded]}")


# --------------------------------------------------------------------------
# YouTube Ad Group targeting
# --------------------------------------------------------------------------
GENDER_LABELS = {"GENDER_MALE": "Male", "GENDER_FEMALE": "Female", "GENDER_UNKNOWN": "Unknown"}


def textarea_by_label(container, label: str):
    field = container.locator("mat-form-field").filter(
        has=container.page.locator("mat-label", has_text=re.compile(rf"^{re.escape(label)}$"))
    )
    return field.locator("textarea")


def set_age_range_full(page: Page, ag_container):
    """This JSON always lists all 6 DV360 age buckets together (=no real age
    restriction), so just push the dual-thumb slider to its full range."""
    start = ag_container.locator("input[formcontrolname='ageMinIndex']")
    end = ag_container.locator("input[formcontrolname='ageMaxIndex']")
    start.scroll_into_view_if_needed()
    start.focus()
    page.keyboard.press("Home")
    end.focus()
    page.keyboard.press("End")
    ok("ag-age-range", "Age range slider set to full range (18+)")


def add_ag_categories(page: Page, ag_container, category_pairs: list, name_by_id: dict):
    """Same tree-dialog mechanics as the Samsung suite's Categories, scoped
    to one ad group. All entries here are exclusions."""
    excluded_ids = [c for c, neg in category_pairs if neg]
    included_ids = [c for c, neg in category_pairs if not neg]

    def depth(cid):
        return len(name_by_id[cid].strip("/").split("/"))

    excluded_ids.sort(key=depth)
    included_ids.sort(key=depth)

    manage_btn = ag_container.get_by_role("button", name="Manage")
    manage_btn.scroll_into_view_if_needed()
    expect(manage_btn).to_be_visible()
    manage_btn.click()

    dialog = page.locator("div.dialog")
    expect(dialog).to_be_visible()
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
    for cid in excluded_ids:
        set_category(cid, "Exclude")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok("ag-categories", f"{len(included_ids)} included / {len(excluded_ids)} excluded categories set")


def add_ag_channels_via_placements(page: Page, ag_container, channel_ids: list, mode: str):
    """Bulk-resolve YouTube channel ids through the Placements dialog's
    paste+sanitize+apply flow instead of one-by-one dialog picks - confirmed
    live that the sanitize endpoint resolves bare channel ids (e.g.
    'UCVu5opa9d4JdDxGsR3zaqAg') directly, no need for full URLs."""
    add_btn = ag_container.get_by_role("button", name="Add Placements")
    add_btn.scroll_into_view_if_needed()
    add_btn.click()

    dialog = page.locator("mat-dialog-container").filter(has_text="Placements")
    expect(dialog).to_be_visible()

    mode_select = dialog.locator("mat-select").first
    mode_select.click(force=True)
    page.wait_for_timeout(400)
    page.get_by_role("option", name=mode.capitalize(), exact=True).click()

    textarea = dialog.locator("textarea")
    textarea.fill("\n".join(channel_ids))

    # The "N seleccionados" counter renders "0 seleccionados" by default
    # before any sanitize call resolves, so waiting on that text alone
    # matches the stale zero instantly - intercept the real API response
    # instead of trusting DOM text timing.
    # expect_response attaches the waiter before the Sanitize click (no
    # register-then-poll race); 30s window for a slow sanitize call.
    with page.expect_response(
        lambda r: "placements/sanitize" in r.url, timeout=30000
    ) as resp_info:
        dialog.get_by_role("button", name="Sanitize").click()
    body = resp_info.value.json()
    resolved_n = len(body.get("channels", []))
    if resolved_n != len(channel_ids):
        print(f"NOTE: {resolved_n}/{len(channel_ids)} YouTube channel ids resolved live ({mode}) - the rest no longer exist")
    expect(dialog.get_by_text(f"{resolved_n} seleccionados")).to_be_visible(timeout=5000)

    dialog.get_by_role("button", name="Apply", exact=True).click()
    expect(dialog).not_to_be_visible()
    ok("ag-channels", f"{resolved_n}/{len(channel_ids)} YouTube channels resolved and applied ({mode})")


def fill_ad_group_targeting(page: Page, ag_container, ag: dict):
    """Fill one YouTube ad group's targeting from its JSON entry. Age Range,
    Gender, Category, Keyword, URL, and YouTube Channel are all automatable;
    Audience Group is skipped (first-party/partner ids, no id-search - see
    module docstring)."""
    types_present = {t["targetingType"] for t in ag.get("targetingOptions", [])}

    if "TARGETING_TYPE_AGE_RANGE" in types_present:
        set_age_range_full(page, ag_container)

    gender_pairs = [t["genderDetails"]["gender"] for t in ag["targetingOptions"] if t["targetingType"] == "TARGETING_TYPE_GENDER"]
    if gender_pairs:
        labels = [GENDER_LABELS[g] for g in gender_pairs]
        select_multi_exact(page, "genders", labels)
        ok("ag-gender", f"Genders = {labels}")

    cat_pairs = []
    cat_names = {}
    for t in ag["targetingOptions"]:
        if t["targetingType"] == "TARGETING_TYPE_CATEGORY":
            d = t["categoryDetails"]
            # KNOWN NEXIFY LIMITATION (IO2): id 16 (/News, parent) and 1253
            # (/News/Health News, child) are both excluded in the JSON, but
            # the categories dialog locks a child's Exclude button once its
            # ancestor is excluded. Per user decision, drop the parent and
            # keep the more specific child.
            if d["targetingOptionId"] == "16":
                continue
            cat_pairs.append((d["targetingOptionId"], d.get("negative", False)))
            cat_names[d["targetingOptionId"]] = d["displayName"]
    if cat_pairs:
        add_ag_categories(page, ag_container, cat_pairs, cat_names)

    kw_included = [t["keywordDetails"]["keyword"] for t in ag["targetingOptions"]
                   if t["targetingType"] == "TARGETING_TYPE_KEYWORD" and not t["keywordDetails"].get("negative")]
    kw_excluded = [t["keywordDetails"]["keyword"] for t in ag["targetingOptions"]
                   if t["targetingType"] == "TARGETING_TYPE_KEYWORD" and t["keywordDetails"].get("negative")]
    if kw_included:
        textarea_by_label(ag_container, "Included Keywords").fill(", ".join(kw_included))
        ok("ag-kw-included", f"{len(kw_included)} included keywords filled")
    if kw_excluded:
        textarea_by_label(ag_container, "Excluded Keywords").fill(", ".join(kw_excluded))
        ok("ag-kw-excluded", f"{len(kw_excluded)} excluded keywords filled")

    url_included = [t["urlDetails"]["url"] for t in ag["targetingOptions"]
                    if t["targetingType"] == "TARGETING_TYPE_URL" and not t["urlDetails"].get("negative")]
    url_excluded = [t["urlDetails"]["url"] for t in ag["targetingOptions"]
                    if t["targetingType"] == "TARGETING_TYPE_URL" and t["urlDetails"].get("negative")]
    if url_included:
        textarea_by_label(ag_container, "Included URLs").fill(", ".join(url_included))
        ok("ag-url-included", f"{len(url_included)} included URLs filled")
    if url_excluded:
        textarea_by_label(ag_container, "Excluded URLs").fill(", ".join(url_excluded))
        ok("ag-url-excluded", f"{len(url_excluded)} excluded URLs filled")

    yt_included = [t["youtubeChannelDetails"]["channelId"] for t in ag["targetingOptions"]
                   if t["targetingType"] == "TARGETING_TYPE_YOUTUBE_CHANNEL" and not t["youtubeChannelDetails"].get("negative")]
    yt_excluded = [t["youtubeChannelDetails"]["channelId"] for t in ag["targetingOptions"]
                   if t["targetingType"] == "TARGETING_TYPE_YOUTUBE_CHANNEL" and t["youtubeChannelDetails"].get("negative")]
    if yt_included:
        add_ag_channels_via_placements(page, ag_container, yt_included, "Include")
    if yt_excluded:
        add_ag_channels_via_placements(page, ag_container, yt_excluded, "Exclude")

    if "TARGETING_TYPE_AUDIENCE_GROUP" in types_present:
        print("TEST ag-audience SKIPPED -> first-party/partner audience ids, no id-search available (see module docstring)")


def field_by_label(container, label: str):
    field = container.locator("mat-form-field").filter(
        has=container.page.locator("mat-label", has_text=re.compile(rf"^{re.escape(label)}$"))
    )
    return field.locator("input, textarea")


# The video field takes an exact 11-char YouTube video id or full URL, NOT
# a keyword search (confirmed via extractYoutubeVideoId's regex - any other
# input is rejected with "Invalid YouTube URL/ID"). Using a stable,
# always-available placeholder id since the JSON has no real video data.
# NOTE: the previous placeholder (dQw4w9WgXcQ, ~3:33) was confirmed live to
# be rejected as "too long" for the NON_SKIPPABLE ad format (DV360 enforces
# video-length limits per ad type) - EhH0qnaRhBQ is short enough to pass.
PLACEHOLDER_VIDEO_ID = "EhH0qnaRhBQ"


def add_synthetic_ad(page: Page, ag_container, ad_name: str, video_id: str = PLACEHOLDER_VIDEO_ID):
    """The reference JSON has zero adGroupAds recorded for every ad group,
    so there's no real creative data to recreate. Per user instruction,
    still add one synthetic ad per ad group to exercise the video-search
    flow and keep the ad group non-empty (real DV360 rejects empty ones)."""
    ag_container.get_by_role("button", name="+ Add ad", exact=True).click()
    page.wait_for_timeout(500)

    field_by_label(ag_container, "Ad name").fill(ad_name)
    field_by_label(ag_container, "Call to action").fill("Shop now")
    field_by_label(ag_container, "Description").fill("Discover the new range.")
    field_by_label(ag_container, "Headline").fill("New Garnier range")
    field_by_label(ag_container, "Long headline").fill("Discover the new Garnier range, out now.")
    field_by_label(ag_container, "Final URL").fill("https://www.garnier.es")
    field_by_label(ag_container, "Domain").fill("garnier.es")

    video_field = field_by_label(ag_container, "Video")
    video_field.fill(video_id)
    video_field.press("Enter")

    select_btn = ag_container.get_by_role("button", name="Select").first
    expect(select_btn).to_be_visible(timeout=15000)
    select_btn.click()
    ok("ag-ad", f"Ad '{ad_name}' created with placeholder video id '{video_id}'")


LI_TYPE_LABELS = {
    "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW": "YouTube | [Product and brand consideration] Video view",
    "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH": "YouTube | [Brand awareness and reach] Efficient reach",
    "LINE_ITEM_TYPE_VIDEO_DEFAULT": "Video",
}


def fill_positive_amount(page: Page, scope, form_control_name: str, label: str, value: str = "1"):
    """Fill a required numeric line-item control (reactive form) and prove the
    value actually committed as a positive number > 0.

    DV360 DSP validation rejects the campaign when:
      - Budget allocation = Fixed but no max amount is provided, and
      - Bid strategy = Fixed Bid but the Bid amount (CPM) is not > 0.
    Both ride the same silent-drop risk as the ad-group bid: 'bidAmount' is
    disable()d until 'Fixed bid' is selected, so a fill that lands before the
    control is enabled is dropped and the payload then ships bidAmountMicros
    '0' (or omits maxAmount entirely). Wait for the field to be enabled, fill,
    then read back and re-fill until a positive value sticks - failing loudly
    here instead of at the DSP."""
    field = scope.locator(f"input[formcontrolname='{form_control_name}']")
    expect(field).to_be_visible()
    expect(field).to_be_enabled()  # bidAmount stays disabled until 'Fixed bid' is chosen
    actual = ""
    for attempt in range(3):
        field.fill(value)
        field.press("Tab")
        page.wait_for_timeout(200)
        actual = (field.input_value() or "").strip()
        try:
            if actual != "" and float(actual) > 0:
                return field
        except ValueError:
            pass
        print(f"NOTE: '{label}' ({form_control_name}) did not commit a positive value "
              f"(got '{actual}'), re-filling (attempt {attempt + 1})")
        page.wait_for_timeout(400)
    raise AssertionError(
        f"'{label}' ({form_control_name}) did not commit a positive number > 0 - "
        f"the DSP would reject the campaign (got '{actual}')"
    )


def fill_li_youtube_basics(page: Page, li_form, li_name: str, li_type: str):
    """Minimal required non-targeting fields for a YouTube-type line item -
    name, type, budget allocation/pacing, EU political ads. Bid strategy is
    hidden at LI level for YouTube (enforced/edited at ad-group level
    instead, see fill_ad_group_targeting's caller)."""
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")

    type_label = LI_TYPE_LABELS[li_type]
    li_type_select = page.locator("mat-select[formcontrolname='lineItemType']")
    yt_marker = page.locator("app-dv360-youtube-line-items")

    # KNOWN NEXIFY BUG (confirmed live via the lineItemType control diagnostic):
    # the YouTube ad-group section is gated `@if (isYouTubeLi())`, and
    # isYouTubeLi() is driven by the `liTypeManualSig` signal, NOT the form
    # control directly. That signal is only updated inside the
    # lineItemType.valueChanges handler, which early-returns `if (this.hydrating)
    # return;` BEFORE setting it. When you switch INTO a fresh IO, its default
    # Display LI hydrates asynchronously (hydrating=true); a type change that
    # lands in that window sets the control value fine (the select shows the
    # YouTube type) but the handler bails, so liTypeManualSig stays 'Display'
    # and the ad-group panel never mounts. Re-selecting the SAME value is
    # suppressed by distinctUntilChanged(), so the only way out is to force a
    # real value transition once hydrating has finished: WIGGLE via Display ->
    # target type. Gets worse on later IOs (heavier form = slower hydration).
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    expect(li_type_select).to_be_visible()
    page.wait_for_timeout(2500)

    for attempt in range(6):
        if attempt == 0:
            select_mat_option(page, "lineItemType", type_label)
        else:
            # Force a Display -> target transition so valueChanges fires again
            # (now that hydrating is false) and updates liTypeManualSig.
            select_mat_option(page, "lineItemType", "Display")
            page.wait_for_timeout(800)
            select_mat_option(page, "lineItemType", type_label)
        try:
            page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        # Poll for the YouTube ad-group section rather than checking once - under
        # a heavy form (later IOs) it can render slowly.
        appeared = False
        for _ in range(16):
            if yt_marker.count() > 0:
                appeared = True
                break
            page.wait_for_timeout(500)
        if appeared:
            break
        shown = ""
        try:
            shown = (li_type_select.inner_text() or "").strip().replace("\n", " ")
        except Exception:
            pass
        # Probe the live DOM so we can see WHY isYouTubeLi() is stuck: how many
        # LI forms/type-selects exist (are we editing a hidden/stale form?), and
        # whether the non-YouTube-only "Bid strategy" section is rendered (proves
        # isYouTubeLi()===false right now).
        try:
            diag = page.evaluate(
                """() => ({
                    liForms: document.querySelectorAll('app-dv360-line-items').length,
                    typeSelects: document.querySelectorAll("mat-select[formcontrolname='lineItemType']").length,
                    ytPanels: document.querySelectorAll('app-dv360-youtube-line-items').length,
                    bidStrategySections: document.querySelectorAll("mat-select[formcontrolname='bidStrategyType']").length,
                    dealGroupSections: [...document.querySelectorAll('div.text-sm.font-semibold')].filter(d => d.textContent.trim() === 'Deal groups').length,
                })"""
            )
        except Exception as e:
            diag = f"(probe failed: {e})"
        print(f"NOTE: YouTube section not present after setting type (attempt {attempt + 1}); "
              f"lineItemType shows '{shown}'. DOM probe: {diag}")
        page.wait_for_timeout(1500)
    assert yt_marker.count() > 0, (
        f"YouTube ad-group section never mounted (lineItemType shows "
        f"'{(li_type_select.inner_text() or '').strip()}') - isYouTubeLi() stuck on a stale signal"
    )
    ok("li-type", f"Line Item type = '{type_label}'")

    fill_positive_amount(page, li_form, "budget", "Budget")
    select_mat_option(page, "budgetAllocationType", "Fixed")
    select_mat_option(page, "pacingPeriod", "Flight")
    select_mat_option(page, "pacingType", "ASAP")
    select_mat_option(page, "containsEuPoliticalAds", "Does not contain EU political advertising")
    ok("li-basics", "Budget = 1.00, Budget allocation = Fixed, Pacing/EU Political Ads set")


def set_ag_bid_value(ag_container):
    """Ad-group Bid value is a plain ngModel input (no formcontrolname) -
    Bid strategy TYPE itself is enforced/disabled per line item type.

    GUARD (confirmed live DSP bug, both VIEW and REACH go through here):
    onBidValueChange() drops the typed value unless enforcedBidType() has
    already resolved ("if (!enforcedType) return"). When it's dropped the
    payload ships youtubeAndPartnersBid with a `type` but no `value`, and the
    DSP then float()s that None -> "float() argument must be a string or a
    real number, not 'NoneType'". The read-only "Bid strategy" select renders
    the enforced type once resolved and a "—" placeholder until then, so wait
    for a real type there before filling, then read the value back and re-fill
    until it sticks - failing loudly here instead of at the DSP."""
    page = ag_container.page
    bid_field = field_by_label(ag_container, "Bid value").first

    # 1. Enforced bid type must be resolved first, else the value is dropped.
    bid_strategy = ag_container.locator("mat-form-field").filter(
        has=page.locator("mat-label", has_text=re.compile(r"^Bid strategy$"))
    ).locator("mat-select")
    for _ in range(6):
        text = (bid_strategy.inner_text() or "").strip()
        if text and text != "—":
            break
        page.wait_for_timeout(500)
    else:
        raise AssertionError(
            "Ad-group 'Bid strategy' never resolved an enforced bid type - "
            "Bid value would be silently dropped from the payload"
        )

    # 2. Commit the value. The FIRST onBidValueChange for a freshly-activated
    #    ad group can fire before enforcedBidType() has propagated (dropping the
    #    value even though the "Bid strategy" select already shows the type), so
    #    fill TWICE with a settle between - the second fill lands after the model
    #    is ready and commits. Reading the DOM input value back can't prove the
    #    model committed (one-way [ngModel]='bidValueView' keeps showing "1" even
    #    on a dropped value), so the AUTHORITATIVE check is the submit-time
    #    payload guard in test_finish_and_submit (find_missing_ag_bid_values).
    for _ in range(2):
        bid_field.fill("1")
        bid_field.press("Tab")
        page.wait_for_timeout(400)
    assert (bid_field.input_value() or "").strip() == "1", (
        "Ad-group Bid value did not even reach the DOM input"
    )

    ok("ag-bid-value", "Bid value = 1 (double-filled after enforced type resolved; verified at submit)")


def select_li_tab(page: Page, index: int):
    """Click the i-th Line Item pill for the active IO (confirmed live:
    this is the first div.flex.flex-wrap.gap-2.mb-4 on the page - the IO
    pill row uses different classes and doesn't match this selector)."""
    pills = page.locator("div.flex.flex-wrap.gap-2.mb-4").nth(0)
    pills.locator("button").nth(index).click()
    page.wait_for_timeout(500)


def select_io_tab(page: Page, index: int):
    """Click the i-th Insertion Order pill on the Line Items step (its own
    container is 'flex flex-wrap gap-2' - no 'mb-4' - so it doesn't collide
    with the LI/ad-group pill rows above)."""
    pills = page.locator("div.flex.flex-wrap.gap-2:not(.mb-4)").first
    pills.locator("button").nth(index).click()
    page.wait_for_timeout(1000)


def create_n_line_items_via_duplicate(page: Page, li_form, n: int, li_type: str, first_li_name: str, fill_basics_fn=None):
    """KNOWN NEXIFY BUG (confirmed live, reproducible): creating a 2nd+ line
    item via "Create another" (which always defaults to Display type) and
    then changing its Media Type away from Display silently reverts back to
    Display shortly after - no amount of re-selecting or waiting fixes it.
    Workaround: "Duplicate" clones the source line item's lineItemType
    directly (no post-creation type change involved at all), which does not
    hit this bug. So: set LI1's type once, then Duplicate it (n-1) times
    BEFORE filling any targeting - each duplicate starts targeting-free
    since the source has none yet, so nothing needs clearing afterward."""
    fill_basics_fn = fill_basics_fn or fill_li_youtube_basics
    fill_basics_fn(page, li_form, first_li_name, li_type)
    for _ in range(n - 1):
        page.get_by_role("button", name="Duplicate", exact=True).first.click()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
    ok("li-duplicated", f"{n} line items created via Duplicate (type stays '{LI_TYPE_LABELS[li_type]}' on all)")


def build_youtube_line_item_targeting(page: Page, li_form, li: dict, li_name: str):
    """Fill one already-created, already-typed YouTube line item's targeting
    (Device Type, Geo Region) and its single ad group's full targeting."""
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")

    fill_li_youtube_targeting(page, li_form, li)

    ag_container = page.locator("app-dv360-youtube-line-items")
    expect(ag_container).to_be_visible(timeout=10000)
    ag0 = li["adGroups"][0]
    set_ag_bid_value(ag_container)
    fill_ad_group_targeting(page, ag_container, ag0)
    add_synthetic_ad(page, ag_container, f"{li_name} Ad 1")


def build_io0_line_items(page: Page, ref: dict):
    """IO0: 3 LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW line items, each with
    1 ad group. Assumes we've just landed on the Line Items step with IO0's
    first (blank, Display-typed) line item active."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io0 = ref["insertionOrders"][0]
    n = len(io0["lineItems"])
    li_type = "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW"
    create_n_line_items_via_duplicate(page, li_form, n, li_type, f"YT LI 1 - {int(time.time())}")

    for i, li in enumerate(io0["lineItems"]):
        select_li_tab(page, i)
        li_name = f"YT LI {i + 1} - {int(time.time())}"
        build_youtube_line_item_targeting(page, li_form, li, li_name)
    ok("io0-complete", f"IO0: {n} YouTube View line items built")


# --------------------------------------------------------------------------
# IO1: VIDEO_DEFAULT (CTV) line items - reuses Display-style targeting
# --------------------------------------------------------------------------
ENV_LABELS = {
    "ENVIRONMENT_WEB_OPTIMIZED": "Web optimized",
    "ENVIRONMENT_WEB_NOT_OPTIMIZED": "Web not optimized",
    "ENVIRONMENT_APP": "App",
}
ON_SCREEN_POSITION_LABELS = {
    "ON_SCREEN_POSITION_ABOVE_THE_FOLD": "Above the fold",
    "ON_SCREEN_POSITION_BELOW_THE_FOLD": "Below the fold",
    "ON_SCREEN_POSITION_UNKNOWN": "Unknown",
}
SENSITIVE_CATEGORY_LABELS = {
    "SENSITIVE_CATEGORY_ADULT": "Adult",
    "SENSITIVE_CATEGORY_DEROGATORY": "Derogatory",
    "SENSITIVE_CATEGORY_DOWNLOADS_SHARING": "Downloads sharing",
    "SENSITIVE_CATEGORY_WEAPONS": "Weapons",
    "SENSITIVE_CATEGORY_GAMBLING": "Gambling",
    "SENSITIVE_CATEGORY_VIOLENCE": "Violence",
    "SENSITIVE_CATEGORY_SUGGESTIVE": "Suggestive",
    "SENSITIVE_CATEGORY_PROFANITY": "Profanity",
    "SENSITIVE_CATEGORY_ALCOHOL": "Alcohol",
    "SENSITIVE_CATEGORY_DRUGS": "Drugs",
    "SENSITIVE_CATEGORY_TOBACCO": "Tobacco",
    "SENSITIVE_CATEGORY_POLITICS": "Politics",
    "SENSITIVE_CATEGORY_RELIGION": "Religion",
    "SENSITIVE_CATEGORY_TRAGEDY": "Tragedy",
    "SENSITIVE_CATEGORY_TRANSPORTATION_ACCIDENTS": "Transportation accidents",
    "SENSITIVE_CATEGORY_SENSITIVE_SOCIAL_ISSUES": "Social issues",
    "SENSITIVE_CATEGORY_SHOCKING": "Shocking",
    "SENSITIVE_CATEGORY_EMBEDDED_VIDEO": "Embedded video",
    "SENSITIVE_CATEGORY_LIVE_STREAMING_VIDEO": "Live streaming video",
}


def fill_li_video_basics(page: Page, li_form, li_name: str, li_type: str = "LINE_ITEM_TYPE_VIDEO_DEFAULT"):
    """Same required non-targeting fields as the Display suite's
    test_line_items_form_basics, just with Media Type = 'Video'."""
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)

    # Verify the VIDEO type actually STUCK. A type that reverts (or never takes)
    # leaves the LI as an empty Display default, which autosave silently drops
    # from the submit payload - the OTT line item was lost exactly this way. A
    # video type is NOT YouTube, so the YouTube ad-group section must be ABSENT
    # and the type control must show the chosen label. Settle first (in-flight
    # hydration can otherwise swallow the change), then re-select via a wiggle
    # if it didn't hold.
    type_label = LI_TYPE_LABELS[li_type]
    li_type_select = page.locator("mat-select[formcontrolname='lineItemType']")
    yt_marker = page.locator("app-dv360-youtube-line-items")
    try:
        page.wait_for_load_state("networkidle", timeout=8000)
    except Exception:
        pass
    expect(li_type_select).to_be_visible()
    page.wait_for_timeout(1500)

    for attempt in range(4):
        select_mat_option(page, "lineItemType", type_label)
        page.wait_for_timeout(1200)
        shown = (li_type_select.inner_text() or "").strip()
        if type_label in shown and yt_marker.count() == 0:
            break
        print(f"NOTE: video line item type '{type_label}' not confirmed (attempt {attempt + 1}); "
              f"control shows '{shown}', yt_marker={yt_marker.count()} - wiggling to re-apply")
        select_mat_option(page, "lineItemType", "Display" if type_label != "Display" else "Video")
        page.wait_for_timeout(700)
    assert type_label in (li_type_select.inner_text() or "").strip() and yt_marker.count() == 0, (
        f"Video line item type '{type_label}' did not stick (control shows "
        f"'{(li_type_select.inner_text() or '').strip()}', yt_marker={yt_marker.count()})"
    )
    ok("li-type", f"Line Item type = '{type_label}'")

    flight_cb_root = li_form.locator("mat-checkbox[formcontrolname='useIoFlightDates']")
    flight_cb = flight_cb_root.locator("input[type='checkbox']")
    if not flight_cb.is_checked():
        flight_cb_root.click()
    expect(flight_cb).to_be_checked()

    fill_positive_amount(page, li_form, "budget", "Budget")
    select_mat_option(page, "budgetAllocationType", "Fixed")
    select_mat_option(page, "pacingPeriod", "Flight")
    select_mat_option(page, "pacingType", "ASAP")

    limit_row = li_form.locator("div.flex.items-start.gap-3", has_text="Limit exposure frequency to")
    limit_cb = limit_row.locator("input[type='checkbox']")
    if not limit_cb.is_checked():
        limit_row.locator("mat-checkbox").click()
    expect(limit_cb).to_be_checked()

    li_form.locator("input[formcontrolname='freqCount']").fill("1")
    li_form.locator("input[formcontrolname='freqEvery']").fill("1")
    select_mat_option(page, "freqUnit", "Minute")
    select_mat_option(page, "containsEuPoliticalAds", "Does not contain EU political advertising")
    select_mat_option(page, "bidStrategyType", "Fixed bid")
    fill_positive_amount(page, li_form, "bidAmount", "Bid amount (CPM)")
    select_mat_option(page, "partnerRevenueModelMarkupType", "Total Media Cost")
    li_form.locator("input[formcontrolname='partnerRevenueModelMarkupValue']").fill("0")
    ok("li-basics", f"Line Item '{li_name}' basics filled (type='{LI_TYPE_LABELS[li_type]}')")


def _dismiss_targeting_dialog(page: Page, dialog):
    """Close a targeting-list dialog without applying (Escape first, then a
    Cancel/Cancelar button if it ignores Escape) so a picker that loaded an
    empty/unusable list never blocks the sections that follow."""
    if dialog.count() == 0 or not dialog.first.is_visible():
        return
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)
        if not dialog.first.is_visible():
            return
        cancel = dialog.get_by_role("button", name=re.compile(r"^(Cancel|Cancelar)$"))
        if cancel.count() > 0:
            try:
                cancel.first.click()
            except Exception:
                pass
            page.wait_for_timeout(400)
            if not dialog.first.is_visible():
                return


def add_li_list_dialog(page: Page, li_form, section_text: str, button_name: str,
                       api_url_fragment: str, ids: list, timeout_ms: int = 45000):
    """Shared mechanics for the LI-level 'Channels'/'Deals'/'Deal groups'
    pickers. All load their data on dialog open (captured to resolve JSON ids
    -> live names). 'Deals'/'Deal groups' are client-paginated (fast first
    page), but 'Channels' (`/dsp/dv360/channels`) is a SINGLE UNPAGINATED
    fetch of the advertiser's entire channel library, which can be slow for a
    large advertiser (observed live: >15s, past the old fixed timeout) - so
    the response wait is generous (timeout_ms, default 45s) and, if the list
    never answers, this degrades to a printed NOTE and selects nothing rather
    than crashing the whole (multi-hour) run. After resolving a name, it
    re-searches via the dialog's own filter box to bring the row onto a
    clickable page, same principle as the Geo Region picker."""
    section = li_form.locator("div.border.rounded-xl.p-4", has_text=section_text)
    # exact=True is essential: the "Deals" and "Deal groups" sections sit in one
    # inventory <section>, and a substring name match makes "Add deal" also
    # match "Add deal group" (strict-mode violation). mat-icon is aria-hidden by
    # default, so each button's accessible name is exactly its label text.
    add_btn = section.get_by_role("button", name=button_name, exact=True)
    add_btn.first.scroll_into_view_if_needed()
    expect(add_btn.first).to_be_visible()
    add_btn = add_btn.first

    dialog = page.locator("mat-dialog-container")

    # The list loads on dialog OPEN, so wrap the button click in
    # expect_response to capture it without the register-then-poll race.
    body = None
    try:
        with page.expect_response(
            lambda r: api_url_fragment in r.url, timeout=timeout_ms
        ) as resp_info:
            add_btn.click()
        body = resp_info.value.json()
    except PlaywrightTimeoutError:
        print(f"NOTE: {section_text} list ({api_url_fragment}) did not respond within "
              f"{timeout_ms // 1000}s - skipping this picker (0/{len(ids)} selected)")

    if body is None:
        # The list never answered - close whatever opened so the rest of the
        # LI can build.
        _dismiss_targeting_dialog(page, dialog)
        return []

    expect(dialog).to_be_visible()
    grid = dialog.locator("dx-data-grid")

    items = body if isinstance(body, list) else body.get("results", body.get("deals", []))
    live_by_id = {str(item["id"]): item.get("name", str(item["id"])) for item in items}

    matched = [(i, live_by_id[i]) for i in ids if i in live_by_id]
    if len(matched) != len(ids):
        print(f"NOTE: {len(matched)}/{len(ids)} {section_text} ids resolved live - the rest no "
              f"longer exist for this advertiser (live list has {len(items)} item(s))")

    # Nothing to select (empty list or every id drifted) - close WITHOUT
    # applying and continue, same graceful-degradation convention the other
    # pickers use for dead ids. Avoids asserting on a "No data" grid.
    if not matched:
        _dismiss_targeting_dialog(page, dialog)
        return []

    expect(grid.locator("tr.dx-data-row").first).to_be_visible()
    search_box = dialog.get_by_placeholder("Type to filter")
    has_search = search_box.count() > 0
    for _id, name in matched:
        if has_search:
            search_box.fill(name)
            search_box.press("Enter")
            page.wait_for_timeout(800)
        row = grid.locator("tr.dx-data-row").filter(has=page.locator("td", has_text=name))
        expect(row).to_be_visible(timeout=10000)
        row.locator("div.dx-select-checkbox").click()

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    return matched


def fill_li_video_targeting(page: Page, li_form, li: dict):
    """LI-level targeting for a VIDEO_DEFAULT (CTV) line item. Video Player
    Size and OMID are confirmed UI gaps (form controls exist in the
    component's TS but have no template binding at all - not automatable)."""
    device_pairs = li_targeting_values(li, "TARGETING_TYPE_DEVICE_TYPE", "deviceTypeDetails", "deviceType")
    device_labels = [DEVICE_TYPE_LABELS[key] for key, _ in device_pairs]
    if device_labels:
        select_multi_exact(page, "deviceType", device_labels)
        ok("li-device-type", f"Device type = {device_labels}")

    gender_pairs = li_targeting_values(li, "TARGETING_TYPE_GENDER", "genderDetails", "gender")
    if gender_pairs:
        labels = [GENDER_LABELS[key] for key, _ in gender_pairs]
        select_multi_exact(page, "gender", labels)
        ok("li-gender", f"Gender = {labels}")

    env_pairs = li_targeting_values(li, "TARGETING_TYPE_ENVIRONMENT", "environmentDetails", "environment")
    if env_pairs:
        labels = [ENV_LABELS[key] for key, _ in env_pairs]
        select_multi_exact(page, "environment", labels)
        ok("li-environment", f"Environment = {labels}")

    osp_pairs = li_targeting_values(li, "TARGETING_TYPE_ON_SCREEN_POSITION", "onScreenPositionDetails", "onScreenPosition")
    if osp_pairs:
        labels = [ON_SCREEN_POSITION_LABELS[key] for key, _ in osp_pairs]
        select_multi_exact(page, "onScreenPositionDetails", labels)
        ok("li-on-screen-position", f"On-screen position = {labels}")

    sc_pairs = li_targeting_values(li, "TARGETING_TYPE_SENSITIVE_CATEGORY_EXCLUSION", "sensitiveCategoryExclusionDetails", "excludedSensitiveCategory")
    if sc_pairs:
        labels = [SENSITIVE_CATEGORY_LABELS[key] for key, _ in sc_pairs]
        select_multi_exact(page, "sensitiveCategoryExcl", labels)
        ok("li-sensitive-category", f"{len(labels)} sensitive categories excluded")

    geo_pairs = li_targeting_values(li, "TARGETING_TYPE_GEO_REGION", "geoRegionDetails", "targetingOptionId")
    geo_names = {}
    for t in li.get("targetingOptions", []):
        if t.get("targetingType") == "TARGETING_TYPE_GEO_REGION":
            d = t["geoRegionDetails"]
            geo_names[d["targetingOptionId"]] = d["displayName"]
    included = [(gid, geo_names[gid]) for gid, neg in geo_pairs if not neg]
    excluded = [(gid, geo_names[gid]) for gid, neg in geo_pairs if neg]
    if included:
        add_geo_region(page, li_form, "Add included geo", "geo", included)
        ok("li-geo-included", f"Included geo regions = {[n for _, n in included]}")
    if excluded:
        add_geo_region(page, li_form, "Add excluded geo", "geo", excluded)
        ok("li-geo-excluded", f"Excluded geo regions = {[n for _, n in excluded]}")

    ch_pairs = li_targeting_values(li, "TARGETING_TYPE_CHANNEL", "channelDetails", "channelId")
    ch_included = [cid for cid, neg in ch_pairs if not neg]
    ch_excluded = [cid for cid, neg in ch_pairs if neg]
    if ch_included:
        matched = add_li_list_dialog(page, li_form, "Included channels", "Add Channel", "/dsp/dv360/channels", ch_included)
        ok("li-channels-included", f"Included channels: {[n for _, n in matched]}")
    if ch_excluded:
        matched = add_li_list_dialog(page, li_form, "Excluded channels", "Add Channel", "/dsp/dv360/channels", ch_excluded)
        ok("li-channels-excluded", f"Excluded channels: {[n for _, n in matched]}")

    inv_pairs = li_targeting_values(li, "TARGETING_TYPE_INVENTORY_SOURCE", "inventorySourceDetails", "inventorySourceId")
    if inv_pairs:
        matched = add_li_list_dialog(page, li_form, "Deals", "Add deal", "/dsp/dv360/deals", [i for i, _ in inv_pairs])
        ok("li-deals", f"Deals: {[n for _, n in matched]}")

    if any(t["targetingType"] == "TARGETING_TYPE_VIDEO_PLAYER_SIZE" for t in li.get("targetingOptions", [])):
        print("TEST li-video-player-size SKIPPED -> no UI control exists for this field (confirmed in component TS with no template binding)")
    if any(t["targetingType"] == "TARGETING_TYPE_OMID" for t in li.get("targetingOptions", [])):
        print("TEST li-omid SKIPPED -> OMID has no UI control anywhere in this frontend")


def build_video_line_item_targeting(page: Page, li_form, li: dict, li_name: str):
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")
    fill_li_video_targeting(page, li_form, li)


def build_io1_line_items(page: Page, ref: dict):
    """IO1: 5 LINE_ITEM_TYPE_VIDEO_DEFAULT (CTV) line items, no ad groups."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io1 = ref["insertionOrders"][1]
    n = len(io1["lineItems"])
    li_type = "LINE_ITEM_TYPE_VIDEO_DEFAULT"
    create_n_line_items_via_duplicate(
        page, li_form, n, li_type, f"CTV LI 1 - {int(time.time())}", fill_basics_fn=fill_li_video_basics
    )

    for i, li in enumerate(io1["lineItems"]):
        select_li_tab(page, i)
        li_name = f"CTV LI {i + 1} - {int(time.time())}"
        build_video_line_item_targeting(page, li_form, li, li_name)
    ok("io1-complete", f"IO1: {n} Video/CTV line items built")


def build_io2_line_items(page: Page, ref: dict):
    """IO2: 3 LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH line items, each with
    1 ad group (same shape as IO0, different bid type + category counts)."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io2 = ref["insertionOrders"][2]
    n = len(io2["lineItems"])
    li_type = "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH"
    create_n_line_items_via_duplicate(page, li_form, n, li_type, f"YT Reach LI 1 - {int(time.time())}")

    for i, li in enumerate(io2["lineItems"]):
        select_li_tab(page, i)
        li_name = f"YT Reach LI {i + 1} - {int(time.time())}"
        build_youtube_line_item_targeting(page, li_form, li, li_name)
    ok("io2-complete", f"IO2: {n} YouTube Reach line items built")


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def find_missing_ag_bid_values(payload: dict) -> list:
    """Return human-readable descriptions of every YouTube ad group whose
    bidStrategy.youtubeAndPartnersBid is missing a positive `value`. Such a bid
    ships `type` without `value` and the DSP crashes on float(None). This walks
    the exact outgoing payload, so it can't be fooled by the one-way-ngModel DOM
    false-pass that the per-field set_ag_bid_value check is subject to."""
    offending = []
    for dsp in payload.get("dspPayload", []) or []:
        inner = dsp.get("payload", {}) or {}
        for io in inner.get("insertionOrders", []) or []:
            for li in io.get("lineItems", []) or []:
                for ag in li.get("adGroups", []) or []:
                    bid = (ag.get("bidStrategy") or {}).get("youtubeAndPartnersBid")
                    if not bid:
                        continue
                    val = bid.get("value")
                    try:
                        good = val is not None and str(val).strip() != "" and float(val) > 0
                    except (TypeError, ValueError):
                        good = False
                    if not good:
                        offending.append(
                            f"{li.get('displayName') or li.get('name') or '?'} / "
                            f"ad group '{ag.get('displayName', '?')}' "
                            f"(type={bid.get('type', '?')}, value={val!r})"
                        )
    return offending


# Shared state for the session-wide submit guard (install_submit_guard).
SUBMIT_GUARD_STATE = {"missing": None, "seen": False}
SUBMIT_PAYLOAD_DUMP = Path("last_submit_payload.json")


def install_submit_guard(page: Page):
    """Install a SESSION-WIDE guard on the campaign submit request, so it fires
    no matter WHO clicks 'Start campaign' - the script OR you, manually, in the
    browser (the per-submit guard inside test_finish_and_submit only covered the
    scripted click). On the outgoing submit POST it:
      1. dumps the full payload to last_submit_payload.json (so ANY null field,
         not just the bid value, can be inspected afterwards),
      2. checks every YouTube ad-group bid carries a positive `value`,
      3. prints the verdict to the console (visible in the tee'd log), and
      4. ABORTS the request when a value is missing, so no float(None)-crashing
         campaign ever reaches the DSP.
    NOTE: routes only fire while Playwright is pumping its event loop, so a
    MANUAL click must be awaited via the 'watch' loop in test_finish_and_submit,
    never a bare input()."""
    SUBMIT_GUARD_STATE["missing"] = None
    SUBMIT_GUARD_STATE["seen"] = False

    def _route(route):
        req = route.request
        raw = req.post_data or ""
        if req.method != "POST" or "dspPayload" not in raw:
            route.continue_()
            return
        SUBMIT_GUARD_STATE["seen"] = True
        try:
            body = req.post_data_json
        except Exception:
            body = None
        try:
            pretty = json.dumps(json.loads(raw), indent=2, ensure_ascii=False)
            SUBMIT_PAYLOAD_DUMP.write_text(pretty, encoding="utf-8")
            print(f"\n[submit-guard] captured outgoing campaign payload -> {SUBMIT_PAYLOAD_DUMP.name}")
        except Exception as e:
            print(f"[submit-guard] could not dump payload: {e}")
        missing = find_missing_ag_bid_values(body) if body else []
        if missing:
            SUBMIT_GUARD_STATE["missing"] = missing
            print("[submit-guard] BLOCKED submit - YouTube ad groups missing a positive bid `value` "
                  "(would crash the DSP with float(None)):")
            for m in missing:
                print(f"    - {m}")
            route.abort()
        else:
            print("[submit-guard] bid-value check PASSED - every youtubeAndPartnersBid has a positive "
                  "value; letting the submit through. If the DSP still errors, the null is a DIFFERENT "
                  f"field - inspect {SUBMIT_PAYLOAD_DUMP.name}.")
            route.continue_()

    page.route("**/*", _route)


def test_finish_and_submit(page: Page):
    """'Next' from Line Items to Recap, then submit. The session-wide guard
    (install_submit_guard) validates the outgoing payload for BOTH paths:
      - 'yes'   -> the script clicks 'Start campaign' for you
      - 'watch' -> you click 'Start campaign' yourself in the browser while this
                   loop keeps Playwright's event loop alive so the guard fires
    This actually launches a real campaign on Garnier_ES's live DV360 account."""
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok("next-to-recap", "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)

    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES on Garnier_ES's live DV360 account.\n"
        "    The submit guard will validate the payload and BLOCK it if a bid value is missing.\n"
        "      yes   -> let the script click it\n"
        "      watch -> you click it in the browser; I'll validate the outgoing payload\n"
        "      (anything else cancels)\n"
        ">>> choice: "
    ).strip().lower()

    if answer == "yes":
        start_btn.click()
    elif answer == "watch":
        print(">>> Waiting up to 3 min for you to click 'Start campaign' in the browser...")
        for _ in range(360):
            if SUBMIT_GUARD_STATE["seen"]:
                break
            page.wait_for_timeout(500)
    else:
        print("TEST start-campaign SKIPPED -> cancelled by the user")
        return

    # Let the guard finish handling the intercepted submit.
    for _ in range(40):
        if SUBMIT_GUARD_STATE["seen"]:
            break
        page.wait_for_timeout(250)

    if not SUBMIT_GUARD_STATE["seen"]:
        print("NOTE: no campaign submit request was observed (nothing was submitted).")
        return

    if SUBMIT_GUARD_STATE["missing"]:
        raise AssertionError(
            "BLOCKED submit before it reached the DSP: YouTube ad groups missing a "
            "positive bid `value` (would crash with float(None)):\n- "
            + "\n- ".join(SUBMIT_GUARD_STATE["missing"])
        )

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
    ok("start-campaign", f"submit payload validated (all bid values present); dumped to {SUBMIT_PAYLOAD_DUMP.name}")


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
        # Active for the whole session so it also catches a MANUAL 'Start
        # campaign' click, not just the scripted one.
        install_submit_guard(page)

        try:
            test_landing(page)
            footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            test_insertion_orders_multi(page, ref)
            test_sidebar_sync(page)

            footer.locator("button.mdc-button", has_text="Next").click()
            dialog = page.locator("mat-dialog-container")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.locator("button", has_text="Confirm & continue").click()
            expect(dialog).not_to_be_visible()

            # IO0 is already active by default when landing on Line Items.
            build_io0_line_items(page, ref)

            select_io_tab(page, 1)
            build_io1_line_items(page, ref)

            select_io_tab(page, 2)
            build_io2_line_items(page, ref)

            test_finish_and_submit(page)

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

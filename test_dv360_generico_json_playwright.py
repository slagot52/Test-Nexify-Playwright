# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 "Genérico" video suite)
================================================================================
Checks that DV360 "Genérico" (standard Video / CTV) line-item targeting in
Nexify can be driven from a real DV360 API export, by comparing the export's
values against what the UI actually lets you pick.

Reference JSON: template_2429284_56991293_Generico.json (Samsung campaign).
Client "Samsung" / advertiser "Samsung_ES_Starcom" (DV360 advertiserId
2429284) - the same advertiser the JSON was exported from, so
advertiser-scoped pickers (channels, negative keyword lists, audiences) can
find matching data.

Structure: 2 Insertion Orders, 1 Line Item each, both
LINE_ITEM_TYPE_VIDEO_DEFAULT (Video), no ad groups.

Every LI-level targeting section inserts the JSON's REAL distinct values
(not just the first 2), while budgets/bids stay at a token 1 EUR/1 CPM to
avoid real spend. The flow does not click "Start campaign" without an
explicit typed confirmation.

Targeting types covered per line item (all confirmed to have a Nexify
control in dv360-line-items.component.html for a Video line item):
  Device Type, Environment, Sensitive Category (excl), Digital Content
  Label / Excluded content rating, On-screen position, Instream position
  (Video only), Display/Outstream position, Predicted viewability, Age
  range, Channels (excl), Negative Keyword List, Included audiences (Google
  audiences only), Geo Region, Categories (excl), URLs (excl), Day & time.

Known UI gaps (present in the JSON, no corresponding Nexify control -
skipped with a printed NOTE, not silently dropped):
  - TARGETING_TYPE_EXCHANGE (28 entries): no Exchange control exists in the
    DV360 line-item component template at all.
  - TARGETING_TYPE_OMID: no UI control anywhere in this frontend.
  - First-party/partner audiences: not present in this JSON (only Google
    audiences are), so the id-search limitation from the other suites does
    not apply here.

Run with:        python test_dv360_generico_json_playwright.py
"""

import datetime
import json
import random
import string
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

from test_dv360_playwright import (
    AUTH_FILE,
    BASE_URL,
    ok,
    select_mat_option,
    fill_and_verify,
    manual_login,
    test_landing,
    test_global_setup,
    test_template_dialog,
)
from test_dv360_json_playwright import (
    test_general_info,     # Samsung / Samsung_ES_Starcom General Info step
    test_sidebar_sync,     # sidebar brand==advertiser check
    select_mat_option_on,  # for day-time-selector rows (selectionChange selects)
)
from test_dv360_youtube_json_playwright import (
    li_targeting_values,
    select_multi_exact,
    add_geo_region,
    add_li_list_dialog,
    fill_li_video_basics,
    create_n_line_items_via_duplicate,
    select_io_tab,
    DEVICE_TYPE_LABELS,
    ENV_LABELS,
    ON_SCREEN_POSITION_LABELS,
    SENSITIVE_CATEGORY_LABELS,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_2429284_56991293_Generico.json")
CLIENT = "Samsung"
ADVERTISER = "Samsung_ES_Starcom"  # DV360 advertiserId 2429284 - same as the reference JSON
DATE_FMT = "%m/%d/%Y"

# API-token -> UI label maps for the targeting types the other two suites
# don't already cover. Sourced 1:1 from the frontend enums (src/open-api/
# models/dv-360-*.ts): the enum KEY is the API token, the enum VALUE is the
# label rendered by enumLabel() in the mat-select options.
DIGITAL_CONTENT_LABEL_LABELS = {
    "CONTENT_RATING_TIER_UNRATED": "Unrated",
    "CONTENT_RATING_TIER_GENERAL": "General",
    "CONTENT_RATING_TIER_PARENTAL_GUIDANCE": "Parental Guidance",
    "CONTENT_RATING_TIER_TEENS": "Teens",
    "CONTENT_RATING_TIER_MATURE": "Mature",
    "CONTENT_RATING_TIER_FAMILIES": "Families",
}
VIEWABILITY_LABELS = {
    "VIEWABILITY_10_PERCENT_OR_MORE": "10% or greater",
    "VIEWABILITY_20_PERCENT_OR_MORE": "20% or greater",
    "VIEWABILITY_30_PERCENT_OR_MORE": "30% or greater",
    "VIEWABILITY_40_PERCENT_OR_MORE": "40% or greater",
    "VIEWABILITY_50_PERCENT_OR_MORE": "50% or greater",
    "VIEWABILITY_60_PERCENT_OR_MORE": "60% or greater",
    "VIEWABILITY_70_PERCENT_OR_MORE": "70% or greater",
    "VIEWABILITY_80_PERCENT_OR_MORE": "80% or greater",
    "VIEWABILITY_90_PERCENT_OR_MORE": "90% or greater (most viewable)",
}
INSTREAM_LABELS = {
    "CONTENT_INSTREAM_POSITION_PRE_ROLL": "Pre-Roll",
    "CONTENT_INSTREAM_POSITION_MID_ROLL": "Mid-Roll",
    "CONTENT_INSTREAM_POSITION_POST_ROLL": "Post-Roll",
    "CONTENT_INSTREAM_POSITION_UNKNOWN": "Unknown",
}
OUTSTREAM_LABELS = {
    "CONTENT_OUTSTREAM_POSITION_UNKNOWN": "Unknown",
    "CONTENT_OUTSTREAM_POSITION_IN_ARTICLE": "In article",
    "CONTENT_OUTSTREAM_POSITION_IN_BANNER": "In banner",
    "CONTENT_OUTSTREAM_POSITION_IN_FEED": "In feed",
    "CONTENT_OUTSTREAM_POSITION_INTERSTITIAL": "interstitial",
}
DAY_OF_WEEK_LABELS = {
    "MONDAY": "Monday",
    "TUESDAY": "Tuesday",
    "WEDNESDAY": "Wednesday",
    "THURSDAY": "Thursday",
    "FRIDAY": "Friday",
    "SATURDAY": "Saturday",
    "SUNDAY": "Sunday",
}

# Age slider stops from the component (ageStops), and the coarse DV360 age
# buckets they bound. The stops line up exactly with DV360's coarse bucket
# edges, so a [min_index, max_index] thumb pair over the stops selects a
# contiguous set of coarse buckets.
AGE_STOPS = [18, 25, 35, 45, 55, 65]
COARSE_AGE_BUCKETS = {
    "AGE_RANGE_18_24": (18, 24),
    "AGE_RANGE_25_34": (25, 34),
    "AGE_RANGE_35_44": (35, 44),
    "AGE_RANGE_45_54": (45, 54),
    "AGE_RANGE_55_64": (55, 64),
    "AGE_RANGE_65_UP": (65, 120),
}


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


def hour_label(hour: int) -> str:
    """DV360 day-and-time hours are 0-24 integers; the UI selects show 12h
    labels. endHour 24 (midnight next day) renders as '12:00 AM', same as 0."""
    h = hour % 24
    suffix = "AM" if h < 12 else "PM"
    hour12 = h % 12 or 12
    return f"{hour12}:00 {suffix}"


# --------------------------------------------------------------------------
# Insertion Orders: create both IOs from the reference JSON
# --------------------------------------------------------------------------
def create_insertion_orders(page: Page, ref: dict):
    """Create one IO per entry in ref['insertionOrders'] via 'Create
    another'. Only token, always-valid IO fields are filled (display name
    uses the standard counter convention, budget stays at 1) - the flight
    dates always use today+offset, never the JSON's (long-expired) real
    dates, same convention as every other suite."""
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

    n = len(ref["insertionOrders"])
    today = datetime.date.today()
    for i in range(n):
        if i > 0:
            page.get_by_role("button", name="Create another", exact=True).first.click()
            page.wait_for_timeout(800)

        io_display_name = f"IO {i + 1} - {CLIENT} - {int(time.time())}"
        fill_and_verify(io_form, "displayName", io_display_name)

        select_mat_option(page, "insertionOrderType", "Standard")

        df = io_form.locator("input[formcontrolname='dateFrom']")
        dt = io_form.locator("input[formcontrolname='dateTo']")
        df.fill((today + datetime.timedelta(days=1)).strftime(DATE_FMT))
        dt.fill((today + datetime.timedelta(days=2)).strftime(DATE_FMT))
        dt.press("Tab")
        page.wait_for_timeout(500)

        purchase_order = "".join(random.choices(string.ascii_letters + string.digits, k=8))
        fill_and_verify(io_form, "purchaseOrder", purchase_order)

        budget_field = io_form.locator("input[formcontrolname='budget']")
        expect(budget_field).to_be_visible()
        budget_field.fill("1")
        budget_field.press("Tab")

        # JSON optimizationObjective is BRAND_AWARENESS -> "Awareness".
        select_mat_option(page, "optimizationObjective", "Awareness")
        select_mat_option(page, "pacingPeriod", "Flight")
        select_mat_option(page, "pacingType", "Ahead")
        # KPI type doesn't affect targeting; use the same always-valid option
        # the frozen suite validates rather than the JSON's viewability KPI.
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

        ok(f"io{i}-fields", f"IO {i} ('{io_display_name}') base fields filled")

    ok("ios-created", f"{n} Insertion Orders created")


# --------------------------------------------------------------------------
# LI-level targeting helpers specific to this suite
# --------------------------------------------------------------------------
def set_age_range(page: Page, li_form, li: dict):
    """Drive the dual-thumb age slider to cover exactly the JSON's coarse age
    buckets. AGE_STOPS align with DV360's coarse bucket edges, so the min
    thumb goes to the stop equal to the lowest bucket's floor and the max
    thumb to the first stop strictly above the highest bucket's ceiling."""
    keys = [
        t["ageRangeDetails"]["ageRange"]
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_AGE_RANGE"
    ]
    if not keys:
        return

    lows = [COARSE_AGE_BUCKETS[k][0] for k in keys if k in COARSE_AGE_BUCKETS]
    highs = [COARSE_AGE_BUCKETS[k][1] for k in keys if k in COARSE_AGE_BUCKETS]
    if not lows:
        return
    min_age, max_age = min(lows), max(highs)

    min_index = AGE_STOPS.index(min_age) if min_age in AGE_STOPS else 0
    max_index_val = next((i for i, s in enumerate(AGE_STOPS) if s > max_age), len(AGE_STOPS) - 1)
    max_slider_index = len(AGE_STOPS) - 1

    start = li_form.locator("input[formcontrolname='ageMinIndex']")
    end = li_form.locator("input[formcontrolname='ageMaxIndex']")
    start.scroll_into_view_if_needed()

    start.focus()
    page.keyboard.press("Home")  # -> index 0
    for _ in range(min_index):
        page.keyboard.press("ArrowRight")

    end.focus()
    page.keyboard.press("End")  # -> index max_slider_index
    for _ in range(max_slider_index - max_index_val):
        page.keyboard.press("ArrowLeft")

    # JSON has no AGE_RANGE_UNKNOWN, so the Unknown checkbox stays unchecked.
    ok("li-age-range", f"Age range set to buckets {keys} (slider indices {min_index}..{max_index_val})")


def add_negative_keyword_lists(page: Page, li_form, li: dict):
    """'Negative Keyword List' picker - resolve the JSON's ids against the
    dialog's own data-load response (advertiser-scoped) and select each."""
    ids = list(dict.fromkeys(
        t["negativeKeywordListDetails"]["negativeKeywordListId"]
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_NEGATIVE_KEYWORD_LIST"
    ))
    if not ids:
        return

    captured = []
    page.on(
        "response",
        lambda r, c=captured: c.append(r) if "/dsp/dv360/negativeKeywordsLists" in r.url else None,
    )

    section = li_form.locator("div.border.rounded-xl.p-4", has_text="Negative Keyword List")
    add_btn = section.get_by_role("button", name="Add List")
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    grid = dialog.locator("dx-data-grid")
    expect(grid.locator("tr.dx-data-row").first).to_be_visible()

    for _ in range(20):
        if captured:
            break
        page.wait_for_timeout(250)
    assert captured, "Did not observe the negative keyword lists API response"
    live = {item["id"]: item["name"] for item in captured[-1].json()["results"]}

    matched = [(lid, live[lid]) for lid in ids if lid in live]
    if len(matched) != len(ids):
        print(f"NOTE: {len(matched)}/{len(ids)} negative keyword list ids resolved live - the rest no longer exist")
    assert matched, "None of the JSON's negativeKeywordListIds exist in the live account"

    for lid, name in matched:
        row = grid.locator("tr.dx-data-row").filter(has=page.get_by_text(name, exact=True))
        expect(row).to_be_visible()
        row.locator("div.dx-select-checkbox").click()

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok("li-negative-keyword-list", f"Negative keyword lists: {[n for _, n in matched]}")


def add_google_audiences(page: Page, li_form, li: dict):
    """'Included audiences' - Google audiences sub-type only (this JSON has
    no custom/first-party audiences). Selects the type, resolves each JSON
    googleAudienceId against the live data, then searches by name and checks
    the matching row by position (names aren't guaranteed unique)."""
    ids = []
    for t in li.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_AUDIENCE_GROUP":
            continue
        g = t["audienceGroupDetails"].get("includedGoogleAudienceGroup")
        if not g:
            continue
        for s in g.get("settings", []):
            if s["googleAudienceId"] not in ids:
                ids.append(s["googleAudienceId"])
    if not ids:
        return

    section = li_form.locator("div.border.rounded-xl.p-4", has_text="Included audiences")
    add_btn = section.get_by_role("button", name="Add audience")
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    type_select = dialog.locator("mat-select").first
    grid = dialog.locator("dx-data-grid")
    search_box = dialog.get_by_placeholder("Write to filter audiences")

    captured = []
    page.on(
        "response",
        lambda r, c=captured: c.append(r) if "/dsp/dv360/audiences" in r.url else None,
    )

    def wait_for_response(baseline, timeout_ms=8000):
        waited = 0
        while len(captured) <= baseline and waited < timeout_ms:
            page.wait_for_timeout(200)
            waited += 200
        return len(captured) > baseline

    def search_term_candidates(name: str):
        # Server-side search does 'contains' on the raw name, which fails for
        # prefixed names like '[In-Market] : ...' - fall back to the ':' tail.
        candidates = [name]
        if ":" in name:
            tail = name.split(":")[-1].strip()
            if tail and tail not in candidates:
                candidates.append(tail)
        return candidates

    def find_and_check(_id: str, name: str):
        for term in search_term_candidates(name):
            baseline = len(captured)
            search_box.fill(term)
            search_box.press("Enter")
            wait_for_response(baseline)
            if not captured:
                continue
            results = captured[-1].json()["results"]
            idx = next((i for i, item in enumerate(results) if item["id"] == _id), None)
            if idx is None:
                continue
            row = grid.locator("tr.dx-data-row").nth(idx)
            expect(row).to_be_visible()
            row.locator("div.dx-select-checkbox").click()
            return True
        return False

    # Select the "Google audiences" type. The JSON only carries audience ids
    # (no names), and the picker's search is a server-side 'contains' on the
    # NAME - so we can't search for an id directly. Instead we page through
    # the Google-audience list via "Load more" to discover each id's name
    # (the only place names exist), stopping as soon as all target ids are
    # resolved, then select each one by name-search (fast, unambiguous).
    search_box.fill("")
    type_select.click(force=True)
    page.wait_for_timeout(400)
    page.get_by_role("option", name="Google audiences", exact=True).click()
    wait_for_response(0)
    assert captured, "Did not observe the audiences API response for 'Google audiences'"

    id_to_name = {}

    def ingest(resp):
        for item in resp.json().get("results", []):
            id_to_name[str(item["id"])] = item["name"]

    ingest(captured[-1])
    load_more = dialog.locator("button", has_text="Load more")
    pages = 0
    while not all(i in id_to_name for i in ids) and pages < 120:
        if load_more.count() == 0 or not load_more.first.is_visible():
            break
        baseline = len(captured)
        load_more.first.click()
        if not wait_for_response(baseline):
            break
        ingest(captured[-1])
        pages += 1

    found = [(i, id_to_name[i]) for i in ids if i in id_to_name]
    missing = [i for i in ids if i not in id_to_name]
    if missing:
        print(f"NOTE: {len(found)}/{len(ids)} Google audience ids resolved after paging {pages} extra page(s); unresolved (drift): {missing}")

    # Selecting rows one-by-one via name-search resets the grid to a short,
    # server-filtered result set, so nth(idx) stays reliable (vs. hunting a
    # row inside the huge accumulated grid, which dx virtualizes).
    selected = [(i, n) for i, n in found if find_and_check(i, n)]
    if len(selected) != len(found):
        print(f"NOTE: {len(selected)}/{len(found)} resolved Google audiences could be located via search")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok("li-audiences-google", f"Included Google audiences ({len(selected)}/{len(ids)}): {[n for _, n in selected]}")


def add_categories(page: Page, li_form, li: dict):
    """'Categories' section - one 'Manage' tree dialog with Include/Exclude
    buttons per node. Shallower categories are set first so a node is never
    hidden under a still-collapsed ancestor."""
    cats = []
    name_by_id = {}
    for t in li.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_CATEGORY":
            continue
        d = t["categoryDetails"]
        cats.append((d["targetingOptionId"], d.get("negative", False)))
        name_by_id[d["targetingOptionId"]] = d["displayName"]
    if not cats:
        return

    def depth(cid):
        return len(name_by_id[cid].strip("/").split("/"))

    included_ids = sorted([c for c, neg in cats if not neg], key=depth)
    excluded_ids = sorted([c for c, neg in cats if neg], key=depth)

    manage_btn = li_form.get_by_role("button", name="Manage")
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
    ok("li-categories", f"{len(included_ids)} included / {len(excluded_ids)} excluded categories set")


def add_urls(page: Page, li_form, li: dict):
    """Included/Excluded URLs - plain comma-separated textareas, no picker."""
    included, excluded = [], []
    for t in li.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_URL":
            continue
        u = t["urlDetails"]
        (excluded if u.get("negative") else included).append(u["url"])

    if included:
        f = li_form.locator("textarea[formcontrolname='includedUrlIds']")
        f.fill(", ".join(included))
        ok("li-urls-included", f"{len(included)} included URLs filled")
    if excluded:
        f = li_form.locator("textarea[formcontrolname='excludedUrlIds']")
        f.fill(", ".join(excluded))
        ok("li-urls-excluded", f"{len(excluded)} excluded URLs filled")


def add_day_time(page: Page, li_form, li: dict):
    """'Day & time' section (<day-time-selector>) - one row per JSON entry.
    Each row's 3 mat-selects use (selectionChange), not formcontrolname, so
    they're driven with select_mat_option_on."""
    rows_data = [
        (
            DAY_OF_WEEK_LABELS[t["dayAndTimeDetails"]["dayOfWeek"]],
            hour_label(t["dayAndTimeDetails"]["startHour"]),
            hour_label(t["dayAndTimeDetails"]["endHour"]),
        )
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_DAY_AND_TIME"
    ]
    if not rows_data:
        return

    selector = li_form.locator("day-time-selector:visible").first
    selector.scroll_into_view_if_needed()

    # The day-time-selector's row list does NOT reset when the line-item form
    # rebinds to a different LI (unlike every other control), so a freshly
    # selected LI can still show the previously-built LI's rows. Remove any
    # carried-over rows first - removeRow fires against the now-active LI's
    # control, so the earlier LI (committed while it was active) is untouched.
    existing = selector.locator("div.day-time-row")
    guard = 0
    while existing.count() > 0 and guard < 50:
        existing.first.locator("button[aria-label='Remove row']").click()
        page.wait_for_timeout(150)
        guard += 1
    expect(existing).to_have_count(0)

    add_row_btn = selector.get_by_role("button", name="Add row")
    for i, (day, start, end) in enumerate(rows_data):
        add_row_btn.click()
        row = selector.locator("div.day-time-row").nth(i)
        expect(row).to_be_visible()
        row.scroll_into_view_if_needed()
        select_mat_option_on(page, row.locator("mat-select").nth(0), day)
        select_mat_option_on(page, row.locator("mat-select").nth(1), start)
        select_mat_option_on(page, row.locator("mat-select").nth(2), end)

    expect(selector.locator("div.day-time-row")).to_have_count(len(rows_data))
    ok("li-day-time", f"{len(rows_data)} day & time rows added")


def fill_generico_targeting(page: Page, li_form, li: dict):
    """Fill every automatable LI-level targeting section for one
    VIDEO_DEFAULT line item from its JSON entry."""
    # --- multi-select enum sections ---
    device = [DEVICE_TYPE_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_DEVICE_TYPE", "deviceTypeDetails", "deviceType")]
    if device:
        select_multi_exact(page, "deviceType", device)
        ok("li-device-type", f"Device type = {device}")

    env = [ENV_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_ENVIRONMENT", "environmentDetails", "environment")]
    if env:
        select_multi_exact(page, "environment", env)
        ok("li-environment", f"Environment = {env}")

    sens = [SENSITIVE_CATEGORY_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_SENSITIVE_CATEGORY_EXCLUSION",
        "sensitiveCategoryExclusionDetails", "excludedSensitiveCategory")]
    if sens:
        select_multi_exact(page, "sensitiveCategoryExcl", sens)
        ok("li-sensitive-category", f"{len(sens)} sensitive categories excluded")

    dcl = [DIGITAL_CONTENT_LABEL_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_DIGITAL_CONTENT_LABEL_EXCLUSION",
        "digitalContentLabelExclusionDetails", "excludedContentRatingTier")]
    if dcl:
        select_multi_exact(page, "contentRatingTierExcl", dcl)
        ok("li-content-rating", f"Excluded content rating = {dcl}")

    osp = [ON_SCREEN_POSITION_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_ON_SCREEN_POSITION",
        "onScreenPositionDetails", "onScreenPosition")]
    if osp:
        select_multi_exact(page, "onScreenPositionDetails", osp)
        ok("li-on-screen-position", f"On-screen position = {osp}")

    ins = [INSTREAM_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_CONTENT_INSTREAM_POSITION",
        "contentInstreamPositionDetails", "contentInstreamPosition")]
    if ins:
        select_multi_exact(page, "instreamPosition", ins)
        ok("li-instream-position", f"Instream position = {ins}")

    outs = [OUTSTREAM_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_CONTENT_OUTSTREAM_POSITION",
        "contentOutstreamPositionDetails", "contentOutstreamPosition")]
    if outs:
        select_multi_exact(page, "contentOutstreamPositionDetails", outs)
        ok("li-outstream-position", f"Display/outstream position = {outs}")

    view = [
        VIEWABILITY_LABELS[t["viewabilityDetails"]["viewability"]]
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_VIEWABILITY"
    ]
    if view:
        # Single-choice mat-select (not multiple).
        select_mat_option(page, "viewability", view[0])
        ok("li-viewability", f"Predicted viewability = {view[0]}")

    set_age_range(page, li_form, li)

    # --- picker-dialog sections ---
    ch_pairs = li_targeting_values(li, "TARGETING_TYPE_CHANNEL", "channelDetails", "channelId")
    ch_included = [cid for cid, neg in ch_pairs if not neg]
    ch_excluded = [cid for cid, neg in ch_pairs if neg]
    if ch_included:
        matched = add_li_list_dialog(page, li_form, "Included channels", "Add Channel", "/dsp/dv360/channels", ch_included)
        ok("li-channels-included", f"Included channels: {[n for _, n in matched]}")
    if ch_excluded:
        matched = add_li_list_dialog(page, li_form, "Excluded channels", "Add Channel", "/dsp/dv360/channels", ch_excluded)
        ok("li-channels-excluded", f"Excluded channels: {[n for _, n in matched]}")

    add_negative_keyword_lists(page, li_form, li)
    add_google_audiences(page, li_form, li)

    geo_pairs = li_targeting_values(li, "TARGETING_TYPE_GEO_REGION", "geoRegionDetails", "targetingOptionId")
    geo_names = {
        t["geoRegionDetails"]["targetingOptionId"]: t["geoRegionDetails"]["displayName"]
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_GEO_REGION"
    }
    geo_included = [(g, geo_names[g]) for g, neg in geo_pairs if not neg]
    geo_excluded = [(g, geo_names[g]) for g, neg in geo_pairs if neg]
    if geo_included:
        add_geo_region(page, li_form, "Add included geo", "geo", geo_included)
        ok("li-geo-included", f"Included geo regions = {[n for _, n in geo_included]}")
    if geo_excluded:
        add_geo_region(page, li_form, "Add excluded geo", "geo", geo_excluded)
        ok("li-geo-excluded", f"Excluded geo regions = {[n for _, n in geo_excluded]}")

    add_categories(page, li_form, li)
    add_urls(page, li_form, li)
    add_day_time(page, li_form, li)

    # --- confirmed UI gaps: present in the JSON, no Nexify control ---
    if any(t["targetingType"] == "TARGETING_TYPE_EXCHANGE" for t in li.get("targetingOptions", [])):
        print("TEST li-exchange SKIPPED -> no Exchange control exists in the DV360 line-item UI (confirmed absent from the component template)")
    if any(t["targetingType"] == "TARGETING_TYPE_OMID" for t in li.get("targetingOptions", [])):
        print("TEST li-omid SKIPPED -> OMID has no UI control anywhere in this frontend")


def build_io_line_items(page: Page, ref: dict, io_index: int, tag: str):
    """Each IO here has exactly one VIDEO_DEFAULT line item. Type it to Video
    via the Duplicate-safe path (n=1 just fills basics once), then drive its
    targeting."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    li = ref["insertionOrders"][io_index]["lineItems"][0]
    li_name = f"{tag} LI 1 - {int(time.time())}"
    create_n_line_items_via_duplicate(
        page, li_form, 1, "LINE_ITEM_TYPE_VIDEO_DEFAULT", li_name,
        fill_basics_fn=fill_li_video_basics,
    )
    fill_generico_targeting(page, li_form, li)
    ok(f"io{io_index}-complete", f"IO{io_index}: Video line item built")


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def finish_and_submit(page: Page):
    """'Next' from Line Items to Recap, then attempt 'Start campaign'. Same
    safety gate as every other suite - this actually launches a real campaign
    on Samsung_ES_Starcom's live DV360 account, so it only clicks through if
    you type 'yes'."""
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok("next-to-recap", "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)
    answer = input(
        "\n>>> 'Start campaign' ACTUALLY LAUNCHES the campaign on Samsung_ES_Starcom's "
        "live DV360 account. Type 'yes' to confirm the click (anything else cancels): "
    ).strip().lower()
    if answer == "yes":
        start_btn.click()
        errors_dialog = page.locator("app-campaign-activation-errors-dialog")
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
        ok("start-campaign", "'Start campaign' performed, no validation-errors dialog shown")
    else:
        print("TEST start-campaign SKIPPED -> click on 'Start campaign' cancelled by the user")


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
            footer = test_general_info(page)       # Samsung / Samsung_ES_Starcom
            test_template_dialog(page, footer)
            test_global_setup(page)
            create_insertion_orders(page, ref)
            test_sidebar_sync(page)

            # Line Items step: Next opens the "Review insertion orders" dialog.
            footer.locator("button.mdc-button", has_text="Next").click()
            dialog = page.locator("mat-dialog-container")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.locator("button", has_text="Confirm & continue").click()
            expect(dialog).not_to_be_visible()

            # IO0 is active by default when landing on Line Items.
            build_io_line_items(page, ref, 0, "CTV")

            select_io_tab(page, 1)
            build_io_line_items(page, ref, 1, "CTV")

            finish_and_submit(page)

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

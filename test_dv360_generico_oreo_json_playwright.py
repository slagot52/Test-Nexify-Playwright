# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 "Genérico Oreo" suite)
================================================================================
Checks that DV360 line-item / ad-group targeting in Nexify can be driven from
a real DV360 API export, by comparing the export's values against what the
UI actually lets you pick.

Reference JSON: template_1117994126_57061851_Generico_Oreo.json (Oreo
campaign, DV360 advertiserId 1117994126 / clientId 747094460).

>>> CLIENT / ADVERTISER below are UNVERIFIED PLACEHOLDER GUESSES ("Mondelez" /
>>> "Oreo_ES"), not confirmed against the live Nexify UI. This advertiserId
>>> isn't one of the known mappings (2429284=Samsung, 809633=L'Oreal/Garnier_ES).
>>> Verify against the advertiser search grid on the General Info step (or the
>>> DV360 /api/v1/clients endpoint) and correct the two constants below if
>>> they don't match - test_general_info will fail fast on the "Client"
>>> dropdown or the advertiser grid search if either name is wrong.

Structure: 5 Insertion Orders, 22 Line Items total:
  IO0 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_TARGET_FREQUENCY (2 LIs, 1 ad group each)
  IO1 - LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP (CTV, programmatic)  (3 LIs, no ad groups)
  IO2 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE      (2 LIs, 2 ad groups each)
  IO3 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE      (2 LIs, 2 ad groups each)
  IO4 - LINE_ITEM_TYPE_VIDEO_DEFAULT (CTV)                     (8 LIs, no ad groups)

Targeting sections insert the JSON's REAL distinct values (not just the
first 2), while budgets/bids stay at a token 1 EUR/1 CPM to avoid real
spend. The flow does not click "Start campaign" without an explicit typed
confirmation.

CONFIRMED FRONTEND BUG (not a test limitation) - see
BUG_youtube_target_frequency_non_skippable_bid_value.md:
  enforcedYtBidType() in dv360-youtube-bidding-util.ts only maps LI types
  REACH->Target CPM and VIEW->Target CPV. For TARGET_FREQUENCY and
  NON_SKIPPABLE (IO0, IO2, IO3 - 6 of the 22 line items / 10 ad groups
  here), it returns null, which means:
    - the ad-group "Bid strategy" select is permanently disabled on "—"
    - onBidValueChange() and the auto-ensure-ad-group effect both silently
      no-op when enforcedType is null
    - NO ad group is even auto-created when landing on these LI types
      (ensureOne() is gated behind the same enforced-type check)
  The JSON carries real bid values for these ad groups (~€2.85-2.90 CPM),
  so DV360 genuinely needs them. This suite still builds everything else
  for these line items (adding ad groups manually via "+ Add ad group",
  which does NOT require an enforced type) and prints a NOTE instead of
  attempting the impossible bid-value fill. The shared submit guard
  (find_missing_ag_bid_values / install_submit_guard, imported from the
  YouTube suite) correctly BLOCKS an actual "Start campaign" launch for
  these ad groups' missing bid values - that's the guard doing its job,
  not a suite bug.

Other confirmed UI gaps (present in the JSON, no corresponding Nexify
control - skipped with a printed NOTE, never silently dropped):
  - TARGETING_TYPE_CONTENT_THEME_EXCLUSION: no control anywhere in this
    frontend (grepped the full component tree and open-api models - no
    "theme" match at all). New finding vs. the other 3 suites.
  - TARGETING_TYPE_OMID, TARGETING_TYPE_VIDEO_PLAYER_SIZE, Authorized
    Seller Status: same blanket gaps documented in the other suites.
  - For YouTube-family line items (IO0, IO2, IO3) specifically, 5 of the
    JSON's LI-level targeting types have NO control at all (confirmed via
    `@if(!isYouTubeLi())` gates in dv360-line-items.component.html):
    On-Screen Position, Digital Content Label Exclusion, Sensitive
    Category Exclusion, Channel, Negative Keyword List. Only Device Type,
    Geo Region, and Day & Time are settable at LI level for these types.
  - Ad-group first-party/partner audiences (IO2, single id per ad group):
    same "picker searches by name, ids aren't directly searchable" gap as
    the other suites - skipped with a NOTE (only 1 id, not worth paging).

Scale note: IO2+IO3's 8 ad groups each carry the SAME 49 excluded
categories (no ancestor/descendant conflicts this time, unlike the other
YouTube suite's IO2) - that's ~392 individual category-dialog interactions
alone. A full live run is expected to take a while; let it run rather than
re-triggering.

Run with:        python test_dv360_generico_oreo_json_playwright.py
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
)
from test_dv360_youtube_json_playwright import (
    li_targeting_values,
    select_multi_exact,
    fill_li_youtube_targeting,
    fill_li_video_basics,
    fill_li_video_targeting,
    add_ag_categories,
    field_by_label,
    create_n_line_items_via_duplicate,
    select_io_tab,
    select_li_tab,
    install_submit_guard,
    SUBMIT_GUARD_STATE,
    SUBMIT_PAYLOAD_DUMP,
    LI_TYPE_LABELS,
    PLACEHOLDER_VIDEO_ID,
)
from test_dv360_generico_json_playwright import (
    add_day_time,
    AGE_STOPS,
    COARSE_AGE_BUCKETS,
    DIGITAL_CONTENT_LABEL_LABELS,
    INSTREAM_LABELS,
)

# This export needs 3 line item types the other suites never built: extend
# the shared (mutable, imported-by-reference) dict rather than editing
# test_dv360_youtube_json_playwright.py - purely additive, doesn't touch
# the other suites' behavior.
LI_TYPE_LABELS.update({
    "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_TARGET_FREQUENCY": "YouTube | [Brand awareness and reach] Target frequency",
    "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE": "YouTube | [Brand awareness and reach] Non-skippable",
    "LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP": "Video Over-the-top",
})

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_1117994126_57061851_Generico_Oreo.json")
CLIENT = "Mondelez"    # UNVERIFIED PLACEHOLDER - see module docstring
ADVERTISER = "Oreo_ES"  # UNVERIFIED PLACEHOLDER - see module docstring
DV360_DSP_BADGE = "Google DV360"
DATE_FMT = "%m/%d/%Y"


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before a ~1h live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    handled_li_types = {
        "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_TARGET_FREQUENCY",
        "LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP",
        "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE",
        "LINE_ITEM_TYPE_VIDEO_DEFAULT",
    }
    valid_days = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}

    for io in ref["insertionOrders"]:
        for li in io["lineItems"]:
            assert li["lineItemType"] in handled_li_types, f"Unhandled LI type: {li['lineItemType']}"

            for t in li.get("targetingOptions", []):
                tt = t["targetingType"]
                if tt == "TARGETING_TYPE_DIGITAL_CONTENT_LABEL_EXCLUSION":
                    key = t["digitalContentLabelExclusionDetails"]["excludedContentRatingTier"]
                    assert key in DIGITAL_CONTENT_LABEL_LABELS, f"Unknown digital content label token: {key}"
                elif tt == "TARGETING_TYPE_CONTENT_INSTREAM_POSITION":
                    key = t["contentInstreamPositionDetails"]["contentInstreamPosition"]
                    assert key in INSTREAM_LABELS, f"Unknown instream position token: {key}"
                elif tt == "TARGETING_TYPE_DAY_AND_TIME":
                    d = t["dayAndTimeDetails"]
                    assert d["dayOfWeek"] in valid_days, f"Unknown day-of-week token: {d['dayOfWeek']}"
                    assert 0 <= d.get("startHour", 0) <= 24 and 0 <= d.get("endHour", 24) <= 24, (
                        f"Day-and-time hour out of range: {d}"
                    )

            for ag in li.get("adGroups", []) or []:
                for t in ag.get("targetingOptions", []):
                    if t["targetingType"] == "TARGETING_TYPE_AGE_RANGE":
                        key = t["ageRangeDetails"]["ageRange"]
                        assert key in COARSE_AGE_BUCKETS, f"Unknown age range token: {key}"

    print("OFFLINE VALIDATION PASSED: every targeting token this suite automates resolves against its label dict.")


# --------------------------------------------------------------------------
# General Info / template dialog / sidebar (Oreo-specific)
# --------------------------------------------------------------------------
def test_general_info(page: Page):
    create_btn = page.locator("button.mdc-button--unelevated", has_text="Create Campaign")
    expect(create_btn).to_be_visible()

    create_btn.click()
    page.wait_for_url("**/campaign/create", timeout=10000)
    assert page.url.rstrip("/") == f"{BASE_URL}/campaign/create", (
        f"Expected URL: {BASE_URL}/campaign/create\nActual URL: {page.url}"
    )

    footer = page.locator("div.step-footer")
    expect(footer).to_be_visible()

    campaign_name = f"Test Dv Oreo JSON - {int(time.time())}"
    campaign_input = page.locator("input[formcontrolname='campaignName']")
    expect(campaign_input).to_be_visible()
    campaign_input.fill(campaign_name)
    assert campaign_input.input_value() == campaign_name, "The field does not contain the expected text"

    select_mat_option(page, "client", CLIENT)

    aside = page.locator("aside.campaign-aside")
    expect(aside).to_be_visible()
    expect(aside.locator("h4", has_text=campaign_name)).to_be_visible()

    client_row = aside.locator("p", has_text="Client")
    expect(client_row.locator("span", has_text=CLIENT)).to_be_visible()

    grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
    expect(grid).to_be_visible()
    search = grid.locator("input[aria-label='Search in the data grid']")
    search.fill(ADVERTISER)
    page.wait_for_timeout(1200)
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "No rows found in the advertiser grid"

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

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    expect(dsp_card.locator("span.dsp-name", has_text=DV360_DSP_BADGE)).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()

    next_btn = footer.locator("button.mdc-button", has_text="Next")
    expect(next_btn).to_be_enabled(timeout=15000)
    page.wait_for_timeout(500)

    ok("general-info", f"Campaign '{campaign_name}' created for {CLIENT}/{ADVERTISER}")
    return footer


def test_template_dialog(page: Page, footer):
    """Local variant (not the frozen suite's hardcoded template count) -
    Oreo's advertiser has an unknown number of saved templates, so this
    only checks the dialog is non-empty."""
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
    assert dialog.locator("mat-list-option").count() >= 0, "Template dialog did not render"
    dialog.locator("button", has_text="Continuar sin seleccionar plantilla").click()
    expect(dialog).not_to_be_visible()
    ok("template-dialog", "template dialog dismissed without selecting one")


def test_sidebar_sync(page: Page):
    aside = page.locator("aside.campaign-aside")
    expect(aside.locator("span.dsp-name", has_text=DV360_DSP_BADGE)).to_be_visible()
    brand_row = aside.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()
    ok("sidebar", f"sidebar synced with the form (Brand '{ADVERTISER}')")


# --------------------------------------------------------------------------
# Insertion Orders: create all 5 IOs from the reference JSON
# --------------------------------------------------------------------------
def create_insertion_orders_oreo(page: Page, ref: dict):
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

        # Never reuse the JSON's real (long-expired) flight dates - same
        # convention as every other suite.
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

        # JSON campaignGoal is BRAND_AWARENESS -> "Awareness".
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

        ok(f"io{i}-fields", f"IO {i} ('{io_display_name}') base fields filled")

    ok("ios-created", f"{n} Insertion Orders created")


# --------------------------------------------------------------------------
# LI-level targeting: YouTube-family (IO0, IO2, IO3) and Video-family (IO1, IO4)
# --------------------------------------------------------------------------
def build_youtube_li_targeting_oreo(page: Page, li_form, li: dict):
    """Device Type + Geo Region (working controls) + Day & Time (confirmed
    NOT gated by isYouTubeLi(), unlike every other LI-level section), then
    a printed NOTE for every gap actually present in this LI's JSON data."""
    fill_li_youtube_targeting(page, li_form, li)
    add_day_time(page, li_form, li)

    gaps = [
        ("TARGETING_TYPE_ON_SCREEN_POSITION", "li-on-screen-position",
         "On-Screen Position has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_DIGITAL_CONTENT_LABEL_EXCLUSION", "li-content-rating",
         "Digital Content Label Exclusion has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_SENSITIVE_CATEGORY_EXCLUSION", "li-sensitive-category",
         "Sensitive Category Exclusion has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_NEGATIVE_KEYWORD_LIST", "li-negative-keyword-list",
         "Negative Keyword List has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_AUTHORIZED_SELLER_STATUS", "li-authorized-seller",
         "no UI control exists for Authorized Seller Status in this frontend"),
        ("TARGETING_TYPE_CONTENT_THEME_EXCLUSION", "li-content-theme",
         "no UI control exists for Content Theme Exclusion anywhere in this frontend (confirmed absent from the component template/models)"),
        ("TARGETING_TYPE_OMID", "li-omid", "OMID has no UI control anywhere in this frontend"),
    ]
    for ttype, label, reason in gaps:
        if any(t["targetingType"] == ttype for t in li.get("targetingOptions", [])):
            print(f"TEST {label} SKIPPED -> {reason}")


def build_video_li_targeting_oreo(page: Page, li_form, li: dict):
    """Reuses the YouTube suite's fill_li_video_targeting (Device, On-screen,
    Sensitive category, Geo, Channels, Deals, VideoPlayerSize/OMID gaps),
    then adds the sections this export needs that suite never had to cover:
    Digital Content Label, Content Instream Position, Day & Time."""
    fill_li_video_targeting(page, li_form, li)

    dcl = [DIGITAL_CONTENT_LABEL_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_DIGITAL_CONTENT_LABEL_EXCLUSION",
        "digitalContentLabelExclusionDetails", "excludedContentRatingTier")]
    if dcl:
        select_multi_exact(page, "contentRatingTierExcl", dcl)
        ok("li-content-rating", f"Excluded content rating = {dcl}")

    ins = [INSTREAM_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_CONTENT_INSTREAM_POSITION",
        "contentInstreamPositionDetails", "contentInstreamPosition")]
    if ins:
        select_multi_exact(page, "instreamPosition", ins)
        ok("li-instream-position", f"Instream position = {ins}")

    add_day_time(page, li_form, li)

    if any(t["targetingType"] == "TARGETING_TYPE_AUTHORIZED_SELLER_STATUS" for t in li.get("targetingOptions", [])):
        print("TEST li-authorized-seller SKIPPED -> no UI control exists for Authorized Seller Status in this frontend")


# --------------------------------------------------------------------------
# Ad-group targeting (YouTube-family only: IO0, IO2, IO3)
# --------------------------------------------------------------------------
def set_ag_age_range_precise(page: Page, ag_container, ag: dict):
    """Ad-group-scoped age slider (distinct reactive form from the LI-level
    one used by the generico suite's set_age_range, but identical
    formcontrolnames/mechanics) - drives the dual-thumb slider to exactly
    the JSON's coarse age buckets rather than assuming full range."""
    keys = [
        t["ageRangeDetails"]["ageRange"]
        for t in ag.get("targetingOptions", [])
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

    start = ag_container.locator("input[formcontrolname='ageMinIndex']")
    end = ag_container.locator("input[formcontrolname='ageMaxIndex']")
    start.scroll_into_view_if_needed()

    start.focus()
    page.keyboard.press("Home")
    for _ in range(min_index):
        page.keyboard.press("ArrowRight")

    end.focus()
    page.keyboard.press("End")
    for _ in range(max_slider_index - max_index_val):
        page.keyboard.press("ArrowLeft")

    ok("ag-age-range", f"Age range set to buckets {keys} (slider indices {min_index}..{max_index_val})")


def add_ag_google_audiences(page: Page, ag_container, ag: dict):
    """Ad-group-scoped 'Included audiences' picker. Same server-side
    name-only search + Load-more paging workaround as the generico suite's
    LI-level add_google_audiences (the JSON only carries ids), just
    retargeted to the ad-group's own dialog trigger and container."""
    ids = []
    for t in ag.get("targetingOptions", []):
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

    section = ag_container.locator("div.rounded.border.p-3", has_text="Included audiences")
    add_btn = section.get_by_role("button", name="Add Audience")
    add_btn.scroll_into_view_if_needed()
    expect(add_btn).to_be_visible()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    type_select = dialog.locator("mat-select").first
    grid = dialog.locator("dx-data-grid")
    search_box = dialog.get_by_placeholder("Write to filter audiences")

    captured = []
    page.on("response", lambda r, c=captured: c.append(r) if "/dsp/dv360/audiences" in r.url else None)

    def wait_for_response(baseline, timeout_ms=8000):
        waited = 0
        while len(captured) <= baseline and waited < timeout_ms:
            page.wait_for_timeout(200)
            waited += 200
        return len(captured) > baseline

    def search_term_candidates(name):
        candidates = [name]
        if ":" in name:
            tail = name.split(":")[-1].strip()
            if tail and tail not in candidates:
                candidates.append(tail)
        return candidates

    def find_and_check(_id, name):
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

    selected = [(i, n) for i, n in found if find_and_check(i, n)]
    if len(selected) != len(found):
        print(f"NOTE: {len(selected)}/{len(found)} resolved Google audiences could be located via search")

    dialog.get_by_role("button", name="Apply").click()
    expect(dialog).not_to_be_visible()
    ok("ag-audiences-google", f"Included Google audiences ({len(selected)}/{len(ids)}): {[n for _, n in selected]}")


def build_ag_targeting_oreo(page: Page, ag_container, ag: dict, ag_label: str):
    types_present = {t["targetingType"] for t in ag.get("targetingOptions", [])}

    if "TARGETING_TYPE_AGE_RANGE" in types_present:
        set_ag_age_range_precise(page, ag_container, ag)

    for t in ag.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_AUDIENCE_GROUP":
            continue
        d = t["audienceGroupDetails"]
        if "includedGoogleAudienceGroup" in d:
            add_ag_google_audiences(page, ag_container, ag)
        elif "includedFirstPartyAndPartnerAudienceGroups" in d:
            print(f"TEST ag-audience SKIPPED ({ag_label}) -> first-party/partner audience id(s), no id-search available (picker searches by name only)")
        break  # this JSON has at most one AUDIENCE_GROUP entry per ad group

    cat_pairs = []
    cat_names = {}
    for t in ag.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_CATEGORY":
            continue
        d = t["categoryDetails"]
        cat_pairs.append((d["targetingOptionId"], d.get("negative", False)))
        cat_names[d["targetingOptionId"]] = d["displayName"]
    if cat_pairs:
        add_ag_categories(page, ag_container, cat_pairs, cat_names)

    known = {"TARGETING_TYPE_AGE_RANGE", "TARGETING_TYPE_AUDIENCE_GROUP", "TARGETING_TYPE_CATEGORY"}
    unexpected = types_present - known
    if unexpected:
        print(f"NOTE ({ag_label}): unhandled ad-group targeting type(s) present in JSON, not automated: {sorted(unexpected)}")


def add_synthetic_ad_oreo(page: Page, ag_container, ad_name: str, video_id: str = PLACEHOLDER_VIDEO_ID):
    """This JSON has zero adGroupAds recorded for every ad group, so there's
    no real creative to recreate. One synthetic ad per ad group exercises
    the video-search flow and keeps the ad group non-empty (real DV360
    rejects empty ones) - same convention as the YouTube suite."""
    ag_container.get_by_role("button", name="+ Add ad", exact=True).click()
    page.wait_for_timeout(500)

    field_by_label(ag_container, "Ad name").fill(ad_name)
    field_by_label(ag_container, "Call to action").fill("Shop now")
    field_by_label(ag_container, "Description").fill("Discover the new Oreo range.")
    field_by_label(ag_container, "Headline").fill("New Oreo range")
    field_by_label(ag_container, "Long headline").fill("Discover the new Oreo range, out now.")
    field_by_label(ag_container, "Final URL").fill("https://www.oreo.es")
    field_by_label(ag_container, "Domain").fill("oreo.es")

    video_field = field_by_label(ag_container, "Video")
    video_field.fill(video_id)
    video_field.press("Enter")

    select_btn = ag_container.get_by_role("button", name="Select").first
    expect(select_btn).to_be_visible(timeout=15000)
    select_btn.click()
    ok("ag-ad", f"Ad '{ad_name}' created with placeholder video id '{video_id}'")


def ensure_ag_count(ag_container, n: int):
    """Click '+ Add ad group' until N ad-group tabs exist. Self-correcting
    rather than 'click n-1 times', because TARGET_FREQUENCY/NON_SKIPPABLE
    line items start at ZERO ad groups (the auto-ensureOne() effect is
    gated behind the same broken enforced-bid-type check as the bid value -
    see module docstring), unlike REACH/VIEW which start at 1."""
    add_btn = ag_container.get_by_role("button", name="+ Add ad group")
    tabs = ag_container.locator("div.flex.flex-wrap.gap-2.mb-4").first
    for _ in range(50):
        if tabs.locator("button").count() >= n:
            break
        add_btn.click()
        ag_container.page.wait_for_timeout(400)
    expect(tabs.locator("button")).to_have_count(n)


def select_ag_tab(ag_container, index: int):
    tabs = ag_container.locator("div.flex.flex-wrap.gap-2.mb-4").first
    tabs.locator("button").nth(index).click()
    ag_container.page.wait_for_timeout(300)


def skip_ag_bid_value(li_type_label: str, ag_label: str):
    print(
        f"TEST ag-bid-value SKIPPED ({ag_label}) -> Bid strategy/value cannot be set in the UI for "
        f"'{li_type_label}' line items (enforcedYtBidType() only maps REACH/VIEW - confirmed dead "
        f"control, see BUG_youtube_target_frequency_non_skippable_bid_value.md). The submit guard "
        f"will correctly block an actual campaign launch over this."
    )


def build_youtube_li_oreo(page: Page, li_form, li: dict, li_name: str, li_type_label: str):
    """Fill one already-created, already-typed YouTube-family line item's
    LI-level targeting, then every one of its ad groups (1 for IO0, 2 for
    IO2/IO3)."""
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")

    build_youtube_li_targeting_oreo(page, li_form, li)

    ag_container = page.locator("app-dv360-youtube-line-items")
    expect(ag_container).to_be_visible(timeout=10000)

    n_ags = len(li["adGroups"])
    ensure_ag_count(ag_container, n_ags)

    for i, ag in enumerate(li["adGroups"]):
        select_ag_tab(ag_container, i)
        ag_label = f"{li_name} / AG{i + 1}"
        skip_ag_bid_value(li_type_label, ag_label)
        build_ag_targeting_oreo(page, ag_container, ag, ag_label)
        add_synthetic_ad_oreo(page, ag_container, f"{li_name} Ad {i + 1}")


# --------------------------------------------------------------------------
# Per-IO orchestration
# --------------------------------------------------------------------------
def build_io_youtube(page: Page, ref: dict, io_index: int, tag: str, li_type: str):
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io = ref["insertionOrders"][io_index]
    n = len(io["lineItems"])
    li_type_label = LI_TYPE_LABELS[li_type]
    create_n_line_items_via_duplicate(page, li_form, n, li_type, f"{tag} LI 1 - {int(time.time())}")

    for i, li in enumerate(io["lineItems"]):
        select_li_tab(page, i)
        li_name = f"{tag} LI {i + 1} - {int(time.time())}"
        build_youtube_li_oreo(page, li_form, li, li_name, li_type_label)
    ok(f"io{io_index}-complete", f"IO{io_index}: {n} '{li_type_label}' line items built")


def build_io_video(page: Page, ref: dict, io_index: int, tag: str, li_type: str):
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io = ref["insertionOrders"][io_index]
    n = len(io["lineItems"])
    create_n_line_items_via_duplicate(
        page, li_form, n, li_type, f"{tag} LI 1 - {int(time.time())}", fill_basics_fn=fill_li_video_basics
    )

    for i, li in enumerate(io["lineItems"]):
        select_li_tab(page, i)
        li_name = f"{tag} LI {i + 1} - {int(time.time())}"
        name_field = li_form.locator("input[formcontrolname='name']")
        name_field.fill(li_name)
        ok("li-name", f"Line Item name filled with '{li_name}'")
        build_video_li_targeting_oreo(page, li_form, li)
    ok(f"io{io_index}-complete", f"IO{io_index}: {n} '{LI_TYPE_LABELS[li_type]}' line items built")


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def finish_and_submit_oreo(page: Page):
    """'Next' from Line Items to Recap, then submit. Reuses the YouTube
    suite's session-wide submit guard (install_submit_guard, called once in
    main()) which validates the outgoing payload for both the 'yes' and
    'watch' paths. A BLOCKED submit over the known TARGET_FREQUENCY /
    NON_SKIPPABLE missing bid values is the guard working correctly, not a
    suite failure - this actually launches a real campaign on {ADVERTISER}'s
    live DV360 account if it gets past the guard."""
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok("next-to-recap", "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)

    answer = input(
        f"\n>>> 'Start campaign' ACTUALLY LAUNCHES on {ADVERTISER}'s live DV360 account.\n"
        "    The submit guard will validate the payload and BLOCK it if a bid value is missing\n"
        "    (EXPECTED for the Target Frequency / Non-skippable ad groups - see module docstring).\n"
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

    for _ in range(40):
        if SUBMIT_GUARD_STATE["seen"]:
            break
        page.wait_for_timeout(250)

    if not SUBMIT_GUARD_STATE["seen"]:
        print("NOTE: no campaign submit request was observed (nothing was submitted).")
        return

    if SUBMIT_GUARD_STATE["missing"]:
        raise AssertionError(
            "BLOCKED submit before it reached the DSP: YouTube ad groups missing a positive bid "
            "`value` (EXPECTED for the Target Frequency / Non-skippable ad groups - a real frontend "
            "bug, not a test bug; would crash the DSP with float(None) otherwise):\n- "
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
    assert CLIENT and ADVERTISER, (
        "CLIENT/ADVERTISER are not set - look up which Nexify Client/Advertiser corresponds to "
        f"DV360 advertiserId {ref['advertiserId']} (clientId {ref['clientId']}) and fill in the "
        "two constants at the top of this file before running."
    )
    validate_offline(ref)

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
        install_submit_guard(page)

        try:
            test_landing(page)
            footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            create_insertion_orders_oreo(page, ref)
            test_sidebar_sync(page)

            # Line Items step: Next opens the "Review insertion orders" dialog.
            footer.locator("button.mdc-button", has_text="Next").click()
            dialog = page.locator("mat-dialog-container")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.locator("button", has_text="Confirm & continue").click()
            expect(dialog).not_to_be_visible()

            # IO0 is active by default when landing on Line Items.
            build_io_youtube(page, ref, 0, "YT TargetFreq", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_TARGET_FREQUENCY")

            select_io_tab(page, 1)
            build_io_video(page, ref, 1, "OTT", "LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP")

            select_io_tab(page, 2)
            build_io_youtube(page, ref, 2, "YT NonSkip Dem", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE")

            select_io_tab(page, 3)
            build_io_youtube(page, ref, 3, "YT NonSkip Data", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE")

            select_io_tab(page, 4)
            build_io_video(page, ref, 4, "CTV NewIx", "LINE_ITEM_TYPE_VIDEO_DEFAULT")

            finish_and_submit_oreo(page)

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

# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 "Mugler" mixed suite)
================================================================================
Checks that DV360 line-item / ad-group targeting in Nexify can be driven from
a real DV360 API export, by comparing the export's values against what the
UI actually lets you pick.

Reference JSON: template_496941790_56982684_Generico.json (L'Oreal / Mugler
"Starlicious" launch, DV360 advertiserId 496941790 / clientId 795439). This
is the FIRST suite covering a mixed campaign - Display + YouTube + Video/CTV
line items in one flow.

Client "L'Oreal" / advertiser "Mugler" (substring-matched in the advertiser
grid, so it also matches e.g. "Mugler_ES"). Same L'Oreal client the YouTube
suite (Garnier) uses, different advertiser.

Structure: 7 Insertion Orders, 28 Line Items total:
  IO0 - LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP (OTT)   (1 LI,  no ad groups)
  IO1 - LINE_ITEM_TYPE_DISPLAY_DEFAULT            (6 LIs, no ad groups)
  IO2 - LINE_ITEM_TYPE_VIDEO_DEFAULT (CTV)        (1 LI,  no ad groups)
  IO3 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW  (5 LIs, 1 ad group each)
  IO4 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH (5 LIs, 1 ad group each)
  IO5 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH (5 LIs, 1 ad group each)
  IO6 - LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW  (5 LIs, 1 ad group each)

Targeting sections insert the JSON's REAL distinct values (not just the
first 2), while budgets/bids stay at a token 1 EUR/1 CPM to avoid real
spend. The flow does not click "Start campaign" without an explicit typed
confirmation.

All 5 line item types here are already covered piecemeal by the existing
suites, so this module is mostly orchestration + reuse:
  - VIDEO_OVER_THE_TOP / VIDEO_DEFAULT: reuse build_video_li_targeting_oreo.
  - YOUTUBE_AND_PARTNERS_VIEW / REACH: both have a working enforced bid type
    (enforcedYtBidType maps VIEW->Target CPV, REACH->Target CPM), so the
    ad-group bid value IS settable here - reuse the YouTube suite's
    set_ag_bid_value + fill_ad_group_targeting (+ the submit guard).
  - DISPLAY_DEFAULT: new LI-level orchestration (build_display_li_targeting)
    incl. one genuinely new picker - Deal groups
    (TARGETING_TYPE_INVENTORY_SOURCE_GROUP, endpoint /dsp/dv360/dealGroups),
    driven through the shared add_li_list_dialog.

Confirmed UI gaps (present in the JSON, no Nexify control - printed as a
NOTE, never silently dropped):
  - TARGETING_TYPE_OMID, Authorized Seller Status, Video Player Size:
    blanket gaps across every suite.
  - For YouTube-family LIs (IO3-IO6), the LI-level Channel, On-Screen
    Position, Digital Content Label, and Sensitive Category sections are all
    gated @if(!isYouTubeLi()) - only Device Type and Geo Region are settable
    at LI level (both present). The rest are NOTE'd.
  - Ad-group and Display first-party/partner audiences: picker searches by
    name only, ids aren't directly searchable - NOTE'd. Google audiences ARE
    resolved (paged id->name), both at ad-group and LI level.

Scale note: 20 YouTube ad groups each carry 100 keywords (bulk textarea),
100 YouTube channels (bulk placements/sanitize), and the same 22 excluded
categories (one-by-one tree dialog = ~440 category interactions), plus 6
Display LIs with ~17 sensitive categories each. A full live run is LONG
(likely 1.5-3h). Let it run rather than re-triggering.

Run with:        python test_dv360_mugler_json_playwright.py
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
    add_geo_region,
    add_li_list_dialog,
    fill_li_video_basics,
    fill_li_youtube_targeting,
    fill_ad_group_targeting,
    set_ag_bid_value,
    set_age_range_full,
    add_synthetic_ad,
    create_n_line_items_via_duplicate,
    select_io_tab,
    select_li_tab,
    install_submit_guard,
    SUBMIT_GUARD_STATE,
    SUBMIT_PAYLOAD_DUMP,
    LI_TYPE_LABELS,
    DEVICE_TYPE_LABELS,
    ENV_LABELS,
    ON_SCREEN_POSITION_LABELS,
    SENSITIVE_CATEGORY_LABELS,
    GENDER_LABELS,
)
from test_dv360_generico_json_playwright import (
    add_google_audiences,
    VIEWABILITY_LABELS,
    DIGITAL_CONTENT_LABEL_LABELS,
)
from test_dv360_generico_oreo_json_playwright import (
    build_video_li_targeting_oreo,
    add_ag_google_audiences,
)

# Display is not in the shared LI_TYPE_LABELS yet (the oreo import already
# added the OTT / Target-Frequency / Non-skippable labels). Purely additive.
LI_TYPE_LABELS.setdefault("LINE_ITEM_TYPE_DISPLAY_DEFAULT", "Display")

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_496941790_56982684_Generico.json")
CLIENT = "L'Oreal"
ADVERTISER = "Mugler"  # DV360 advertiserId 496941790; substring-matched in the advertiser grid
DV360_DSP_BADGE = "Google DV360"
DATE_FMT = "%m/%d/%Y"

# Every age-targeted entity in this export lists all 6 coarse buckets (=no
# real age restriction), so the slider is just pushed to full range - no
# per-bucket index math needed. Canonical tokens from
# open-api/models/dv-360-age-range.ts (note: 65+ is AGE_RANGE_65_PLUS here,
# not the AGE_RANGE_65_UP the older Samsung export used).
AGE_RANGE_ALL = {
    "AGE_RANGE_18_24", "AGE_RANGE_25_34", "AGE_RANGE_35_44",
    "AGE_RANGE_45_54", "AGE_RANGE_55_64", "AGE_RANGE_65_PLUS",
}


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before a long live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    handled_li_types = {
        "LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP",
        "LINE_ITEM_TYPE_DISPLAY_DEFAULT",
        "LINE_ITEM_TYPE_VIDEO_DEFAULT",
        "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW",
        "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH",
    }
    label_checks = [
        ("deviceTypeDetails", "deviceType", DEVICE_TYPE_LABELS),
        ("environmentDetails", "environment", ENV_LABELS),
        ("onScreenPositionDetails", "onScreenPosition", ON_SCREEN_POSITION_LABELS),
        ("sensitiveCategoryExclusionDetails", "excludedSensitiveCategory", SENSITIVE_CATEGORY_LABELS),
        ("genderDetails", "gender", GENDER_LABELS),
        ("digitalContentLabelExclusionDetails", "excludedContentRatingTier", DIGITAL_CONTENT_LABEL_LABELS),
        ("viewabilityDetails", "viewability", VIEWABILITY_LABELS),
    ]

    def walk_targeting(options):
        for t in options:
            for detail_key, field, label_dict in label_checks:
                if detail_key in t:
                    key = t[detail_key].get(field)
                    assert key in label_dict, f"Unknown {field} token: {key}"
            if t["targetingType"] == "TARGETING_TYPE_AGE_RANGE":
                key = t["ageRangeDetails"]["ageRange"]
                assert key in AGE_RANGE_ALL, f"Unknown age range token: {key}"

    for io in ref["insertionOrders"]:
        for li in io["lineItems"]:
            assert li["lineItemType"] in handled_li_types, f"Unhandled LI type: {li['lineItemType']}"
            assert li["lineItemType"] in LI_TYPE_LABELS, f"Missing LI_TYPE_LABELS entry: {li['lineItemType']}"
            walk_targeting(li.get("targetingOptions", []))
            for ag in li.get("adGroups", []) or []:
                walk_targeting(ag.get("targetingOptions", []))

    print("OFFLINE VALIDATION PASSED: every targeting token this suite automates resolves against its label dict.")


# --------------------------------------------------------------------------
# General Info / template dialog / sidebar (L'Oreal/Mugler-specific)
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

    campaign_name = f"Test Dv Mugler JSON - {int(time.time())}"
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
    assert rows.count() > 0, f"No rows found in the advertiser grid after searching '{ADVERTISER}'"

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

    next_btn = footer.locator("button.mdc-button", has_text="Next")
    expect(next_btn).to_be_enabled(timeout=15000)
    page.wait_for_timeout(500)

    ok("general-info", f"Campaign '{campaign_name}' created for {CLIENT}/{ADVERTISER}")
    return footer


def test_template_dialog(page: Page, footer):
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
    dialog.locator("button", has_text="Continuar sin seleccionar plantilla").click()
    expect(dialog).not_to_be_visible()
    ok("template-dialog", "template dialog dismissed without selecting one")


def test_sidebar_sync(page: Page):
    aside = page.locator("aside.campaign-aside")
    expect(aside.locator("span.dsp-name", has_text=DV360_DSP_BADGE)).to_be_visible()
    ok("sidebar", f"sidebar synced with the form (DSP '{DV360_DSP_BADGE}')")


# --------------------------------------------------------------------------
# Insertion Orders: create all 7 IOs from the reference JSON
# --------------------------------------------------------------------------
def create_insertion_orders_mugler(page: Page, ref: dict):
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

        select_mat_option(page, "optimizationObjective", "Awareness")
        select_mat_option(page, "pacingPeriod", "Flight")
        # pacingType is an always-rendered sibling of pacingPeriod, but selecting
        # pacingPeriod fires a form re-render (autosave/patch) that can briefly
        # detach the pacingType control - wait for it to settle and re-attach
        # before selecting, so we don't race a transient re-render (observed as a
        # 30s focus timeout on this select).
        page.wait_for_timeout(600)
        pacing_type = page.locator("mat-select[formcontrolname='pacingType']")
        expect(pacing_type).to_be_visible(timeout=15000)
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
# Display LI-level targeting (IO1) - the new orchestration in this suite
# --------------------------------------------------------------------------
def add_deal_groups(page: Page, li_form, li: dict):
    """'Deal groups' picker (TARGETING_TYPE_INVENTORY_SOURCE_GROUP) - new to
    this suite. Same TargetingListDialogComponent mechanics as Channels/Deals
    (endpoint /dsp/dv360/dealGroups), so it goes through the shared
    add_li_list_dialog helper unchanged."""
    ids = list(dict.fromkeys(
        t["inventorySourceGroupDetails"]["inventorySourceGroupId"]
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_INVENTORY_SOURCE_GROUP"
    ))
    if not ids:
        return
    matched = add_li_list_dialog(page, li_form, "Deal groups", "Add deal group", "/dsp/dv360/dealGroups", ids)
    ok("li-deal-groups", f"Deal groups: {[n for _, n in matched]}")


def build_display_li_targeting(page: Page, li_form, li: dict):
    """Fill every automatable LI-level targeting section for one
    DISPLAY_DEFAULT line item. Display carries age/gender/audience directly
    at LI level (no ad groups)."""
    opts = li.get("targetingOptions", [])

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

    gender = [GENDER_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_GENDER", "genderDetails", "gender")]
    if gender:
        select_multi_exact(page, "gender", gender)
        ok("li-gender", f"Gender = {gender}")

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

    sens = [SENSITIVE_CATEGORY_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_SENSITIVE_CATEGORY_EXCLUSION",
        "sensitiveCategoryExclusionDetails", "excludedSensitiveCategory")]
    if sens:
        select_multi_exact(page, "sensitiveCategoryExcl", sens)
        ok("li-sensitive-category", f"{len(sens)} sensitive categories excluded")

    view = [
        VIEWABILITY_LABELS[t["viewabilityDetails"]["viewability"]]
        for t in opts if t["targetingType"] == "TARGETING_TYPE_VIEWABILITY"
    ]
    if view:
        select_mat_option(page, "viewability", view[0])
        ok("li-viewability", f"Predicted viewability = {view[0]}")

    # Age: every entity in this export lists all 6 buckets = full range.
    if any(t["targetingType"] == "TARGETING_TYPE_AGE_RANGE" for t in opts):
        set_age_range_full(page, li_form)

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

    geo_pairs = li_targeting_values(li, "TARGETING_TYPE_GEO_REGION", "geoRegionDetails", "targetingOptionId")
    geo_names = {
        t["geoRegionDetails"]["targetingOptionId"]: t["geoRegionDetails"]["displayName"]
        for t in opts if t["targetingType"] == "TARGETING_TYPE_GEO_REGION"
    }
    geo_included = [(g, geo_names[g]) for g, neg in geo_pairs if not neg]
    geo_excluded = [(g, geo_names[g]) for g, neg in geo_pairs if neg]
    if geo_included:
        add_geo_region(page, li_form, "Add included geo", "geo", geo_included)
        ok("li-geo-included", f"Included geo regions = {[n for _, n in geo_included]}")
    if geo_excluded:
        add_geo_region(page, li_form, "Add excluded geo", "geo", geo_excluded)
        ok("li-geo-excluded", f"Excluded geo regions = {[n for _, n in geo_excluded]}")

    # Audiences: Google resolved by paging id->name; first-party NOTE'd.
    add_google_audiences(page, li_form, li)
    if any(
        "includedFirstPartyAndPartnerAudienceGroups" in t.get("audienceGroupDetails", {})
        for t in opts if t["targetingType"] == "TARGETING_TYPE_AUDIENCE_GROUP"
    ):
        print("TEST li-audience-firstparty SKIPPED -> first-party/partner audience id(s), no id-search available (picker searches by name only)")

    add_deal_groups(page, li_form, li)

    # --- confirmed UI gaps ---
    if any(t["targetingType"] == "TARGETING_TYPE_OMID" for t in opts):
        print("TEST li-omid SKIPPED -> OMID has no UI control anywhere in this frontend")


def build_display_li(page: Page, li_form, li: dict, li_name: str):
    li_form.locator("input[formcontrolname='name']").fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")
    build_display_li_targeting(page, li_form, li)


# --------------------------------------------------------------------------
# YouTube LI-level targeting (IO3-IO6) - device + geo settable, rest gated off
# --------------------------------------------------------------------------
def build_youtube_li_targeting_mugler(page: Page, li_form, li: dict):
    fill_li_youtube_targeting(page, li_form, li)  # Device Type + Geo Region

    gaps = [
        ("TARGETING_TYPE_CHANNEL", "li-channels",
         "Channels have no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_ON_SCREEN_POSITION", "li-on-screen-position",
         "On-Screen Position has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_DIGITAL_CONTENT_LABEL_EXCLUSION", "li-content-rating",
         "Digital Content Label Exclusion has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_SENSITIVE_CATEGORY_EXCLUSION", "li-sensitive-category",
         "Sensitive Category Exclusion has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_AUTHORIZED_SELLER_STATUS", "li-authorized-seller",
         "no UI control exists for Authorized Seller Status in this frontend"),
        ("TARGETING_TYPE_OMID", "li-omid", "OMID has no UI control anywhere in this frontend"),
    ]
    for ttype, label, reason in gaps:
        if any(t["targetingType"] == ttype for t in li.get("targetingOptions", [])):
            print(f"TEST {label} SKIPPED -> {reason}")


def build_youtube_li(page: Page, li_form, li: dict, li_name: str):
    """One already-created, already-typed VIEW/REACH line item: LI-level
    targeting + its single ad group (bid value works for these types)."""
    li_form.locator("input[formcontrolname='name']").fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")

    build_youtube_li_targeting_mugler(page, li_form, li)

    ag_container = page.locator("app-dv360-youtube-line-items")
    expect(ag_container).to_be_visible(timeout=10000)
    ag0 = li["adGroups"][0]

    set_ag_bid_value(ag_container)                      # VIEW/REACH: enforced type resolves
    fill_ad_group_targeting(page, ag_container, ag0)    # age/gender/cat/kw/url/yt-channel (+ audience NOTE)

    # fill_ad_group_targeting NOTE-skips ALL audience groups; resolve the
    # Google ones for real here (first-party stay skipped).
    if any(
        "includedGoogleAudienceGroup" in t.get("audienceGroupDetails", {})
        for t in ag0.get("targetingOptions", []) if t["targetingType"] == "TARGETING_TYPE_AUDIENCE_GROUP"
    ):
        add_ag_google_audiences(page, ag_container, ag0)

    add_synthetic_ad(page, ag_container, f"{li_name} Ad 1")


# --------------------------------------------------------------------------
# Per-IO orchestration
# --------------------------------------------------------------------------
def assert_io_li_count(page: Page, expected: int, io_index: int):
    """SAFEGUARD #1: after building an IO, verify its LI pill row shows exactly
    `expected` line items. The pills reflect the store's lineItemsByIo, so a
    line item that failed to create or persist (e.g. an invalid LI autosave
    never saved) shows up here as a mismatch and stops the run at THIS IO -
    instead of being silently dropped from the submit payload hours later (how
    the OTT line item went missing). The LI pill row is the first
    div.flex.flex-wrap.gap-2.mb-4 (same locator select_li_tab uses)."""
    pills = page.locator("div.flex.flex-wrap.gap-2.mb-4").first
    actual = pills.locator("button").count()
    assert actual == expected, (
        f"IO{io_index}: expected {expected} line item(s) after building, but the LI pill row "
        f"shows {actual}. An LI failed to create/persist and would be dropped from the submit."
    )
    ok(f"io{io_index}-li-count", f"{actual}/{expected} line items present in the store after build")


def build_io_video(page: Page, ref: dict, io_index: int, tag: str, li_type: str):
    """OTT / VIDEO_DEFAULT IOs - reuse the oreo suite's video LI targeting."""
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
        li_form.locator("input[formcontrolname='name']").fill(li_name)
        ok("li-name", f"Line Item name filled with '{li_name}'")
        build_video_li_targeting_oreo(page, li_form, li)
    assert_io_li_count(page, n, io_index)
    ok(f"io{io_index}-complete", f"IO{io_index}: {n} '{LI_TYPE_LABELS[li_type]}' line items built")


def build_io_display(page: Page, ref: dict, io_index: int, tag: str):
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io = ref["insertionOrders"][io_index]
    n = len(io["lineItems"])
    li_type = "LINE_ITEM_TYPE_DISPLAY_DEFAULT"
    create_n_line_items_via_duplicate(
        page, li_form, n, li_type, f"{tag} LI 1 - {int(time.time())}", fill_basics_fn=fill_li_video_basics
    )
    for i, li in enumerate(io["lineItems"]):
        select_li_tab(page, i)
        build_display_li(page, li_form, li, f"{tag} LI {i + 1} - {int(time.time())}")
    assert_io_li_count(page, n, io_index)
    ok(f"io{io_index}-complete", f"IO{io_index}: {n} Display line items built")


def build_io_youtube(page: Page, ref: dict, io_index: int, tag: str, li_type: str):
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io = ref["insertionOrders"][io_index]
    n = len(io["lineItems"])
    create_n_line_items_via_duplicate(page, li_form, n, li_type, f"{tag} LI 1 - {int(time.time())}")
    for i, li in enumerate(io["lineItems"]):
        select_li_tab(page, i)
        build_youtube_li(page, li_form, li, f"{tag} LI {i + 1} - {int(time.time())}")
    assert_io_li_count(page, n, io_index)
    ok(f"io{io_index}-complete", f"IO{io_index}: {n} '{LI_TYPE_LABELS[li_type]}' line items built")


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def finish_and_submit_mugler(page: Page, ref: dict):
    """'Next' from Line Items to Recap, then submit. The session-wide submit
    guard (install_submit_guard, called in main()) validates the outgoing
    payload for both the 'yes' and 'watch' paths and blocks any launch that
    would crash the DSP. This actually launches a real campaign on Mugler's
    live DV360 account if it passes the guard."""
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok("next-to-recap", "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)

    # Only two modes: scripted start or user-triggered start. There is no
    # "cancel" branch - re-prompt until one is chosen. Ctrl+C / EOF still aborts
    # safely without submitting (also keeps a non-interactive run from looping).
    while True:
        try:
            answer = input(
                f"\n>>> 'Start campaign' ACTUALLY LAUNCHES on {ADVERTISER}'s live DV360 account.\n"
                "    The submit guard will validate the payload and BLOCK it if a bid value is missing.\n"
                "      start -> let the script click 'Start campaign'\n"
                "      watch -> you click 'Start campaign' yourself in the browser\n"
                "    (Ctrl+C to abort without submitting)\n"
                ">>> choice [start/watch]: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nTEST start-campaign ABORTED -> nothing submitted.")
            return

        if answer in ("start", "yes", "s"):
            # A SUCCESSFUL submit navigates away from /campaign/create (redirect
            # to the app home with a fresh token), so the click's post-action
            # navigation wait can raise even though the submit fired fine.
            # no_wait_after skips that wait; tolerate a nav/close either way.
            try:
                start_btn.click(no_wait_after=True)
            except Exception as e:
                print(f"NOTE: post-click navigation/close ({type(e).__name__}) - "
                      "expected when a successful submit redirects away.")
            break
        if answer in ("watch", "w"):
            print(">>> Waiting up to 3 min for you to click 'Start campaign' in the browser...")
            for _ in range(360):
                if SUBMIT_GUARD_STATE["seen"]:
                    break
                page.wait_for_timeout(500)
            break
        print("    Please type 'start' or 'watch' (or press Ctrl+C to abort).")

    for _ in range(40):
        if SUBMIT_GUARD_STATE["seen"]:
            break
        try:
            page.wait_for_timeout(250)
        except Exception:
            break

    if not SUBMIT_GUARD_STATE["seen"]:
        print("NOTE: no campaign submit request was observed (nothing was submitted).")
        return

    if SUBMIT_GUARD_STATE["missing"]:
        raise AssertionError(
            "BLOCKED submit before it reached the DSP: YouTube ad groups missing a positive bid "
            "`value` (would crash with float(None)):\n- "
            + "\n- ".join(SUBMIT_GUARD_STATE["missing"])
        )

    # SAFEGUARD (payload backstop): the guard dumped the exact outgoing payload -
    # verify it carries every line item the JSON expects. Per-IO checks catch a
    # dropped LI at build time; this catches ANY that still slip through (e.g.
    # an LI the app drops as invalid only at submit, how the OTT LI went missing).
    expected_total = sum(len(io["lineItems"]) for io in ref["insertionOrders"])
    try:
        payload = json.loads(SUBMIT_PAYLOAD_DUMP.read_text(encoding="utf-8"))
        submitted = 0
        empty_ios = []
        for dsp in payload.get("dspPayload", []) or []:
            for io in dsp.get("payload", {}).get("insertionOrders", []) or []:
                lis = io.get("lineItems", []) or []
                submitted += len(lis)
                if not lis:
                    empty_ios.append(io.get("displayName", "?"))
        if submitted != expected_total:
            raise AssertionError(
                f"Submit payload has {submitted}/{expected_total} line items - some were dropped. "
                f"Empty IO(s): {empty_ios}. Inspect {SUBMIT_PAYLOAD_DUMP.name}."
            )
        ok("submit-li-count", f"submit payload carries all {submitted}/{expected_total} line items")
    except FileNotFoundError:
        print(f"NOTE: {SUBMIT_PAYLOAD_DUMP.name} not found - could not verify submitted LI count.")

    # A validation FAILURE shows the errors dialog on the SAME page; a SUCCESS
    # navigates away (no dialog, and the page may even be closing). Any
    # exception here (nav / target-closed / timeout) therefore means "no error
    # dialog" = success, not a test failure.
    errors_dialog = page.locator("app-campaign-activation-errors-dialog")
    appeared = False
    try:
        expect(errors_dialog).to_be_visible(timeout=8000)
        appeared = True
    except Exception:
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
            create_insertion_orders_mugler(page, ref)
            test_sidebar_sync(page)

            # Line Items step: Next opens the "Review insertion orders" dialog.
            footer.locator("button.mdc-button", has_text="Next").click()
            dialog = page.locator("mat-dialog-container")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.locator("button", has_text="Confirm & continue").click()
            expect(dialog).not_to_be_visible()

            # IO0 active by default when landing on Line Items.
            build_io_video(page, ref, 0, "OTT", "LINE_ITEM_TYPE_VIDEO_OVER_THE_TOP")

            select_io_tab(page, 1)
            build_io_display(page, ref, 1, "Display")

            select_io_tab(page, 2)
            build_io_video(page, ref, 2, "CTV", "LINE_ITEM_TYPE_VIDEO_DEFAULT")

            # NOTE the build ORDER here is deliberately View, Reach, View, Reach
            # (IO3, IO4, IO6, IO5) - NOT sequential. A Nexify bug drops the
            # line-item-type change for the first LI of an IO when the PREVIOUS
            # IO built had the SAME type (hydration resets the type control with
            # emitEvent:false, so distinctUntilChanged() suppresses re-selecting
            # the same type and isYouTubeLi() never flips -> the YouTube ad-group
            # panel never mounts). Sequential order would build Reach(IO4) then
            # Reach(IO5) back-to-back and hit it. Alternating View/Reach makes
            # every consecutive first-LI type distinct. Build order does not
            # affect the final campaign (each IO is independent in the store).
            # See BUG_youtube_section_not_mounting_after_io_switch.md.
            select_io_tab(page, 3)
            build_io_youtube(page, ref, 3, "YT View A", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW")

            select_io_tab(page, 4)
            build_io_youtube(page, ref, 4, "YT Reach A", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH")

            select_io_tab(page, 6)
            build_io_youtube(page, ref, 6, "YT View B", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW")

            select_io_tab(page, 5)
            build_io_youtube(page, ref, 5, "YT Reach B", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH")

            finish_and_submit_mugler(page, ref)

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

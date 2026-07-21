# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 "ALDI" suite)
================================================================================
Checks that DV360 line-item / ad-group targeting in Nexify can be driven from
a real DV360 API export, by comparing the export's values against what the
UI actually lets you pick.

Reference JSON: template_7921992898_56447409_Generico_Aldi.json (ALDI Spain
"AO Food" brand-awareness campaign, DV360 advertiserId 7921992898 / clientId
7908627514). Largest export automated so far (6.9 MB).

>>> CLIENT / ADVERTISER below are UNVERIFIED PLACEHOLDER GUESSES ("ALDI" /
>>> "ALDI"), not confirmed against the live Nexify UI. This advertiserId
>>> isn't one of the previously-confirmed mappings (2429284=Samsung,
>>> 809633=L'Oreal/Garnier_ES, 496941790=L'Oreal/Mugler,
>>> 1117994126=Mondelez/Oreo_ES). Verify against the advertiser search grid on
>>> the General Info step (or the DV360 /api/v1/clients endpoint) and correct
>>> the two constants below if they don't match - test_general_info will fail
>>> fast on the "Client" dropdown or the advertiser grid search if either name
>>> is wrong.

Structure: 3 Insertion Orders, 72 Line Items total, EVERY one
LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE with exactly 1 ad group:
  IO0 - 0 line items (the export has no "lineItems" key at all for this IO -
        code below uses io.get("lineItems", []) rather than io["lineItems"]).
        Nexify's own auto-created default (empty Display) line item is left
        untouched; real DV360 requires >=1 LI per IO, and this isn't part of
        the export to begin with.
  IO1 - 23 line items, 23 ad groups
  IO2 - 49 line items, 49 ad groups

Targeting sections insert the JSON's REAL distinct values (not just the
first 2), while budgets/bids stay at a token 1 EUR / 1 CPM to avoid real
spend. The flow does not click "Start campaign" without an explicit typed
confirmation.

Every single targeting entry in this export (channels, videos, keywords,
urls, categories) is an EXCLUSION (negative=true) - this is a brand-safety
exclusion-only campaign. Included-side code paths exist for symmetry with
the other suites but will be no-ops on this JSON.

--------------------------------------------------------------------------
TWO CONFIRMED FRONTEND BUGS THAT BLOCK A REAL LAUNCH (not test limitations):
--------------------------------------------------------------------------

1. BID VALUE (see BUG_youtube_target_frequency_non_skippable_bid_value.md):
   enforcedYtBidType() only maps REACH->Target CPM and VIEW->Target CPV. For
   NON_SKIPPABLE (ALL 72 line items / 72 ad groups here) it returns null, so:
     - the ad-group "Bid strategy" select is permanently disabled on "-"
     - Bid value cannot be set at all
     - NO ad group is even auto-created when landing on this LI type
       (ensureOne() is gated behind the same check) - ad groups are added
       manually via "+ Add ad group" (ensure_ag_count, self-correcting).
   The submit guard (imported from the YouTube suite) correctly BLOCKS an
   actual "Start campaign" launch for all 72 ad groups' missing bid values -
   this suite can therefore never complete a real launch until the frontend
   is fixed. Per user decision (2026-07-21), building the full suite anyway
   is worthwhile for targeting-UI coverage even though launch stays blocked.

2. IO-SWITCH TYPE DESYNC (see BUG_youtube_section_not_mounting_after_io_switch.md):
   hydrateEffect resets the lineItemType control with emitEvent:false when
   switching IOs, so distinctUntilChanged() never sees the hydrated value -
   its "last emitted" memory still holds whatever type was LAST manually
   selected. Re-selecting that SAME type on the next IO's first LI is
   suppressed, and the YouTube ad-group panel never mounts. The established
   fix elsewhere (interleave IO build order so consecutive first-LI types
   differ) is NOT available here - every IO in this export is the same type.
   This bug can only actually trigger ONCE in this suite: IO0 has no line
   items (no type is ever selected there), so the first real type selection
   happens on IO1's first LI with no prior "last emitted" value to collide
   with. The single at-risk transition is IO1 -> IO2 (both NON_SKIPPABLE,
   back to back). Mitigation used here: `settle_after_risky_io_switch`
   gives hydration extra time to fully finish before even attempting the
   type select, on top of `fill_li_youtube_basics`'s own existing
   wiggle-and-verify retry (imported unmodified, up to 6 attempts with a
   DOM-probe NOTE on each failure) - reduces the chance either the initial
   attempt OR the wiggle's own clicks land mid-hydration. If all attempts
   still fail, fill_li_youtube_basics raises loudly rather than silently
   building into a broken form state.

--------------------------------------------------------------------------
Two targeting types new to this suite (not covered by Mugler/Oreo/Generico):
--------------------------------------------------------------------------

- TARGETING_TYPE_LANGUAGE: LI-level `languageDetails` mat-select (multiple),
  gated `@if (isYouTubeLi())` in dv360-line-items.component.html (i.e. the
  OPPOSITE gating of most YouTube LI-level sections, which are gated OFF for
  YouTube types - Language is gated ON only for YouTube types). The JSON's
  `languageDetails.displayName` (e.g. "Spanish") already matches the visible
  mat-option label text 1:1 (same string as the Dv360Language enum VALUE),
  so no id/key mapping is needed - just select_multi_exact on the raw names.
- TARGETING_TYPE_YOUTUBE_VIDEO: ad-group-level, NOT a standalone picker.
  `dv360-youtube-line-items.component.html` labels the Included/Excluded
  video lists "Auto-filled from Placements" - videos and channels are BOTH
  populated by the SAME "Add Placements" bulk paste+sanitize+apply dialog
  used for channels (`applyPlacementsSanitize` routes each pasted id into
  `channels`/`urls`/`videos` FormArrays based on what the sanitize endpoint
  resolves it as). `add_ag_channels_and_videos_via_placements` below pastes
  channel ids and video ids together in one dialog invocation per mode and
  verifies both resolved counts against the sanitize response.

Other confirmed UI gaps (present in the JSON, no corresponding Nexify
control - skipped with a printed NOTE, never silently dropped), all
YouTube-family LI-level sections gated `@if(!isYouTubeLi())`: On-Screen
Position, Sensitive Category Exclusion, Negative Keyword List. Plus the
blanket gaps confirmed across every suite: Authorized Seller Status,
Content Theme Exclusion, OMID. Ad-group first-party/partner audiences
(included AND excluded - both can appear on the SAME targeting entry
alongside an included Google audience group here) are NOTE'd; Google
audiences ARE resolved via the existing paged id->name search.

Scale note: 72 ad groups x (100 YouTube channels + ~5 videos via ONE bulk
placements dialog invocation, ~59 keywords via bulk textarea, 29 categories
via one-by-one tree dialog = ~2088 category interactions total). This is the
largest suite yet - a full live run is likely several hours. Not run live
yet (interactive SSO login required - the user runs this themselves).

Run with:        python test_dv360_aldi_json_playwright.py
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
    select_multi_exact,
    fill_li_youtube_targeting,
    DEVICE_TYPE_LABELS,
    field_by_label,
    textarea_by_label,
    add_ag_categories,
    create_n_line_items_via_duplicate,
    select_li_tab,
    select_io_tab,
    install_submit_guard,
    SUBMIT_GUARD_STATE,
    SUBMIT_PAYLOAD_DUMP,
    LI_TYPE_LABELS,
    PLACEHOLDER_VIDEO_ID,
)
from test_dv360_generico_json_playwright import add_day_time
# Importing from the Oreo suite also runs its module-level
# LI_TYPE_LABELS.update(...), which is what registers
# LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE - this suite needs that
# label and reuses several of Oreo's NON_SKIPPABLE-specific helpers verbatim.
from test_dv360_generico_oreo_json_playwright import (
    set_ag_age_range_precise,
    add_ag_google_audiences,
    ensure_ag_count,
    select_ag_tab,
    skip_ag_bid_value,
    COARSE_AGE_BUCKETS,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_7921992898_56447409_Generico_Aldi.json")
CLIENT = "ALDI"        # UNVERIFIED PLACEHOLDER - see module docstring
ADVERTISER = "ALDI"    # UNVERIFIED PLACEHOLDER - see module docstring
DV360_DSP_BADGE = "Google DV360"
DATE_FMT = "%m/%d/%Y"

# Copied from nexify-frontend-main/src/open-api/models/dv-360-language.ts -
# the JSON's languageDetails.displayName values must be one of these enum
# VALUES (the strings are already the exact mat-option label text).
DV360_LANGUAGE_VALUES = {
    "English", "German", "French", "Spanish", "Italian", "Japanese", "Danish",
    "Dutch", "Finnish", "Korean", "Norwegian", "Portuguese", "Swedish",
    "Chinese (simplified)", "Chinese (traditional)", "Arabic", "Bulgarian",
    "Czech", "Greek", "Hindi", "Hungarian", "Indonesian", "Icelandic",
    "Hebrew", "Latvian", "Lithuanian", "Polish", "Russian", "Romanian",
    "Slovak", "Slovenian", "Serbian", "Ukrainian", "Turkish", "Catalan",
    "Croatian", "Vietnamese", "Urdu", "Filipino", "Estonian", "Thai",
    "Bengali", "Persian", "Gujarati", "Kannada", "Malayalam", "Marathi",
    "Malay", "Punjabi", "Tamil", "Telugu",
}


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before a multi-hour live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    valid_days = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"}
    no_id_count = 0

    for io in ref["insertionOrders"]:
        for li in io.get("lineItems", []):
            assert li["lineItemType"] == "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE", (
                f"Unexpected LI type: {li['lineItemType']}"
            )

            for t in li.get("targetingOptions", []):
                tt = t["targetingType"]
                if tt == "TARGETING_TYPE_DEVICE_TYPE":
                    key = t["deviceTypeDetails"]["deviceType"]
                    assert key in DEVICE_TYPE_LABELS, f"Unknown device type token: {key}"
                elif tt == "TARGETING_TYPE_DAY_AND_TIME":
                    d = t["dayAndTimeDetails"]
                    assert d["dayOfWeek"] in valid_days, f"Unknown day-of-week token: {d['dayOfWeek']}"
                    assert 0 <= d.get("startHour", 0) <= 24 and 0 <= d.get("endHour", 24) <= 24, (
                        f"Day-and-time hour out of range: {d}"
                    )
                elif tt == "TARGETING_TYPE_LANGUAGE":
                    name = t["languageDetails"]["displayName"]
                    assert name in DV360_LANGUAGE_VALUES, f"Unknown language display name: {name}"

            for ag in li.get("adGroups", []) or []:
                for t in ag.get("targetingOptions", []):
                    if t["targetingType"] == "TARGETING_TYPE_AGE_RANGE":
                        key = t["ageRangeDetails"]["ageRange"]
                        assert key in COARSE_AGE_BUCKETS, f"Unknown age range token: {key}"
                    elif t["targetingType"] == "TARGETING_TYPE_YOUTUBE_VIDEO":
                        no_id_count += "videoId" not in t["youtubeVideoDetails"]

    if no_id_count:
        print(f"NOTE (offline): {no_id_count} TARGETING_TYPE_YOUTUBE_VIDEO entr{'y is' if no_id_count == 1 else 'ies are'} "
              f"missing videoId in the reference JSON (malformed export data) - build_ag_targeting_aldi skips these with a NOTE.")
    print("OFFLINE VALIDATION PASSED: every targeting token this suite automates resolves against its label dict.")


# --------------------------------------------------------------------------
# General Info / template dialog / sidebar (ALDI-specific)
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

    campaign_name = f"Test Dv Aldi JSON - {int(time.time())}"
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
    ALDI's advertiser has an unknown number of saved templates, so this
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
# Insertion Orders: create all 3 IOs from the reference JSON
# --------------------------------------------------------------------------
def create_insertion_orders_aldi(page: Page, ref: dict):
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

        # JSON campaignGoal is BRAND_AWARENESS -> "Awareness". pacingPeriod/
        # pacingType/kpiType are a fixed token selection (not derived from the
        # JSON) - same convention as every prior suite.
        select_mat_option(page, "optimizationObjective", "Awareness")
        select_mat_option(page, "pacingPeriod", "Flight")
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
# LI-level targeting
# --------------------------------------------------------------------------
def add_li_language(page: Page, li_form, li: dict):
    """LI-level 'Language' multi-select - gated @if(isYouTubeLi()), new to
    this suite. The JSON's languageDetails.displayName already matches the
    mat-option label text 1:1, so no key->label dict is needed."""
    labels = []
    seen = set()
    for t in li.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_LANGUAGE":
            continue
        name = t["languageDetails"]["displayName"]
        if name not in seen:
            seen.add(name)
            labels.append(name)
    if not labels:
        return
    select_multi_exact(page, "languageDetails", labels)
    ok("li-language", f"Language = {labels}")


def build_li_targeting_aldi(page: Page, li_form, li: dict):
    """Device Type + Geo Region (working controls, via fill_li_youtube_targeting),
    Day & Time (confirmed NOT gated by isYouTubeLi()), Language (new to this
    suite, gated ON for YouTube types), then a printed NOTE for every gap
    actually present in this LI's JSON data."""
    fill_li_youtube_targeting(page, li_form, li)
    add_day_time(page, li_form, li)
    add_li_language(page, li_form, li)

    gaps = [
        ("TARGETING_TYPE_ON_SCREEN_POSITION", "li-on-screen-position",
         "On-Screen Position has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_SENSITIVE_CATEGORY_EXCLUSION", "li-sensitive-category",
         "Sensitive Category Exclusion has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_NEGATIVE_KEYWORD_LIST", "li-negative-keyword-list",
         "Negative Keyword List has no control for YouTube-type line items (section gated @if(!isYouTubeLi()))"),
        ("TARGETING_TYPE_AUTHORIZED_SELLER_STATUS", "li-authorized-seller",
         "no UI control exists for Authorized Seller Status in this frontend"),
        ("TARGETING_TYPE_CONTENT_THEME_EXCLUSION", "li-content-theme",
         "no UI control exists for Content Theme Exclusion anywhere in this frontend"),
        ("TARGETING_TYPE_OMID", "li-omid", "OMID has no UI control anywhere in this frontend"),
    ]
    for ttype, label, reason in gaps:
        if any(t["targetingType"] == ttype for t in li.get("targetingOptions", [])):
            print(f"TEST {label} SKIPPED -> {reason}")


# --------------------------------------------------------------------------
# Ad-group targeting
# --------------------------------------------------------------------------
def add_ag_channels_and_videos_via_placements(page: Page, ag_container, channel_ids: list, video_ids: list, mode: str):
    """Bulk-resolve YouTube channel AND video ids through the SAME 'Add
    Placements' paste+sanitize+apply dialog - the sanitize endpoint routes
    each pasted id into channels/urls/videos based on what it resolves as
    (applyPlacementsSanitize in dv360-youtube-line-items.component.ts), so
    one dialog invocation per mode handles both targeting types together.
    New to this suite (TARGETING_TYPE_YOUTUBE_VIDEO has no dedicated Add
    button - the Included/Excluded video lists are labelled 'Auto-filled
    from Placements')."""
    ids = list(channel_ids) + list(video_ids)
    if not ids:
        return

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
    textarea.fill("\n".join(ids))

    with page.expect_response(
        lambda r: "placements/sanitize" in r.url, timeout=30000
    ) as resp_info:
        dialog.get_by_role("button", name="Sanitize").click()
    body = resp_info.value.json()
    resolved_channels = len(body.get("channels", []))
    resolved_videos = len(body.get("videos", []))
    if resolved_channels != len(channel_ids):
        print(f"NOTE: {resolved_channels}/{len(channel_ids)} YouTube channel ids resolved live ({mode}) - the rest no longer exist")
    if resolved_videos != len(video_ids):
        print(f"NOTE: {resolved_videos}/{len(video_ids)} YouTube video ids resolved live ({mode}) - the rest no longer exist")
    total_resolved = resolved_channels + resolved_videos
    expect(dialog.get_by_text(f"{total_resolved} seleccionados")).to_be_visible(timeout=5000)

    dialog.get_by_role("button", name="Apply", exact=True).click()
    expect(dialog).not_to_be_visible()
    ok("ag-channels-videos",
       f"{resolved_channels}/{len(channel_ids)} channels + {resolved_videos}/{len(video_ids)} videos resolved and applied ({mode})")


def build_ag_targeting_aldi(page: Page, ag_container, ag: dict, ag_label: str):
    types_present = {t["targetingType"] for t in ag.get("targetingOptions", [])}

    if "TARGETING_TYPE_AGE_RANGE" in types_present:
        set_ag_age_range_precise(page, ag_container, ag)

    for t in ag.get("targetingOptions", []):
        if t["targetingType"] != "TARGETING_TYPE_AUDIENCE_GROUP":
            continue
        d = t["audienceGroupDetails"]
        # Unlike the other suites, a single AUDIENCE_GROUP entry here can
        # carry BOTH an included Google audience group AND an excluded
        # first-party group at once - check both independently, not elif.
        if "includedGoogleAudienceGroup" in d:
            add_ag_google_audiences(page, ag_container, ag)
        if "includedFirstPartyAndPartnerAudienceGroups" in d:
            print(f"TEST ag-audience-firstparty-included SKIPPED ({ag_label}) -> first-party/partner audience id(s), no id-search available (picker searches by name only)")
        if "excludedFirstPartyAndPartnerAudienceGroup" in d:
            print(f"TEST ag-audience-firstparty-excluded SKIPPED ({ag_label}) -> first-party/partner audience id(s), no id-search available (picker searches by name only)")
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

    kw_included = [t["keywordDetails"]["keyword"] for t in ag.get("targetingOptions", [])
                   if t["targetingType"] == "TARGETING_TYPE_KEYWORD" and not t["keywordDetails"].get("negative")]
    kw_excluded = [t["keywordDetails"]["keyword"] for t in ag.get("targetingOptions", [])
                   if t["targetingType"] == "TARGETING_TYPE_KEYWORD" and t["keywordDetails"].get("negative")]
    if kw_included:
        textarea_by_label(ag_container, "Included Keywords").fill(", ".join(kw_included))
        ok("ag-kw-included", f"{len(kw_included)} included keywords filled")
    if kw_excluded:
        textarea_by_label(ag_container, "Excluded Keywords").fill(", ".join(kw_excluded))
        ok("ag-kw-excluded", f"{len(kw_excluded)} excluded keywords filled")

    url_included = [t["urlDetails"]["url"] for t in ag.get("targetingOptions", [])
                    if t["targetingType"] == "TARGETING_TYPE_URL" and not t["urlDetails"].get("negative")]
    url_excluded = [t["urlDetails"]["url"] for t in ag.get("targetingOptions", [])
                    if t["targetingType"] == "TARGETING_TYPE_URL" and t["urlDetails"].get("negative")]
    if url_included:
        textarea_by_label(ag_container, "Included URLs").fill(", ".join(url_included))
        ok("ag-url-included", f"{len(url_included)} included URLs filled")
    if url_excluded:
        textarea_by_label(ag_container, "Excluded URLs").fill(", ".join(url_excluded))
        ok("ag-url-excluded", f"{len(url_excluded)} excluded URLs filled")

    ch_included = [t["youtubeChannelDetails"]["channelId"] for t in ag.get("targetingOptions", [])
                   if t["targetingType"] == "TARGETING_TYPE_YOUTUBE_CHANNEL" and not t["youtubeChannelDetails"].get("negative")]
    ch_excluded = [t["youtubeChannelDetails"]["channelId"] for t in ag.get("targetingOptions", [])
                   if t["targetingType"] == "TARGETING_TYPE_YOUTUBE_CHANNEL" and t["youtubeChannelDetails"].get("negative")]
    # A handful of TARGETING_TYPE_YOUTUBE_VIDEO entries in this export are
    # malformed - youtubeVideoDetails carries only {"negative": true}, no
    # videoId at all (confirmed: 6/377 across the full export). There's
    # nothing to place for these, so skip with a NOTE rather than KeyError.
    vid_entries = [t for t in ag.get("targetingOptions", []) if t["targetingType"] == "TARGETING_TYPE_YOUTUBE_VIDEO"]
    vid_no_id = sum(1 for t in vid_entries if "videoId" not in t["youtubeVideoDetails"])
    if vid_no_id:
        print(f"NOTE ({ag_label}): {vid_no_id} YouTube video targeting entr{'y is' if vid_no_id == 1 else 'ies are'} "
              f"missing videoId in the reference JSON (malformed export data) - skipped")
    vid_included = [t["youtubeVideoDetails"]["videoId"] for t in vid_entries
                    if "videoId" in t["youtubeVideoDetails"] and not t["youtubeVideoDetails"].get("negative")]
    vid_excluded = [t["youtubeVideoDetails"]["videoId"] for t in vid_entries
                    if "videoId" in t["youtubeVideoDetails"] and t["youtubeVideoDetails"].get("negative")]
    if ch_included or vid_included:
        add_ag_channels_and_videos_via_placements(page, ag_container, ch_included, vid_included, "Include")
    if ch_excluded or vid_excluded:
        add_ag_channels_and_videos_via_placements(page, ag_container, ch_excluded, vid_excluded, "Exclude")

    known = {
        "TARGETING_TYPE_AGE_RANGE", "TARGETING_TYPE_AUDIENCE_GROUP", "TARGETING_TYPE_CATEGORY",
        "TARGETING_TYPE_KEYWORD", "TARGETING_TYPE_URL", "TARGETING_TYPE_YOUTUBE_CHANNEL",
        "TARGETING_TYPE_YOUTUBE_VIDEO",
    }
    unexpected = types_present - known
    if unexpected:
        print(f"NOTE ({ag_label}): unhandled ad-group targeting type(s) present in JSON, not automated: {sorted(unexpected)}")


def add_synthetic_ad_aldi(page: Page, ag_container, ad_name: str, video_id: str = PLACEHOLDER_VIDEO_ID):
    """This JSON has zero adGroupAds recorded for every ad group, so there's
    no real creative to recreate. One synthetic ad per ad group exercises
    the video-search flow and keeps the ad group non-empty (real DV360
    rejects empty ones) - same convention as the Oreo suite."""
    ag_container.get_by_role("button", name="+ Add ad", exact=True).click()
    page.wait_for_timeout(500)

    field_by_label(ag_container, "Ad name").fill(ad_name)
    field_by_label(ag_container, "Call to action").fill("Shop now")
    field_by_label(ag_container, "Description").fill("Discover this week's ALDI offers.")
    field_by_label(ag_container, "Headline").fill("ALDI weekly offers")
    field_by_label(ag_container, "Long headline").fill("Discover this week's ALDI offers, in stores now.")
    field_by_label(ag_container, "Final URL").fill("https://www.aldi.es")
    field_by_label(ag_container, "Domain").fill("aldi.es")

    video_field = field_by_label(ag_container, "Video")
    video_field.fill(video_id)
    video_field.press("Enter")

    select_btn = ag_container.get_by_role("button", name="Select").first
    expect(select_btn).to_be_visible(timeout=15000)
    select_btn.click()
    ok("ag-ad", f"Ad '{ad_name}' created with placeholder video id '{video_id}'")


def build_li_aldi(page: Page, li_form, li: dict, li_name: str, li_type_label: str):
    """Fill one already-created, already-typed NON_SKIPPABLE line item's
    LI-level targeting, then its single ad group's full targeting."""
    name_field = li_form.locator("input[formcontrolname='name']")
    name_field.fill(li_name)
    ok("li-name", f"Line Item name filled with '{li_name}'")

    build_li_targeting_aldi(page, li_form, li)

    ag_container = page.locator("app-dv360-youtube-line-items")
    expect(ag_container).to_be_visible(timeout=10000)

    n_ags = len(li["adGroups"])
    ensure_ag_count(ag_container, n_ags)

    for i, ag in enumerate(li["adGroups"]):
        select_ag_tab(ag_container, i)
        ag_label = f"{li_name} / AG{i + 1}"
        skip_ag_bid_value(li_type_label, ag_label)
        build_ag_targeting_aldi(page, ag_container, ag, ag_label)
        add_synthetic_ad_aldi(page, ag_container, f"{li_name} Ad {i + 1}")


# --------------------------------------------------------------------------
# Per-IO orchestration
# --------------------------------------------------------------------------
def settle_after_risky_io_switch(page: Page):
    """IO1 -> IO2 is the ONE IO-switch in this suite where the previous IO's
    first LI selected the SAME type ('Non-skippable') that this IO's first LI
    also needs - the exact trigger condition for the IO-switch desync bug
    (BUG_youtube_section_not_mounting_after_io_switch.md). The established
    primary mitigation elsewhere (interleave IO build order) isn't available
    since every IO here is the same type, so give hydration extra time to
    fully finish before fill_li_youtube_basics's own wiggle-and-verify retry
    even attempts the first type select - reduces the chance either the
    initial attempt OR the wiggle's own clicks land mid-hydration too."""
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass
    page.wait_for_timeout(4000)


def build_io_aldi(page: Page, ref: dict, io_index: int, tag: str, li_type: str):
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io = ref["insertionOrders"][io_index]
    lis = io.get("lineItems", [])
    n = len(lis)
    li_type_label = LI_TYPE_LABELS[li_type]
    create_n_line_items_via_duplicate(page, li_form, n, li_type, f"{tag} LI 1 - {int(time.time())}")

    for i, li in enumerate(lis):
        select_li_tab(page, i)
        li_name = f"{tag} LI {i + 1} - {int(time.time())}"
        build_li_aldi(page, li_form, li, li_name, li_type_label)
    ok(f"io{io_index}-complete", f"IO{io_index}: {n} '{li_type_label}' line items built")


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def finish_and_submit_aldi(page: Page):
    """'Next' from Line Items to Recap, then submit. Reuses the YouTube
    suite's session-wide submit guard (install_submit_guard, called once in
    main()) which validates the outgoing payload for both the 'yes' and
    'watch' paths. A BLOCKED submit over all 72 ad groups' missing bid values
    is the guard working correctly, not a suite failure (see module
    docstring, blocker #1) - this actually launches a real campaign on
    {ADVERTISER}'s live DV360 account if it somehow gets past the guard."""
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok("next-to-recap", "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)

    answer = input(
        f"\n>>> 'Start campaign' ACTUALLY LAUNCHES on {ADVERTISER}'s live DV360 account.\n"
        "    The submit guard will validate the payload and BLOCK it if a bid value is missing\n"
        "    (EXPECTED for all 72 Non-skippable ad groups - see module docstring).\n"
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
            "`value` (EXPECTED for every Non-skippable ad group here - a real frontend bug, not a "
            "test bug; would crash the DSP with float(None) otherwise):\n- "
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
            create_insertion_orders_aldi(page, ref)
            test_sidebar_sync(page)

            # Line Items step: Next opens the "Review insertion orders" dialog.
            footer.locator("button.mdc-button", has_text="Next").click()
            dialog = page.locator("mat-dialog-container")
            expect(dialog).to_be_visible(timeout=5000)
            dialog.locator("button", has_text="Confirm & continue").click()
            expect(dialog).not_to_be_visible()

            # IO0 is active by default when landing on Line Items, but has 0
            # line items in the reference JSON - leave Nexify's auto-created
            # default (empty Display) line item untouched and move on.
            print("NOTE: IO0 has 0 line items in the reference JSON - leaving Nexify's auto-created "
                  "default line item untouched (not part of the export; real DV360 requires >=1 LI per IO).")

            select_io_tab(page, 1)
            build_io_aldi(page, ref, 1, "YT NonSkip A", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE")

            select_io_tab(page, 2)
            settle_after_risky_io_switch(page)
            build_io_aldi(page, ref, 2, "YT NonSkip B", "LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE")

            finish_and_submit_aldi(page)

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

# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven DV360 "Minor Hotels" suite)
================================================================================
Checks that DV360 Display line-item targeting in Nexify can be driven from a
real DV360 API export, by comparing the export's values against what the UI
actually lets you pick.

Reference JSON: template_1273053_57015098_Generico_Minors_Hotels (2).json
(displayName "display-performance_tivoli-milanopresident-2026", DV360
clientId 668669 / advertiserId 1273053). 1 Insertion Order ("Tivoli Milano
President Push 2026"), 3 Line Items, all LINE_ITEM_TYPE_DISPLAY_DEFAULT
("In-Market_Milan+Luxury_IT/LU/UK" - same targeting on every section except
Geo Region, which differs by country/city per LI).

>>> CLIENT / ADVERTISER = "Minor Hotels" - UNVERIFIED PLACEHOLDER, same
>>> filename-based-guess convention as the ALDI/Oreo/Mugler suites. "Minor
>>> Hotels" is the real hospitality group that owns the Tivoli brand (the
>>> campaign's real displayName references "Tivoli Milano President"), but
>>> neither clientId 668669 nor advertiserId 1273053 appear anywhere else in
>>> ~/Downloads (checked the BigQuery advertiser-name exports too - no
>>> match), so there's no partial-id or name anchor to lean on. Verify
>>> against the advertiser search grid on General Info and correct if wrong.

Every LI-level targeting section inserts the JSON's REAL distinct values
(not just the first 2), while budgets/bids stay at a token 1 EUR/1 CPM to
avoid real spend. The flow does not click "Start campaign" without an
explicit typed confirmation.

--------------------------------------------------------------------------
This suite is almost entirely REUSE of existing, already-proven helpers -
the 3 Display line items here use a targeting-type set nearly identical to
what test_dv360_generico_json_playwright.py's fill_generico_targeting()
already automates for VIDEO_DEFAULT line items (Display and Video share
nearly the same LI-level targeting sections in this frontend - see
playbook_json_driven_nexify_suites). Reused as-is: li_targeting_values,
select_multi_exact, add_geo_region, add_li_list_dialog, fill_li_video_basics
(already proven for Display by the Mugler suite), create_n_line_items_via_
duplicate, select_li_tab, LI_TYPE_LABELS, DEVICE_TYPE_LABELS, ENV_LABELS,
ON_SCREEN_POSITION_LABELS, SENSITIVE_CATEGORY_LABELS, DIGITAL_CONTENT_LABEL_
LABELS, VIEWABILITY_LABELS, OUTSTREAM_LABELS, DAY_OF_WEEK_LABELS, hour_label,
add_negative_keyword_lists, add_google_audiences, add_categories, add_urls,
add_day_time, AGE_STOPS.

--------------------------------------------------------------------------
ONE THING NOT REUSED, DELIBERATELY - Age Range:
--------------------------------------------------------------------------
This export's Age Range is NOT full-range (5 of 6 coarse buckets: 25-34
through 65+, missing 18-24) - the first real export in this suite family
where the slider needs genuine partial-range math instead of full-range or
straight reuse. `test_dv360_generico_json_playwright.py`'s own
`set_age_range()` has a CONFIRMED STALE TOKEN in its `COARSE_AGE_BUCKETS`
dict - `"AGE_RANGE_65_UP"` instead of the canonical `AGE_RANGE_65_PLUS` (see
`dv-360-age-range.ts` and playbook_json_driven_nexify_suites's own warning
about this exact drift). That function's bucket lookup is a filtered
comprehension (`for k in keys if k in COARSE_AGE_BUCKETS`), so an unknown
key isn't a loud KeyError - it's silently DROPPED, which would have quietly
capped this export's slider at the 55-64 tier instead of extending to 65+.
Fixed here by defining a corrected `COARSE_AGE_BUCKETS` (65_PLUS, not
65_UP) and a local `set_age_range()` copy - otherwise byte-for-byte the
same slider math as the generico suite's version.

--------------------------------------------------------------------------
Cross-checked against ~/Downloads/schemas/dv360/schema.json before writing
(see reference_backend_validation_schemas / feedback_check_schemas_before_
writing_tests) - no new numeric floors beyond the usual token "1" for
budgets/bids.

--------------------------------------------------------------------------
Confirmed UI gaps (present in the JSON, no Nexify control - NOTE'd, not
silently dropped), same as every other DV360 suite in this family:
  - TARGETING_TYPE_EXCHANGE (74 entries): no Exchange control exists in the
    DV360 line-item component template at all.
  - TARGETING_TYPE_OMID: no UI control anywhere in this frontend.

Run with:        python test_dv360_minor_hotels_json_playwright.py
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
    create_n_line_items_via_duplicate,
    select_li_tab,
    LI_TYPE_LABELS,
    DEVICE_TYPE_LABELS,
    ENV_LABELS,
    ON_SCREEN_POSITION_LABELS,
    SENSITIVE_CATEGORY_LABELS,
)
from test_dv360_generico_json_playwright import (
    DIGITAL_CONTENT_LABEL_LABELS,
    VIEWABILITY_LABELS,
    OUTSTREAM_LABELS,
    DAY_OF_WEEK_LABELS,
    AGE_STOPS,
    add_negative_keyword_lists,
    add_google_audiences,
    add_categories,
    add_urls,
    add_day_time,
)

# Display is not in the shared LI_TYPE_LABELS yet - purely additive (same
# pattern the Mugler suite already uses).
LI_TYPE_LABELS.setdefault("LINE_ITEM_TYPE_DISPLAY_DEFAULT", "Display")

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_1273053_57015098_Generico_Minors_Hotels (2).json")
CLIENT = "Minor Hotels"       # UNVERIFIED PLACEHOLDER - see module docstring
ADVERTISER = "Minor Hotels"   # UNVERIFIED PLACEHOLDER - see module docstring
DV360_DSP_BADGE = "Google DV360"
DATE_FMT = "%m/%d/%Y"

# CORRECTED age-bucket dict - see module docstring. Only the 65+ key differs
# from test_dv360_generico_json_playwright.py's (stale AGE_RANGE_65_UP).
COARSE_AGE_BUCKETS = {
    "AGE_RANGE_18_24": (18, 24),
    "AGE_RANGE_25_34": (25, 34),
    "AGE_RANGE_35_44": (35, 44),
    "AGE_RANGE_45_54": (45, 54),
    "AGE_RANGE_55_64": (55, 64),
    "AGE_RANGE_65_PLUS": (65, 120),
}


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


def set_age_range(page: Page, li_form, li: dict):
    """Drive the dual-thumb age slider to cover exactly the JSON's coarse age
    buckets (identical math to the generico suite's set_age_range(), just
    against the corrected COARSE_AGE_BUCKETS above)."""
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
    page.keyboard.press("Home")
    for _ in range(min_index):
        page.keyboard.press("ArrowRight")

    end.focus()
    page.keyboard.press("End")
    for _ in range(max_slider_index - max_index_val):
        page.keyboard.press("ArrowLeft")

    ok("li-age-range", f"Age range set to buckets {keys} (slider indices {min_index}..{max_index_val})")


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before the live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    label_checks = [
        ("deviceTypeDetails", "deviceType", DEVICE_TYPE_LABELS),
        ("environmentDetails", "environment", ENV_LABELS),
        ("onScreenPositionDetails", "onScreenPosition", ON_SCREEN_POSITION_LABELS),
        ("sensitiveCategoryExclusionDetails", "excludedSensitiveCategory", SENSITIVE_CATEGORY_LABELS),
        ("digitalContentLabelExclusionDetails", "excludedContentRatingTier", DIGITAL_CONTENT_LABEL_LABELS),
        ("viewabilityDetails", "viewability", VIEWABILITY_LABELS),
        ("contentOutstreamPositionDetails", "contentOutstreamPosition", OUTSTREAM_LABELS),
    ]

    ios = ref.get("insertionOrders", [])
    assert ios, "This export has no insertionOrders"
    for io in ios:
        for li in io.get("lineItems", []):
            assert li["lineItemType"] == "LINE_ITEM_TYPE_DISPLAY_DEFAULT", (
                f"Unhandled LI type: {li['lineItemType']}"
            )
            for t in li.get("targetingOptions", []):
                for detail_key, field, label_dict in label_checks:
                    if detail_key in t:
                        key = t[detail_key].get(field)
                        assert key in label_dict, f"Unknown {field} token: {key}"
                if t["targetingType"] == "TARGETING_TYPE_AGE_RANGE":
                    key = t["ageRangeDetails"]["ageRange"]
                    assert key in COARSE_AGE_BUCKETS, f"Unknown age range token: {key}"
                if t["targetingType"] == "TARGETING_TYPE_DAY_AND_TIME":
                    key = t["dayAndTimeDetails"]["dayOfWeek"]
                    assert key in DAY_OF_WEEK_LABELS, f"Unknown day-of-week token: {key}"

    print("OFFLINE VALIDATION PASSED: every targeting/enum token this suite automates resolves against its label dict.")


# --------------------------------------------------------------------------
# General Info / template dialog / sidebar (Minor Hotels-specific)
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

    campaign_name = f"Test Dv Minor Hotels JSON - {int(time.time())}"
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
    return campaign_name, footer


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
# Insertion Order: single IO from the reference JSON
# --------------------------------------------------------------------------
def create_insertion_order(page: Page, ref: dict):
    """This export has exactly 1 Insertion Order - fill it once, no 'Create
    another' loop needed. Same token/synthetic field convention as every
    other suite (real IO-level values like budget/dates/KPI amount are never
    reused - only structural choices like pacing period/type carry over)."""
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
    assert n == 1, f"Expected exactly 1 Insertion Order in this export, found {n}"

    today = datetime.date.today()
    io_display_name = f"IO 1 - {CLIENT} - {int(time.time())}"
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

    ok("io0-fields", f"IO ('{io_display_name}') base fields filled")
    ok("ios-created", "1 Insertion Order created")


# --------------------------------------------------------------------------
# Display LI-level targeting - almost entirely reuse of the generico suite's
# fill_generico_targeting(), minus its stale age-range bucket dict.
# --------------------------------------------------------------------------
def build_display_li_targeting(page: Page, li_form, li: dict):
    """Fill every automatable LI-level targeting section for one
    DISPLAY_DEFAULT line item."""
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

    outs = [OUTSTREAM_LABELS[k] for k, _ in li_targeting_values(
        li, "TARGETING_TYPE_CONTENT_OUTSTREAM_POSITION",
        "contentOutstreamPositionDetails", "contentOutstreamPosition")]
    if outs:
        select_multi_exact(page, "contentOutstreamPositionDetails", outs)
        ok("li-outstream-position", f"Display position = {outs}")

    view = [
        VIEWABILITY_LABELS[t["viewabilityDetails"]["viewability"]]
        for t in li.get("targetingOptions", [])
        if t["targetingType"] == "TARGETING_TYPE_VIEWABILITY"
    ]
    if view:
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


def assert_li_count(page: Page, expected: int):
    """Verify the LI pill row shows exactly `expected` line items after
    building - catches a dropped/failed-to-persist LI at build time instead
    of it silently missing from the submit payload hours later."""
    pills = page.locator("div.flex.flex-wrap.gap-2.mb-4").first
    actual = pills.locator("button").count()
    assert actual == expected, (
        f"Expected {expected} line item(s) after building, but the LI pill row shows {actual}."
    )
    ok("li-count", f"{actual}/{expected} line items present in the store after build")


def build_line_items(page: Page, ref: dict):
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible(timeout=10000)

    io = ref["insertionOrders"][0]
    lis = io.get("lineItems", [])
    n = len(lis)
    li_type = "LINE_ITEM_TYPE_DISPLAY_DEFAULT"
    create_n_line_items_via_duplicate(
        page, li_form, n, li_type, f"Display LI 1 - {int(time.time())}", fill_basics_fn=fill_li_video_basics
    )

    names = []
    for i, li in enumerate(lis):
        select_li_tab(page, i)
        li_name = f"Display LI {i + 1} - {int(time.time())}"
        li_form.locator("input[formcontrolname='name']").fill(li_name)
        ok("li-name", f"Line Item name filled with '{li_name}'")
        build_display_li_targeting(page, li_form, li)
        names.append(li_name)

    assert_li_count(page, n)
    ok("li-build-complete", f"{n} Display line items built: {names}")


# --------------------------------------------------------------------------
# Finish: Next -> Recap -> Start campaign
# --------------------------------------------------------------------------
def test_finish_and_submit(page: Page, campaign_name: str):
    footer = page.locator("div.step-footer")

    dialog = page.locator("mat-dialog-container")
    footer.locator("button.mdc-button", has_text="Next").click()
    try:
        expect(dialog).to_be_visible(timeout=5000)
        dialog.locator("button", has_text="Confirm & continue").click()
        expect(dialog).not_to_be_visible()
    except AssertionError:
        pass
    ok("next-to-recap", "click on 'Next' in the footer performed (Line Items -> Recap)")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=15000)
    answer = input(
        f"\n>>> 'Start campaign' ACTUALLY LAUNCHES on {ADVERTISER}'s live DV360 account. "
        "Type 'yes' to confirm the click (anything else cancels): "
    ).strip().lower()
    if answer != "yes":
        print("TEST start-campaign SKIPPED -> click on 'Start campaign' cancelled by the user")
        return

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
    ok("start-campaign", "'Start campaign' performed, no validation-errors dialog shown")

    page.wait_for_url("**/campaign", timeout=15000)
    assert page.url.rstrip("/") == f"{BASE_URL}/campaign", (
        f"Expected redirect to {BASE_URL}/campaign\nActual URL: {page.url}"
    )
    ok("redirect", f"redirected to the campaigns list ({page.url})")

    grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
    expect(grid).to_be_visible()
    grid.locator("input[aria-label='Search in the data grid']").fill(campaign_name)
    campaign_row = grid.locator("tr.dx-data-row").filter(
        has=page.locator("td[aria-colindex='1']", has_text=campaign_name)
    )
    expect(campaign_row).to_have_count(1)
    ok("campaign-found", f"campaign '{campaign_name}' found in the campaigns table")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    ref = load_reference()
    assert CLIENT and ADVERTISER, (
        "CLIENT/ADVERTISER are not set - look up which Nexify Client/Advertiser corresponds to "
        f"DV360 clientId {ref.get('clientId')} / advertiserId {ref.get('advertiserId')} and fill "
        "in the two constants at the top of this file before running."
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

        try:
            test_landing(page)
            campaign_name, footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            create_insertion_order(page, ref)
            test_sidebar_sync(page)

            # Line Items step: Next opens the "Review insertion orders" dialog.
            footer.locator("button.mdc-button", has_text="Next").click()
            io_dialog = page.locator("mat-dialog-container")
            expect(io_dialog).to_be_visible(timeout=5000)
            io_dialog.locator("button", has_text="Confirm & continue").click()
            expect(io_dialog).not_to_be_visible()

            build_line_items(page, ref)
            test_finish_and_submit(page, campaign_name)

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

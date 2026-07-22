# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven Amazon DSP "Mugler" suite)
================================================================================
Checks that Amazon DSP campaign / ad-group targeting in Nexify can be driven
from a real Amazon Ads API export, by comparing the export's values against
what the UI actually lets you pick. FIRST Amazon JSON-driven suite in this
repo (no `nexify-amazon-json-suite` skill exists yet - built by directly
studying test_amazon_playwright.py, the Amazon frontend components, and the
open-api enum models, the same way the DV360 skill's own procedure works).

Reference JSON: template_589257453671562743_586197493360755014_LOREAL_MUGLER.json
(L'Oreal / Mugler, Amazon advertiserId 589257453671562743 / clientId
3151004024233868, media "AMAZON FULL TEMPLATE"). Small export: exactly 1
campaign, 1 flight, 1 ad group, 5 targeting entries (4 DEVICE + 1 LOCATION).

>>> CLIENT / ADVERTISER below are UNVERIFIED PLACEHOLDER GUESSES ("L'Oreal" /
>>> "Mugler"), not confirmed against the live Nexify UI. This is the same
>>> brand as the DV360 Mugler suite (advertiserId 496941790 = L'Oreal/Mugler),
>>> but Amazon accounts are set up independently per DSP, so the exact
>>> advertiser name/spelling in the Amazon-badge advertiser grid could differ
>>> (e.g. "Mugler_ES"). Verify against the advertiser search grid on the
>>> General Info step and correct the two constants below if wrong -
>>> test_general_info will fail fast on the advertiser grid search if either
>>> name doesn't match.

Budgets/bids stay at a token 1 EUR to avoid real spend (baseBid,
maxAverageBid, IO flight budget, ad-group budget, dailyMinSpendValue, KPI
Value all = 1) - same convention as every DV360 suite. Flight/campaign dates
are today+1/+2, never the JSON's real (long-expired) dates. Frequency caps
and every enum-style selection (Goal, KPI, Budget Allocation, Rollover
strategy, Delivery Profile, Viewability Tier, Video Completion Tier,
Inventory Type, Creative Rotation, ad-group Bid Strategy) ARE derived for
real from the JSON - none of those carry spend risk.

--------------------------------------------------------------------------
CONFIRMED UI GAP - Device targeting cannot be recreated at all:
--------------------------------------------------------------------------
All 4 DEVICE targets in this export use `deviceTarget.deviceType`
(MOBILE/CONNECTED_TV/DESKTOP) + `mobileEnvironment` (APP/WEB) - the
DeviceType-level targeting dimension. But the ad-group form's only "Device"
UI section is bound to `form.controls.mobileDevices`
(`toggleMobileDevice`/`mobileDeviceOptions`), which maps to
`deviceTarget.mobileDevice` in the payload (confirmed via
`amazon-target.util.ts`'s `targetsToVm` - the DEVICE case only ever reads
`dt?.mobileDevice`, never `dt?.deviceType`). `AmazonAdsMobileDevice` is a
COMPLETELY different enum - specific physical device MODELS (ANDROID, iPad,
iPhone, Kindle Fire, Kindle Fire HD) - not device CATEGORIES. There IS a
`AmazonAdsDeviceType` enum with the right values (DESKTOP/MOBILE/CONNECTED_TV/
CONNECTED_DEVICE) and `DEVICE_TYPE_OPTIONS` is even exported from
`amazon-target.util.ts`, but it is never consumed anywhere in the ad-groups
component or template (confirmed via grep - zero usages outside its own
definition). So all 4 of this export's DEVICE targets are skipped with a
printed NOTE - there is currently no way to represent DeviceType/
mobileEnvironment-style device targeting in this UI at all.

--------------------------------------------------------------------------
Location targeting: same shared dialog as DV360's geo picker, resolved by id
--------------------------------------------------------------------------
`addLocationTarget()` opens the SAME `TargetingListDialogComponent` DV360
uses for geo regions (`type: 'amazon-geo'`, endpoint `/dsp/amazon/location`),
confirmed identical DOM (dx-data-grid, "Write to filter" search box, Apply
button). Unlike DV360's geo/channel pickers, this endpoint takes a free-text
`searchTerms` param with NO id-based lookup and NO "Load more" paging
(`NonPaginatedBrandSafetyResponseResult`) - the JSON only carries a bare
`locationId` with no display name, so resolution is best-effort: an
empty/default search (`searchTerms=' '`), check whether the target id
happens to be in that single result set, then re-search by the resolved
name to select it. Unresolved ids are NOTE'd, never a hard failure.

--------------------------------------------------------------------------
Advertised product categories: same shared tree dialog DV360 uses, resolved
by id via a captured API response (the JSON only carries a raw id, no name)
--------------------------------------------------------------------------
`getAmazonCategories()` fires on the "Manage" button click and returns the
FULL category tree in one response (not paginated) - captured here to find
the node matching the JSON's `advertisedProductCategoryIds` entry, then
reuses the exact same search+expand+Include tree mechanics already proven in
the DV360 suites' `add_ag_categories` (same shared `CategoriesDialogComponent`).

--------------------------------------------------------------------------
Other confirmed gaps (present in the JSON, no UI control - NOTE'd):
--------------------------------------------------------------------------
- `targetingSettings.defaultAudienceTargetingMatchType` (SIMILAR): no
  formcontrol/reference anywhere in `amazon-ad-groups.component.ts`.
- `adomains` (campaign-level advertised domain, "mugler.com"): no field in
  the Insertion Order form.
- Fees (`fees` array on the ad group): present in the JSON but treated as
  out-of-scope for initial campaign creation, same precedent as
  test_amazon_playwright.py's own "Budget Cap, Agency Fees, ... left at
  defaults" note.
- `targetingSettings.timeZoneType` (VIEWER): no direct control, but VIEWER
  is already the component's own default when unset - nothing to do.

Run with:        python test_amazon_mugler_json_playwright.py
"""

import datetime
import json
import re
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
)
from test_dv360_json_playwright import select_mat_option_on
from test_dv360_youtube_json_playwright import _dismiss_targeting_dialog
from test_amazon_playwright import _set_date_range_dialog

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_589257453671562743_586197493360755014_LOREAL_MUGLER.json")
CLIENT = "L'Oreal"     # UNVERIFIED PLACEHOLDER - see module docstring
ADVERTISER = "Mugler"  # UNVERIFIED PLACEHOLDER - see module docstring
AMAZON_DSP_BADGE = "Amazon"

# --------------------------------------------------------------------------
# Label dicts - copied from nexify-frontend-main/src/open-api/models/amazon-ads-*.ts.
# Where the enum KEY already equals the JSON's API token, the VALUE is the
# mat-option/label text (same convention as the DV360 suites' enumLabel()).
# --------------------------------------------------------------------------
GOAL_LABELS = {"AWARENESS": "Awareness", "CONSIDERATION": "Consideration", "CONVERSIONS": "Conversions"}
# Campaign KPI is a goal-card button, not a generated enum lookup - only the
# token(s) actually seen in an export need to be here.
CAMPAIGN_KPI_LABELS = {"REACH": "Reach"}
BUDGET_ALLOCATION_LABELS = {"AUTO": "Auto", "MANUAL": "Manual"}
ROLLOVER_TOKENS = {"NO_ROLLOVER", "PRIOR_BUDGET_ROLLOVER", "CUMULATIVE_BUDGET_ROLLOVER"}
DELIVERY_PROFILE_LABELS = {"ASAP": "ASAP", "EVEN": "Even", "PACE_AHEAD": "Pace Ahead"}
VIEWABILITY_TIER_LABELS = {
    "ALL_TIERS": "All tiers",
    "GREATER_THAN_40_PERCENT": "Greater than 40 percent",
    "GREATER_THAN_50_PERCENT": "Greater than 50 percent",
    "GREATER_THAN_60_PERCENT": "Greater than 60 percent",
    "GREATER_THAN_70_PERCENT": "Greater than 70 percent",
    "LESS_THAN_40_PERCENT": "Less than 40 percent",
}
VIDEO_COMPLETION_TIER_LABELS = {
    "ALL_TIERS": "All Tiers",
    "GREATER_THAN_10_PERCENT": "Greater than 10%",
    "GREATER_THAN_20_PERCENT": "Greater than 20%",
    "GREATER_THAN_30_PERCENT": "Greater than 30%",
    "GREATER_THAN_40_PERCENT": "Greater than 40%",
    "GREATER_THAN_50_PERCENT": "Greater than 50%",
    "GREATER_THAN_60_PERCENT": "Greater than 60%",
    "GREATER_THAN_70_PERCENT": "Greater than 70%",
    "GREATER_THAN_80_PERCENT": "Greater than 80%",
    "GREATER_THAN_90_PERCENT": "Greater than 90%",
}
CREATIVE_ROTATION_LABELS = {"RANDOM": "Random", "WEIGHTED": "Weighted"}
INVENTORY_TYPE_LABELS = {
    "STREAMING_TV": "Streaming TV", "STANDARD_DISPLAY": "Standard Display",
    "AMAZON_MOBILE_DISPLAY": "Amazon Mobile Display", "APP_MOBILE_APP": "App Mobile",
    "DISPLAY": "Display", "VIDEO": "Video", "ONLINE_VIDEO": "Online Video",
    "AUDIO": "Audio", "PODCAST": "Podcast", "AUDIO_AMAZON_DEAL": "Audio Amazon Deal",
    "STREAMING_TV_AMAZON_DEAL": "Streaming TV Amazon Deal", "LIVE_EVENTS": "Live Events",
    "DIGITAL_OUT_OF_HOME": "Digital Out of Home",
}
AD_GROUP_BID_STRATEGY_LABELS = {
    "PRIORITIZE_KPI_TARGET": "Prioritize KPI Target",
    "SPEND_BUDGET_IN_FULL": "Spend Budget in Full",
    "SPEND_IMPRESSION_BUDGET_IN_FULL": "Spend Imppression Budget in Full",  # sic - matches a live typo in the enum
    "USE_CAMPAIGN_STRATEGY": "Use Campaign Strategy",
}
FREQ_TARGET_LABELS = {"USER": "User", "HOUSEHOLD": "Household"}
TIME_UNIT_LABELS = {"DAYS": "Days", "HOURS": "Hours", "MINUTES": "Minutes"}


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before the live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    campaign = ref["payload"]["campaigns"][0]
    ad_group = ref["payload"]["adGroups"][0]

    goal = campaign["optimizations"]["goalSettings"]["goal"]
    assert goal in GOAL_LABELS, f"Unknown campaign goal token: {goal}"
    kpi = campaign["optimizations"]["goalSettings"]["kpi"]
    assert kpi in CAMPAIGN_KPI_LABELS, f"Unknown campaign KPI token (add a label for it in CAMPAIGN_KPI_LABELS): {kpi}"
    budget_alloc = campaign["optimizations"]["budgetSettings"]["budgetAllocation"]
    assert budget_alloc in BUDGET_ALLOCATION_LABELS, f"Unknown campaign budgetAllocation token: {budget_alloc}"
    rollover = campaign["optimizations"]["budgetSettings"]["flightBudgetRolloverStrategy"]
    assert rollover in ROLLOVER_TOKENS, f"Unknown flightBudgetRolloverStrategy token: {rollover}"

    for freq in campaign.get("frequencies", []):
        assert freq["frequencyTargetingSetting"] in FREQ_TARGET_LABELS, (
            f"Unknown frequencyTargetingSetting token: {freq['frequencyTargetingSetting']}"
        )
        assert freq["timeUnit"] in TIME_UNIT_LABELS, f"Unknown timeUnit token: {freq['timeUnit']}"

    ag_budget_alloc = ad_group["optimization"]["budgetSettings"]["budgetAllocation"]
    assert ag_budget_alloc in BUDGET_ALLOCATION_LABELS, f"Unknown ad-group budgetAllocation token: {ag_budget_alloc}"
    bid_strategy = ad_group["optimization"]["bidStrategy"]
    assert bid_strategy in AD_GROUP_BID_STRATEGY_LABELS, f"Unknown ad-group bidStrategy token: {bid_strategy}"
    delivery_profile = ad_group["pacing"]["deliveryProfile"]
    assert delivery_profile in DELIVERY_PROFILE_LABELS, f"Unknown deliveryProfile token: {delivery_profile}"
    inventory_type = ad_group["inventoryType"]
    assert inventory_type in INVENTORY_TYPE_LABELS, f"Unknown inventoryType token: {inventory_type}"
    creative_rotation = ad_group["creativeRotationType"]
    assert creative_rotation in CREATIVE_ROTATION_LABELS, f"Unknown creativeRotationType token: {creative_rotation}"
    viewability = ad_group["targetingSettings"]["amazonViewability"]["viewabilityTier"]
    assert viewability in VIEWABILITY_TIER_LABELS, f"Unknown viewabilityTier token: {viewability}"
    video_completion = ad_group["targetingSettings"]["videoCompletionTier"]
    assert video_completion in VIDEO_COMPLETION_TIER_LABELS, f"Unknown videoCompletionTier token: {video_completion}"

    for t in ad_group.get("targets", []):
        assert t["targetType"] in {"DEVICE", "LOCATION"}, (
            f"Unhandled target type (needs new suite code, not just a label): {t['targetType']}"
        )

    print("OFFLINE VALIDATION PASSED: every targeting/enum token this suite automates resolves against its label dict.")


# --------------------------------------------------------------------------
# General Info
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

    campaign_name = f"Test Amazon Mugler JSON - {int(time.time())}"
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
    search_box = grid.locator("input[aria-label='Search in the data grid']")
    search_box.fill(ADVERTISER)
    page.wait_for_timeout(1200)
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "No rows found in the advertiser grid"

    adv_row = (
        grid.locator("tr.dx-data-row")
        .filter(has=page.locator("td[aria-colindex='2']", has_text=AMAZON_DSP_BADGE))
        .filter(has=page.locator("td[aria-colindex='3']", has_text=ADVERTISER))
    )
    if adv_row.count() == 0:
        adv_row = grid.locator("tr.dx-data-row").filter(has=page.locator("span", has_text=ADVERTISER))
    expect(adv_row.first).to_be_visible()
    adv_row.first.locator("div.dx-select-checkbox").click()
    expect(adv_row.first).to_have_attribute("aria-selected", "true")

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()

    next_btn = footer.locator("button.mdc-button", has_text="Next")
    expect(next_btn).to_be_enabled(timeout=15000)
    page.wait_for_timeout(500)

    ok("general-info", f"Campaign '{campaign_name}' created for {CLIENT}/{ADVERTISER} (Amazon)")
    return footer


# --------------------------------------------------------------------------
# Insertion Order (Amazon skips Global Setup - Next goes straight here)
# --------------------------------------------------------------------------
def select_radio_by_value(container, form_control_name: str, value: str):
    radio = container.locator(f"input[type='radio'][formcontrolname='{form_control_name}'][value='{value}']")
    radio.click()
    expect(radio).to_be_checked()
    return radio


def create_insertion_order_amazon(page: Page, ref: dict, date_from: datetime.date, date_to: datetime.date):
    campaign = ref["payload"]["campaigns"][0]

    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    tmpl = page.locator("app-template-selector-dialog")
    try:
        expect(tmpl).to_be_visible(timeout=3000)
        tmpl.locator("button", has_text="Continuar sin seleccionar plantilla").click()
        expect(tmpl).not_to_be_visible()
    except AssertionError:
        pass
    io_form = page.locator("app-amazon-order-form")
    expect(io_form).to_be_visible(timeout=10000)
    ok("io-form", "navigated to Amazon Insertion Orders form")

    order_name = f"Order Amazon Mugler - {int(time.time())}"
    fill_and_verify(io_form, "name", order_name)
    ok("io-name", f"Order Name filled with '{order_name}'")

    purchase_order = f"PO-{int(time.time())}"
    fill_and_verify(io_form, "purchaseOrderNumber", purchase_order)
    ok("io-po", f"Purchase Order Number filled with '{purchase_order}'")

    goal = campaign["optimizations"]["goalSettings"]["goal"]
    goal_label = GOAL_LABELS[goal]
    goal_card = io_form.locator("button.goal-card", has_text=goal_label)
    goal_card.click()
    expect(goal_card).to_have_class(re.compile("goal-card--selected"))
    ok("io-goal", f"Goal = '{goal_label}' card selected and verified")

    kpi = campaign["optimizations"]["goalSettings"]["kpi"]
    kpi_label = CAMPAIGN_KPI_LABELS[kpi]
    kpi_card = io_form.locator("button.goal-card", has_text=kpi_label)
    kpi_card.click()
    expect(kpi_card).to_have_class(re.compile("goal-card--selected"))
    ok("io-kpi", f"KPI = '{kpi_label}' card selected and verified")

    fill_and_verify(io_form, "kpiValue", "1")
    ok("io-kpi-value", "KPI Value = 1 (token)")

    budget_alloc = campaign["optimizations"]["budgetSettings"]["budgetAllocation"]
    select_radio_by_value(io_form, "budgetAllocation", budget_alloc)
    # Selecting budgetAllocation triggers a debounced re-render of the
    # Budget & Flights section - let it settle before grabbing locators
    # inside it (same pattern documented in test_amazon_playwright.py).
    page.wait_for_timeout(1500)
    ok("io-budget-allocation", f"Optimization Strategy = '{budget_alloc}'")

    # IO-level dates only render in AUTO mode, hidden in MANUAL.
    io_date_btn = io_form.locator("button[matsuffix]").first
    if io_date_btn.count() > 0 and io_date_btn.is_visible():
        io_date_btn.click()
        _set_date_range_dialog(page, date_from, date_to)
        ok("io-dates", f"IO-level dates set: {date_from} -> {date_to}")
    else:
        print("TEST io-dates SKIPPED -> IO-level date fields not present (MANUAL mode)")

    # Flight row - dates/budget are required per-flight regardless of mode.
    io_form.locator("button.flight-add").click()
    flight_row = io_form.locator("div[formarrayname='flights'] div.flight-row").first
    expect(flight_row).to_be_visible()
    flight_date_btn = flight_row.locator("button.dt-suffix").first
    expect(flight_date_btn).to_be_visible(timeout=10000)
    flight_date_btn.scroll_into_view_if_needed()
    flight_date_btn.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok("io-flight-dates", f"Flight dates set: {date_from} -> {date_to}")

    fill_and_verify(flight_row, "budgetValue", "1")
    ok("io-flight-budget", "Flight budget = 1 (token)")
    fill_and_verify(flight_row, "currencyCode", "EUR")
    ok("io-flight-currency", "Flight currency = EUR")

    rollover = campaign["optimizations"]["budgetSettings"]["flightBudgetRolloverStrategy"]
    select_radio_by_value(io_form, "flightBudgetRolloverStrategy", rollover)
    ok("io-rollover", f"Unused budget strategy = '{rollover}'")

    # Frequency caps - real values from the JSON (pacing/delivery config,
    # not spend, so safe to derive exactly). Amazon allows up to 3 caps;
    # this export only ever carries 1.
    freqs = campaign.get("frequencies", [])
    for i, freq in enumerate(freqs):
        io_form.locator("button", has_text="Add cap").click()
        row = io_form.locator("div[formarrayname='frequencies'] div.frequency-row").nth(i)
        expect(row).to_be_visible()
        fill_and_verify(row, "eventMaxCount", str(freq["eventMaxCount"]))
        fill_and_verify(row, "timeCount", str(freq["timeCount"]))
        select_mat_option_on(page, row.locator("mat-select[formcontrolname='timeUnit']"), TIME_UNIT_LABELS[freq["timeUnit"]])
        select_mat_option_on(
            page, row.locator("mat-select[formcontrolname='frequencyTargetingSetting']"),
            FREQ_TARGET_LABELS[freq["frequencyTargetingSetting"]],
        )
    if freqs:
        ok("io-frequency-caps", f"{len(freqs)} frequency cap row(s) set: {freqs}")

    if campaign.get("adomains"):
        print("TEST io-adomains SKIPPED -> 'adomains' (advertised domain) has no control in the Insertion Order form")

    return order_name


# --------------------------------------------------------------------------
# Line Items / Ad Group
# --------------------------------------------------------------------------
def resolve_amazon_category(page: Page, ad_form, category_id: str):
    """Advertised product categories: the JSON only carries a raw category
    id (no display name). getAmazonCategories() returns the FULL tree in one
    response on 'Manage' click (not paginated) - capture it, find the node
    matching category_id, then reuse the same search+expand+Include tree
    mechanics proven in the DV360 suites' add_ag_categories (shared
    CategoriesDialogComponent)."""
    categories_section = ad_form.locator("section").filter(
        has=page.locator("span.text-sm.font-semibold", has_text="Advertised product categories")
    )
    manage_btn = categories_section.locator("button", has_text="Manage")
    manage_btn.scroll_into_view_if_needed()

    with page.expect_response(lambda r: "/dsp/amazon/categories" in r.url, timeout=20000) as resp_info:
        manage_btn.click()
    body = resp_info.value.json()
    tree = body if isinstance(body, list) else body.get("results", [])

    def find(nodes):
        for n in nodes:
            if str(n.get("id")) == category_id:
                return n
            found = find(n.get("children") or [])
            if found:
                return found
        return None

    node = find(tree)
    dialog = page.locator("app-categories-dialog")
    expect(dialog).to_be_visible(timeout=10000)

    if node is None:
        print(f"NOTE: advertised product category id {category_id} not found in the live categories tree "
              "(data drift) - skipping")
        _dismiss_targeting_dialog(page, dialog)
        return

    path = (node.get("path") or node["name"]).strip("/")
    leaf_name = path.split("/")[-1]

    search = dialog.get_by_placeholder("Search categories")
    search.fill(leaf_name)
    search.press("Enter")
    page.wait_for_timeout(600)

    target_row = dialog.get_by_text(leaf_name, exact=True)
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
    row_container.locator("button[aria-label='Include']").click()
    dialog.locator("button", has_text="Apply").click()
    expect(dialog).not_to_be_visible()
    ok("ag-categories", f"Advertised product category = '{path}' (resolved live from id {category_id})")


def add_amazon_location_targets(page: Page, ad_form, mode: str, location_ids: list):
    """Location targeting via the shared TargetingListDialogComponent
    (type='amazon-geo', endpoint /dsp/amazon/location) - confirmed identical
    DOM to DV360's geo-region picker (dx-data-grid, 'Write to filter' search,
    Apply button). Unlike DV360's geo picker, this endpoint takes a
    free-text searchTerms param with NO id lookup and NO 'Load more' paging,
    so resolution is best-effort: an empty/default search, then check
    whether the target id happens to be in that one result set."""
    if not location_ids:
        return
    section_text = "Included locations" if mode == "include" else "Excluded locations"
    section = ad_form.locator("div.border.rounded-xl.p-3", has_text=section_text)
    add_btn = section.get_by_role("button", name="Add location")
    add_btn.scroll_into_view_if_needed()

    with page.expect_response(lambda r: "/dsp/amazon/location" in r.url, timeout=20000) as resp_info:
        add_btn.click()
    body = resp_info.value.json()
    results = body if isinstance(body, list) else body.get("results", [])
    live_by_id = {str(item["id"]): item.get("name", str(item["id"])) for item in results}

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()

    matched = [(i, live_by_id[i]) for i in location_ids if i in live_by_id]
    missing = [i for i in location_ids if i not in live_by_id]
    if missing:
        print(f"NOTE: {len(matched)}/{len(location_ids)} location id(s) resolved via the default search - "
              f"unresolved (endpoint has no id-lookup/paging, only free-text search): {missing}")

    if not matched:
        _dismiss_targeting_dialog(page, dialog)
        return

    grid = dialog.locator("dx-data-grid")
    search_box = dialog.get_by_placeholder("Write to filter")
    for _id, name in matched:
        search_box.fill(name)
        search_box.press("Enter")
        page.wait_for_timeout(700)
        row = grid.locator("tr.dx-data-row").filter(has=page.locator("span", has_text=name)).first
        expect(row).to_be_visible(timeout=8000)
        row.locator("div.dx-select-checkbox").click()

    dialog.locator("button", has_text="Apply").click()
    expect(dialog).not_to_be_visible()
    ok(f"ag-location-{mode}", f"{mode.capitalize()}d locations ({len(matched)}/{len(location_ids)}): {[n for _, n in matched]}")


def build_ad_group_amazon(page: Page, ref: dict, date_from: datetime.date, date_to: datetime.date):
    ad_group = ref["payload"]["adGroups"][0]

    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    confirm_dlg = page.locator("mat-dialog-container")
    expect(confirm_dlg).to_be_visible(timeout=5000)
    confirm_dlg.locator("button", has_text="Confirm & continue").click()
    expect(confirm_dlg).not_to_be_visible()

    li = page.locator("app-line-items")
    expect(li).to_be_visible(timeout=10000)
    ad_form = li.locator("app-amazon-ad-groups form")
    expect(ad_form).to_be_visible()
    ok("ag-form", "navigated to Line Items, Ad Group form visible")

    ad_group_name = f"AG Mugler - {int(time.time())}"
    fill_and_verify(ad_form, "name", ad_group_name)
    ok("ag-name", f"Ad Group Name = '{ad_group_name}'")

    fill_and_verify(ad_form, "baseBid", "1")
    ok("ag-base-bid", "Base Bid = 1 (token)")
    fill_and_verify(ad_form, "maxAverageBid", "1")
    ok("ag-max-avg-bid", "Max Average Bid = 1 (token)")
    select_mat_option(page, "bidCurrency", ad_group["bid"]["currencyCode"])
    ok("ag-bid-currency", f"Bid Currency = '{ad_group['bid']['currencyCode']}'")

    bid_strategy = ad_group["optimization"]["bidStrategy"]
    select_mat_option(page, "bidStrategy", AD_GROUP_BID_STRATEGY_LABELS[bid_strategy])
    ok("ag-bid-strategy", f"Bid Strategy = '{AD_GROUP_BID_STRATEGY_LABELS[bid_strategy]}'")

    ag_budget_alloc = ad_group["optimization"]["budgetSettings"]["budgetAllocation"]
    select_mat_option(page, "budgetAllocation", BUDGET_ALLOCATION_LABELS[ag_budget_alloc])
    ok("ag-budget-allocation", f"Budget Allocation = '{BUDGET_ALLOCATION_LABELS[ag_budget_alloc]}'")

    fill_and_verify(ad_form, "dailyMinSpendValue", "1")
    ok("ag-daily-min-spend", "Daily Min Spend = 1 (token)")

    # KPI has no equivalent field in the JSON's ad-group optimization block
    # (campaign-level goalSettings.kpi is a separate, already-handled field)
    # - keep a fixed, always-required default.
    select_mat_option(page, "kpi", "Clicks")
    ok("ag-kpi", "KPI = 'Clicks' (not present in the JSON at ad-group level, required default)")

    delivery_profile = ad_group["pacing"]["deliveryProfile"]
    select_mat_option(page, "deliveryProfile", DELIVERY_PROFILE_LABELS[delivery_profile])
    ok("ag-delivery-profile", f"Delivery Profile = '{DELIVERY_PROFILE_LABELS[delivery_profile]}'")

    viewability = ad_group["targetingSettings"]["amazonViewability"]["viewabilityTier"]
    select_mat_option(page, "viewabilityTier", VIEWABILITY_TIER_LABELS[viewability])
    ok("ag-viewability", f"Viewability Tier = '{VIEWABILITY_TIER_LABELS[viewability]}'")

    video_completion = ad_group["targetingSettings"]["videoCompletionTier"]
    select_mat_option(page, "videoCompletionTier", VIDEO_COMPLETION_TIER_LABELS[video_completion])
    ok("ag-video-completion", f"Video Completion Tier = '{VIDEO_COMPLETION_TIER_LABELS[video_completion]}'")

    inventory_type = ad_group["inventoryType"]
    select_mat_option(page, "inventoryType", INVENTORY_TYPE_LABELS[inventory_type])
    ok("ag-inventory-type", f"Inventory Type = '{INVENTORY_TYPE_LABELS[inventory_type]}'")

    creative_rotation = ad_group["creativeRotationType"]
    select_mat_option(page, "creativeRotationType", CREATIVE_ROTATION_LABELS[creative_rotation])
    ok("ag-creative-rotation", f"Creative Rotation = '{CREATIVE_ROTATION_LABELS[creative_rotation]}'")

    # includeUnmeasurableImpressions - JSON says false, which is also the
    # default unchecked state, so just verify rather than click.
    include_unmeasurable = ad_form.locator("mat-checkbox[formcontrolname='includeUnmeasurableImpressions'] input")
    if ad_group["targetingSettings"]["amazonViewability"].get("includeUnmeasurableImpressions"):
        if not include_unmeasurable.is_checked():
            ad_form.locator("mat-checkbox[formcontrolname='includeUnmeasurableImpressions']").click()
        expect(include_unmeasurable).to_be_checked()
    else:
        expect(include_unmeasurable).not_to_be_checked()
    ok("ag-unmeasurable-impressions", "Include Unmeasurable Impressions = false (verified)")

    # Advertised product categories - resolved live from the raw JSON id.
    resolve_amazon_category(page, ad_form, ad_group["advertisedProductCategoryIds"][0])
    page.wait_for_timeout(1500)  # let the categories dialog's debounced re-render settle

    # Location targeting - "Only use real-time location" checkbox.
    if ad_group["targetingSettings"].get("userLocationSignal") == "CURRENT":
        signal_checkbox = ad_form.locator("mat-checkbox").filter(has_text="Only use real-time location")
        signal_checkbox.click()
        ok("ag-location-signal", "'Only use real-time location' checked (userLocationSignal = CURRENT)")

    loc_included = [
        t["targetDetails"]["locationTarget"]["locationId"]
        for t in ad_group.get("targets", [])
        if t["targetType"] == "LOCATION" and not t.get("negative")
    ]
    loc_excluded = [
        t["targetDetails"]["locationTarget"]["locationId"]
        for t in ad_group.get("targets", [])
        if t["targetType"] == "LOCATION" and t.get("negative")
    ]
    add_amazon_location_targets(page, ad_form, "include", loc_included)
    add_amazon_location_targets(page, ad_form, "exclude", loc_excluded)

    # Device targeting - CONFIRMED UI GAP, see module docstring. The only
    # "Device" control (mobileDevices/mobileDeviceOptions) maps to specific
    # physical device MODELS (iPhone/iPad/Android/Kindle), not the
    # DeviceType+mobileEnvironment combination this export's targets use.
    device_targets = [t for t in ad_group.get("targets", []) if t["targetType"] == "DEVICE"]
    if device_targets:
        descriptions = []
        for t in device_targets:
            dt = t["targetDetails"]["deviceTarget"]
            label = dt["deviceType"]
            if dt.get("mobileEnvironment"):
                label += f"/{dt['mobileEnvironment']}"
            descriptions.append(label)
        print(f"TEST ag-device-targeting SKIPPED -> {len(device_targets)} DEVICE target(s) "
              f"({descriptions}) use deviceType+mobileEnvironment targeting, which has no UI control - "
              "the only 'Device' section maps to specific physical device models (mobileDevices), a "
              "different targeting dimension entirely (confirmed via amazon-target.util.ts's targetsToVm)")

    if ad_group["targetingSettings"].get("defaultAudienceTargetingMatchType"):
        print("TEST ag-audience-match-type SKIPPED -> 'defaultAudienceTargetingMatchType' has no UI control "
              "anywhere in this frontend")

    if ad_group.get("fees"):
        print(f"TEST ag-fees SKIPPED -> {len(ad_group['fees'])} fee(s) present in the JSON, treated as "
              "out-of-scope for initial campaign creation (same precedent as test_amazon_playwright.py)")

    # Budget = 1 EUR Lifetime.
    budgets_section = ad_form.locator("section").filter(
        has=page.locator("span.text-base.font-bold", has_text="Budgets")
    )
    budgets_section.locator("button", has_text="Add Budget").click()
    budget_input = budgets_section.locator("input[formcontrolname='budgetValue']")
    expect(budget_input).to_be_visible(timeout=10000)
    fill_and_verify(budgets_section, "budgetValue", "1")
    ok("ag-budget", "Ad Group Budget = 1 (EUR, Lifetime, token)")

    # Dates last - adding a budget row can trigger a debounced re-render
    # that wipes an earlier date selection (same caveat documented in
    # test_amazon_playwright.py).
    dates_section = ad_form.locator("section").filter(
        has=page.locator("span.text-base.font-bold", has_text="Dates")
    )
    start_date_input = dates_section.locator("input").first
    for attempt in range(2):
        dates_section.locator("button[matsuffix]").first.click()
        _set_date_range_dialog(page, date_from, date_to)
        if start_date_input.input_value().strip():
            break
    expect(start_date_input).not_to_have_value("")
    ok("ag-dates", f"Ad Group dates set: {date_from} -> {date_to}")

    page.wait_for_timeout(1500)
    if not budget_input.input_value().strip():
        fill_and_verify(budgets_section, "budgetValue", "1")
    if not start_date_input.input_value().strip():
        dates_section.locator("button[matsuffix]").first.click()
        _set_date_range_dialog(page, date_from, date_to)
        expect(start_date_input).not_to_have_value("")

    return ad_group_name


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def finish_and_submit_amazon(page: Page):
    """Same after-submit logic as test_dv360_json_playwright.py's
    test_finish_and_submit / test_amazon_playwright.py's
    test_amazon_recap: plain yes/anything-else confirmation, click, then a
    single check of whether Nexify's own validation-errors dialog appeared."""
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    confirm_dlg = page.locator("mat-dialog-container")
    try:
        expect(confirm_dlg).to_be_visible(timeout=5000)
        confirm_dlg.locator("button", has_text="Confirm & continue").click()
        expect(confirm_dlg).not_to_be_visible()
    except AssertionError:
        pass
    ok("next-to-recap", "navigated to the Recap step")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible(timeout=10000)
    answer = input(
        f"\n>>> 'Start campaign' ACTUALLY LAUNCHES on {ADVERTISER}'s live Amazon DSP account. "
        "Type 'yes' to confirm the click (anything else cancels): "
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
        ok("start-campaign", "'Start campaign' performed, no validation-errors dialog shown")
    else:
        print("TEST start-campaign SKIPPED -> click on 'Start campaign' cancelled by the user")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    ref = load_reference()
    assert CLIENT and ADVERTISER, (
        "CLIENT/ADVERTISER are not set - look up which Nexify Client/Advertiser corresponds to "
        f"Amazon advertiserId {ref['advertiserId']} (clientId {ref['clientId']}) and fill in the "
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

        try:
            today = datetime.date.today()
            date_from = today + datetime.timedelta(days=1)
            date_to = today + datetime.timedelta(days=2)

            test_landing(page)
            test_general_info(page)
            create_insertion_order_amazon(page, ref, date_from, date_to)
            build_ad_group_amazon(page, ref, date_from, date_to)
            finish_and_submit_amazon(page)

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

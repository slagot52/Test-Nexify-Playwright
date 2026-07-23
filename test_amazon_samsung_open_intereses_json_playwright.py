# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven Amazon DSP "Samsung Open Intereses" suite)
================================================================================
Checks that Amazon DSP campaign / ad-group targeting in Nexify can be driven
from a real Amazon Ads API export, by comparing the export's values against
what the UI actually lets you pick. Third Amazon JSON-driven suite in this
repo, after test_amazon_mugler_json_playwright.py and
test_amazon_samsung_display_json_playwright.py - both live on their own
not-yet-merged branches/PRs, so (same lesson learned building the Display
suite) this file is intentionally self-contained rather than importing from
either, so it stands on its own against main.

Reference JSON: template_8315549690802_592174647160962828_AMAZON_SAMSUNG_OPEN_INTERESES.json
(Samsung, Amazon advertiserId 8315549690802 / clientId 3635719820670341 -
same account already CONFIRMED LIVE via the Display suite). 1 campaign, 5
ad groups, 277 targeting entries total (7 AUDIENCE + 10 DEVICE + 255 KEYWORD
+ 5 LOCATION). All 5 ad groups share the same inventoryType (DISPLAY),
optimization/pacing/targetingSettings shape and advertisedProductCategoryIds
- they differ only in name (an audience-segment tag after "_FF~") and their
targets list (one ad group carries 255 keywords, the rest just a couple of
audiences/devices/locations).

CLIENT/ADVERTISER = "Samsung"/"Samsung_ES_Starcom" - reused directly, no
longer a placeholder guess: CONFIRMED LIVE 2026-07-23 for this exact
advertiserId (8315549690802) via the Display suite's successful run.

Budgets/bids stay at a token amount to avoid real spend (baseBid,
maxAverageBid, IO flight budget, ad-group budget, KPI Value all = 1).
dailyMinSpendValue is the one exception - CONFIRMED LIVE via the Display
suite that Amazon DSP rejects it below 4.75 at Start-campaign submission, so
it's filled with "5" here too, not "1". Frequency caps and every enum-style
selection (Goal, KPI, Budget Allocation, Delivery Profile, Viewability Tier,
Inventory Type, Creative Rotation, ad-group Bid Strategy) ARE derived for
real from the JSON. This export's campaign has `"frequencies": null`
(explicit null, not merely absent) - handled with `campaign.get(...) or []`
rather than the `.get(key, [])` pattern used elsewhere (which only catches a
missing KEY, not a present key whose value is null).

--------------------------------------------------------------------------
NEW - Keyword targeting: a single free-text textarea, not a dialog/picker
--------------------------------------------------------------------------
Unlike every other targeting type covered so far (Amazon or DV360), Keyword
Targeting has no picker dialog at all: `amazon-ad-groups.component.html`
renders one `<textarea formControlName="keywordsText">` ("Keywords
(comma-separated)"), and `amazon-ad-groups.component.ts` always parses it as
`.split(',').map(trim)` into an INCLUDE-only list with `matchType` hardcoded
to `'MULTISIGNAL_BROAD'` (`exclude` is always sent as `[]`, no matter what's
typed). So: (a) this suite can only represent this export's 255 *included*
keywords (all already `negative: false` here, so no data is lost), and
(b) the resulting API matchType will always be MULTISIGNAL_BROAD even though
this JSON tags every one of them BROAD - a UI simplification the suite
cannot work around, NOTE'd rather than silently misreported.

--------------------------------------------------------------------------
NEW - Multiple ad groups per campaign: "Create another" + auto-rebinding form
--------------------------------------------------------------------------
Unlike the single-ad-group Display suite, this export has 5. The Ad Groups
section (`amazon-ad-groups.component.html`) keeps ONE reactive form that
rebinds to whichever ad group is "active" (`hydrateEffect` watches
`activeAdGroup()` and patches the form) - there's a tab strip (one button per
ad group, `selectAdGroup(i)`) plus "Duplicate" (`onDuplicateAdGroup`) and
"Create another" (`onCreateAdGroup`, always adds a BLANK ad group and makes
it active, confirmed via `AmazonAdGroupsStore.add()` setting
`_activeIndex` to the new last index). The Line Items step already starts
with one ad group by default, so: fill ad group 0 directly, then for each
subsequent one click "Create another" (not "Duplicate" - a blank slate is
correct here, these ad groups don't share field values, only their targeting
shape) and refill.

--------------------------------------------------------------------------
CONFIRMED UI GAP - Device targeting cannot be recreated at all (same as
Display/Mugler): all DEVICE targets use `deviceTarget.deviceType` +
`mobileEnvironment` - the ad-group form's only "Device" section
(`mobileDevices`/`mobileDeviceOptions`) maps to `deviceTarget.mobileDevice`,
a completely different enum (specific device MODELS, not categories).
NOTE'd per target, not silently dropped.

--------------------------------------------------------------------------
Other confirmed gaps (present in the JSON, no UI control - NOTE'd, same as
the Display suite): campaign-level `bidSettings.bidStrategy` (dead/unwired
control); ad-group-level `frequencies`; campaign-level `countries`/
`marketplaces`; campaign-level `optimizations.conversionSettings.viewWeight`
(no matching field anywhere - `conversionTrackingEnabled` is a different,
unrelated section); `targetingSettings.defaultAudienceTargetingMatchType`;
ad-group `fees`; campaign-level `fees` (AGENCY). Video Completion Tier is
skipped for all 5 ad groups here too (all DISPLAY inventoryType) - see
DISPLAY_FAMILY_INVENTORY_TYPES below, same confirmed product bug as the
Display suite (Amazon rejects the campaign downstream if this field is set
for a display-family ad group; Nexify's UI has no client-side gate for it).

Run with:        python test_amazon_samsung_open_intereses_json_playwright.py
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
REFERENCE_JSON = Path("/Users/k052/Downloads/template_8315549690802_592174647160962828_AMAZON_SAMSUNG_OPEN_INTERESES.json")
CLIENT = "Samsung"                 # CONFIRMED LIVE 2026-07-23 via the Display suite
ADVERTISER = "Samsung_ES_Starcom"  # CONFIRMED LIVE 2026-07-23 via the Display suite
AMAZON_DSP_BADGE = "Amazon"

# CONFIRMED LIVE 2026-07-23 (Display suite): Amazon DSP rejects the whole
# campaign at processing time if Video Completion Tier is set on a
# display-family ad group. Nexify's UI has no client-side gate for this.
DISPLAY_FAMILY_INVENTORY_TYPES = {"DISPLAY", "STANDARD_DISPLAY", "AMAZON_MOBILE_DISPLAY", "APP_MOBILE_APP"}

# --------------------------------------------------------------------------
# Label dicts - copied from nexify-frontend-main/src/open-api/models/amazon-ads-*.ts.
# Where the enum KEY already equals the JSON's API token, the VALUE is the
# mat-option/label text (same convention as the DV360 suites' enumLabel()).
# --------------------------------------------------------------------------
GOAL_LABELS = {"AWARENESS": "Awareness", "CONSIDERATION": "Consideration", "CONVERSIONS": "Conversions"}
# Campaign KPI is a goal-card button, not a generated enum lookup - only the
# token(s) actually seen in an export need to be here.
CAMPAIGN_KPI_LABELS = {
    "REACH": "Reach",
    "CLICK_THROUGH_RATE": "Click through rate (CTR)",
    "COST_PER_CONVERSION_OFF_AMAZON": "Cost per action (CPA)",
}
BUDGET_ALLOCATION_LABELS = {"AUTO": "Auto", "MANUAL": "Manual"}
ROLLOVER_TOKENS = {"NO_ROLLOVER", "PRIOR_BUDGET_ROLLOVER", "CUMULATIVE_BUDGET_ROLLOVER"}
DELIVERY_PROFILE_LABELS = {"ASAP": "ASAP", "EVEN": "Even", "PACE_AHEAD": "Pace Ahead"}
# CONFIRMED LIVE 2026-07-23 (Display suite): the frontend source's raw enum
# VALUE strings ("All tiers", "Greater than 40 percent", ...) do NOT match
# what the live UI actually renders - the local nexify-frontend-main/
# reference copy is stale for this one enum. These are the live-confirmed
# option labels.
VIEWABILITY_TIER_LABELS = {
    "ALL_TIERS": "All tiers (greatest reach)",
    "GREATER_THAN_40_PERCENT": "40% and greater",
    "GREATER_THAN_50_PERCENT": "50% and greater",
    "GREATER_THAN_60_PERCENT": "60% and greater",
    "GREATER_THAN_70_PERCENT": "70% and greater (most viewable)",
    "LESS_THAN_40_PERCENT": "Up to 40%",
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


def select_radio_by_value(container, form_control_name: str, value: str):
    radio = container.locator(f"input[type='radio'][formcontrolname='{form_control_name}'][value='{value}']")
    radio.click()
    expect(radio).to_be_checked()
    return radio


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
    (type='amazon-geo', endpoint /dsp/amazon/location). CONFIRMED (via
    targeting-list-dialog.component.ts's ngOnInit) that no request fires
    just from opening the dialog - the search must be submitted (Enter/
    search-icon) first, which is what actually calls loadOptions(). Endpoint
    is a NonPaginatedBrandSafetyResponseResult - free-text searchTerms only,
    no id lookup, no 'Load more' - so resolution is best-effort: one blank
    default search, check whether the target id(s) happen to be in that one
    result set, then re-search by the resolved name (one at a time) to
    select each row (the dialog's running selection persists across
    re-searches)."""
    if not location_ids:
        return
    section_text = "Included locations" if mode == "include" else "Excluded locations"
    section = ad_form.locator("div.border.rounded-xl.p-4", has_text=section_text)
    add_btn = section.get_by_role("button", name="Add location")
    add_btn.scroll_into_view_if_needed()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    search_box = dialog.get_by_placeholder("Write to filter")

    with page.expect_response(lambda r: "/dsp/amazon/location" in r.url, timeout=20000) as resp_info:
        search_box.press("Enter")
    body = resp_info.value.json()
    results = body if isinstance(body, list) else body.get("results", [])
    live_by_id = {str(item["id"]): item.get("name", str(item["id"])) for item in results}

    matched = [(i, live_by_id[i]) for i in location_ids if i in live_by_id]
    missing = [i for i in location_ids if i not in live_by_id]
    if missing:
        print(f"NOTE: {len(matched)}/{len(location_ids)} location id(s) resolved via the default search - "
              f"unresolved (endpoint has no id-lookup/paging, only free-text search): {missing}")

    if not matched:
        _dismiss_targeting_dialog(page, dialog)
        return

    grid = dialog.locator("dx-data-grid")
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


def add_amazon_audience_targets(page: Page, ad_form, mode: str, audience_ids: list):
    """Audience targeting via the same shared TargetingListDialogComponent
    (type='amazon-audiences', endpoint /dsp/amazon/audiences) - another
    NonPaginatedBrandSafetyResponseResult, same best-effort id resolution as
    Location. The dialog also exposes a category/subcategory filter
    (getAmazonAudienceCategories), left unset here so the blank search casts
    the widest net."""
    if not audience_ids:
        return
    section_text = "Included audiences" if mode == "include" else "Excluded audiences"
    section = ad_form.locator("div.border.rounded-xl.p-3", has_text=section_text)
    add_btn = section.get_by_role("button", name="Add audience")
    add_btn.scroll_into_view_if_needed()
    add_btn.click()

    dialog = page.locator("mat-dialog-container")
    expect(dialog).to_be_visible()
    search_box = dialog.get_by_placeholder("Write to filter audiences")

    with page.expect_response(lambda r: "/dsp/amazon/audiences" in r.url, timeout=20000) as resp_info:
        search_box.press("Enter")
    body = resp_info.value.json()
    results = body if isinstance(body, list) else body.get("results", [])
    live_by_id = {str(item["id"]): item.get("name", str(item["id"])) for item in results}

    matched = [(i, live_by_id[i]) for i in audience_ids if i in live_by_id]
    missing = [i for i in audience_ids if i not in live_by_id]
    if missing:
        print(f"NOTE: {len(matched)}/{len(audience_ids)} audience id(s) resolved via the default (no "
              f"category/subcategory) search - unresolved (endpoint has no id-lookup/paging, only "
              f"free-text search): {missing}")

    if not matched:
        _dismiss_targeting_dialog(page, dialog)
        return

    grid = dialog.locator("dx-data-grid")
    for _id, name in matched:
        search_box.fill(name)
        search_box.press("Enter")
        page.wait_for_timeout(700)
        row = grid.locator("tr.dx-data-row").filter(has=page.locator("span", has_text=name)).first
        expect(row).to_be_visible(timeout=8000)
        row.locator("div.dx-select-checkbox").click()

    dialog.locator("button", has_text="Apply").click()
    expect(dialog).not_to_be_visible()
    ok(f"ag-audience-{mode}", f"{mode.capitalize()}d audiences ({len(matched)}/{len(audience_ids)}): {[n for _, n in matched]}")


def add_amazon_keyword_targets(ad_form, keywords: list):
    """Keyword targeting is a single free-text textarea (formcontrolname
    'keywordsText'), not a dialog/picker - confirmed via
    amazon-ad-groups.component.ts: on submit it's always split on commas
    into an INCLUDE-only list with matchType hardcoded to
    'MULTISIGNAL_BROAD' (exclude is always []). This export's keywords are
    all BROAD/include already, so no targeting data is lost, but the
    resulting API matchType will differ from the JSON's literal 'BROAD'
    token - a UI simplification, NOTE'd below rather than silently
    misreported."""
    if not keywords:
        return
    field = ad_form.locator("textarea[formcontrolname='keywordsText']")
    expect(field).to_be_visible()
    value = ", ".join(keywords)
    field.fill(value)
    actual = field.input_value()
    assert actual == value, "'keywordsText': the textarea's value doesn't match what was filled"
    ok("ag-keywords", f"{len(keywords)} keyword(s) filled into the comma-separated textarea (will submit as "
       "matchType MULTISIGNAL_BROAD - the UI has no way to preserve BROAD vs. other match types, or excluded keywords)")


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before the live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    campaign = ref["payload"]["campaigns"][0]
    ad_groups = ref["payload"]["adGroups"]
    assert ad_groups, "This export has no ad groups"

    goal = campaign["optimizations"]["goalSettings"]["goal"]
    assert goal in GOAL_LABELS, f"Unknown campaign goal token: {goal}"
    kpi = campaign["optimizations"]["goalSettings"]["kpi"]
    assert kpi in CAMPAIGN_KPI_LABELS, f"Unknown campaign KPI token (add a label for it in CAMPAIGN_KPI_LABELS): {kpi}"
    budget_alloc = campaign["optimizations"]["budgetSettings"]["budgetAllocation"]
    assert budget_alloc in BUDGET_ALLOCATION_LABELS, f"Unknown campaign budgetAllocation token: {budget_alloc}"

    rollover = campaign["optimizations"]["budgetSettings"].get("flightBudgetRolloverStrategy")
    if rollover:
        assert rollover in ROLLOVER_TOKENS, f"Unknown flightBudgetRolloverStrategy token: {rollover}"

    for freq in (campaign.get("frequencies") or []):
        assert freq["frequencyTargetingSetting"] in FREQ_TARGET_LABELS, (
            f"Unknown frequencyTargetingSetting token: {freq['frequencyTargetingSetting']}"
        )
        assert freq["timeUnit"] in TIME_UNIT_LABELS, f"Unknown timeUnit token: {freq['timeUnit']}"

    for ad_group in ad_groups:
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
        video_completion = ad_group["targetingSettings"].get("videoCompletionTier")
        if video_completion:
            assert video_completion in VIDEO_COMPLETION_TIER_LABELS, f"Unknown videoCompletionTier token: {video_completion}"

        for t in ad_group.get("targets", []):
            assert t["targetType"] in {"AUDIENCE", "DEVICE", "KEYWORD", "LOCATION"}, (
                f"Unhandled target type (needs new suite code, not just a label): {t['targetType']}"
            )
            if t["targetType"] == "AUDIENCE":
                assert "defaultValue" in t["targetDetails"]["audienceTarget"]["audienceId"], (
                    "AUDIENCE target missing audienceId.defaultValue"
                )
            if t["targetType"] == "KEYWORD":
                assert t["targetDetails"]["keywordTarget"].get("keyword"), "KEYWORD target missing 'keyword' text"

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

    campaign_name = f"Test Amazon Samsung Open Intereses JSON - {int(time.time())}"
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

    order_name = f"Order Amazon Samsung Open Intereses - {int(time.time())}"
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

    if campaign["optimizations"].get("bidSettings", {}).get("bidStrategy"):
        print("TEST io-bid-strategy SKIPPED -> 'bidSettings.bidStrategy' has a TypeScript form control "
              "but no corresponding element anywhere in the Insertion Order form's HTML (dead/unwired control)")

    if campaign["optimizations"].get("conversionSettings"):
        print("TEST io-conversion-settings SKIPPED -> 'optimizations.conversionSettings' (e.g. viewWeight) has "
              "no matching control - 'conversionTrackingEnabled' on this form is a different, unrelated section")

    # IO-level dates only render in AUTO mode, hidden in MANUAL.
    io_date_btn = io_form.locator("button[matsuffix]").first
    if io_date_btn.count() > 0 and io_date_btn.is_visible():
        io_date_btn.click()
        _set_date_range_dialog(page, date_from, date_to)
        ok("io-dates", f"IO-level dates set: {date_from} -> {date_to}")
    else:
        print("TEST io-dates SKIPPED -> IO-level date fields not present (MANUAL mode)")

    # Flight row - dates/budget are required per-flight regardless of mode.
    # This export has 3 real (long-expired) flight budget segments; only ONE
    # token flight is created here, same collapsing convention every suite
    # uses for budgets/dates.
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

    rollover = campaign["optimizations"]["budgetSettings"].get("flightBudgetRolloverStrategy")
    if rollover:
        select_radio_by_value(io_form, "flightBudgetRolloverStrategy", rollover)
        ok("io-rollover", f"Unused budget strategy = '{rollover}'")
    else:
        default_radio = io_form.locator(
            "input[type='radio'][formcontrolname='flightBudgetRolloverStrategy'][value='NO_ROLLOVER']"
        )
        expect(default_radio).to_be_checked()
        print("TEST io-rollover SKIPPED -> 'flightBudgetRolloverStrategy' not present in this export, "
              "verified the form's own default ('NO_ROLLOVER') is already selected")

    # Frequency caps - real values from the JSON (pacing/delivery config, not
    # spend, so safe to derive exactly). This export's campaign.frequencies
    # is explicit `null` (not merely absent), hence `or []` rather than
    # `.get(key, [])` (which only catches a missing key).
    freqs = campaign.get("frequencies") or []
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
    else:
        print("TEST io-frequency-caps SKIPPED -> campaign.frequencies is null in this export")

    if campaign.get("adomains"):
        print("TEST io-adomains SKIPPED -> 'adomains' (advertised domain) has no control in the Insertion Order form")
    if campaign.get("countries") or campaign.get("marketplaces"):
        print(f"TEST io-countries-marketplaces SKIPPED -> countries={campaign.get('countries')} "
              f"marketplaces={campaign.get('marketplaces')} have no matching control in the Insertion Order form")
    if campaign.get("fees"):
        print(f"TEST io-fees SKIPPED -> {len(campaign['fees'])} campaign-level fee(s) present in the JSON "
              "(e.g. AGENCY), treated as out-of-scope same as the baseline suite's Agency Fee precedent")

    return order_name


# --------------------------------------------------------------------------
# Line Items / Ad Groups (this export has 5 - "Create another" between them)
# --------------------------------------------------------------------------
AD_GROUP_TAG_RE = re.compile(r"_FF~(.+)$")


def _ad_group_tag(ad_group: dict, index: int) -> str:
    """Extract the trailing '_FF~<segment>' tag from the JSON's ad-group
    name for a human-readable, distinguishing suite-generated name (these 5
    ad groups are otherwise identical apart from their targeting) - matches
    the spirit of a prior product-feedback finding that indistinguishable
    ad-group names make live debugging harder."""
    m = AD_GROUP_TAG_RE.search(ad_group.get("name", ""))
    return m.group(1).strip() if m else f"AdGroup{index + 1}"


def _fill_single_ad_group(page: Page, ad_form, ad_group: dict, date_from: datetime.date, date_to: datetime.date, index: int):
    tag = _ad_group_tag(ad_group, index)
    ad_group_name = f"AG Samsung Open Intereses {tag} - {int(time.time())}"
    fill_and_verify(ad_form, "name", ad_group_name)
    ok(f"ag{index}-name", f"Ad Group Name = '{ad_group_name}'")

    fill_and_verify(ad_form, "baseBid", "1")
    ok(f"ag{index}-base-bid", "Base Bid = 1 (token)")
    if ad_group["bid"].get("maxAverageBid") is not None:
        fill_and_verify(ad_form, "maxAverageBid", "1")
        ok(f"ag{index}-max-avg-bid", "Max Average Bid = 1 (token)")
    else:
        print(f"TEST ag{index}-max-avg-bid SKIPPED -> 'maxAverageBid' not present in this export (optional field)")
    select_mat_option(page, "bidCurrency", ad_group["bid"]["currencyCode"])
    ok(f"ag{index}-bid-currency", f"Bid Currency = '{ad_group['bid']['currencyCode']}'")

    bid_strategy = ad_group["optimization"]["bidStrategy"]
    select_mat_option(page, "bidStrategy", AD_GROUP_BID_STRATEGY_LABELS[bid_strategy])
    ok(f"ag{index}-bid-strategy", f"Bid Strategy = '{AD_GROUP_BID_STRATEGY_LABELS[bid_strategy]}'")

    ag_budget_alloc = ad_group["optimization"]["budgetSettings"]["budgetAllocation"]
    select_mat_option(page, "budgetAllocation", BUDGET_ALLOCATION_LABELS[ag_budget_alloc])
    ok(f"ag{index}-budget-allocation", f"Budget Allocation = '{BUDGET_ALLOCATION_LABELS[ag_budget_alloc]}'")

    # CONFIRMED LIVE 2026-07-23 (Display suite): Amazon DSP rejects Daily Min
    # Spend below 4.75 at Start-campaign submission - the "1" token every
    # other suite uses for non-real spend fields is too low for this field.
    fill_and_verify(ad_form, "dailyMinSpendValue", "5")
    ok(f"ag{index}-daily-min-spend", "Daily Min Spend = 5 (token, above the confirmed live minimum of 4.75)")

    # KPI has no equivalent field in the JSON's ad-group optimization block
    # (campaign-level goalSettings.kpi is a separate, already-handled field)
    # - keep a fixed, always-required default.
    select_mat_option(page, "kpi", "Clicks")
    ok(f"ag{index}-kpi", "KPI = 'Clicks' (not present in the JSON at ad-group level, required default)")

    delivery_profile = ad_group["pacing"]["deliveryProfile"]
    select_mat_option(page, "deliveryProfile", DELIVERY_PROFILE_LABELS[delivery_profile])
    ok(f"ag{index}-delivery-profile", f"Delivery Profile = '{DELIVERY_PROFILE_LABELS[delivery_profile]}'")

    viewability = ad_group["targetingSettings"]["amazonViewability"]["viewabilityTier"]
    select_mat_option(page, "viewabilityTier", VIEWABILITY_TIER_LABELS[viewability])
    ok(f"ag{index}-viewability", f"Viewability Tier = '{VIEWABILITY_TIER_LABELS[viewability]}'")

    inventory_type = ad_group["inventoryType"]
    select_mat_option(page, "inventoryType", INVENTORY_TYPE_LABELS[inventory_type])
    ok(f"ag{index}-inventory-type", f"Inventory Type = '{INVENTORY_TYPE_LABELS[inventory_type]}'")

    # CONFIRMED LIVE 2026-07-23 (Display suite): Amazon DSP rejects the whole
    # campaign downstream if Video Completion Tier is set for a
    # display-family ad group - Nexify's UI has no client-side gate for it.
    video_completion = ad_group["targetingSettings"].get("videoCompletionTier")
    if video_completion and inventory_type not in DISPLAY_FAMILY_INVENTORY_TYPES:
        select_mat_option(page, "videoCompletionTier", VIDEO_COMPLETION_TIER_LABELS[video_completion])
        ok(f"ag{index}-video-completion", f"Video Completion Tier = '{VIDEO_COMPLETION_TIER_LABELS[video_completion]}'")
    else:
        print(f"TEST ag{index}-video-completion SKIPPED -> inventoryType '{inventory_type}' does not accept "
              "Video Completion Tier (CONFIRMED LIVE: Amazon DSP rejects the whole campaign at processing time "
              "if set for DISPLAY - a real Nexify product bug, not fixed here)")

    creative_rotation = ad_group["creativeRotationType"]
    select_mat_option(page, "creativeRotationType", CREATIVE_ROTATION_LABELS[creative_rotation])
    ok(f"ag{index}-creative-rotation", f"Creative Rotation = '{CREATIVE_ROTATION_LABELS[creative_rotation]}'")

    # includeUnmeasurableImpressions - JSON says false, which is also the
    # default unchecked state, so just verify rather than click.
    include_unmeasurable = ad_form.locator("mat-checkbox[formcontrolname='includeUnmeasurableImpressions'] input")
    if ad_group["targetingSettings"]["amazonViewability"].get("includeUnmeasurableImpressions"):
        if not include_unmeasurable.is_checked():
            ad_form.locator("mat-checkbox[formcontrolname='includeUnmeasurableImpressions']").click()
        expect(include_unmeasurable).to_be_checked()
    else:
        expect(include_unmeasurable).not_to_be_checked()
    ok(f"ag{index}-unmeasurable-impressions", "Include Unmeasurable Impressions = false (verified)")

    # Advertised product categories - resolved live from the raw JSON id
    # (same id for all 5 ad groups in this export).
    resolve_amazon_category(page, ad_form, ad_group["advertisedProductCategoryIds"][0])
    page.wait_for_timeout(1500)  # let the categories dialog's debounced re-render settle

    # Location targeting - "Only use real-time location" checkbox. This
    # export wants CURRENT (checked) for every ad group, which also happens
    # to be the form's own default - the click loop only fires if the
    # current state actually differs, so this never needs the force-click
    # workaround confirmed necessary for the Display suite's MULTIPLE_SIGNALS
    # case, but reuses the same robust logic regardless.
    location_signal = ad_group["targetingSettings"].get("userLocationSignal")
    signal_checkbox = ad_form.locator("mat-checkbox").filter(has_text="Only use real-time location")
    signal_input = signal_checkbox.locator("input")
    want_checked = location_signal == "CURRENT"
    signal_checkbox.scroll_into_view_if_needed()
    for _ in range(3):
        if signal_input.is_checked() == want_checked:
            break
        signal_input.click(force=True)
        page.wait_for_timeout(400)
    if want_checked:
        expect(signal_input).to_be_checked()
    else:
        expect(signal_input).not_to_be_checked()
    ok(f"ag{index}-location-signal", f"'Only use real-time location' = {want_checked} (userLocationSignal = {location_signal})")

    aud_included = [
        t["targetDetails"]["audienceTarget"]["audienceId"]["defaultValue"]
        for t in ad_group.get("targets", [])
        if t["targetType"] == "AUDIENCE" and not t.get("negative")
    ]
    aud_excluded = [
        t["targetDetails"]["audienceTarget"]["audienceId"]["defaultValue"]
        for t in ad_group.get("targets", [])
        if t["targetType"] == "AUDIENCE" and t.get("negative")
    ]
    add_amazon_audience_targets(page, ad_form, "include", aud_included)
    add_amazon_audience_targets(page, ad_form, "exclude", aud_excluded)

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

    # Keyword targeting - single comma-separated textarea, include-only.
    keywords = [
        t["targetDetails"]["keywordTarget"]["keyword"]
        for t in ad_group.get("targets", [])
        if t["targetType"] == "KEYWORD" and not t.get("negative")
    ]
    excluded_keywords = [
        t["targetDetails"]["keywordTarget"]["keyword"]
        for t in ad_group.get("targets", [])
        if t["targetType"] == "KEYWORD" and t.get("negative")
    ]
    add_amazon_keyword_targets(ad_form, keywords)
    if excluded_keywords:
        print(f"TEST ag{index}-keywords-excluded SKIPPED -> {len(excluded_keywords)} excluded keyword(s) present "
              "in the JSON, but the Keywords textarea always submits an include-only list (exclude is hardcoded "
              "to [] in the frontend)")

    # Device targeting - CONFIRMED UI GAP, see module docstring.
    device_targets = [t for t in ad_group.get("targets", []) if t["targetType"] == "DEVICE"]
    if device_targets:
        descriptions = []
        for t in device_targets:
            dt = t["targetDetails"]["deviceTarget"]
            label = dt["deviceType"]
            if dt.get("mobileEnvironment"):
                label += f"/{dt['mobileEnvironment']}"
            descriptions.append(label)
        print(f"TEST ag{index}-device-targeting SKIPPED -> {len(device_targets)} DEVICE target(s) "
              f"({descriptions}) use deviceType+mobileEnvironment targeting, which has no UI control - "
              "the only 'Device' section maps to specific physical device models (mobileDevices), a "
              "different targeting dimension entirely (confirmed via amazon-target.util.ts's targetsToVm)")

    if ad_group["targetingSettings"].get("defaultAudienceTargetingMatchType"):
        print(f"TEST ag{index}-audience-match-type SKIPPED -> 'defaultAudienceTargetingMatchType' has no UI "
              "control anywhere in this frontend")

    if ad_group.get("frequencies"):
        print(f"TEST ag{index}-frequencies SKIPPED -> {len(ad_group['frequencies'])} ad-group-level frequency "
              "cap(s) present in the JSON, but the Ad Group form has no 'frequencies' control at all (only the "
              "Insertion Order form does)")

    if ad_group.get("fees"):
        print(f"TEST ag{index}-fees SKIPPED -> {len(ad_group['fees'])} fee(s) present in the JSON, treated as "
              "out-of-scope for initial campaign creation (same precedent as test_amazon_playwright.py)")

    # Budget = 1 EUR Lifetime. Some ad groups in this export carry BOTH a
    # DAILY and a LIFETIME budget segment - the form only has one "Budget
    # (EUR, Lifetime)" field (no recurrence-period selector at all), so
    # both collapse into the same single token value, same convention as
    # collapsing the campaign's real flight segments to one.
    if len(ad_group.get("budgets", [])) > 1:
        print(f"TEST ag{index}-budget-segments NOTE -> {len(ad_group['budgets'])} budget segments in the JSON "
              "(e.g. DAILY + LIFETIME) collapse into the form's single Lifetime-only budget field")
    budgets_section = ad_form.locator("section").filter(
        has=page.locator("span.text-base.font-bold", has_text="Budgets")
    )
    budgets_section.locator("button", has_text="Add Budget").click()
    budget_input = budgets_section.locator("input[formcontrolname='budgetValue']")
    expect(budget_input).to_be_visible(timeout=10000)
    fill_and_verify(budgets_section, "budgetValue", "1")
    ok(f"ag{index}-budget", "Ad Group Budget = 1 (EUR, Lifetime, token)")

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
    ok(f"ag{index}-dates", f"Ad Group dates set: {date_from} -> {date_to}")

    page.wait_for_timeout(1500)
    if not budget_input.input_value().strip():
        fill_and_verify(budgets_section, "budgetValue", "1")
    if not start_date_input.input_value().strip():
        dates_section.locator("button[matsuffix]").first.click()
        _set_date_range_dialog(page, date_from, date_to)
        expect(start_date_input).not_to_have_value("")

    return ad_group_name


def build_ad_groups_amazon(page: Page, ref: dict, date_from: datetime.date, date_to: datetime.date):
    ad_groups = ref["payload"]["adGroups"]

    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    confirm_dlg = page.locator("mat-dialog-container")
    expect(confirm_dlg).to_be_visible(timeout=5000)
    confirm_dlg.locator("button", has_text="Confirm & continue").click()
    expect(confirm_dlg).not_to_be_visible()

    li = page.locator("app-line-items")
    expect(li).to_be_visible(timeout=10000)
    ad_groups_section = li.locator("app-amazon-ad-groups")
    ad_form = ad_groups_section.locator("form")
    expect(ad_form).to_be_visible()
    ok("ag-form", "navigated to Line Items, Ad Group form visible")

    names = []
    for i, ad_group in enumerate(ad_groups):
        if i > 0:
            # The Line Items step starts with one ad group by default; each
            # subsequent one needs an explicit "Create another" (a blank
            # slate, NOT "Duplicate" - these ad groups don't share field
            # values). The form rebinds automatically to the new active ad
            # group (hydrateEffect watches activeAdGroup()).
            create_btn = ad_groups_section.locator("button", has_text="Create another")
            create_btn.scroll_into_view_if_needed()
            create_btn.click()
            page.wait_for_timeout(500)
        name = _fill_single_ad_group(page, ad_form, ad_group, date_from, date_to, i)
        names.append(name)

    ok("ag-count", f"{len(names)} ad group(s) created: {names}")
    return names


# --------------------------------------------------------------------------
# Finish and submit
# --------------------------------------------------------------------------
def finish_and_submit_amazon(page: Page):
    """Same after-submit logic as the Display/Mugler suites: plain
    yes/anything-else confirmation, click, then a single check of whether
    Nexify's own validation-errors dialog appeared."""
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
            build_ad_groups_amazon(page, ref, date_from, date_to)
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

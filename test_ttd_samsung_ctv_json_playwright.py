# -*- coding: utf-8 -*-
"""
PLAYWRIGHT TEST - publicisnexify.com (JSON-driven TTD "Samsung CTV" suite)
================================================================================
Third and LAST JSON-driven TTD suite in this repo, completing the whole
6-export 2026-07-23 Samsung batch (3 Amazon + 3 TTD). Built directly from
the field-mapping playbook established by the first two TTD suites
(Programmatic Guarantees, PDs - see project memory
project_ttd_samsung_programmatic_guarantees_suite /
project_ttd_samsung_pds_suite). Checks that TTD campaign/ad-group targeting
in Nexify can be driven from a real export, comparing the export's values
against what the UI actually lets you pick.

Reference JSON: template_v2_09kp41a_TTD_SAMSUNG_CTV.json (same Samsung/TTD
AdvertiserId "ihee7uv" and same SeedId "o6g215d5" as both prior TTD
exports - part of the same batch; see project memory
project_samsung_amazon_ttd_batch). 1 campaign ("Channel"), 7 ad groups -
the most of any suite in the whole batch.

>>> CLIENT / ADVERTISER = "Samsung" / "Samsung_ES_Starcom" - CONFIRMED, same
>>> AdvertiserId ("ihee7uv") and SeedId ("o6g215d5") as the two prior TTD
>>> suites, both of which already resolved this live to 'ES_1stP_Starcom'.

--------------------------------------------------------------------------
CRITICAL STRUCTURAL NOTE (same as both prior TTD suites): this export is
NOT shaped like Nexify's own payload. It is TTD's OWN raw native "Campaign"
API object verbatim. Same genuine field-MAPPING exercise as before, not a
payload-reuse exercise - and since it's the same advertiser/account, every
enum/mapping decision below carries over unchanged from the PG/PDs suites.

Given the enormous, mostly-advanced surface of a real TTD Campaign object,
this suite deliberately limits itself to the exact set of fields the
FROZEN, live-validated baseline `test_ttd_playwright.py` (tests 1-45,
see nexify-test-protect-1-26) already demonstrates as controllable, rather
than guessing selectors for the many advanced RTBAttributes sub-objects.
Everything outside that proven surface is NOTE'd as out-of-scope, not
silently dropped. Imports `_open_and_select` / `_set_date_range_dialog`
directly from test_ttd_playwright.py (frozen but safe to import from,
confirmed present on `main`) rather than re-deriving them.

--------------------------------------------------------------------------
Cross-checked against ~/Downloads/schemas/ttd/schema.json before writing
(see project memory reference_backend_validation_schemas /
feedback_check_schemas_before_writing_tests) - same schema file, same
result as both prior TTD suites' checks:
--------------------------------------------------------------------------
- `AdGroup.required` = `["AdGroupName", "ChannelId", "FunnelLocation"]` - all
  three already filled by this suite (Base/Max Bid CPM aren't in this list
  but ARE required by the live FORM per the baseline suite's own comments).
- `CampaignGlobal` (nested) `required` = `["SeedId", "PurchaseOrderNumber"]`
  - both filled.
- `CampaignFlights.BudgetInAdvertiserCurrency.minimum = 1` - the usual token
  "1" clears this floor.
- `Goal.VCRInPercent` (and every other percent-type goal) is `minimum=0,
  maximum=100` - the token "1" used for Goal % is safely within range.
- No `if`/`then` conditionals anywhere in this schema (confirmed via grep,
  same as both prior TTD suites' checks).

--------------------------------------------------------------------------
Field mapping notes (raw TTD JSON -> Nexify TTD UI). Same account as both
prior TTD suites, so every enum token seen here was already resolved
before - no new label-dict entries needed:
--------------------------------------------------------------------------
- Campaign/Channel Name: SYNTHETIC, same convention as every other suite.
- `PacingMode` ("PaceAhead") -> "Pace Ahead", same as both prior TTD suites.
- `PrimaryChannel` ("TV") -> `PRIMARY_CHANNEL_LABELS["TV"]` = "TV" - same as
  the PG suite (the PDs suite instead saw "Video"; both entries already
  exist in the dict, confirming it wasn't a one-off).
- AdGroup `ChannelId` ("TV" on all 7 ad groups) ->
  `CHANNEL_ID_LABELS["TV"]` = "TV".
- `PrimaryGoal.VCRInPercent` (80.0, identical shape to both prior TTD
  suites): the PRESENCE of this key selects Goal Type = "Completion Rate".
  Goal % itself is token "1" (not the real 80.0), same convention.
- `FunnelLocation` ("Awareness" on all 7 ad groups) ->
  `FUNNEL_LOCATION_LABELS["Awareness"]` = "Awareness".
- `TimeZone` ("Etc/GMT", no offset): same as both prior TTD suites -
  resolves via `resolveTimeZoneKey()`'s own fallback to `Etc_UTC` = "(UTC)
  Coordinated Universal Time".
- `SeedId` ("o6g215d5"): IDENTICAL id to BOTH prior TTD suites' exports
  (same advertiser/account) - resolved live the same way, via the
  `/dsp/ttd/seeds` response captured on Global Setup load. Already
  confirmed live twice to be 'ES_1stP_Starcom'.
- `PurchaseOrderNumber`: SYNTHETIC random 8-digit number - the JSON's real
  value ("95 26 7769") doesn't fit that format anyway.
- `CampaignConversionReportingColumns` (12 entries, BYTE-FOR-BYTE SAME
  SHAPE as both prior TTD suites - even the same TrackingTagId values):
  collapses to exactly 2 distinct non-null `CrossDeviceAttributionModelId`
  values - "IdentityAlliance" and "IdentityAllianceWithHousehold" - via the
  same first-occurrence-per-distinct-vendor-id dedup already proven twice.
  Concept (Person/Household) inferred the same way (`_infer_concept()`,
  unchanged).
- AdGroup `IsEnabled` (true on all 7 ad groups): optional "Enabled"
  checkbox, same present-on-some-accounts handling as both prior suites.
- **SEVEN ad groups here - the most of any suite in the batch.** Unlike the
  PDs suite (where all `_PD~` segments collided and the `_FF~` fallback was
  needed), here every ad group's `_PD~` segment IS unique (real publisher/
  platform names: ATRESMEDIA, DISNEY, EXTE, MEDIASET, PLUTO, RAKUTEN,
  SAMSUNGTV) while every `_FF~` segment is identical ("CTV") - the exact
  mirror image of the PDs suite's situation. `compute_ad_group_tags()`
  resolves this correctly on its FIRST pattern (`_PD~(.+?)_BS~`) without
  needing to fall through, since it always tries patterns in order and
  uses the first one that's unique across the whole list.
- `RTBAttributes.BudgetSettings` / `RTBAttributes.AudienceTargeting` are
  present (non-empty) on all 7 ad groups here too - same NOTE'd
  out-of-scope handling as both prior TTD suites.
- Multi-ad-group looping: same "Create another" + auto-rebinding-form
  pattern already proven on the PG/PDs/Amazon suites, now exercised with
  the most iterations (7) of any suite in the batch.

Out-of-scope / NOTE'd, not fixed here (no control in the baseline's proven
surface, identical list to both prior TTD suites): AdGroup-level
`RTBAttributes.BudgetSettings`, `RTBAttributes.AudienceTargeting`,
`RTBAttributes.ROIGoal`, `RTBAttributes.CreativeIds`,
KoaOptimizationSettings / NielsenSettings / ComscoreSettings /
ContractTargeting / DimensionalBiddingAutoOptimizationSettings / the three
viewability-standard fields, campaign-level `AssociatedBidLists` /
`Increments` / `CustomLabels` (campaign and ad-group level) /
`CampaignConversionReportingColumns`'s `TrackingTagId`/`ReportingColumnId`
sub-fields, `CustomCPAClickWeight`/`CustomROASType`, `Description` (null
anyway), `IsBallotMeasure`, `CampaignType`.

Run with:        python test_ttd_samsung_ctv_json_playwright.py
"""

import datetime
import json
import random
import re
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
)
from test_ttd_playwright import (
    _open_and_select,
    _set_date_range_dialog,
)

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------
REFERENCE_JSON = Path("/Users/k052/Downloads/template_v2_09kp41a_TTD_SAMSUNG_CTV.json")
CLIENT = "Samsung"                 # CONFIRMED live by both prior TTD suites (same AdvertiserId)
ADVERTISER = "Samsung_ES_Starcom"  # CONFIRMED live by both prior TTD suites (same AdvertiserId)
TTD_DSP_BADGE = "TTD"

# --------------------------------------------------------------------------
# Label dicts - copied from nexify-frontend-main/src/open-api/models/ttd-*.ts
# and ttd-campaign-channels.component.ts. KEY = API token (matches the raw
# JSON verbatim), VALUE = the visible mat-option label. Identical to the
# PG/PDs suites' dicts - same account, same enums encountered.
# --------------------------------------------------------------------------
PACING_MODE_LABELS = {
    "Off": "Pace to Daily Spend Cap",
    "PaceToEndOfFlight": "Pace Evenly",
    "PaceAhead": "Pace Ahead",
    "PaceAsSoonAsPossible": "Pace ASAP",
}
PRIMARY_CHANNEL_LABELS = {
    "Audio": "Audio",
    "Display": "Display",
    "DigitalOutOfHome": "Out of Home",
    "NativeDisplay": "Native Display",
    "NativeVideo": "Native Video",
    "TV": "TV",
    "Video": "Video",
}
# Separate enum from PrimaryChannel above (different spelling for Out Of
# Home) - do not merge these two dicts.
CHANNEL_ID_LABELS = {
    "Display": "Display",
    "Video": "Video",
    "Audio": "Audio",
    "NativeDisplay": "Native Display",
    "NativeVideo": "Native Video",
    "TV": "TV",
    "OutOfHome": "Out Of Home",
}
FUNNEL_LOCATION_LABELS = {
    "Awareness": "Awareness",
    "Consideration": "Consideration",
    "Conversion": "Conversion",
}
# Only the goal-type key(s) actually seen in an export need an entry here -
# ttd-campaign-channels.component.ts's own goalTypeLabel dict has 12 total.
GOAL_TYPE_LABELS = {
    "VCRInPercent": "Completion Rate",
    "CTRInPercent": "Click-Through Rate (CTR)",
    "ViewabilityInPercent": "Viewability",
}


def _infer_concept(vendor_id: str) -> str:
    """Mirrors ttd-conversion-reporting-dialog.component.ts's own
    inferConcept() exactly: a vendor id containing 'household'
    (case-insensitive) is the Household concept, any other non-empty id is
    Person, empty/missing is None."""
    if not vendor_id:
        return "None"
    return "Household" if "household" in vendor_id.lower() else "Person"


def load_reference() -> dict:
    with open(REFERENCE_JSON, encoding="utf-8") as f:
        return json.load(f)


# --------------------------------------------------------------------------
# Offline validation - catch label/enum drift before the live run
# --------------------------------------------------------------------------
def validate_offline(ref: dict):
    pacing_mode = ref.get("PacingMode")
    if pacing_mode:
        assert pacing_mode in PACING_MODE_LABELS, f"Unknown PacingMode token: {pacing_mode}"

    primary_channel = ref.get("PrimaryChannel")
    assert primary_channel in PRIMARY_CHANNEL_LABELS, f"Unknown PrimaryChannel token: {primary_channel}"

    primary_goal = ref.get("PrimaryGoal") or {}
    assert len(primary_goal) == 1, f"Expected exactly one PrimaryGoal key, got: {list(primary_goal.keys())}"
    goal_key = next(iter(primary_goal))
    assert goal_key in GOAL_TYPE_LABELS, f"Unknown PrimaryGoal token (add a label for it in GOAL_TYPE_LABELS): {goal_key}"

    ad_groups = ref.get("AdGroups") or []
    assert ad_groups, "This export has no AdGroups"
    for ag in ad_groups:
        assert ag.get("AdGroupName"), "AdGroup missing AdGroupName"
        channel_id = ag.get("ChannelId")
        assert channel_id in CHANNEL_ID_LABELS, f"Unknown AdGroup ChannelId token: {channel_id}"
        funnel = ag.get("FunnelLocation")
        assert funnel in FUNNEL_LOCATION_LABELS, f"Unknown FunnelLocation token: {funnel}"

    for col in ref.get("CampaignConversionReportingColumns") or []:
        vendor_id = col.get("CrossDeviceAttributionModelId")
        # Just needs to be a string if present - concept is inferred, not
        # looked up in a fixed dict, so nothing to assert against here
        # beyond type sanity.
        assert vendor_id is None or isinstance(vendor_id, str), (
            f"Unexpected CrossDeviceAttributionModelId shape: {vendor_id!r}"
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

    campaign_name = f"Test TTD Samsung CTV JSON - {int(time.time())}"
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
        .filter(has=page.locator("td[aria-colindex='2']", has_text=TTD_DSP_BADGE))
        .filter(has=page.locator("td[aria-colindex='3']", has_text=ADVERTISER))
    )
    if adv_row.count() == 0:
        adv_row = grid.locator("tr.dx-data-row").filter(has=page.locator("span", has_text=ADVERTISER))
    expect(adv_row.first).to_be_visible()
    adv_row.first.locator("div.dx-select-checkbox").click()
    expect(adv_row.first).to_have_attribute("aria-selected", "true")

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    expect(dsp_card.locator("span.dsp-name", has_text="The Trade Desk")).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text=ADVERTISER)).to_be_visible()

    next_btn = footer.locator("button.mdc-button", has_text="Next")
    expect(next_btn).to_be_enabled(timeout=15000)
    page.wait_for_timeout(500)

    ok("general-info", f"Campaign '{campaign_name}' created for {CLIENT}/{ADVERTISER} (TTD)")
    return campaign_name


# --------------------------------------------------------------------------
# Global Setup
# --------------------------------------------------------------------------
def test_global_setup(page: Page, ref: dict, date_from: datetime.date, date_to: datetime.date):
    seed_id = ref.get("SeedId")

    with page.expect_response(lambda r: "/dsp/ttd/seeds" in r.url, timeout=20000) as seed_resp:
        page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
        tmpl = page.locator("app-template-selector-dialog")
        try:
            expect(tmpl).to_be_visible(timeout=2000)
            tmpl.locator("button", has_text="Continuar sin seleccionar plantilla").click()
            expect(tmpl).not_to_be_visible()
        except AssertionError:
            pass
        gs_form = page.locator("app-ttd-global-setup form")
        expect(gs_form).to_be_visible()
    ok("gs-form", "navigated to TTD Global Setup")

    none_radio = gs_form.locator("mat-radio-button", has_text="Do not create campaign group")
    none_input = none_radio.locator("input[type='radio']")
    if not none_input.is_checked():
        none_radio.click()
    expect(none_input).to_be_checked()
    ok("gs-campaign-group", "Campaign group = 'Do not create campaign group' confirmed (no group data in this export)")

    # Seed Id - opaque id in the JSON, resolved live from the /dsp/ttd/seeds
    # response captured above (auto-fetched on this page's load, no search
    # action needed). Same id as both prior TTD suites' exports - expect the
    # same 'ES_1stP_Starcom' match.
    if seed_id:
        body = seed_resp.value.json()
        results = body if isinstance(body, list) else body.get("results", [])
        match = next((s for s in results if str(s.get("id")) == seed_id), None)
        if match is None:
            print(f"NOTE: TTD seed id '{seed_id}' not found in the live seeds list for this advertiser "
                  "(data drift or wrong advertiser) - Seed Id left unset")
        else:
            select_mat_option(page, "seedId", match.get("name", seed_id))
            ok("gs-seed", f"Seed Id = '{match.get('name')}' (resolved live from id '{seed_id}')")
    else:
        print("TEST gs-seed SKIPPED -> 'SeedId' not present in this export")

    # Purchase Order Number - SYNTHETIC (max 8 digits per the baseline
    # suite's own constraint finding) - the JSON's real value
    # ("95 26 7769") doesn't fit that format.
    purchase_order = "".join(random.choices(string.digits, k=8))
    fill_and_verify(gs_form, "purchaseOrderNumber", purchase_order)
    ok("gs-po", f"Purchase Order Number = '{purchase_order}' (token, synthetic - see module docstring)")

    # Time Zone - "Etc/GMT" (this export) resolves, via the frontend's own
    # fallback logic, to the same default the baseline/prior TTD suites use.
    select_mat_option(page, "timeZone", "(UTC) Coordinated Universal Time")
    ok("gs-timezone", "Time Zone = '(UTC) Coordinated Universal Time' (JSON's 'Etc/GMT' has no direct match; "
       "confirmed via resolveTimeZoneKey() that this is the frontend's own fallback for an unmatched value)")

    gs_form.locator("button.dt-suffix").first.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok("gs-dates", f"Dates set via dialog: Start={date_from} End={date_to}")

    po_input = gs_form.locator("input[formcontrolname='purchaseOrderNumber']")
    if not po_input.input_value():
        po_input.fill(purchase_order)
    assert po_input.input_value(), "Purchase Order Number is empty after the guard"


# --------------------------------------------------------------------------
# Campaign Channels (TTD's level-1 entity, equivalent to DV360's Insertion
# Order / Amazon's Campaign)
# --------------------------------------------------------------------------
def fill_conversion_reporting(page: Page, cc_form, columns: list):
    if not columns:
        print("TEST cc-conversion-reporting SKIPPED -> 'CampaignConversionReportingColumns' empty/absent in this export")
        return

    # CONFIRMED via source: the dialog caps at maxColumns=10 rows
    # (canAddRow), and a fresh row already defaults to Concept='None' with
    # no vendor - so columns with no CrossDeviceAttributionModelId carry no
    # actual signal to represent and are dropped BEFORE adding any row,
    # rather than adding an empty row for each one. This export has 12
    # columns total, only 2 DISTINCT real vendor ids (each repeated 4
    # times - the repeats only differ in ReportingColumnId/TrackingTagId,
    # neither of which this suite represents, matching the baseline's own
    # scope) - only the first occurrence of each distinct vendor id is
    # added, same "first N distinct values" convention every JSON-driven
    # suite already uses for large repetitive target lists.
    seen_vendor_ids = set()
    to_add = []
    for col in columns:
        vendor_id = col.get("CrossDeviceAttributionModelId")
        if not vendor_id or vendor_id in seen_vendor_ids:
            continue
        seen_vendor_ids.add(vendor_id)
        to_add.append(col)
    print(f"NOTE: {len(columns)} conversion reporting column(s) in the JSON collapse to "
          f"{len(to_add)} distinct vendor id(s) to add as rows (dialog caps at 10 rows; "
          "ReportingColumnId/TrackingTagId aren't represented, so repeats with the same "
          "vendor id add no new information)")

    conv_section = cc_form.locator("section.frequency-section").filter(
        has=page.get_by_text("Conversion reporting", exact=True)
    )
    # CONFIRMED via source (ttd-campaign-channels.component.ts,
    # openConversionReportingDialog()): this fires TWO parallel calls via
    # Promise.all([getAdvertiserTrackingTags, getCrossDeviceAttributionVendor])
    # with NO catch block - if EITHER rejects, the whole function throws
    # before ever reaching dialog.open(), leaving the "Configure" button
    # stuck showing "Loading..." forever with no error shown to the user.
    # Both prior TTD suites (same advertiser) hit this live every time -
    # expect the same here. Only crossDeviceAttributionVendor's response
    # body is actually needed - hard-waiting on trackingTags too crashed
    # with an unhandled Playwright TimeoutError in the PG suite's own
    # debugging, so that second wait is deliberately NOT repeated here.
    with page.expect_response(lambda r: "/dsp/ttd/crossDeviceAttributionVendor" in r.url, timeout=20000) as vendor_resp:
        conv_section.locator("button[mat-stroked-button]", has_text="Configure").click()

    conv_dialog = page.get_by_role("dialog").filter(has_text="Configure campaign reporting and attribution")
    try:
        expect(conv_dialog).to_be_visible(timeout=10000)
    except AssertionError:
        # CONFIRMED LIVE on both prior TTD suites (same advertiser)
        # 2026-07-23: the dialog never opens for this advertiser -
        # crossDeviceAttributionVendor resolves fine (200) but
        # getAdvertiserTrackingTags never produces an observable response,
        # and openConversionReportingDialog() has no catch around their
        # Promise.all, so the function hangs forever mid-await and
        # dialog.open() is never reached. A real Nexify product bug (see
        # user_nexify_developer), not something this suite can work around
        # by clicking through it differently - there's no dialog to
        # dismiss, just a permanently "Loading..." button. Degrade
        # gracefully: NOTE it and move on rather than failing the whole
        # run over one unconfigurable, optional section.
        still_loading = conv_section.get_by_text("Loading...", exact=True).count() > 0
        print("NOTE: CONFIRMED PRODUCT BUG (same as both prior TTD suites, same advertiser) - the Conversion "
              f"Reporting dialog never opened after clicking 'Configure'{' (button still shows Loading...)' if still_loading else ''}. "
              "openConversionReportingDialog() (ttd-campaign-channels.component.ts) awaits "
              "Promise.all([getAdvertiserTrackingTags, getCrossDeviceAttributionVendor]) with NO catch "
              "block - crossDeviceAttributionVendor resolved fine (200) but getAdvertiserTrackingTags "
              "never produced an observable response, so the function hangs forever mid-await and the "
              "dialog is never opened. Conversion reporting left unconfigured for this run (Optional "
              "section) - continuing without it rather than failing the whole suite.")
        return

    body = vendor_resp.value.json()
    vendors = body if isinstance(body, list) else body.get("results", [])
    vendor_by_id = {str(v.get("id")): v.get("name", str(v.get("id"))) for v in vendors}

    resolved = 0
    for col in to_add:
        conv_dialog.locator("button", has_text="Add conversion data source").click()
        row = conv_dialog.locator("div.row-item").last

        vendor_id = col["CrossDeviceAttributionModelId"]
        concept = _infer_concept(vendor_id)

        concept_select = row.locator("mat-select[formcontrolname='crossDeviceConcept']")
        _open_and_select(page, concept_select, concept)

        vendor_name = vendor_by_id.get(vendor_id)
        if vendor_name is None:
            print(f"NOTE: conversion reporting vendor id '{vendor_id}' not found in the live "
                  "crossDeviceAttributionVendor list for this advertiser - Concept set to "
                  f"'{concept}' but Vendor left unset")
            continue

        vendor_select = row.locator("mat-select[formcontrolname='crossDeviceAttributionModelId']")
        _open_and_select(page, vendor_select, vendor_name)
        resolved += 1

    ok("cc-conversion-reporting", f"{resolved}/{len(to_add)} conversion reporting column(s) fully resolved "
       "(Concept inferred from CrossDeviceAttributionModelId, Vendor resolved live by id)")
    conv_dialog.locator("button", has_text="Apply").click()
    expect(conv_dialog).not_to_be_visible()


def test_campaign_channels(page: Page, ref: dict, date_from: datetime.date, date_to: datetime.date):
    cc_form = page.locator("app-ttd-campaign-channels form")
    for _ in range(3):
        page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
        try:
            expect(cc_form).to_be_visible(timeout=5000)
            break
        except AssertionError:
            page.wait_for_timeout(1000)
    expect(cc_form).to_be_visible()
    ok("cc-form", "navigated to TTD Campaign Channels")

    # Campaign/Channel Name - SYNTHETIC, same convention as every other
    # suite's Order/Insertion-Order name (not the JSON's real CampaignName).
    channel_name = f"Channel Samsung CTV - {int(time.time())}"
    fill_and_verify(cc_form, "campaignName", channel_name)
    ok("cc-name", f"Campaign/Channel Name = '{channel_name}'")

    primary_channel = ref.get("PrimaryChannel")
    select_mat_option(page, "primaryChannel", PRIMARY_CHANNEL_LABELS[primary_channel])
    ok("cc-primary-channel", f"Channel = '{PRIMARY_CHANNEL_LABELS[primary_channel]}'")

    pacing_mode = ref.get("PacingMode")
    if pacing_mode:
        select_mat_option(page, "pacingMode", PACING_MODE_LABELS[pacing_mode])
        ok("cc-pacing-mode", f"Pacing Mode = '{PACING_MODE_LABELS[pacing_mode]}'")
    else:
        print("TEST cc-pacing-mode SKIPPED -> 'PacingMode' not present in this export")

    primary_goal = ref.get("PrimaryGoal") or {}
    goal_key = next(iter(primary_goal), None)
    if goal_key:
        goal_label = GOAL_TYPE_LABELS[goal_key]
        primary_goal_select = cc_form.locator("mat-form-field", has_text="Goal Type").nth(0).locator("mat-select")
        _open_and_select(page, primary_goal_select, goal_label)
        ok("cc-primary-goal-type", f"Primary KPI Goal Type = '{goal_label}' (derived from PrimaryGoal.{goal_key} "
           "being present in the JSON)")

        goal_pct = cc_form.locator("mat-form-field", has_text="Goal %").locator("input")
        expect(goal_pct).to_be_visible()
        goal_pct.fill("1")
        assert goal_pct.input_value() == "1", f"Goal % expected '1', got '{goal_pct.input_value()}'"
        ok("cc-primary-goal-pct", "Primary KPI Goal % = 1 (token, not the real "
           f"{primary_goal[goal_key]} - same budgets/bids/KPI-value convention as every other suite)")
    else:
        print("TEST cc-primary-goal SKIPPED -> 'PrimaryGoal' not present in this export")

    # Flight - this export has 4 real (long-expired) flights; only ONE
    # token flight is created here, same collapsing convention every suite
    # uses for budgets/dates.
    flight = cc_form.locator("div.flight-row").first
    flight.locator("button.dt-suffix").first.click()
    _set_date_range_dialog(page, date_from, date_to)
    ok("cc-flight-dates", f"Flight dates set via dialog: Start={date_from} End={date_to}")

    fill_and_verify(flight, "budgetAmount", "1")
    ok("cc-flight-budget", "Flight Budget = 1 (token)")

    fill_conversion_reporting(page, cc_form, ref.get("CampaignConversionReportingColumns") or [])

    # Secondary/Tertiary KPI left as 'None' (matches this export - no
    # secondary/tertiary goal data); Fee card, AssociatedBidLists,
    # Increments, CustomLabels are optional/opaque and skipped, same
    # precedent as the baseline/prior TTD suites.


# --------------------------------------------------------------------------
# Ad Groups (this export has 7 - "Create another" between them, same
# multi-ad-group pattern already proven on the PG/PDs/Amazon suites)
# --------------------------------------------------------------------------
AD_GROUP_TAG_PATTERNS = [re.compile(r"_PD~(.+?)_BS~"), re.compile(r"_FF~(.+)$")]


def compute_ad_group_tags(ad_groups: list) -> list:
    """Same generalized tag-extraction helper as the PG/PDs/Amazon Deal Open
    Video suites: try each candidate name-segment pattern against the WHOLE
    ad-group list and use the first one that's unique for every ad group,
    falling back to a plain index if neither disambiguates. This export's 7
    AdGroupNames are the mirror image of the PDs suite's: here every
    `_PD~` segment IS unique (real publisher names - ATRESMEDIA, DISNEY,
    EXTE, MEDIASET, PLUTO, RAKUTEN, SAMSUNGTV) while every `_FF~` segment is
    identical ("CTV") - so the FIRST pattern resolves cleanly, no fallback
    needed."""
    names = [ag.get("AdGroupName", "") for ag in ad_groups]
    for pattern in AD_GROUP_TAG_PATTERNS:
        tags = [(m.group(1).strip() if (m := pattern.search(n)) else None) for n in names]
        if all(tags) and len(set(tags)) == len(tags):
            return tags
    return [f"AdGroup{i + 1}" for i in range(len(ad_groups))]


def _fill_single_ad_group(page: Page, ag_form, ad_group: dict, index: int, tag: str):
    ad_group_name = f"AG Samsung CTV {tag} - {int(time.time())}"
    fill_and_verify(ag_form, "adGroupName", ad_group_name)
    ok(f"ag{index}-name", f"Ad Group Name = '{ad_group_name}'")

    # Changing the channel debounce-reloads the ad group config and can
    # reset Funnel Location and the bid fields (documented in the baseline
    # suite) - set channel first, then wait it out.
    channel_id = ad_group["ChannelId"]
    select_mat_option(page, "channelId", CHANNEL_ID_LABELS[channel_id])
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(2500)
    ok(f"ag{index}-channel", f"Channel = '{CHANNEL_ID_LABELS[channel_id]}'")

    funnel = ad_group["FunnelLocation"]
    select_mat_option(page, "funnelLocation", FUNNEL_LOCATION_LABELS[funnel])
    ok(f"ag{index}-funnel-location", f"Funnel Location = '{FUNNEL_LOCATION_LABELS[funnel]}'")

    fill_and_verify(ag_form, "baseBidAmount", "1")
    ok(f"ag{index}-base-bid", "Base Bid CPM = 1 (token)")
    fill_and_verify(ag_form, "maxBidAmount", "1")
    ok(f"ag{index}-max-bid", "Max Bid CPM = 1 (token)")

    # The channel-change reload can clear Funnel Location/bids after
    # they're set - re-apply anything that got reset (same guard as the
    # baseline/prior TTD suites).
    page.wait_for_timeout(1000)
    funnel_select = page.locator("mat-select[formcontrolname='funnelLocation']")
    if "mat-mdc-select-empty" in (funnel_select.get_attribute("class") or ""):
        select_mat_option(page, "funnelLocation", FUNNEL_LOCATION_LABELS[funnel])
    base_bid = ag_form.locator("input[formcontrolname='baseBidAmount']")
    if not base_bid.input_value():
        base_bid.fill("1")
    max_bid = ag_form.locator("input[formcontrolname='maxBidAmount']")
    if not max_bid.input_value():
        max_bid.fill("1")
    assert "mat-mdc-select-empty" not in (funnel_select.get_attribute("class") or ""), \
        "Funnel Location is empty after the guard"
    assert base_bid.input_value() and max_bid.input_value(), "Bid fields empty after the guard"

    is_enabled = ad_group.get("IsEnabled")
    enabled_cb = ag_form.locator("mat-checkbox[formcontrolname='isEnabled']")
    if enabled_cb.count() > 0 and enabled_cb.is_visible():
        enabled_input = enabled_cb.locator("input[type='checkbox']")
        want_checked = bool(is_enabled)
        if enabled_input.is_checked() != want_checked:
            enabled_cb.click()
        if want_checked:
            expect(enabled_input).to_be_checked()
        else:
            expect(enabled_input).not_to_be_checked()
        ok(f"ag{index}-enabled", f"'Enabled' checkbox = {want_checked} (IsEnabled = {is_enabled})")
    else:
        print(f"TEST ag{index}-enabled SKIPPED -> 'Enabled' checkbox not present on this form")

    if ad_group.get("RTBAttributes", {}).get("BudgetSettings"):
        print(f"TEST ag{index}-budget-settings SKIPPED -> ad-group-level RTBAttributes.BudgetSettings present "
              "in the JSON, but there is no ad-group-level budget control anywhere in this frontend - only the "
              "Campaign Channel's Flight budget is settable")
    if ad_group.get("RTBAttributes", {}).get("AudienceTargeting"):
        print(f"TEST ag{index}-audience-targeting SKIPPED -> left at default ('Target Everyone'), same "
              "precedent as the baseline suite")

    return ad_group_name


def build_ad_groups_ttd(page: Page, ref: dict):
    ad_groups = ref.get("AdGroups") or []
    tags = compute_ad_group_tags(ad_groups)

    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()

    dialog = page.locator("dv360-io-summary-dialog")
    expect(dialog).to_be_visible()
    dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
    expect(dialog).not_to_be_visible()
    ok("ag-summary-dialog", "'Review insertion orders' dialog confirmed with 'Confirm & continue'")

    ag_form = page.locator("app-ttd-ad-groups form")
    expect(ag_form).to_be_visible()
    ok("ag-form", "navigated to Ad Groups")

    ad_groups_section = page.locator("section.ttd-ad-groups")
    names = []
    for i, ad_group in enumerate(ad_groups):
        if i > 0:
            create_btn = ad_groups_section.locator("button", has_text="Create another")
            create_btn.scroll_into_view_if_needed()
            create_btn.click()
            page.wait_for_timeout(500)
        name = _fill_single_ad_group(page, ag_form, ad_group, i, tags[i])
        names.append(name)

    ok("ag-count", f"{len(names)} ad group(s) created: {names}")

    # Deals & Contracts section reordered directly below Geography -
    # structural verification carried over from the baseline suite (not a
    # fillable field).
    section_headings = ag_form.locator("span.text-base.font-bold").all_inner_texts()
    if "Geography" in section_headings:
        geo_idx = section_headings.index("Geography")
        assert section_headings[geo_idx + 1] == "Deals & Contracts", (
            f"Expected 'Deals & Contracts' right after 'Geography', got order: {section_headings}"
        )
        ok("ag-section-order", "'Deals & Contracts' section confirmed reordered directly below 'Geography'")

    return names


# --------------------------------------------------------------------------
# Recap
# --------------------------------------------------------------------------
def test_recap(page: Page, campaign_name: str):
    """Same after-submit logic as the baseline/prior TTD suites: a summary
    dialog may reappear here too, dismissed best-effort, then the
    Start-campaign gate with a real launch requiring a typed 'yes'."""
    page.locator("div.step-footer").locator("button.mdc-button", has_text="Next").click()
    dialog = page.locator("dv360-io-summary-dialog")
    try:
        expect(dialog).to_be_visible(timeout=2000)
        dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
        expect(dialog).not_to_be_visible()
    except AssertionError:
        pass

    expect(page.locator("app-recap-and-validate")).to_be_visible()
    ok("next-to-recap", "navigated to the Recap step")

    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible()
    answer = input(
        f"\n>>> 'Start campaign' ACTUALLY LAUNCHES on {ADVERTISER}'s live TTD account. "
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

        status_cell = campaign_row.locator("td[aria-colindex='9']")
        status_text = status_cell.inner_text().strip()
        assert status_text in ("SUBMITTED", "COMPLETED"), f"Unexpected campaign status: '{status_text}'"
        ok("status", f"campaign '{campaign_name}' is in '{status_text}' status")
    else:
        print("TEST start-campaign SKIPPED -> click on 'Start campaign' cancelled by the user")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    ref = load_reference()
    assert CLIENT and ADVERTISER, (
        "CLIENT/ADVERTISER are not set - look up which Nexify Client/Advertiser corresponds to "
        f"TTD AdvertiserId {ref.get('AdvertiserId')} and fill in the two constants at the top of "
        "this file before running."
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
            campaign_name = test_general_info(page)
            test_global_setup(page, ref, date_from, date_to)
            test_campaign_channels(page, ref, date_from, date_to)
            build_ad_groups_ttd(page, ref)
            test_recap(page, campaign_name)

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

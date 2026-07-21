# Bug: YouTube ad-group Bid strategy/value has NO control at all for Target Frequency / Non-skippable line items

## Symptom

For a DV360 line item of type `LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_TARGET_FREQUENCY`
or `LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_NON_SKIPPABLE`, the ad-group "Bid
strategy" field is permanently disabled showing `—`, and the "Bid value"
input silently discards anything typed into it. Unlike
[BUG_youtube_ad_group_bid_value.md](BUG_youtube_ad_group_bid_value.md) (a
timing race that resolves itself once the enforced type loads), this never
resolves — there is currently no way in the UI to set a bid value for these
two line item types at all. Submitting such a campaign would crash the DSP
the same way: `float() argument must be a string or a real number, not
'NoneType'`.

A second, related symptom: landing on one of these line item types does not
even auto-create the first ad group. The "YouTube Ad Groups" section renders
with zero tabs until "+ Add ad group" is clicked manually.

## Root cause

**File:** `nexify-frontend-main/src/app/shared/utils/dv360-youtube-bidding-util.ts`

```ts
export function enforcedYtBidType(
  lineItemType: string | null | undefined,
): Dv360YoutubeAndPartnersBiddingStrategyType | null {
  const t = lineItemType ?? '';

  if (t === 'LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH') {
    return DV360_YT_BID_TYPE.TARGET_CPM as unknown as Dv360YoutubeAndPartnersBiddingStrategyType;
  }

  if (t === 'LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_VIEW') {
    return DV360_YT_BID_TYPE.TARGET_CPM as unknown as Dv360YoutubeAndPartnersBiddingStrategyType;
  }

  return null;   // <-- every other YouTube LI type, including
                 //     TARGET_FREQUENCY and NON_SKIPPABLE, falls through here
}
```

This function only knows about two of the DV360 YouTube line item types.
Every other `LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_*` type (Target Frequency,
Non-skippable, Action, Ad sequence, Audio, Non-skippable OTT, Default video
ads, …) gets `null` back. The DV360 API itself absolutely supports and
expects a bid strategy for these types — confirmed via a real DV360 API
export (`template_1117994126_57061851_Generico_Oreo.json`), where Target
Frequency and Non-skippable ad groups both carry a real
`youtubeAndPartnersBid` with type `TARGET_CPM` and a positive `value`
(~€2.85–2.90). This is a coverage gap in the frontend's enum mapping, not a
DV360 API limitation.

## Where it breaks, downstream of the null

**File:** `.../dv360-youtube-line-items/dv360-youtube-line-items.component.ts`

Three places all early-return on `!enforcedType`:

```ts
// 1. Ad group auto-creation never fires for these LI types.
effect(() => {
  const liKey = this.liKeySig();
  const enforcedType = this.enforcedBidType();
  if (!liKey || !enforcedType) return;        // <-- ensureOne() never runs
  this.ytAdGroupsStore.ensureOne(liKey);
  this.ytAdGroupsStore.ensureBidTypeForLi(liKey, enforcedType);
});

// 2. Bid value hydration always shows blank.
effect(() => {
  const adGroup = this.activeAdGroup();
  const enforcedType = this.enforcedBidType();
  if (!adGroup || !enforcedType) {
    this.bidValueView = null;                 // <-- always null for these types
    return;
  }
  ...
});

// 3. Typing into Bid value is silently discarded.
onBidValueChange(value: number | null) {
  const adGroup = this.activeAdGroup();
  const enforcedType = this.enforcedBidType();
  if (!adGroup || !enforcedType) return;       // <-- every keystroke dropped
  ...
}
```

**File:** `.../dv360-youtube-line-items.component.html` (lines 44–58)

```html
<mat-label>Bid strategy</mat-label>
@if (enforcedBidType(); as bidType) {
    <mat-select [ngModel]="bidType" disabled> ... </mat-select>
} @else {
    <mat-select [ngModel]="null" disabled>
        <mat-option [value]="null">—</mat-option>   <!-- permanent for these LI types -->
    </mat-select>
}
```

The "Bid strategy" select is *always* disabled (read-only, mirroring the
enforced type) — that part is by design for REACH/VIEW. But because no
other LI type ever gets an enforced type, the select is stuck on `—`
forever for them, and there is no alternate manual dropdown anywhere in the
template. There is no path to set a bid strategy type or value at all.

Manually adding an ad group (`addAdGroup()`, the "+ Add ad group" button)
does work standalone — it passes `enforcedType ?? undefined` to the store,
which just creates a blank ad group with
`bidStrategy.youtubeAndPartnersBid.type = 'YOUTUBE_AND_PARTNERS_BIDDING_STRATEGY_TYPE_UNSPECIFIED'`
and no `value`. So the ad group can be created and its other targeting
(categories, audiences, age range) filled in fine — only the bid is
unreachable.

## How to fix

1. **Extend `enforcedYtBidType()`** to cover the rest of the
   `LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_*` enum (`Dv360LineItemType`, in
   `open-api/models/dv-360-line-item-type.ts`), each mapped to whatever bid
   strategy type(s) DV360 actually allows for it. If a given type
   legitimately supports more than one bid strategy (unlike REACH/VIEW's
   1:1 mapping), the "Bid strategy" select will need to stop being
   permanently `disabled` and instead offer the valid options for that LI
   type — the current design assumes a single enforced type per LI type,
   which may not generalize to every YouTube LI type DV360 supports.
2. Once (1) is fixed, re-verify the ad-group auto-creation effect and
   `onBidValueChange` behave correctly for the newly-covered types (they
   should, since they're both already correctly gated on `enforcedBidType()`
   — the fix is purely in the mapping function).
3. **Block submission (minimum, already covered by the test suite)** — a
   campaign with any `youtubeAndPartnersBid.type` in
   `UNSPECIFIED`/missing-value state should never reach the DSP. See below.

Add a component test covering every `LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_*`
enum value: the ad-group Bid strategy must resolve to a real (non-null)
type, and a typed Bid value must be readable back from the committed model,
not just the DOM.

## Test-suite mitigation (already applied)

`test_dv360_generico_oreo_json_playwright.py` (which exercises Target
Frequency and Non-skippable line items) does not attempt to set the
ad-group bid at all for these two LI types — it prints a `NOTE` and moves
on, since the field is confirmed unreachable rather than merely flaky. It
adds ad groups manually via "+ Add ad group" (`ensure_ag_count`, since the
auto-create effect never fires) and still fills every other automatable
ad-group section (age range, audiences, categories).

The shared submit guard from `test_dv360_youtube_json_playwright.py`
(`find_missing_ag_bid_values` + `install_submit_guard`) is imported as-is
and correctly flags these ad groups' `UNSPECIFIED`/valueless bid strategy as
missing, blocking an actual "Start campaign" launch — no broken campaign
for these line item types can reach the DSP through this suite, but the
underlying gap (no way to set a real bid for them) is a genuine, unfixed
frontend limitation.

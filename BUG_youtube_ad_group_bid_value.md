# Bug: YouTube ad-group Bid value silently dropped → DSP `float(None)` crash

## Symptom

When a DV360 YouTube campaign is sent to the DSP, the backend rejects it with:

```
float() argument must be a string or a real number, not 'NoneType'
```

The campaign builds and submits normally in the UI — the error only appears
on the DSP side while it parses the payload.

## Root cause

In the outgoing campaign payload, one or more YouTube **ad groups** ship a bid
strategy that has a `type` but no `value`:

```json
"bidStrategy": {
  "youtubeAndPartnersBid": {
    "type": "YOUTUBE_AND_PARTNERS_BIDDING_STRATEGY_TYPE_TARGET_CPM"
    // <-- "value" is missing
  }
}
```

A correct ad group looks like this instead:

```json
"bidStrategy": {
  "youtubeAndPartnersBid": {
    "type": "YOUTUBE_AND_PARTNERS_BIDDING_STRATEGY_TYPE_TARGET_CPM",
    "value": "1"
  }
}
```

The DSP does the equivalent of `float(youtubeAndPartnersBid.value)`. When
`value` is absent it becomes `None`, and `float(None)` raises the error above.

## Where it happens

**File:** `nexify-frontend-main/src/app/features/campaign-create/steps/line-items/components/dv360-youtube-line-items/dv360-youtube-line-items.component.ts`
**Method:** `onBidValueChange` (~line 942)

```ts
onBidValueChange(value: number | null) {
  const adGroup = this.activeAdGroup();
  const enforcedType = this.enforcedBidType();
  if (!adGroup || !enforcedType) return;   // <-- value silently dropped here
  ...
  this.patchActiveAdGroup({
    bidStrategy: {
      youtubeAndPartnersBid: { ...prevBid, type: enforcedType, value: apiValue },
    },
  });
  this.bidValueView = value;
}
```

The Bid value is committed to the ad-group model **only if `enforcedBidType()`
has already resolved**. If the user types a value before that happens, the
early `return` discards it.

Crucially, the bid `type` is stamped onto the ad group **separately** (derived
from the line-item type), so it's always present. That's why the payload looks
almost complete — only the numeric `value` goes missing.

**Template:** `.../dv360-youtube-line-items.component.html` (lines 44–70)

```html
<!-- Bid strategy: shows the enforced type once resolved, "—" until then -->
@if (enforcedBidType(); as bidType) { ... } @else { <mat-option>—</mat-option> }

<!-- Bid value: editable the WHOLE time, including during the "—" window -->
<input matInput type="number" [ngModel]="bidValueView"
       (ngModelChange)="onBidValueChange($event)" />
```

The "Bid strategy" select is gated on `enforcedBidType()` (shows `—` until
ready), but the "Bid value" input is editable the entire time — so a value can
be entered during the unresolved window and lost.

## Why it's intermittent

In a campaign with several YouTube line items, each ad group resolves its
enforced bid type independently. Whichever ad groups haven't resolved yet at
the moment their Bid value is entered lose it; the rest are fine. So the same
campaign can ship a mix of valid and broken bids, and which ones break varies
run to run — a timing race.

## How to fix

Frontend, in rough order of preference:

1. **Gate the input (preferred).** Disable / make the "Bid value" input
   read-only until `enforcedBidType()` has resolved — mirroring how the
   "Bid strategy" select is already gated. If the value can't be entered
   early, it can't be dropped.

2. **Stash and apply.** In `onBidValueChange`, when `enforcedType` isn't ready,
   hold the pending value and apply it once the type resolves, instead of
   returning and discarding it.

3. **Block submission (minimum).** Add validation that prevents campaign
   submission when any YouTube ad group has a `youtubeAndPartnersBid.type`
   without a `value`, so it fails clearly in-app rather than crashing the DSP.

Add a component test covering: entering a Bid value **before** the enforced bid
type resolves must still yield a committed `value` (or a blocked submit) — never
a bid object with type-but-no-value.

## Related: two more Fixed-mode numeric fields with the same drop pattern

The DSP enforces two more rules on the Line Items step, and both fail the same
way — a required numeric that gets dropped when its control isn't ready yet:

1. **Budget allocation = Fixed → a max amount is required.**
2. **Bid strategy = Fixed Bid → Bid amount (CPM) must be a positive number > 0.**

**File:** `.../dv360-line-items/dv360-line-items.component.ts`

- `bidAmount` is initialised to `null` (~line 398) and is **`disable()`d until
  "Fixed bid" is selected** (~lines 1570 / 1584). If the value is entered
  before the control is enabled, it's dropped and the payload falls back to
  `bidAmountMicros: '0'` (~line 1772) — which violates rule 2 ("> 0").
- For a Fixed allocation with a null budget, `maxAmount` is **omitted entirely**
  from the payload (`...(maxAmount != null ? { maxAmount } : {})`, ~line 1637) —
  which violates rule 1 ("must indicate max amount").

Same fix shape as the ad-group bid: **gate the input** (keep Bid amount
disabled/read-only until Fixed bid is fully applied, and require a max amount
whenever allocation is Fixed), and/or **block submission** when a Fixed-mode
line item has a missing or non-positive amount, so it fails clearly in-app
instead of crashing / being rejected by the DSP. Add tests covering: entering
a Fixed-bid amount before the control enables, and a Fixed allocation with an
empty budget, must never ship `bidAmountMicros: '0'` or a missing `maxAmount`.

## Test-suite mitigation (already applied)

`test_dv360_youtube_json_playwright.py` was hardened on all three fields:

- `set_ag_bid_value` (ad-group bid) — waits for the "Bid strategy" select to
  show a real enforced type instead of `—` before filling, then reads the value
  back and re-fills until it sticks.
- `fill_positive_amount` (new helper, used for `budget` and the Fixed-bid
  `bidAmount`) — waits for the control to be enabled, fills, then reads back and
  re-fills until a positive number > 0 is committed.

All three now fail loudly at build time instead of at the DSP. This stops the
test from shipping a broken payload, but it does **not** fix the underlying
bugs: a real user who fills any of these fields too early still hits the same
DSP rejection / crash.

## ⚠️ CAVEAT: the ad-group bid guard is unreliable — verify committed state, not DOM

**`set_ag_bid_value` can FALSE-PASS. Do not trust it as-is.**

Observed live: a run where the test did **not** fail still shipped a payload
whose YouTube ad groups had `youtubeAndPartnersBid.type` but **no `value`** (all
5 ad groups), and the DSP `float(None)`-crashed on it. So the guard let a
valueless ad group through.

Root reason: the guard checks the value by reading the **DOM input value back**
(`bid_field.input_value() == "1"`). But the ad-group Bid value input is one-way
`[ngModel]="bidValueView"` with `(ngModelChange)="onBidValueChange($event)"`.
Typing sets the DOM value regardless of whether the handler commits it, so the
input can read `"1"` while `onBidValueChange` took its early `return` (enforced
type not resolved) and the model / payload value stays null. **DOM value ≠
committed model value.** The `to_have_value`-style readback cannot tell the
difference, so the guard passes on a value that never reaches the payload.

(Contrast the budget / Fixed-bid `bidAmount` fields: those are reactive-form
controls bound by `formcontrolname`, where a successful `fill` does update the
model — so `fill_positive_amount`'s readback is meaningful there. The unreliable
case is specifically the ad-group bid's one-way `ngModel` input.)

When revisiting, before trusting any result:
- Run once with `... 2>&1 | tee run_youtube.log` to confirm whether the guard
  actually executed for each ad group, or whether the ad-group build was skipped
  entirely (that same run also had empty `assignedTargetingOptions` / `adGroupAds`,
  which would point to the build not running those lines at all — a different bug).
- Rework `set_ag_bid_value` to assert the **committed** value, not the DOM:
  read it back from the Angular component / ad-group store via `javascript_tool`
  (e.g. inspect `adGroup.bidStrategy.youtubeAndPartnersBid.value`), or assert on
  the outgoing request payload itself, so a dropped value can't false-pass.

### RESOLUTION (implemented)

Confirmed empirically once geo was fixed and the build completed: the DOM
readback **did** false-pass on the *first* YouTube ad group (`type` shipped
without `value`) while the other four committed. Two changes were made:

1. `set_ag_bid_value` now **double-fills** the value after the enforced bid type
   resolves — the first `onBidValueChange` for a freshly-activated ad group can
   fire before `enforcedBidType()` has propagated, so the second fill lands after
   the model is ready and commits. (The DOM check is kept only as a "did it reach
   the input at all" sanity assert, not as proof of commit.)
2. **Authoritative backstop** — `find_missing_ag_bid_values` + a `page.route`
   intercept in `test_finish_and_submit` inspect the *actual outgoing submit
   payload*; if any `youtubeAndPartnersBid` lacks a positive `value`, the request
   is **aborted** (no broken campaign reaches the DSP) and the test fails loudly
   naming the exact offenders. This walks the real payload, so it cannot be
   fooled by the one-way-ngModel DOM false-pass.

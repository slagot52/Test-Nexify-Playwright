# Bug: YouTube ad-group section fails to mount when an LI type is set during hydration

## Symptom

Setting a line item's type to a YouTube type (e.g. `LINE_ITEM_TYPE_YOUTUBE_AND_PARTNERS_REACH`)
sets the "Line item type" control correctly — the select visibly shows the
YouTube label — but the **"YouTube Ad Groups" section
(`<app-dv360-youtube-line-items>`) never appears**. Without it, there's no way
to add ad groups, set the ad-group bid, or fill ad-group targeting.

Observed live: reproducible on the *later* Insertion Orders of a large mixed
campaign (e.g. the 3rd YouTube IO in), after several heavy YouTube LIs have
already been built. Earlier IOs work; the failure rate rises as the form gets
heavier. Diagnostic confirmed the `lineItemType` control still reads the
correct YouTube type at failure time — so this is **not** a value revert.

## Root cause

The section is gated in the template:

```html
@if (isYouTubeLi()) {
  <app-dv360-youtube-line-items [liKey]="liUid()" ...>
}
```

`isYouTubeLi()` is computed from a **signal**, not the form control directly:

```ts
readonly isYouTubeLi = computed(() =>
  isYtLineItemType(this.liTypeManualSig() ?? this.form.controls.lineItemType.value),
);
```

`liTypeManualSig` is maintained in two places:
- **`hydrateEffect`** (on switching LI/IO) sets it to the hydrated LI's type and
  resets the form control **with `emitEvent: false`**:
  ```ts
  this.liTypeManualSig.set((patch.lineItemType) ?? null);                 // e.g. Display
  this.form.controls.lineItemType.setValue(patch.lineItemType, { emitEvent: false });
  ```
- the **`lineItemType.valueChanges`** subscription, which is
  `.pipe(distinctUntilChanged())` and also early-returns during hydration:
  ```ts
  this.form.controls.lineItemType.valueChanges
    .pipe(distinctUntilChanged(), takeUntilDestroyed())
    .subscribe((type) => {
      if (this.hydrating) return;
      this.liTypeManualSig.set(type);
      ...
    });
  ```

The killer interaction: because hydration resets the control with
`emitEvent: false`, `distinctUntilChanged()` **never sees** the hydrated value
— its "last emitted" memory still holds **the type you last selected on the
previous IO**. So:

1. Switching into a fresh IO hydrates its default **Display** LI: the control
   value becomes Display (no emission), and `liTypeManualSig` = Display.
2. You select the target YouTube type. If it is the **same** type you selected
   on the previous IO, `distinctUntilChanged()` sees value ≡ last-emitted and
   **suppresses** it — the subscription never runs, so `liTypeManualSig` stays
   **Display**.
3. `isYouTubeLi()` reads `liTypeManualSig` (non-null, wins the `??`) → Display →
   **false** → the ad-group panel never mounts, and the LI renders the full
   non-YouTube layout (Bid strategy, Deals, Deal groups, Sensitive Category,
   Gender, Age, …) even though the type control clearly shows the YouTube type.

The `if (this.hydrating) return` guard is a secondary contributor (it can swallow
a selection that lands mid-hydration), but the **primary, reproducible trigger
is two consecutive IOs (in build order) whose first line item is the same
type**, via the `distinctUntilChanged` + `emitEvent:false` mismatch above.

## Why it hits later IOs / specific pairs

It is not really "load dependent" — it's **order dependent**. In the Mugler
campaign the IOs are OTT, Display, Video, **View, Reach, Reach, View**. Built
sequentially, `View→Reach` transitions are always distinct and work, but the
`Reach(IO4) → Reach(IO5)` pair repeats the type and hits the bug. Interleaving
so consecutive first-LI types differ (View, Reach, View, Reach) avoids it
entirely.

## How to fix (frontend)

Any one of:

1. **Don't gate the signal update on `hydrating`.** Update `liTypeManualSig`
   from `valueChanges` even during hydration (the early return should guard only
   the *side effects* — field clearing, autosave — not the signal that decides
   which sub-UI to render).
2. **Derive `isYouTubeLi()` from the form control**, not a separately-maintained
   signal, so the rendered section can never disagree with the selected type.
3. **Re-assert `liTypeManualSig` when hydration ends** (in `hydrateEffect`'s
   `hydrating = false` tail, set it from the current control value).

Add a test: select a YouTube type while a hydrate is in flight, then assert the
YouTube ad-group section renders.

## Test-suite mitigation (already applied)

Two layers:

1. **Primary (deterministic): interleave the IO build order** so no two
   consecutive first-LI type selections repeat. In
   `test_dv360_mugler_json_playwright.py` the YouTube IOs are built View, Reach,
   View, Reach (IO3, IO4, IO6, IO5) instead of sequentially. Build order does
   not affect the final campaign — each IO is independent in the store — so this
   is safe and sidesteps the `distinctUntilChanged` suppression entirely.
2. **Fallback: `fill_li_youtube_basics`** in
   `test_dv360_youtube_json_playwright.py` settles before selecting the type,
   and if the `<app-dv360-youtube-line-items>` section still isn't present it
   **wiggles the type** (selects `Display`, then the target) to force a distinct
   transition, up to 6 attempts, with a DOM-probe NOTE each time (counts of LI
   forms / type selects / YouTube panels / the non-YouTube "Bid strategy"
   section) for diagnosis. NOTE: the wiggle alone was observed NOT to reliably
   recover once stuck in this state, which is why the build-order interleave is
   the primary mitigation.

Neither fixes the underlying bug: a real user who builds two same-type YouTube
IOs in a row, or picks a YouTube type quickly after switching IOs, can still land
a line item that shows "YouTube …" yet offers no ad-group UI.

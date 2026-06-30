# Test Nexify Playwright

End-to-end test suites using **Playwright (Python)** for the campaign creation
flows on [publicisnexify.com](https://publicisnexify.com/), covering three
DSPs: **DV360**, **The Trade Desk (TTD)**, and **Amazon DSP**.

## Requirements

- Python 3.12+
- Git
- SSO access to publicisnexify.com (an account with permission to create
  campaigns for the advertisers used by the test suites)

## Setup (first time)

Clone the repo and set up a virtual environment:

```bash
git clone git@github.com:slagot52/Test-Nexify-Playwright.git
cd Test-Nexify-Playwright

python -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
playwright install              # downloads the Chromium browser (one time only)
```

## SSO login (first run)

The site requires an SSO login, which Playwright cannot automate. Every suite
uses the "save the session once, reuse it forever" strategy:

1. On the **first run** of any suite, a visible browser opens to the login
   page. Complete the SSO login by hand (including any MFA prompt) until you
   land on the actual `publicisnexify.com` homepage/dashboard — not an
   intermediate Microsoft "Stay signed in?" screen.
2. Go back to the terminal and press **ENTER**. The session (cookies +
   localStorage) is saved to `auth_state.json` in the project root.
3. **Subsequent runs** of any suite load `auth_state.json` and skip the login
   entirely — the session is shared across all three suites.

If a run fails with a "Redirected to login" error, the saved session has
expired. Delete it and run again to perform a new login:

```bash
rm auth_state.json
python test_dv360_playwright.py   # or any suite — triggers a fresh login
```

> ⚠️ `auth_state.json` contains live session cookies. It is already in
> `.gitignore` and **must never be committed or shared**.

## Running a suite

Make sure the virtual environment is activated (`source venv/bin/activate`),
then run any of:

```bash
python test_dv360_playwright.py    # DV360 suite  (58 tests)
python test_ttd_playwright.py      # TTD suite    (43 tests)
python test_amazon_playwright.py   # Amazon DSP suite (40 tests)
```

Each run:
- Opens a **maximized, visible** browser window (headless mode is not used —
  the responsive layout collapses fields at small viewport sizes).
- Prints `TEST N OK -> ...` for each passing check, or `TEST FAILED ❌` with
  details if something breaks.
- Leaves the browser **open** at the end so you can inspect the result —
  press **ENTER** in the terminal to close it.

### The "Start campaign" gate

The final step of each suite clicks **"Start campaign"**, which is a real,
**irreversible production action** (it actually launches the campaign on the
live site). To prevent accidental launches, the script pauses and asks:

```
>>> 'Start campaign' ACTUALLY LAUNCHES the campaign. Type 'yes' to confirm the click (anything else cancels):
```

- Type `yes` to actually submit the campaign.
- Type anything else (e.g. `no`, or just press ENTER) to skip that step —
  the rest of the suite has already run, but no real campaign is created.

## Project files

| File | Purpose |
|------|---------|
| `test_dv360_playwright.py` | DV360 suite + shared helpers (`ok`, `select_mat_option`, `select_all_multi`, `fill_and_verify`, `manual_login`, `test_landing`, etc.) reused by the other two suites |
| `test_ttd_playwright.py`   | TTD suite, imports shared helpers from the DV360 file |
| `test_amazon_playwright.py`| Amazon DSP suite, imports shared helpers from the DV360 file |
| `requirements.txt` | Python dependencies |
| `auth_state.json` | Saved SSO session (git-ignored, created on first run) |

Running any single suite is self-contained — you don't need to run the
others first.

## DV360 test structure

| Range | Section |
|-------|---------|
| 1–3   | Landing, /campaign redirect |
| 4–16  | Create Campaign, General Info |
| 17–26 | Global Setup |
| 27–37 | Insertion Orders |
| 38    | Sidebar sync check |
| 39–58 | Line Items + Start campaign |

## TTD test structure

| Range | Section |
|-------|---------|
| 1–3   | Landing, /campaign redirect |
| 4–16  | Create Campaign, General Info |
| 17–22 | Global Setup |
| 23–30 | Campaign Channels |
| 31–38 | Ad Groups |
| 39–43 | Recap + Start campaign |

## Amazon DSP test structure

| Range | Section |
|-------|---------|
| 1–3   | Landing, /campaign redirect |
| 4–16  | Create Campaign, General Info |
| 17–27 | Insertion Orders |
| 28–38 | Line Items |
| 39–40 | Recap + Start campaign (with confirmation gate) |

## Troubleshooting

- **`ModuleNotFoundError: No module named 'playwright'`** — you're running
  the system Python instead of the project's virtual environment. Run
  `source venv/bin/activate` first, or invoke `venv/bin/python <script>.py`
  directly.
- **"Redirected to login" failure** — the saved SSO session expired. Delete
  `auth_state.json` and run the suite again to log in fresh (see above).
- **A locator/selector starts failing that previously worked** — the live
  site's markup or copy may have changed (this has happened before, e.g. a
  dropdown option being renamed). Re-inspect the element in the browser and
  update the corresponding `select_mat_option`/locator call.

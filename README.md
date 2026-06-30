# Test Nexify Playwright

End-to-end test suites using **Playwright (Python)** for the campaign creation
flows on [publicisnexify.com](https://publicisnexify.com/).

## Requirements

- Python 3.12+
- SSO access to publicisnexify.com

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install          # downloads the browsers (one time only)
```

## SSO login (first run)

The site requires an SSO login, which Playwright cannot automate. We use the
"save the session once, reuse it forever" strategy:

1. On the **first run** the browser opens: complete the SSO login by hand, then
   press ENTER in the terminal. The session is saved to `auth_state.json`.
2. **Subsequent runs** load `auth_state.json` and skip the login.

To force a new login: delete `auth_state.json` and run again.

> ⚠️ `auth_state.json` contains the session cookies and localStorage: it is
> already in `.gitignore` and **must not be committed**.

## Files

| File | DSP | Status |
|------|-----|--------|
| `test_dv360_playwright.py` | DV360 | ✅ Complete (58 tests) |
| `test_ttd_playwright.py`   | TTD   | ✅ Complete (43 tests) |
| `test_amazon_playwright.py`| Amazon DSP | 🚧 In progress |

## Running

```bash
python test_dv360_playwright.py    # DV360 suite
python test_ttd_playwright.py      # TTD suite
python test_amazon_playwright.py   # Amazon DSP suite
```

The browser stays **open** at the end of each run: press ENTER to close it.

The final **Start campaign** step is irreversible: the click happens **only**
if you confirm by typing `yes` in the terminal.

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
| …     | (remaining steps TBD) |

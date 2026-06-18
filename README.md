# Test Nexify Playwright

End-to-end test suite using **Playwright (Python)** for the DV360 campaign
creation flow on [publicisnexify.com](https://publicisnexify.com/).

The test walks through the whole wizard: **Global Setup → Insertion Orders →
Line Items → Start campaign**, filling and verifying every field (58 numbered
checks).

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

## Running

```bash
python test_dv360_playwright.py
```

- The browser stays **open** at the end of the tests for manual inspection:
  press ENTER to close it.
- The last step (**Start campaign**, test 58) is an irreversible production
  action: the click happens **only** if you confirm by typing `yes` in the
  terminal.

## Test structure

| Range | Section |
|-------|---------|
| 1–26  | SSO, campaign creation, General Info, template dialog, **Global Setup** |
| 27–37 | **Insertion Orders** |
| 38    | Sidebar sync check against the form data |
| 39–58 | **Line Items** + navigation and **Start campaign** (with confirmation gate) |

## Files

- `test_dv360_playwright.py` — main suite (publicisnexify.com)

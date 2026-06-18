# Test Nexify Playwright

Suite di test end-to-end con **Playwright (Python)** per il flusso di creazione
campagna DV360 su [publicisnexify.com](https://publicisnexify.com/).

Il test percorre l'intero wizard: **Global Setup → Insertion Orders → Line Items
→ Start campaign**, compilando e verificando ogni campo (58 controlli numerati).

## Requisiti

- Python 3.12+
- Accesso SSO a publicisnexify.com

## Setup

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install          # scarica i browser (una volta sola)
```

## Login SSO (prima esecuzione)

Il sito richiede login SSO, che Playwright non può automatizzare. Si usa la
strategia "salva la sessione una volta, riutilizzala sempre":

1. Alla **prima esecuzione** si apre il browser: completa il login SSO a mano,
   poi premi INVIO nel terminale. La sessione viene salvata in `auth_state.json`.
2. Le **esecuzioni successive** caricano `auth_state.json` e saltano il login.

Per forzare un nuovo login: cancella `auth_state.json` e riesegui.

> ⚠️ `auth_state.json` contiene cookie e localStorage della sessione: è già in
> `.gitignore` e **non va committato**.

## Esecuzione

```bash
python test_nexify_playwright.py
```

- Il browser resta **aperto** alla fine dei test per l'ispezione manuale: premi
  INVIO per chiuderlo.
- L'ultimo step (**Start campaign**, test 58) è un'azione di produzione
  irreversibile: il click avviene **solo** se confermi digitando `si` nel
  terminale.

## Struttura dei test

| Range | Sezione |
|-------|---------|
| 1–26  | SSO, creazione campagna, General Info, dialog template, **Global Setup** |
| 27–37 | **Insertion Orders** |
| 38    | Verifica sync della sidebar coi dati del form |
| 39–58 | **Line Items** + navigazione e **Start campaign** (con gate di conferma) |

## File

- `test_nexify_playwright.py` — suite principale (publicisnexify.com)
- `test_sito_playwright.py` / `test_sito.py` — esempi su saucedemo.com (Playwright / Selenium)
- `GUIDA.md` — guida introduttiva a Selenium/Playwright

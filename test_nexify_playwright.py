# -*- coding: utf-8 -*-
"""
TEST PLAYWRIGHT - publicisnexify.com  (con SSO)
================================================
Il sito richiede login tramite SSO (es. Microsoft / Google / Okta).
Playwright non puo' compilare quei form automaticamente, quindi si usa
la strategia "salva la sessione una volta, riutilizzala sempre":

  1. Prima esecuzione  ->  apre il browser VISIBILE, tu fai il login SSO
                           a mano; alla fine la sessione viene salvata in
                           auth_state.json.
  2. Esecuzioni successive  ->  carica auth_state.json e salta il login.

Per lanciarlo:  python test_nexify_playwright.py
Per forzare un nuovo login:  cancella auth_state.json e riesegui.
"""

import datetime
import json
import random
import re
import string
import time
from pathlib import Path

from playwright.sync_api import Page, expect, sync_playwright

# --------------------------------------------------------------------------
# Costanti
# --------------------------------------------------------------------------
AUTH_FILE = Path(__file__).parent / "auth_state.json"
BASE_URL = "https://publicisnexify.com"
TARGET_URL = BASE_URL + "/"
DATE_FMT = "%m/%d/%Y"  # formato atteso dal mat-datepicker (MM/DD/YYYY)


# --------------------------------------------------------------------------
# Helper riutilizzabili
# --------------------------------------------------------------------------
def ok(numero, messaggio):
    """Stampa l'esito positivo di un test in modo uniforme."""
    print(f"TEST {numero} OK -> {messaggio}")


def select_mat_option(page: Page, form_control_name: str, option_name: str):
    """
    Apre un <mat-select> identificato dal suo formcontrolname e seleziona
    l'opzione con il testo esatto indicato, poi verifica che il campo mostri
    il valore scelto.

    Dettagli importanti gestiti qui:
      - click(force=True): la mat-label flottante intercetta i pointer events
        sul trigger, ma il mat-select gestisce comunque il click e apre il
        pannello.
      - le opzioni sono renderizzate nel CDK overlay (fuori dal form), nel
        pannello con id "<select-id>-panel": ci limitiamo a quel pannello per
        evitare collisioni con altri dropdown.
      - get_by_role(..., exact=True): evita match parziali (es. "CPM" vs "VCPM").
    """
    select = page.locator(f"mat-select[formcontrolname='{form_control_name}']")
    expect(select).to_be_visible()
    select.scroll_into_view_if_needed()
    select_id = select.get_attribute("id")

    # Apre il pannello con retry: a volte il click non registra (timing dopo la
    # chiusura di un overlay precedente). Dal secondo tentativo usiamo la
    # tastiera (focus + Enter), che per i mat-select e' piu' affidabile del click.
    for tentativo in range(4):
        if tentativo == 0:
            select.click(force=True)
        else:
            select.focus()
            select.press("Enter")
        try:
            expect(select).to_have_attribute("aria-expanded", "true", timeout=2000)
            break
        except AssertionError:
            # reset di eventuali stati intermedi prima di riprovare
            page.keyboard.press("Escape")
            continue
    else:
        raise AssertionError(f"Impossibile aprire il mat-select '{form_control_name}'")

    panel = page.locator(f"#{select_id}-panel")
    expect(panel).to_be_visible()

    option = panel.get_by_role("option", name=option_name, exact=True)
    expect(option).to_be_visible()
    option.scroll_into_view_if_needed()
    option.click()

    # Verifica che il valore sia stato applicato; un retry copre i casi in cui
    # il primo click apre solo l'opzione senza confermarla.
    try:
        expect(select).to_contain_text(option_name, timeout=3000)
    except AssertionError:
        if select.get_attribute("aria-expanded") == "true":
            option.click()
        expect(select).to_contain_text(option_name)
    return select


def select_all_multi(page: Page, form_control_name: str, expected_text: str):
    """
    Apre un <mat-select multiple> con direttiva matselectall e seleziona tutte
    le opzioni. Idempotente: clicca "Select all" solo se resta qualche opzione
    non selezionata, cosi' lo stato finale e' sempre "tutte selezionate" anche
    su run ripetuti (un click su select-all gia' attivo deseleziona tutto).
    """
    select = page.locator(f"mat-select[formcontrolname='{form_control_name}']")
    expect(select).to_be_visible()
    select_id = select.get_attribute("id")
    select.click(force=True)

    panel = page.locator(f"#{select_id}-panel")
    expect(panel).to_be_visible()
    select_all_opt = panel.locator("mat-option[matselectalloption]")
    unselected = panel.locator("mat-option:not([matselectalloption])[aria-selected='false']")
    if unselected.count() > 0:
        select_all_opt.click()
    page.keyboard.press("Escape")
    expect(select).to_contain_text(expected_text)
    return select


def fill_and_verify(scope, form_control_name: str, value: str):
    """Compila un input (per formcontrolname) e verifica il valore inserito."""
    field = scope.locator(f"input[formcontrolname='{form_control_name}']")
    expect(field).to_be_visible()
    field.fill(value)
    actual = field.input_value()
    assert actual == value, f"'{form_control_name}': atteso '{value}', trovato '{actual}'"
    return field


# --------------------------------------------------------------------------
# Gestione sessione SSO
# --------------------------------------------------------------------------
def login_manuale(playwright):
    """
    Apre una finestra visibile e aspetta che l'utente completi il login SSO,
    poi salva lo storage state (cookies + localStorage) in auth_state.json.
    """
    print("\nNessuna sessione salvata trovata.")
    print("Si aprira' il browser: esegui il login SSO manualmente.")
    print("Quando sei DENTRO il sito (homepage caricata), premi INVIO qui.")

    browser = playwright.chromium.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()
    page.goto(TARGET_URL)

    input("\n>>> Premi INVIO dopo aver completato il login SSO nel browser... ")

    state = context.storage_state()
    AUTH_FILE.write_text(json.dumps(state))
    print(f"Sessione salvata in {AUTH_FILE.name}")

    browser.close()
    return state


# --------------------------------------------------------------------------
# Gruppi di test
# --------------------------------------------------------------------------
def test_landing(page: Page):
    """TEST 1-3: la pagina /campaign si apre dopo l'SSO ed ha contenuti."""
    response = page.goto(TARGET_URL, wait_until="domcontentloaded")
    assert response.status < 400, f"HTTP {response.status}"
    page.wait_for_load_state("networkidle")

    url_finale = page.url
    if "login" in url_finale.lower() or "sso" in url_finale.lower():
        raise AssertionError(
            f"Reindirizzato al login ({url_finale}). "
            f"Cancella {AUTH_FILE.name} e riesegui per fare un nuovo login."
        )
    assert url_finale.rstrip("/") == f"{BASE_URL}/campaign", (
        f"URL atteso: {BASE_URL}/campaign\nURL trovato: {url_finale}"
    )
    ok(1, f"URL corretto ({url_finale}), titolo: '{page.title()}'")

    expect(page.locator("nav, header, [role='navigation']").first).to_be_visible()
    ok(2, "elemento di navigazione trovato e visibile")

    body_text = page.inner_text("body")
    assert len(body_text.strip()) > 100, "Il body sembra vuoto"
    ok(3, f"testo nel body ({len(body_text.strip())} caratteri)")


def test_general_info(page: Page):
    """TEST 4-16: creazione campagna, step General Info, griglia advertiser."""
    create_btn = page.locator("button.mdc-button--unelevated", has_text="Create Campaign")
    expect(create_btn).to_be_visible()
    ok(4, "pulsante 'Create Campaign' trovato e visibile")

    create_btn.click()
    page.wait_for_url("**/campaign/create", timeout=10000)
    assert page.url.rstrip("/") == f"{BASE_URL}/campaign/create", (
        f"URL atteso: {BASE_URL}/campaign/create\nURL trovato: {page.url}"
    )
    ok(5, f"navigato correttamente su {page.url}")

    footer = page.locator("div.step-footer")
    expect(footer).to_be_visible()
    expect(footer.locator("button.mdc-button", has_text="Cancel")).to_be_visible()
    expect(footer.locator("button.mdc-button", has_text="Save as draft")).to_be_visible()
    expect(footer.locator("button.mdc-button", has_text="Next")).to_be_visible()
    ok(6, "footer visibile con pulsanti Cancel, Save as draft e Next")

    expect(
        page.locator("span.pb-5.text-4xl.font-bold", has_text="Add basic Campaign information")
    ).to_be_visible()
    ok(7, "titolo 'Add basic Campaign information' visibile")

    # Il mat-error compare solo dopo che il campo e' stato toccato: click + Tab.
    campaign_input = page.locator("input[formcontrolname='campaignName']")
    expect(campaign_input).to_be_visible()
    campaign_input.click()
    campaign_input.press("Tab")
    expect(page.locator("mat-error", has_text="Campaign name is required")).to_be_visible()
    ok(8, "campo 'Campaign name' presente con messaggio di validazione")

    campaign_name = f"Test Dv - {int(time.time())}"
    campaign_input.fill(campaign_name)
    assert campaign_input.input_value() == campaign_name, "Il campo non contiene il testo atteso"
    ok(9, f"campo compilato con '{campaign_name}'")

    select_mat_option(page, "client", "L'Oreal")
    ok(10, "dropdown 'Client' trovato e opzione 'L'Oreal' selezionata")

    aside = page.locator("aside.campaign-aside")
    expect(aside).to_be_visible()
    ok(11, "pannello laterale 'campaign-aside' visibile")

    expect(aside.locator("h4", has_text=campaign_name)).to_be_visible()
    ok(12, f"pannello laterale contiene il nome campagna '{campaign_name}'")

    client_row = aside.locator("p", has_text="Client")
    expect(client_row).to_be_visible()
    expect(client_row.locator("span", has_text="L'Oreal")).to_be_visible()
    ok(13, "pannello laterale contiene 'Client' con valore 'L'Oreal'")

    grid = page.locator("div.border.border-slate-200.rounded-xl dx-data-grid")
    expect(grid).to_be_visible()
    expect(grid.locator("td[role='columnheader']", has_text="DSP")).to_be_visible()
    expect(grid.locator("td[role='columnheader']", has_text="Advertiser")).to_be_visible()
    rows = grid.locator("tr.dx-data-row")
    assert rows.count() > 0, "Nessuna riga trovata nella griglia advertiser"
    expect(grid.locator("div.dx-pager")).to_be_visible()
    ok(14, f"griglia advertiser visibile con {rows.count()} righe e paginatore")

    loreal_row = grid.locator("tr.dx-data-row").filter(
        has=page.locator("span", has_text="L'Oréal Paris_ES")
    )
    expect(loreal_row).to_be_visible()
    loreal_row.locator("div.dx-select-checkbox").click()
    expect(loreal_row).to_have_attribute("aria-selected", "true")
    ok(15, "advertiser 'L'Oréal Paris_ES' selezionato nella griglia")

    dsp_card = aside.locator("div.aside-card--dsp")
    expect(dsp_card).to_be_visible()
    expect(dsp_card.locator("span.dsp-name", has_text="Google DV360")).to_be_visible()
    brand_row = dsp_card.locator("p", has_text="Brand")
    expect(brand_row).to_be_visible()
    expect(brand_row.locator("span", has_text="L'Oréal Paris_ES")).to_be_visible()
    ok(16, "pannello laterale aggiornato con DSP 'Google DV360' e Brand 'L'Oréal Paris_ES'")

    return footer


def test_template_dialog(page: Page, footer):
    """TEST 17-19: click Next, dialog template, 'Continuar sin plantilla'."""
    footer.locator("button.mdc-button", has_text="Next").click()
    ok(17, "click su 'Next' eseguito")

    dialog = page.locator("app-template-selector-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2.mat-mdc-dialog-title", has_text="Selecciona una plantilla")).to_be_visible()
    expect(dialog.locator("h2 span", has_text="Google DV360")).to_be_visible()
    expect(dialog.locator("mat-list-option")).to_have_count(3)
    expect(dialog.locator("button", has_text="Cancelar")).to_be_visible()
    expect(dialog.locator("button", has_text="Usar plantilla")).to_be_visible()
    expect(dialog.locator("button", has_text="Continuar sin seleccionar plantilla")).to_be_visible()
    ok(18, "dialog 'Selecciona una plantilla' visibile con opzioni e pulsanti")

    dialog.locator("button", has_text="Continuar sin seleccionar plantilla").click()
    expect(dialog).not_to_be_visible()
    ok(19, "click su 'Continuar sin seleccionar plantilla', dialog chiuso")


def test_global_setup(page: Page):
    """TEST 20-26: form Global Setup DV360."""
    gs_form = page.locator("app-dv360-global-setup form")
    expect(gs_form).to_be_visible()

    gs_campaign_name = f"Test Campaign - {int(time.time())}"
    fill_and_verify(gs_form, "campaignName", gs_campaign_name)
    ok(20, f"Campaign Name compilato con '{gs_campaign_name}'")

    today = datetime.date.today()
    date_from = today + datetime.timedelta(days=1)
    date_to = today + datetime.timedelta(days=2)
    for control, value in (("dateFrom", date_from), ("dateTo", date_to)):
        field = gs_form.locator(f"input[formcontrolname='{control}']")
        field.fill(value.strftime(DATE_FMT))
        field.press("Escape")  # chiude eventuale calendario aperto
    ok(21, f"Date From={date_from} Date To={date_to}")

    fill_and_verify(gs_form, "impressionsPerUser", "1")
    fill_and_verify(gs_form, "perEvery", "1")
    select_mat_option(page, "perUnit", "Week")
    ok(22, "Frequency Cap=1, per every=1, Unit=Week impostati e verificati")

    select_mat_option(page, "targetObjectiveType", "Brand awareness")
    # Il cambio di "Campaign Goal Type" ricarica (in modo DEBOUNCED, lato client)
    # le opzioni di "Target's Objective Type" e ne azzera il valore. Aspettiamo
    # che questo reset tardivo si concluda PRIMA di selezionare CPM, altrimenti
    # la nostra scelta verrebbe sovrascritta dal reload.
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(3000)
    ok(23, "Campaign Goal Type = 'Brand awareness' selezionato e verificato")

    select_all_multi(page, "creativeTypes", "Display")
    ok(24, "Creative Types: 'Select all' selezionato e verificato")

    # TEST 25: 'performanceGoalType' (mappato su 'campaignGoal' lato API) e' il
    # campo che il server segnalava come mancante. La classe 'mat-mdc-select-empty'
    # indica in modo autorevole se il control e' vuoto: ri-selezioniamo CPM finche'
    # il campo non resta stabilmente valorizzato (max 3 tentativi).
    perf_select = page.locator("mat-select[formcontrolname='performanceGoalType']")

    def _perf_empty():
        return "mat-mdc-select-empty" in (perf_select.get_attribute("class") or "")

    for _ in range(3):
        select_mat_option(page, "performanceGoalType", "CPM")
        page.wait_for_timeout(1500)  # lascia scattare un eventuale reset debounced
        if not _perf_empty():
            break
    assert not _perf_empty(), "performanceGoalType resta vuoto dopo i tentativi"
    ok(25, "Target's Objective Type = 'CPM' selezionato, valorizzato e stabile")

    fill_and_verify(gs_form, "performanceGoalAmountMicros", "1")
    ok(26, "Target's Objective Value = 1 inserito e verificato")


def test_insertion_orders(page: Page):
    """TEST 27-28: Step 3 Insertion Orders (Display Name, Insertion Order Type)."""
    # Dal Global Setup si passa allo step Insertion Orders col pulsante "Next"
    # del footer (l'URL non cambia, e' uno step Angular).
    # Il primo click puo' limitarsi a confermare/blur l'ultimo campo compilato
    # senza navigare: riclicchiamo "Next" finche' non compare il form IO.
    footer = page.locator("div.step-footer")
    io_form = page.locator("app-dv360-insertion-orders form")
    for _ in range(3):
        footer.locator("button.mdc-button", has_text="Next").click()
        try:
            expect(io_form).to_be_visible(timeout=5000)
            break
        except AssertionError:
            page.wait_for_timeout(1000)
    expect(io_form).to_be_visible()
    expect(
        page.locator("span.pb-5.text-4xl.font-bold", has_text="create the Insertion Orders")
    ).to_be_visible()

    io_display_name = f"US 1 - LOREAL - Display Ads - {int(time.time())}"
    fill_and_verify(io_form, "displayName", io_display_name)
    ok(27, f"Display Name compilato con '{io_display_name}'")

    select_mat_option(page, "insertionOrderType", "Standard")
    ok(28, "Insertion Order Type = 'Standard' selezionato e verificato")

    # TEST 29: Date range (start = domani, end = dopodomani).
    # Nota: dateFrom/dateTo esistono anche nel Global Setup, quindi qui
    # restiamo dentro io_form per colpire la coppia giusta.
    today = datetime.date.today()
    io_date_from = today + datetime.timedelta(days=1)
    io_date_to = today + datetime.timedelta(days=2)
    df = io_form.locator("input[formcontrolname='dateFrom']")
    dt = io_form.locator("input[formcontrolname='dateTo']")
    df.fill(io_date_from.strftime(DATE_FMT))
    dt.fill(io_date_to.strftime(DATE_FMT))
    dt.press("Enter")
    ok(29, f"Date range From={io_date_from} To={io_date_to}")

    # TEST 30: Purchase Order = testo random alfanumerico, max 8 caratteri.
    purchase_order = "".join(random.choices(string.ascii_letters + string.digits, k=8))
    fill_and_verify(io_form, "purchaseOrder", purchase_order)
    ok(30, f"Purchase Order = '{purchase_order}'")

    # TEST 31: Budget = 1 (campo numerico con suffisso €; la direttiva
    # moneyinput puo' riformattare il valore, quindi verifichiamo che contenga "1").
    budget_field = io_form.locator("input[formcontrolname='budget']")
    expect(budget_field).to_be_visible()
    budget_field.fill("1")
    budget_field.press("Tab")
    budget_val = budget_field.input_value()
    assert "1" in budget_val, f"Budget atteso contenente '1', trovato '{budget_val}'"
    ok(31, f"Budget impostato a '{budget_val}'")

    # TEST 32: Optimization Objective = "Awareness"
    select_mat_option(page, "optimizationObjective", "Awareness")
    ok(32, "Optimization Objective = 'Awareness' selezionato e verificato")

    # TEST 33: Pacing Period = Flight
    select_mat_option(page, "pacingPeriod", "Flight")
    ok(33, "Pacing Period = 'Flight' selezionato e verificato")

    # TEST 34: Pacing Type = Ahead
    select_mat_option(page, "pacingType", "Ahead")
    ok(34, "Pacing Type = 'Ahead' selezionato e verificato")

    # TEST 35: KPI Type = CPM
    select_mat_option(page, "kpiType", "CPM")
    ok(35, "KPI Type = 'CPM' selezionato e verificato")

    # TEST 36: KPI Target = 1
    # Con KPI Type = CPM il campo "KPI Target" diventa numerico (€) con un
    # formcontrolname diverso da 'kpiString': lo individuiamo per etichetta
    # accessibile, cosi' il locator resta valido a prescindere dalla variante.
    kpi_target = io_form.get_by_role("spinbutton", name="KPI Target")
    expect(kpi_target).to_be_visible()
    kpi_target.fill("1")
    assert kpi_target.input_value() == "1", f"KPI Target atteso '1', trovato '{kpi_target.input_value()}'"
    ok(36, "KPI Target = 1 inserito e verificato")

    # TEST 37: checkbox "Unlimited up to the campaign's frequency cap" spuntato.
    # Lo spuntiamo solo se non lo e' gia', poi verifichiamo lo stato finale.
    unlimited_row = io_form.locator(
        "div.flex.items-center.gap-3",
        has_text="Unlimited up to the campaign's frequency cap",
    )
    unlimited_input = unlimited_row.locator("input[type='checkbox']")
    if not unlimited_input.is_checked():
        unlimited_row.locator("mat-checkbox").click()
    expect(unlimited_input).to_be_checked()
    ok(37, "checkbox 'Unlimited up to...' spuntato e verificato")


def test_sidebar_sync(page: Page):
    """
    TEST 38: la sidebar e' aggiornata e riporta gli stessi dati del form
    principale. I valori vengono letti dinamicamente dal form (non hardcoded)
    e confrontati con quanto mostrato nella aside.
    """
    io_form = page.locator("app-dv360-insertion-orders form")
    aside = page.locator("aside.campaign-aside")

    # Display Name del form == nome dell'Insertion Order mostrato nella sidebar
    display_name = io_form.locator("input[formcontrolname='displayName']").input_value().strip()
    assert display_name, "Display Name vuoto nel form principale"
    io_surface = aside.locator(".io-surface").filter(has_text=display_name)
    expect(io_surface).to_be_visible()

    # DSP e Brand (provenienti dallo step 1) presenti nella sidebar
    expect(aside.locator("span.dsp-name", has_text="Google DV360")).to_be_visible()
    brand_row = aside.locator("p", has_text="Brand")
    expect(brand_row.locator("span", has_text="L'Oréal Paris_ES")).to_be_visible()

    # Budget del form riflesso nel "period chip" della sidebar (importo + €)
    budget_val = io_form.locator("input[formcontrolname='budget']").input_value()
    m = re.match(r"\s*(\d+)", budget_val)
    budget_int = m.group(1) if m else budget_val
    period_chip = io_surface.locator(".period-chip")
    expect(period_chip).to_contain_text("€")
    expect(period_chip).to_contain_text(budget_int)

    # La data del budget (anno di domani) e' riportata nel period chip
    anno = str((datetime.date.today() + datetime.timedelta(days=1)).year)
    expect(period_chip).to_contain_text(anno)

    ok(38, f"sidebar sincronizzata col form (IO '{display_name}', budget '{budget_val}')")


def test_line_items(page: Page):
    """TEST 38-39: Step 4 Line Items (con conferma del dialog di riepilogo IO)."""
    # Dallo step Insertion Orders si clicca "Next": si apre il dialog di riepilogo.
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()

    # TEST 39: dialog "Review insertion orders" visibile, conferma con
    # "Confirm & continue" (nel DOM e' "Confirm & continue").
    dialog = page.locator("dv360-io-summary-dialog")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2", has_text="Review insertion orders")).to_be_visible()
    dialog.locator("button.mdc-button", has_text="Confirm & continue").click()
    expect(dialog).not_to_be_visible()
    ok(39, "dialog 'Review insertion orders' confermato con 'Confirm & continue'")

    # TEST 40: verifica che nello stepper il passo "Line Items" sia selezionato.
    line_items_step = page.locator("dx-stepper div.dx-step", has_text="Line Items")
    expect(line_items_step).to_have_attribute("aria-selected", "true")
    ok(40, "navigato allo step 'Line Items' (passo selezionato nello stepper)")


def test_line_items_form(page: Page):
    """TEST 41-58: compilazione del form Line Items (DV360)."""
    li_form = page.locator("app-dv360-line-items form")
    expect(li_form).to_be_visible()

    # TEST 41: Line Item name = "DISPLAY OPEN - " + unix timestamp
    li_name = f"DISPLAY OPEN - {int(time.time())}"
    fill_and_verify(li_form, "name", li_name)
    ok(41, f"Line Item name compilato con '{li_name}'")

    # TEST 42: Media Type / Line item type = Display
    select_mat_option(page, "lineItemType", "Display")
    ok(42, "Media Type / Line item type = 'Display' selezionato e verificato")

    # TEST 43: "Use same flight dates as Insertion Order" spuntato.
    flight_cb_root = li_form.locator("mat-checkbox[formcontrolname='useIoFlightDates']")
    flight_cb = flight_cb_root.locator("input[type='checkbox']")
    if not flight_cb.is_checked():
        flight_cb_root.click()
    expect(flight_cb).to_be_checked()
    ok(43, "checkbox 'Use same flight dates as Insertion Order' confermato spuntato")

    # TEST 44: Budget allocation = Unlimited
    select_mat_option(page, "budgetAllocationType", "Unlimited")
    ok(44, "Budget allocation = 'Unlimited' selezionato e verificato")

    # TEST 45: Pacing period = Flight
    select_mat_option(page, "pacingPeriod", "Flight")
    ok(45, "Pacing period = 'Flight' selezionato e verificato")

    # TEST 46: Pacing type = ASAP
    select_mat_option(page, "pacingType", "ASAP")
    ok(46, "Pacing type = 'ASAP' selezionato e verificato")

    # TEST 47: "Limit exposure frequency to" spuntato (abilita freqCount/Every/Unit).
    limit_row = li_form.locator("div.flex.items-start.gap-3", has_text="Limit exposure frequency to")
    limit_cb = limit_row.locator("input[type='checkbox']")
    if not limit_cb.is_checked():
        limit_row.locator("mat-checkbox").click()
    expect(limit_cb).to_be_checked()
    ok(47, "checkbox 'Limit exposure frequency to' confermato spuntato")

    # TEST 48-49: freqCount = 1, freqEvery = 1
    fill_and_verify(li_form, "freqCount", "1")
    ok(48, "freqCount = 1 inserito e verificato")
    fill_and_verify(li_form, "freqEvery", "1")
    ok(49, "freqEvery = 1 inserito e verificato")

    # TEST 50: freqUnit = Minute (dropdown)
    select_mat_option(page, "freqUnit", "Minute")
    ok(50, "freqUnit = 'Minute' selezionato e verificato")

    # TEST 51: EU Political Ads = "Does not contain EU political advertising"
    select_mat_option(page, "containsEuPoliticalAds", "Does not contain EU political advertising")
    ok(51, "EU Political Ads = 'Does not contain EU political advertising' selezionato")

    # TEST 52: Bid strategy = Fixed bid
    select_mat_option(page, "bidStrategyType", "Fixed bid")
    ok(52, "Bid strategy = 'Fixed bid' selezionato e verificato")

    # TEST 53: Bid amount (CPM) = 1
    fill_and_verify(li_form, "bidAmount", "1")
    ok(53, "Bid amount (CPM) = 1 inserito e verificato")

    # TEST 54: Partner revenue model = Total Media Cost
    select_mat_option(page, "partnerRevenueModelMarkupType", "Total Media Cost")
    ok(54, "Partner revenue model = 'Total Media Cost' selezionato e verificato")

    # TEST 55: Markup = 0
    fill_and_verify(li_form, "partnerRevenueModelMarkupValue", "0")
    ok(55, "Markup = 0 inserito e verificato")

    # TEST 56: click "Add fee" (mat-menu-trigger) e selezione voce "CPM fee".
    add_fee_btn = li_form.locator("button.mat-mdc-menu-trigger", has_text="Add fee")
    expect(add_fee_btn).to_be_visible()
    add_fee_btn.scroll_into_view_if_needed()

    # Apre il menu con retry: il click semplice a volte non apre il mat-menu,
    # quindi dal secondo tentativo usiamo la tastiera (focus + Enter).
    for tentativo in range(4):
        if tentativo == 0:
            add_fee_btn.click(force=True)
        else:
            add_fee_btn.focus()
            add_fee_btn.press("Enter")
        try:
            expect(add_fee_btn).to_have_attribute("aria-expanded", "true", timeout=2000)
            break
        except AssertionError:
            page.keyboard.press("Escape")
            continue
    else:
        raise AssertionError("Impossibile aprire il menu 'Add fee'")

    # Le voci del mat-menu sono renderizzate nel CDK overlay con role="menuitem".
    page.get_by_role("menuitem", name="CPM fee", exact=True).click()
    # Dopo la selezione il menu si chiude (trigger non piu' espanso).
    expect(add_fee_btn).to_have_attribute("aria-expanded", "false")
    ok(56, "click 'Add fee' e selezione voce 'CPM fee'")

    # TEST 57: click "Next" nel footer per procedere.
    footer = page.locator("div.step-footer")
    footer.locator("button.mdc-button", has_text="Next").click()
    ok(57, "click su 'Next' nel footer eseguito")

    # TEST 58: click "Start campaign".
    # ATTENZIONE: e' un'azione consequenziale (lancia DAVVERO la campagna) e
    # difficile da annullare. Per sicurezza richiediamo conferma esplicita da
    # terminale: il click avviene SOLO se l'utente digita 'si'.
    start_btn = page.locator("button.mdc-button", has_text="Start campaign")
    expect(start_btn).to_be_visible()
    risposta = input(
        "\n>>> 'Start campaign' LANCIA DAVVERO la campagna. "
        "Digita 'si' per confermare il click (qualsiasi altra cosa annulla): "
    ).strip().lower()
    if risposta == "si":
        start_btn.click()
        ok(58, "click su 'Start campaign' confermato ed eseguito")
    else:
        print("TEST 58 SALTATO -> click su 'Start campaign' annullato dall'utente")


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
def main():
    with sync_playwright() as p:

        if AUTH_FILE.exists():
            print(f"Sessione trovata in {AUTH_FILE.name}, la riutilizzo.")
        else:
            login_manuale(p)
        storage_state = str(AUTH_FILE)

        print("\nApro il browser con la sessione SSO...")
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()

        try:
            test_landing(page)
            footer = test_general_info(page)
            test_template_dialog(page, footer)
            test_global_setup(page)
            test_insertion_orders(page)
            test_sidebar_sync(page)
            test_line_items(page)
            test_line_items_form(page)

            print("\nTUTTI I TEST SONO PASSATI ✅")
            page.wait_for_timeout(3000)

        except AssertionError as errore:
            print(f"\nTEST FALLITO ❌ : {errore}")

        finally:
            print("\nTest terminati. Il browser resta aperto per l'ispezione.")
            input(">>> Premi INVIO per chiudere il browser... ")
            context.close()
            browser.close()


if __name__ == "__main__":
    main()

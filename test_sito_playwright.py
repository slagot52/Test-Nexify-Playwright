# -*- coding: utf-8 -*-
"""
LO STESSO ESEMPIO, MA CON PLAYWRIGHT
=====================================
Fa esattamente le stesse 4 verifiche della versione Selenium (test_sito.py),
cosi' puoi confrontare le due sintassi fianco a fianco.

Nota la differenza piu' importante: qui NON scriviamo nessuna attesa manuale.
Playwright aspetta da solo che gli elementi siano pronti. Per questo il codice
e' piu' corto e i test sono meno "fragili".

Installazione (vedi GUIDA.md):
    pip install playwright
    playwright install        <-- scarica i browser (una volta sola)

Per lanciarlo:  python test_sito_playwright.py
"""

# 'sync_playwright' = il modo "semplice" (sincrono) di usare Playwright.
# 'expect' = le verifiche intelligenti che aspettano da sole il risultato giusto.
from playwright.sync_api import sync_playwright, expect


def main():
    # 'with' apre Playwright e lo chiude da solo alla fine, senza bisogno di 'finally'
    with sync_playwright() as p:

        # Apriamo Chromium (il motore di Chrome).
        # headless=False = vedi la finestra. Mettendo True gira invisibile.
        print("Apro il browser...")
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()

        try:
            # --------------------------------------------------------------
            # TEST 1: la pagina di login si apre e ha il titolo giusto
            # --------------------------------------------------------------
            page.goto("https://www.saucedemo.com/")
            assert "Swag Labs" in page.title(), "Il titolo della pagina non e' quello atteso"
            print("TEST 1 OK  -> la pagina di login si e' aperta correttamente")

            # --------------------------------------------------------------
            # TEST 2: il login con utente valido funziona
            # --------------------------------------------------------------
            # "#user-name" significa 'l'elemento con id user-name' (sintassi CSS).
            # fill() svuota il campo e ci scrive dentro. Niente attese da gestire.
            page.fill("#user-name", "standard_user")
            page.fill("#password", "secret_sauce")
            page.click("#login-button")

            # expect(...).to_have_text(...) aspetta DA SOLO che compaia il testo giusto.
            # Niente WebDriverWait: e' il grande vantaggio rispetto a Selenium.
            expect(page.locator(".title")).to_have_text("Products")
            print("TEST 2 OK  -> login eseguito, siamo nella pagina dei prodotti")

            # --------------------------------------------------------------
            # TEST 3: nella pagina ci sono dei prodotti in vendita
            # --------------------------------------------------------------
            prodotti = page.locator(".inventory_item")
            assert prodotti.count() > 0, "Non ho trovato nessun prodotto nella lista"
            print(f"TEST 3 OK  -> trovati {prodotti.count()} prodotti nella pagina")

            # --------------------------------------------------------------
            # TEST 4: aggiungo un prodotto al carrello e il contatore diventa 1
            # --------------------------------------------------------------
            page.click("#add-to-cart-sauce-labs-backpack")
            expect(page.locator(".shopping_cart_badge")).to_have_text("1")
            print("TEST 4 OK  -> prodotto aggiunto, il carrello segna 1")

            print("\nTUTTI I TEST SONO PASSATI ✅")
            page.wait_for_timeout(3000)  # pausa di 3s per farti vedere il risultato

        except AssertionError as errore:
            print(f"\nTEST FALLITO ❌ : {errore}")

        finally:
            print("Chiudo il browser.")
            browser.close()


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""
ESEMPIO DI TEST AUTOMATICO CON SELENIUM
========================================
Questo script apre un browser, va su un sito di pratica (www.saucedemo.com),
fa il login e controlla che alcune cose funzionino come dovrebbero.

Il sito saucedemo.com esiste apposta per esercitarsi: puoi usarlo liberamente.

Per lanciarlo:  python test_sito.py
(Prima leggi la GUIDA.md per l'installazione.)
"""

# 1) Importiamo gli strumenti di Selenium che ci servono
from selenium import webdriver                       # il "telecomando" del browser
from selenium.webdriver.common.by import By          # per dire COME cercare un elemento (per id, nome, ecc.)
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time


def main():
    # 2) Apriamo il browser Chrome.
    #    Selenium scarica da solo il driver necessario (da Selenium 4.6 in poi),
    #    quindi non devi installare niente a mano: basta avere Chrome sul computer.
    print("Apro il browser...")
    driver = webdriver.Chrome()

    # 'wait' serve ad ASPETTARE che un elemento compaia prima di usarlo
    # (le pagine web non si caricano istantaneamente). Aspetta al massimo 10 secondi.
    wait = WebDriverWait(driver, 10)

    try:
        # ------------------------------------------------------------------
        # TEST 1: la pagina di login si apre e ha il titolo giusto
        # ------------------------------------------------------------------
        driver.get("https://www.saucedemo.com/")     # apre l'indirizzo
        driver.maximize_window()

        assert "Swag Labs" in driver.title, "Il titolo della pagina non e' quello atteso"
        print("TEST 1 OK  -> la pagina di login si e' aperta correttamente")

        # ------------------------------------------------------------------
        # TEST 2: il login con utente valido funziona
        # ------------------------------------------------------------------
        # Troviamo la casella username (ha attributo id="user-name") e scriviamo dentro
        driver.find_element(By.ID, "user-name").send_keys("standard_user")
        # Troviamo la casella password e scriviamo la password
        driver.find_element(By.ID, "password").send_keys("secret_sauce")
        # Clicchiamo sul pulsante di login (ha id="login-button")
        driver.find_element(By.ID, "login-button").click()

        # Aspettiamo che compaia il titolo "Products" della pagina successiva
        titolo = wait.until(
            EC.visibility_of_element_located((By.CLASS_NAME, "title"))
        )
        assert titolo.text == "Products", "Dopo il login non vedo la pagina Products"
        print("TEST 2 OK  -> login eseguito, siamo nella pagina dei prodotti")

        # ------------------------------------------------------------------
        # TEST 3: nella pagina ci sono dei prodotti in vendita
        # ------------------------------------------------------------------
        prodotti = driver.find_elements(By.CLASS_NAME, "inventory_item")
        assert len(prodotti) > 0, "Non ho trovato nessun prodotto nella lista"
        print(f"TEST 3 OK  -> trovati {len(prodotti)} prodotti nella pagina")

        # ------------------------------------------------------------------
        # TEST 4: aggiungo un prodotto al carrello e il contatore diventa 1
        # ------------------------------------------------------------------
        driver.find_element(By.ID, "add-to-cart-sauce-labs-backpack").click()
        contatore = wait.until(
            EC.visibility_of_element_located((By.CLASS_NAME, "shopping_cart_badge"))
        )
        assert contatore.text == "1", "Il carrello non segna 1 prodotto"
        print("TEST 4 OK  -> prodotto aggiunto, il carrello segna 1")

        print("\nTUTTI I TEST SONO PASSATI ✅")

        # Piccola pausa per farti vedere il risultato prima che il browser si chiuda
        time.sleep(3)

    except AssertionError as errore:
        # Se una verifica (assert) fallisce, finiamo qui: il test e' "rosso"
        print(f"\nTEST FALLITO ❌ : {errore}")

    finally:
        # 'finally' viene eseguito SEMPRE: chiudiamo il browser in ogni caso
        print("Chiudo il browser.")
        driver.quit()


if __name__ == "__main__":
    main()

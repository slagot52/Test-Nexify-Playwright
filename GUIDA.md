# Guida ai test automatici con Selenium (per chi parte da zero)

Selenium è uno strumento che **comanda un vero browser** (Chrome, Firefox…) al posto tuo: apre pagine, clicca pulsanti, scrive nei campi e poi **verifica** che il risultato sia quello giusto. È esattamente quello che fa una persona quando prova un sito a mano — ma in automatico e ripetibile.

In questa cartella trovi un esempio già pronto: `test_sito.py`, che testa il sito di pratica `www.saucedemo.com` (un sito creato apposta per esercitarsi).

---

## Cosa ti serve (una volta sola)

**1. Google Chrome** installato sul computer (probabilmente ce l'hai già).

**2. Python** (versione 3.9 o successiva).

- Verifica se c'è già: apri il Terminale e scrivi `python3 --version`.
- Se non c'è, scaricalo da https://www.python.org/downloads/ e installalo.

**3. La libreria Selenium.** Nel Terminale, dentro questa cartella, scrivi:

```
pip3 install -r requirements.txt
```

(oppure semplicemente `pip3 install selenium`)

> Nota: **non** devi scaricare nessun "driver" a mano. Da Selenium 4.6 in poi se ne occupa lui in automatico.

---

## Come lanciare il test

Apri il Terminale, spostati in questa cartella e scrivi:

```
python3 test_sito.py
```

Si aprirà una finestra di Chrome che da sola fa il login e le verifiche. Nel Terminale vedrai scorrere:

```
TEST 1 OK  -> la pagina di login si e' aperta correttamente
TEST 2 OK  -> login eseguito, siamo nella pagina dei prodotti
TEST 3 OK  -> trovati 6 prodotti nella pagina
TEST 4 OK  -> prodotto aggiunto, il carrello segna 1

TUTTI I TEST SONO PASSATI ✅
```

Se qualcosa non va, vedrai `TEST FALLITO ❌` con la spiegazione.

---

## Come è fatto il codice (i 3 concetti base)

Sono solo tre idee, e con queste fai il 90% dei test:

**1. Trovare un elemento nella pagina** → `driver.find_element(By.ID, "user-name")`
Ogni pulsante o casella ha un "indirizzo" (un `id`, un nome, una classe…). Lo cerchi così.

**2. Fare un'azione** → `.click()` per cliccare, `.send_keys("testo")` per scrivere.

**3. Verificare il risultato** → `assert ...`
`assert` significa "dài per certo che…". Se la cosa è vera il test prosegue; se è falsa, il test fallisce. È il cuore di ogni test: controlla che il sito si comporti come deve.

In più c'è l'**attesa** (`WebDriverWait`): le pagine non si caricano all'istante, quindi prima di toccare un elemento aspettiamo che compaia (fino a 10 secondi). Evita errori "a caso".

---

## Come adattarlo al TUO sito

1. Cambia l'indirizzo in `driver.get("https://...")` con il tuo.
2. Per scoprire l'"indirizzo" di un elemento: apri il sito in Chrome, **tasto destro → Ispeziona** sul pulsante/campo che ti interessa, e guarda se ha un `id`, un `name` o una `class`.
3. Usa quel valore in `find_element` e aggiungi i tuoi `assert`.

Modi più comuni per cercare:

- `By.ID, "valore"` → cerca per attributo `id` (il più affidabile)
- `By.NAME, "valore"` → cerca per attributo `name`
- `By.CLASS_NAME, "valore"` → cerca per classe CSS
- `By.CSS_SELECTOR, "..."` o `By.XPATH, "..."` → per casi più complessi

---

## Vuoi lanciarli senza vedere la finestra del browser? (modalità "headless")

Utile per farli girare velocemente o su un server. Sostituisci la riga
`driver = webdriver.Chrome()` con:

```python
from selenium.webdriver.chrome.options import Options
opzioni = Options()
opzioni.add_argument("--headless=new")
driver = webdriver.Chrome(options=opzioni)
```

---

## Un passo più avanti (quando te la senti)

- **pytest**: lo standard per organizzare tanti test e avere report ordinati (`pip3 install pytest`, poi metti i test in funzioni che iniziano con `test_`).
- **Playwright**: un'alternativa più moderna a Selenium, spesso più veloce e meno "fragile". Stesso concetto, attese automatiche integrate.

Ma per imparare, l'esempio qui sopra è più che sufficiente: modificalo, rompilo, rimettilo a posto. È il modo migliore per capirlo.

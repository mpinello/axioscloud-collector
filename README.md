# AxiosCloud Collector

**v0.2.0 — versione sperimentale.** Archivio personale del registro elettronico AxiosCloud Famiglie: comunicazioni e allegati, argomenti delle lezioni, compiti e verifiche dell'anno scolastico attivo. Esporta JSON e CSV per successive analisi; Google Drive è facoltativo.

Progetto indipendente e non affiliato ad Axios o Google. Usa le richieste HTTP del portale famiglie, senza automazione del browser per la raccolta. **Non esiste qui una promessa di compatibilità con tutte le scuole:** il flusso originario e la raccolta didattica locale della versione configurabile sono stati provati su un account famiglia; altri alunni/anni e casi limite sono verificati con test sintetici. Le API del portale non sono un contratto pubblico e possono cambiare.

## Cosa raccoglie

- Comunicazioni attive e storiche disponibili nell'ambiente/anno corrente, testi e allegati scaricabili; file già integri non vengono riscaricati.
- Tutte le pagine delle liste annuali di argomenti, compiti e verifiche, per tutte le materie.
- Verifiche native e un catalogo integrato con interrogazioni/prove esplicitamente citate negli argomenti o nei compiti; richiami a firme, preparazione e date relative restano separati.
- CSV separati e tabella unica, JSON con celle originali, riepiloghi per materia/mese, istantanee delle modifiche e database SQLite locale.
- Caricamento opzionale dei documenti e delle esportazioni su una cartella Google Drive dell'app, con controlli SHA-256/MD5 e aggiornamenti senza duplicati.

**Non raccoglie voti, assenze, note individuali, messaggi privati o dati di altri alunni.** Non include automaticamente anni scolastici precedenti e non invia notifiche ChatGPT. I contenuti del proprio account possono comunque contenere dati personali: l'archivio nasce privato; decidere esplicitamente cosa condividere.

L'apertura di comunicazioni e allegati **può registrarne la lettura su Axios**. È necessario abilitarla in configurazione; lo strumento non promette di mantenere lo stato “non letto”. Non invia risposte alle circolari, non giustifica assenze, non modifica compiti o valutazioni.

## Requisiti

- Linux o macOS, Python **3.11 o successivo**, account Axios Famiglie con username/password.
- Windows nativo non supportato in questa versione; usare eventualmente un ambiente Linux. Sono impiegati permessi Unix e `flock`.
- Per le sole raccolte locali basta la libreria standard Python. Per il consenso Google servono le dipendenze opzionali indicate più avanti.
- CAPTCHA, OTP, SSO e percorsi di login diversi non sono automatizzati. In caso di richiesta inattesa il programma si ferma; nessun aggiramento o ritentativo automatico delle credenziali.

## Installazione e primo avvio

```sh
git clone https://github.com/mpinello/axioscloud-collector.git
cd axioscloud-collector
python3 -m venv .venv
cp .env.example .env
chmod 600 .env
```

Modificare `.env` con un editor sul proprio computer/server. Non incollare password o token in issue, chat o comandi condivisi.

Compilare almeno:

| Campo | Significato |
|---|---|
| `AXIOS_CUSTOMER_ID` | Codice fiscale della scuola, 11 cifre, come nella schermata di login |
| `AXIOS_USERNAME`, `AXIOS_PASSWORD` | Le proprie credenziali dell'account famiglia |
| `AXIOS_STUDENT_NAME` | Nome mostrato dal selettore alunni; deve identificare un solo alunno |
| `AXIOS_SCHOOL_YEAR` | Anno attivo nel portale, nel formato `AAAA/AAAA` |
| `AXIOS_CLASS_LABEL` | Etichetta locale libera, per esempio `Classe` |

I valori sono letterali: niente `export`, interpolazione o esecuzione della shell. Per spazi iniziali/finali usare virgolette corrispondenti. Il file deve appartenere all'utente che esegue il programma e avere permessi `600`.

Per scaricare anche comunicazioni/allegati, impostare consapevolmente:

```dotenv
COLLECT_COMMUNICATIONS=true
ALLOW_MARK_READ=true
```

Per iniziare con soli argomenti, compiti e verifiche:

```dotenv
COLLECT_COMMUNICATIONS=false
COLLECT_ACADEMIC=true
```

Controlli e raccolta:

```sh
.venv/bin/python collector.py doctor
.venv/bin/python collector.py check
.venv/bin/python collector.py run
```

- `doctor`: verifica struttura e formato della configurazione, senza rete e senza stampare valori sensibili; non verifica la password.
- `check`: un solo tentativo di login, selezione univoca e controllo anno; non apre comunicazioni o allegati.
- `run`: effettua le raccolte abilitate. Il codice di uscita è `0` per successo, `1` per errore o raccolta degradata. Un secondo avvio durante una raccolta esce senza aprire una nuova sessione.

Se più alunni corrispondono al nome, il programma si ferma. Se Axios non permette di distinguerli tramite il nome visualizzato, questo caso richiede un adattamento: non viene selezionato arbitrariamente il primo.

## Dove sono i dati

`DATA_DIR=data` è relativo alla cartella del `.env`, non alla directory corrente del terminale.

```text
data/
  profile.json                     # protegge da mescolamenti di alunni/anni/account
  status.json                      # esito dell'ultima raccolta conclusa
  communications/
    raccolta-download-student.json # testi, dettagli e stato allegati
    allegati/
    dettagli/
  risultati/didattica/AAAA-AAAA/
    argomenti.csv
    compiti.csv
    verifiche.csv                  # solo colonna nativa Axios
    verifiche-e-interrogazioni.csv # catalogo integrato con provenienza
    riferimenti-a-verifiche.csv
    eventi-didattici.csv
    registro-didattico.json
    riepilogo-statistico.json
    storico.sqlite3
    istantanee/
```

I file sono privati (`600`), le cartelle dati `700`. Fare backup di `DATA_DIR` e del `.env` in un luogo protetto. Per un altro alunno o anno usare un `.env` separato e un `DATA_DIR` diverso: non copiare il vecchio database nel nuovo profilo. Questo progetto non migra automaticamente l'installazione personale da cui è nata.

## Google Drive (opzionale)

Seguire [la configurazione Google](docs/google-drive.md). Ogni utilizzatore crea il proprio progetto/client OAuth: nessuna credenziale Google è inclusa nel repository.

La raccolta funziona anche con `DRIVE_UPLOAD=false`. Il consenso richiede soltanto `drive.file`, crea una cartella dell'app nel proprio Drive e non cambia condivisioni. Con questo ambito non basta indicare l'ID di una cartella arbitraria già esistente: l'app deve poterla usare.

## Aggiornamento ogni sei ore

Il progetto non installa cron e non modifica servizi automaticamente. Prima completare con successo almeno una raccolta manuale; poi installare sotto **lo stesso utente** un cron con percorsi assoluti:

```cron
15 */6 * * * /percorso/axioscloud-collector/.venv/bin/python /percorso/axioscloud-collector/collector.py --config /percorso/privato/.env run >>/percorso/privato/collector.log 2>&1
```

Il server deve essere acceso; il computer usato per installarlo può essere spento. Gli orari seguono il fuso del server. Preparare la cartella di log privata, ruotare i log e monitorare codice di uscita e `status.json`; il progetto non include un servizio di notifiche. Si può preferire un timer di sistema equivalente. Un lock impedisce sovrapposizioni. Gli errori di una raccolta non impediscono il tentativo delle altre, ma l'esito finale segnala il problema.

## Controllo del collector

A ogni `run` avviato, il programma aggiorna un file `stato-estrazione-axios.md` locale e, se Drive è abilitato, nella cartella dell'app. Il file contiene stato `running`, `success` o `failed`, orari UTC, ultimo successo e fase/codice sintetico di errore; non contiene credenziali, voti o testi scolastici. L'ID Drive resta stabile fra i tentativi ed è conservato in `health-drive.json` dentro `DATA_DIR`.

Il primo aggiornamento avviene **prima del login Axios**: una sessione rifiutata può quindi produrre un `failed` su Drive, se Google è raggiungibile. Se Drive, il server o la configurazione sono indisponibili, l'aggiornamento può mancare: serve un monitor esterno che avvisi oltre 24 ore senza un nuovo segnale. Un file fermo non dimostra da solo che il cron sia fermo.

Il progetto non crea automaticamente attività ChatGPT o notifiche: [regole e modello di monitor](docs/monitoring.md). Un controllo periodico avvisa al primo run utile, non nel momento esatto del guasto. Gli archivi didattici e gli allegati restano separati dal file di salute.

## Limiti dei conteggi

Una riga nella colonna Verifiche, una giornata con interrogazioni e un voto non sono la stessa cosa. Dettati, esercizi pratici o comprensioni possono essere valutati senza essere etichettati “verifica”. Le date dei compiti sono quelle previste nel registro; la data di assegnazione non è fornita da queste API. Una data passata non prova che l'alunno abbia sostenuto la prova.

Il catalogo usa regole testuali conservative, con possibili falsi positivi/negativi. Abbina evidenze con stessa materia e data quando c'è un solo candidato: questo non garantisce che ogni prova reale sia distinta correttamente. Le fonti originali sono sempre conservate; non usare i conteggi derivati come totale certificato. Tre voti di un'attività interdisciplinare non significherebbero automaticamente tre prove, ma **la raccolta dei voti non è implementata**.

La completezza dichiarata riguarda le liste accessibili all'account nell'anno attivo, non il registro interno dei docenti. Allegati cancellati, annullati, esterni o non più disponibili possono mancare; gli errori sono registrati. I file non PDF sono controllati per dimensione/contenuto inatteso, senza certificare ogni formato. Sono previsti limiti prudenziali di pagine, risposta e download; al loro raggiungimento la raccolta non viene dichiarata completa.

## Sviluppo e versionamento

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q *.py tests
```

La CI usa solo dati sintetici e non accede ad Axios o a Drive. Non configurare credenziali scolastiche nei workflow GitHub. Si parte da **0.1.0**: durante `0.x` possono cambiare schema e configurazione; consultare [CHANGELOG](CHANGELOG.md) prima di aggiornare.

Segnalazioni: indicare versione, piattaforma e messaggio sintetico, senza allegare `.env`, esportazioni, URL firmati, schermate con alunni o dati di login. Vedere [SECURITY](SECURITY.md) e [CONTRIBUTING](CONTRIBUTING.md). Licenza [MIT](LICENSE).

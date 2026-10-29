# Google Drive facoltativo

La raccolta locale non richiede Google. Per l'upload, ogni utilizzatore deve creare il proprio progetto e client OAuth: non usare credenziali di altre famiglie e non pubblicare quelle personali nel repository.

## Configurazione del progetto

1. Aprire [Google Cloud Console](https://console.cloud.google.com/) con il proprio account e creare/selezionare un progetto personale.
2. Abilitare **Google Drive API**.
3. Configurare **Google Auth Platform** (nome app, email di supporto, pubblico). Per un account personale il pubblico è normalmente Esterno.
4. Dichiarare soltanto l'ambito `https://www.googleapis.com/auth/drive.file`. È un ambito raccomandato per accesso ai file usati con l'app; non richiedere `drive` completo per questo progetto.
5. Creare un client OAuth di tipo **Desktop app**. Copiare client ID e client secret nei campi `GOOGLE_CLIENT_ID` e `GOOGLE_CLIENT_SECRET` del proprio `.env`, protetto `600`.
6. Se il progetto è in Test, aggiungere il proprio account agli utenti di test. Per un uso continuativo valutare il passaggio a In produzione: Google documenta una scadenza di sette giorni per i token di rinnovo emessi in Test con questi ambiti. Le richieste di branding/verifica dipendono dalla configurazione; usare informazioni e URL reali richiesti dalla console, senza inventare domini o informative. Dopo il passaggio in produzione rifare il consenso.

Consultare la documentazione ufficiale, che può cambiare:

- [OAuth per applicazioni desktop](https://developers.google.com/identity/protocols/oauth2/native-app)
- [Scelta degli ambiti Drive](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- [Scadenza dei token di rinnovo](https://developers.google.com/identity/protocols/oauth2#expiration)

Le password per app Google non sostituiscono OAuth per queste API.

## Consenso iniziale

Prima completare i campi del profilo Axios, incluso username, alunno e anno: questi identificano la cartella dati. Il consenso non esegue il login Axios e non scarica documenti scolastici.

```sh
.venv/bin/python -m pip install -r requirements-oauth.txt
.venv/bin/python google_authorize.py --config /percorso/privato/.env
```

Il browser usa un callback **solo su `127.0.0.1`**, per dieci minuti. La libreria ufficiale Google esegue lo scambio con PKCE. Il token di rinnovo è scritto nel `.env` privato; non viene stampato. Se `GOOGLE_DRIVE_FOLDER_ID` è vuoto, viene creata una cartella privata dell'app e il suo ID è scritto nella configurazione. Un nuovo consenso con gli stessi parametri ritrova la stessa cartella del profilo.

Il nome della cartella include nome alunno e anno; non condividere la cartella automaticamente. Il programma non cambia condivisioni, ownership o permessi.

Dopo il consenso:

```dotenv
DRIVE_UPLOAD=true
```

Poi eseguire `collector.py run` e controllare l'esito. Allegati delle comunicazioni e cartella didattica saranno nel contenitore dell'app. Le esportazioni didattiche mantengono gli stessi ID Drive quando aggiornate; le istantanee sono aggiunte per versione. Il database SQLite resta sul computer/server, mentre JSON/CSV e istantanee sono caricati.

## Installazione su un server senza browser

Opzione semplice: fare il consenso sul proprio computer con lo stesso profilo e poi trasferire **in modo cifrato** `.env` sul server, impostando proprietario e permessi corretti. Non trasferire un `DATA_DIR` appartenente a un altro profilo. Non inviare il token in chat o email.

In alternativa, se il server SSH permette port forwarding:

```sh
ssh -L 127.0.0.1:8765:127.0.0.1:8765 utente@server
```

Nel terminale remoto usare `google_authorize.py --no-browser --port 8765`, quindi aprire sul computer locale l'URL indicato. Il callback locale viene inoltrato al processo remoto; nessun listener pubblico. Se SSH vieta il forwarding, usare la prima opzione: non disabilitare protezioni del server per aggirarlo.

Con `drive.file` l'app non accede arbitrariamente a tutte le cartelle già presenti. Se occorre una diversa collocazione, spostare la cartella creata dall'app nell'interfaccia Drive, controllando gli eventuali permessi ereditati. Un ID non accessibile non viene risolto richiedendo ambiti più ampi. Se il token è revocato o scade, rifare il consenso; non sono garantite credenziali perpetue.

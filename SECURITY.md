# Sicurezza e riservatezza

Usare esclusivamente il proprio account e contenuti a cui si è autorizzati. Non usare il programma per aggirare CAPTCHA, OTP, SSO, controlli della scuola o limiti del servizio.

Non aprire issue pubbliche con credenziali, codici fiscali reali, nomi di minori, cookie, token, URL firmati, schermate, HTML grezzo del registro o esportazioni. Per segnalazioni funzionali bastano versione, piattaforma, messaggio sintetico e una riproduzione **sintetica**. Per vulnerabilità, preferire la segnalazione privata GitHub se disponibile sul repository; non pubblicare dettagli sfruttabili o segreti.

- `.env` e dati devono appartenere all'utente corrente, con permessi rispettivamente `600` e `700`; il programma rifiuta configurazioni accessibili ad altri utenti.
- Cookie Axios e token di sessione restano in memoria. Le credenziali Axios e il token Google di rinnovo restano invece nel `.env` locale: non sono cifrati dal programma. Proteggere computer, backup e account.
- HTTPS e domini di destinazione sono controllati; i cookie Axios non vengono inoltrati allo storage degli allegati. Redirect Google inattesi non sono seguiti.
- Il programma non cambia le condivisioni Drive. Un archivio creato in una cartella condivisa può ereditare accessi più ampi: controllare i permessi prima di spostarlo.
- Gli allegati sono contenuti esterni: la verifica di formato/integrità non è una scansione antivirus. Non aprire automaticamente file sconosciuti.
- La CI usa esclusivamente fixture sintetiche e runner GitHub ospitati; nessun accesso al registro o a una rete domestica.
- Le estensioni relative alle valutazioni personali non sono implementate e non devono essere aggiunte a cartelle condivise implicitamente.

Se un segreto è stato pubblicato, revocarlo presso il relativo servizio: cancellarlo dall'ultimo commit non è sufficiente. Riesaminare anche la cronologia e i file già condivisi.

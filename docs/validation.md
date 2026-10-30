# Stato della validazione — 0.1.0

- 18 test offline con dati esclusivamente sintetici: parsing, separazione compiti/verifiche, regole del catalogo, duplicati, snapshot, anno/schema inattesi, paginazione troncata, aggiornamenti Drive sullo stesso ID e integrità, configurazione/permessi, isolamento dei profili, consenso letture e selezione ambigua.
- Caso integrato sintetico con un nome alunno e anno differenti da quelli dell'installazione originaria.
- Raccolta didattica locale della nuova CLI eseguita con successo su Linux, contro un account reale, in una cartella di validazione isolata. Nessun dato scolastico o identificativo dell'account incluso qui.
- Flusso originario di comunicazioni/download/Drive verificato nell'installazione personale da cui deriva il codice. Le modifiche del profilo generalizzato per le comunicazioni e per Drive sono coperte da test offline, non da un nuovo upload reale della versione pubblicabile.
- Nessuna verifica su più istituti, SSO, OTP, CAPTCHA o Windows nativo. Non promettere compatibilità con queste varianti.
- CI definita per Python 3.11/3.13 su Linux e macOS, senza credenziali o collegamenti al registro. Consultare gli esiti effettivi della scheda Actions per ciascun commit.

## Estensione 0.2.0

23 test offline complessivi: aggiunti login fallito con Drive ancora disponibile, conservazione dello stato di guasto durante un nuovo tentativo, soglia strettamente oltre 24 ore, timestamp invalidi/futuri e riuso dell'ID Drive. Il controllo cloud resta una responsabilità del monitor configurato dall'utente; i test delle regole non dimostrano che una notifica push sia stata consegnata.

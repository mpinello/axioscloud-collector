# Changelog

## 0.2.0 — 2026-10-30

- File di controllo locale/Drive prima e dopo ogni tentativo, incluso login Axios fallito.
- Stati `running`/`success`/`failed`, orari UTC, ultimo successo e codice di fase senza dettagli sensibili.
- Aggiornamento sullo stesso ID Drive e verifica MD5/dimensione.
- Regole di riferimento per failed, assenza di segnale oltre 24 ore e timestamp invalidi; guida per un monitor cloud esterno.
- Cinque nuovi test sintetici su errori, soglia temporale, stato persistente e aggiornamento del file.

## 0.1.0 — 2026-10-29

Prima versione estratta da un'installazione personale e resa configurabile.

- Raccolta HTTP del portale AxiosCloud Famiglie, con un solo tentativo di login e selezione univoca dell'alunno.
- Comunicazioni correnti/storiche dell'anno attivo, dettagli e download allegati con verifica e deduplica.
- Liste annuali di argomenti, compiti e verifiche, paginazione verificata e doppia lettura prima di confermare lo storico.
- Catalogo di verifiche/interrogazioni e riferimenti testuali separati; fonti originali conservate, senza presunzione di svolgimento o completezza delle prove reali.
- CSV, JSON, riepiloghi e istantanee; SQLite locale.
- Google Drive opzionale, OAuth desktop con PKCE e solo `drive.file`.
- CLI `doctor`, `check`, `run`; profilo alunno/anno isolato, permessi privati e lock.
- Installazione Linux/macOS, esempio di cron ogni sei ore, documentazione dei limiti e test offline sintetici.

La versione generalizzata non è ancora collaudata con tutte le configurazioni scolastiche. Nessuna migrazione automatica dall'installazione originaria; nessun voto o dato reale incluso.

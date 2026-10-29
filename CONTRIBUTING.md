# Contribuire

Le segnalazioni di scuole/configurazioni diverse sono utili, ma devono contenere solo esempi sintetici e anonimizzati. Non servono credenziali per contribuire al codice.

1. Creare un branch da `main`.
2. Riprodurre il problema con una fixture sintetica e un test offline significativo.
3. Eseguire `python -m unittest discover -s tests -v`.
4. Aggiornare README e changelog per modifiche di comportamento o schema.
5. Aprire una pull request con comportamento precedente/successivo, validazione e limiti residui.

Non cambiare automaticamente permessi, letture, destinatari Drive o anni/alunni selezionati. Non aggiungere browser automation o richieste ripetute per aggirare un login inatteso. Una risposta incompleta non deve diventare un archivio dichiarato completo.

I conteggi delle prove devono preservare fonte e incertezza. Prepararsi a una prova, firmare un elaborato, sostenere una verifica e ricevere un voto sono eventi differenti. Conservare sempre il testo originale e impedire doppi conteggi da righe ripetute o viste diverse.

Le versioni iniziali seguono `0.MINOR.PATCH`: correzioni compatibili incrementano PATCH; nuove funzioni o cambiamenti di schema/configurazione incrementano MINOR. Prima di una release eseguire i test su Linux/macOS e verificare il contenuto Git, includendo la cronologia, per evitare la pubblicazione di dati privati.

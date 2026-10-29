#!/usr/bin/env python3
"""Run one configured pupil/year profile; local storage and optional Drive sync."""
import argparse
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import sys
from urllib.error import HTTPError
import axios_http
from axios_http import Stop,private_write
from axios_session import login_selected
from config import load_settings
from version import __version__

def error_label(exc):
    if isinstance(exc,Stop):return str(exc)
    if isinstance(exc,HTTPError):return 'Risposta HTTP '+str(exc.code)+' (URL e dettagli omessi).'
    return 'Operazione interrotta: '+type(exc).__name__

def prepare(settings):
    root=settings.data_dir;root.mkdir(parents=True,exist_ok=True,mode=0o700)
    if root.stat().st_uid!=os.getuid() or root.stat().st_mode & 0o077:raise Stop('DATA_DIR deve appartenere all utente corrente e avere permessi 700.')
    identity=root/'profile.json'
    if identity.exists():
        if json.loads(identity.read_text()).get('profile')!=settings.profile:raise Stop('DATA_DIR appartiene a un altro profilo: usare una cartella diversa per alunno/anno/account.')
    else:private_write(identity,{'profile':settings.profile,'version':__version__})
    return root

def main(argv=None):
    parser=argparse.ArgumentParser(description='Archivio personale AxiosCloud (account famiglia).')
    parser.add_argument('--version',action='version',version=__version__)
    parser.add_argument('--config',default=str(Path(__file__).with_name('.env')),help='File .env privato; i percorsi relativi partono dalla sua cartella.')
    parser.add_argument('command',choices=('doctor','check','run'))
    args=parser.parse_args(argv)
    os.umask(0o077)
    try:
        settings=load_settings(args.config).validate(run=args.command=='run')
        if args.command=='doctor':
            print('Configurazione strutturale valida. Nessuna rete, credenziale o contenuto mostrato.')
            print('Comunicazioni: '+str(settings.communications)+'; didattica: '+str(settings.academic)+'; Drive: '+str(settings.drive))
            return 0
        if args.command=='check':
            for key in ('AXIOS_USERNAME','AXIOS_PASSWORD'):
                if not settings.values.get(key):raise Stop('Configurazione mancante: '+key)
        root=prepare(settings)
        with (root/'run.lock').open('a') as lock:
            try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                print('Una raccolta è già in corso; nessuna seconda sessione avviata.');return 0
            axios_http.OUT=root/'communications';axios_http.STUDENT_LABEL=settings.values['AXIOS_STUDENT_NAME']
            client,dashboard=login_selected(settings.values)
            from academic_archive import school_year,collect
            year=school_year(dashboard)
            if year!=settings.values['AXIOS_SCHOOL_YEAR']:raise Stop('Anno attivo diverso da quello configurato: nessuna raccolta.')
            if args.command=='check':
                print('Accesso, selezione univoca e anno verificati. Nessuna comunicazione o allegato aperto.');return 0
            result={'version':__version__,'iniziato_utc':datetime.now(timezone.utc).isoformat(),'anno_scolastico':year,'operazioni':{},'errori':[]}
            if settings.communications:
                try:
                    listing=client.ajax('FAMILY_COMUNICAZIONI')
                    axios_http.harvest(client,listing,download=True)
                    state=json.loads((axios_http.OUT/'raccolta-download-student.json').read_text())
                    result['operazioni']['comunicazioni']={'numero':len(state['comunicazioni']),'stato':state['stato']}
                    if settings.drive:
                        from drive_upload import publish
                        result['operazioni']['drive_comunicazioni']=publish(axios_http.OUT,settings.values)
                    if state['stato']=='completata con errori download':result['errori'].append('Alcuni allegati non sono stati scaricati; consultare il riepilogo locale.')
                except Exception as exc:result['errori'].append('Comunicazioni: '+error_label(exc))
            if settings.academic:
                try:
                    academic=collect(client,dashboard,root,year,settings.values.get('AXIOS_CLASS_LABEL','Classe'))
                    result['operazioni']['didattica']={'conteggi':academic['conteggi'],'snapshot_sha256':academic['snapshot_sha256']}
                    if settings.drive:
                        from academic_drive import publish_academic
                        uploaded=publish_academic(root,settings.values,year,settings.profile)
                        result['operazioni']['drive_didattica']={'file_modificati':sum(f['esito']!='invariato' for f in uploaded['file']),'valutazioni_documentate':uploaded['valutazioni_documentate']}
                except Exception as exc:result['errori'].append('Didattica: '+error_label(exc))
            result['stato']='completato' if not result['errori'] else 'completato con errori'
            result['terminato_utc']=datetime.now(timezone.utc).isoformat()
            private_write(root/'status.json',result)
            print(json.dumps(result,ensure_ascii=False,indent=2))
            return 0 if not result['errori'] else 1
    except KeyboardInterrupt:
        print('Interrotto.');return 130
    except Exception as exc:
        print('STOP: '+error_label(exc));return 1

if __name__=='__main__':sys.exit(main())

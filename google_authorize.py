#!/usr/bin/env python3
"""Optional Google Desktop OAuth; only app-specific drive.file scope."""
import argparse
import fcntl
import logging
import os
from pathlib import Path
import sys
from config import load_settings,update_values
from collector import prepare,error_label
from axios_http import Stop

SCOPE='https://www.googleapis.com/auth/drive.file'

def main(argv=None):
    parser=argparse.ArgumentParser(description='Consenso Google Drive per il proprio profilo.')
    parser.add_argument('--config',default=str(Path(__file__).with_name('.env')))
    parser.add_argument('--no-browser',action='store_true',help='Mostra il link sul terminale; aprirlo sul computer che raggiunge il callback localhost.')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args(argv)
    os.umask(0o077);logging.disable(logging.CRITICAL)
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import AuthorizedSession
        settings=load_settings(args.config).validate(run=False)
        for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET'):
            if not settings.values.get(key):raise Stop('Client Google mancante: '+key)
        root=prepare(settings)
        with (root/'run.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            v=settings.values
            flow=InstalledAppFlow.from_client_config({'installed':{
                'client_id':v['GOOGLE_CLIENT_ID'],'client_secret':v['GOOGLE_CLIENT_SECRET'],
                'auth_uri':'https://accounts.google.com/o/oauth2/auth','token_uri':'https://oauth2.googleapis.com/token',
                'redirect_uris':['http://127.0.0.1/']}},scopes=[SCOPE],autogenerate_code_verifier=True)
            credentials=flow.run_local_server(host='127.0.0.1',bind_addr='127.0.0.1',port=args.port,
                open_browser=not args.no_browser,timeout_seconds=600,
                authorization_prompt_message='Apri sul browser: {url}',
                success_message='Consenso ricevuto. Puoi chiudere questa scheda.',
                access_type='offline',prompt='consent',include_granted_scopes='false')
            if not credentials.refresh_token:raise Stop('Token di rinnovo non ricevuto.')
            if set(credentials.granted_scopes or credentials.scopes or [])!={SCOPE}:raise Stop('Ambiti concessi diversi da drive.file: token non salvato.')
            # Persist the renewed token even if subsequent folder creation fails.
            update_values(settings.path,{'GOOGLE_REFRESH_TOKEN':credentials.refresh_token})
            with AuthorizedSession(credentials) as session:
                if v.get('GOOGLE_DRIVE_FOLDER_ID'):
                    folder_id=v['GOOGLE_DRIVE_FOLDER_ID']
                    import re
                    if not re.fullmatch(r'[A-Za-z0-9_-]+',folder_id):raise Stop('ID cartella Drive non valido.')
                    response=session.get('https://www.googleapis.com/drive/v3/files/'+folder_id,params={'fields':'id,mimeType,capabilities(canAddChildren)'},timeout=30)
                    response.raise_for_status();folder=response.json()
                    if folder.get('mimeType')!='application/vnd.google-apps.folder' or not folder.get('capabilities',{}).get('canAddChildren'):
                        raise Stop('Cartella Drive non accessibile all applicazione.')
                else:
                    q="trashed = false and mimeType = 'application/vnd.google-apps.folder' and appProperties has { key='collectorProfile' and value='"+settings.profile+"' }"
                    response=session.get('https://www.googleapis.com/drive/v3/files',params={'q':q,'fields':'files(id),nextPageToken'},timeout=30)
                    response.raise_for_status();result=response.json();folders=result.get('files',[])
                    if len(folders)>1 or result.get('nextPageToken'):raise Stop('Più cartelle profilo: selezionare manualmente quella corretta.')
                    if folders:folder_id=folders[0]['id']
                    else:
                        response=session.post('https://www.googleapis.com/drive/v3/files',params={'fields':'id'},json={
                            'name':'AxiosCloud - '+v['AXIOS_STUDENT_NAME']+' - '+v['AXIOS_SCHOOL_YEAR'],
                            'mimeType':'application/vnd.google-apps.folder','appProperties':{'collectorProfile':settings.profile}},timeout=30)
                        response.raise_for_status();folder_id=response.json()['id']
                    update_values(settings.path,{'GOOGLE_DRIVE_FOLDER_ID':folder_id})
            print('Autorizzazione salvata nel file privato. Nessun documento condiviso; DRIVE_UPLOAD resta configurato come prima.')
            return 0
    except ImportError:
        print('Installa le dipendenze opzionali: python -m pip install -r requirements-oauth.txt');return 1
    except Exception as exc:
        print('STOP: '+error_label(exc));return 1

if __name__=='__main__':sys.exit(main())

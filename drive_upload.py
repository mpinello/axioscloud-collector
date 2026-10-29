"""Upload append-only to one configured Drive folder, with remote deduplication."""
import hashlib
import json
import mimetypes
import re
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler
from axios_http import Stop, private_write

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        raise Stop('Redirect Google inatteso: autorizzazione non inoltrata.')

class Drive:
    def __init__(self, config):
        self.config=config
        self.opener=build_opener(NoRedirect())
        self.token=None
    def refresh(self):
        data=urlencode({'grant_type':'refresh_token','client_id':self.config['GOOGLE_CLIENT_ID'],
                        'client_secret':self.config['GOOGLE_CLIENT_SECRET'],
                        'refresh_token':self.config['GOOGLE_REFRESH_TOKEN']}).encode()
        with self.opener.open(Request('https://oauth2.googleapis.com/token',data=data,
                                     headers={'Content-Type':'application/x-www-form-urlencoded'}),timeout=30) as r:
            result=json.load(r)
        if not result.get('access_token'):
            raise Stop('Autorizzazione Google non riuscita.')
        self.token=result['access_token']
    def request(self,path,data=None,method=None,content_type=None):
        url='https://www.googleapis.com'+path if path.startswith('/') else path
        if urlsplit(url).scheme!='https' or urlsplit(url).hostname!='www.googleapis.com':
            raise Stop('Destinazione Google inattesa.')
        headers={'Authorization':'Bearer '+self.token}
        if content_type:headers['Content-Type']=content_type
        with self.opener.open(Request(url,data=data,headers=headers,method=method),timeout=90) as r:
            return json.load(r)
    def upload(self,path,name,folder,key,sha):
        query=f"'{folder}' in parents and trashed = false and appProperties has {{ key='axiosVersion' and value='{key}' }}"
        existing=self.request('/drive/v3/files?'+urlencode({'q':query,'fields':'files(id,name,size,md5Checksum),nextPageToken','pageSize':'100','supportsAllDrives':'true','includeItemsFromAllDrives':'true'}))
        if existing.get('nextPageToken') or len(existing.get('files',[]))>1:
            raise Stop('Duplicati remoti ambigui: upload fermato.')
        payload=path.read_bytes()
        md5=hashlib.md5(payload).hexdigest()
        if existing.get('files'):
            item=existing['files'][0]
            if item.get('md5Checksum')!=md5 or str(item.get('size'))!=str(len(payload)):
                raise Stop('File remoto con stesso identificativo ma contenuto diverso.')
            return item
        metadata={'name':name,'parents':[folder],
                  'appProperties':{'axiosVersion':key,'sha256':sha},
                  'description':'Archivio AxiosCloud Collector; versione identificata dal contenuto. Nessun dato di sessione.'}
        mime=mimetypes.guess_type(name)[0] or ('application/pdf' if b'%PDF-' in payload[:1024] else 'application/octet-stream')
        location_url='https://www.googleapis.com/upload/drive/v3/files?'+urlencode({'uploadType':'resumable','supportsAllDrives':'true','fields':'id,name,size,md5Checksum'})
        headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json; charset=UTF-8',
                 'X-Upload-Content-Type':mime,'X-Upload-Content-Length':str(len(payload))}
        with self.opener.open(Request(location_url,data=json.dumps(metadata).encode(),headers=headers),timeout=30) as r:
            location=r.headers.get('Location','')
        item=self.request(location,data=payload,method='PUT',content_type=mime)
        if item.get('md5Checksum')!=md5 or str(item.get('size'))!=str(len(payload)):
            raise Stop('Conferma integrità Google non riuscita; non confermo upload.')
        return item

def publish(root,config):
    folder=config['GOOGLE_DRIVE_FOLDER_ID']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',folder):raise Stop('ID cartella Drive non valido.')
    snapshot=json.loads((root/'raccolta-download-student.json').read_text())
    if not snapshot.get('stato','').startswith('completata'):
        raise Stop('Raccolta incompleta: pubblicazione rinviata.')
    manifest_path=root/'drive-pubblicati.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    drive=Drive(config);drive.refresh()
    metadata=drive.request('/drive/v3/files/'+folder+'?fields=id,mimeType,capabilities(canAddChildren)&supportsAllDrives=true')
    if metadata.get('mimeType')!='application/vnd.google-apps.folder' or not metadata.get('capabilities',{}).get('canAddChildren'):
        raise Stop('Cartella Google non accessibile in scrittura.')
    added=0
    missing=0
    for post in snapshot['comunicazioni']:
        if post.get('stato_pubblicazione')=='annullata' or re.search(r'\bANNULLATA\b',post['riepilogo'],re.I):continue
        for entry in post.get('download',[]):
            if not entry.get('scaricato'):
                missing+=1
                continue
            path=(root/entry['file_locale']).resolve()
            if not path.is_relative_to((root/'allegati').resolve()) or not path.is_file():raise Stop('Percorso allegato non valido.')
            sha=hashlib.sha256(path.read_bytes()).hexdigest()
            if sha!=entry['sha256']:raise Stop('Hash allegato locale cambiato.')
            key=hashlib.sha256((entry['id_allegato']+':'+sha).encode()).hexdigest()
            # Remote lookup also closes the crash-after-upload/before-manifest window.
            item=drive.upload(path,entry['nome'],folder,key,sha)
            old=manifest.get(key)
            manifest[key]={'id':item['id'],'nome':entry['nome'],'sha256':sha,'comunicazione':post['id']}
            private_write(manifest_path,manifest)
            if not old:added+=1
    return {'file_nuovi_sincronizzati':added,'totale_pubblicati':len(manifest),'allegati_correnti_mancanti':missing}

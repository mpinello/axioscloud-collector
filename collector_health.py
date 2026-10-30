"""Small non-sensitive extraction heartbeat, updated on every attempt."""
from datetime import datetime,timezone,timedelta
import hashlib
import json
from pathlib import Path
import re
import uuid
from urllib.parse import urlencode
from drive_upload import Drive,private_write

NAME='stato-estrazione-axios.md'

def utcnow():return datetime.now(timezone.utc).isoformat()

def begin(root,last_success=None):
    previous={}
    try:previous=json.loads((root/'health-state.json').read_text())
    except (OSError,ValueError):pass
    now=utcnow()
    return {'schema':1,'run_id':str(uuid.uuid4()),'status':'running','started_at_utc':now,
            'updated_at_utc':now,'finished_at_utc':None,'phase':'configuration','error_code':None,
            'last_success_at_utc':previous.get('last_success_at_utc') or last_success,
            'last_completed_status':previous.get('last_completed_status'),
            'last_completed_at_utc':previous.get('last_completed_at_utc')}

def finish(health,success,phase='complete',error_code=None):
    now=utcnow();health=dict(health)
    health.update(status='success' if success else 'failed',phase=phase,error_code=error_code,
                  finished_at_utc=now,updated_at_utc=now,
                  last_completed_status='success' if success else 'failed',last_completed_at_utc=now)
    if success:health['last_success_at_utc']=now
    return health

def markdown(health):
    return ('# Stato estrazione Axios\n\n'
            'File di controllo automatico. Non modificare manualmente gli orari.\n\n'
            'STATO_ULTIMO_RUN: '+health['status']+'\n\n'
            'AGGIORNATO_UTC: '+health['updated_at_utc']+'\n\n'
            '```json\n'+json.dumps(health,ensure_ascii=False,indent=2)+'\n```\n\n'
            'Regole: failed = estrazione/sincronizzazione non completata; running = tentativo avviato, non successo. '
            'Oltre 24 ore senza un aggiornamento valido: segnalare assenza del segnale '
            '(possibile problema cron, server o collegamento Drive; la causa non e determinata dal solo file).\n').encode()

def save_local(root,health):
    private_write(root/'health-state.json',health)
    data=markdown(health);local=root/NAME
    local.write_bytes(data);local.chmod(0o600)
    return data

def publish_health(root,config,health):
    data=save_local(root,health)
    folder=config['GOOGLE_DRIVE_FOLDER_ID']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',folder):raise ValueError('Invalid Drive folder ID')
    drive=Drive(config);drive.refresh()
    manifest=root/'health-drive.json'
    if manifest.exists():
        cached=json.loads(manifest.read_text())
        if cached.get('folder_id')!=folder:raise ValueError('Health destination changed')
        file_id=cached.get('file_id','')
        if not re.fullmatch(r'[A-Za-z0-9_-]+',file_id):raise ValueError('Invalid health file ID')
        existing=drive.request('/drive/v3/files/'+file_id+'?fields=id,mimeType,parents,trashed')
        if existing.get('trashed') or folder not in existing.get('parents',[]) or existing.get('mimeType')!='text/markdown':
            raise ValueError('Health file moved, removed or replaced')
    else:
        query="'"+folder+"' in parents and trashed = false and appProperties has { key='collectorHealth' and value='v1' }"
        response=drive.request('/drive/v3/files?'+urlencode({'q':query,'fields':'files(id,mimeType),nextPageToken','pageSize':'100'}))
        files=response.get('files',[])
        if len(files)>1 or response.get('nextPageToken'):raise ValueError('Ambiguous health files')
        if files:
            existing=files[0]
            if existing.get('mimeType')!='text/markdown':raise ValueError('Invalid health mime type')
            file_id=existing['id']
        else:
            metadata={'name':NAME,'mimeType':'text/markdown','parents':[folder],
                      'appProperties':{'collectorHealth':'v1'},'description':'Esito e orari del collector; nessun dato di accesso o contenuto scolastico.'}
            file_id=drive.request('/drive/v3/files?fields=id',json.dumps(metadata).encode(),'POST','application/json')['id']
        private_write(manifest,{'file_id':file_id,'folder_id':folder})
    item=drive.request('/upload/drive/v3/files/'+file_id+'?uploadType=media&fields=id,size,md5Checksum,modifiedTime',data,'PATCH','text/markdown; charset=UTF-8')
    if item.get('id')!=file_id or item.get('md5Checksum')!=hashlib.md5(data).hexdigest() or str(item.get('size'))!=str(len(data)):
        raise ValueError('Health upload integrity not confirmed')
    return {'file_id':file_id,'modified_time':item.get('modifiedTime'),'status':health['status']}

def warning_codes(health,now=None):
    """Reference rules for tests/docs; cloud task independently applies these to Drive."""
    now=now or datetime.now(timezone.utc)
    warnings=[]
    try:
        updated=datetime.fromisoformat(health['updated_at_utc'].replace('Z','+00:00'))
        if updated.tzinfo is None or updated>now+timedelta(minutes=5):raise ValueError('Invalid timestamp')
    except (KeyError,ValueError,TypeError):return ['invalid_health']
    if now-updated>timedelta(hours=24):warnings.append('stale_health')
    if health.get('status')=='failed' or (health.get('status')=='running' and health.get('last_completed_status')=='failed'):
        warnings.append('failed_extraction')
    if health.get('status') not in ('running','success','failed'):warnings.append('invalid_health')
    return warnings

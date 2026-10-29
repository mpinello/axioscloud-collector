"""Publish class-only academic exports, preserving stable Drive file IDs."""
import hashlib
import json
import mimetypes
from pathlib import Path
from urllib.parse import urlencode
from drive_upload import Drive
from axios_http import Stop,private_write

EXPORTS=('LEGGIMI.md','registro-didattico.json','eventi-didattici.csv','argomenti.csv','compiti.csv','verifiche.csv','riepilogo-statistico.json','verifiche-e-interrogazioni.csv','riferimenti-a-verifiche.csv')

def unique(drive,query):
    r=drive.request('/drive/v3/files?'+urlencode({'q':query+' and trashed = false','fields':'files(id,name,mimeType,parents,size,md5Checksum),nextPageToken','pageSize':'100'}))
    if r.get('nextPageToken') or len(r.get('files',[]))>1:raise Stop('Archivio didattico Drive ambiguo: nessuna scrittura.')
    return r.get('files',[])

def folder(drive,year,role,name,parent=None):
    q="mimeType = 'application/vnd.google-apps.folder' and appProperties has { key='academicArchive' and value='"+year+"' } and appProperties has { key='academicFolder' and value='"+role+"' }"
    if parent:q+=" and '"+parent+"' in parents"
    found=unique(drive,q)
    if found:return found[0]['id']
    data={'name':name,'mimeType':'application/vnd.google-apps.folder','appProperties':{'academicArchive':year,'academicFolder':role}}
    if parent:data['parents']=[parent]
    return drive.request('/drive/v3/files?fields=id',json.dumps(data).encode(),'POST','application/json')['id']

def current_file(drive,path,parent,year):
    role=path.name
    q="'"+parent+"' in parents and appProperties has { key='academicExport' and value='"+role+"' }"
    found=unique(drive,q);existing=found[0] if found else None
    if existing and existing.get('mimeType')=='application/vnd.google-apps.folder':raise Stop('Esportazione Drive inattesa.')
    data=path.read_bytes();md5=hashlib.md5(data).hexdigest();sha=hashlib.sha256(data).hexdigest()
    if existing and existing.get('md5Checksum')==md5 and str(existing.get('size'))==str(len(data)):
        return {'id':existing['id'],'nome':role,'esito':'invariato','sha256':sha}
    mime=mimetypes.guess_type(role)[0] or 'application/octet-stream'
    metadata={'name':role,'appProperties':{'academicExport':role,'academicArchive':year,'sha256':sha},'description':'Registro didattico: aggiornamento automatico.'}
    endpoint='/upload/drive/v3/files'
    if existing:endpoint+='/'+existing['id']
    else:metadata['parents']=[parent]
    headers={'Authorization':'Bearer '+drive.token,'Content-Type':'application/json; charset=UTF-8','X-Upload-Content-Type':mime,'X-Upload-Content-Length':str(len(data))}
    from urllib.request import Request
    url='https://www.googleapis.com'+endpoint+'?'+urlencode({'uploadType':'resumable','fields':'id,size,md5Checksum'})
    with drive.opener.open(Request(url,json.dumps(metadata).encode(),headers,method='PATCH' if existing else 'POST'),timeout=30) as response:
        location=response.headers.get('Location','')
    item=drive.request(location,data,'PUT',mime)
    if item.get('md5Checksum')!=md5 or str(item.get('size'))!=str(len(data)):raise Stop('Integrità esportazione didattica Drive non confermata.')
    if existing and item['id']!=existing['id']:raise Stop('Identificativo esportazione Drive cambiato.')
    return {'id':item['id'],'nome':role,'esito':'aggiornato' if existing else 'creato','sha256':sha}

def publish_academic(root,config,year,profile):
    directory=root/'risultati'/'didattica'/year.replace('/','-')
    status=json.loads((directory/'ultima-raccolta.json').read_text())
    if status.get('stato')!='completo':raise Stop('Archivio didattico incompleto: nessun upload.')
    drive=Drive(config);drive.refresh();key=profile+'-'+year.replace('/','-')
    manifest=directory/'drive-archivio.json'
    if manifest.exists():
        target=json.loads(manifest.read_text())['cartella_drive_id']
        import re
        if not re.fullmatch(r'[A-Za-z0-9_-]+',target):raise Stop('ID archivio didattico Drive non valido.')
        metadata=drive.request('/drive/v3/files/'+target+'?fields=id,mimeType,capabilities(canAddChildren)')
        if metadata.get('mimeType')!='application/vnd.google-apps.folder' or not metadata.get('capabilities',{}).get('canAddChildren'):
            raise Stop('Cartella didattica non accessibile: nessuna destinazione alternativa creata.')
    else:
        target=folder(drive,key,'root','Registro didattico - '+year,config['GOOGLE_DRIVE_FOLDER_ID'])
    archive=folder(drive,key,'snapshots','Istantanee',target)
    files=[current_file(drive,directory/name,target,key) for name in EXPORTS]
    # Also replay older local snapshots after a failed/offline transfer; content-addressed upload is idempotent.
    snapshots=0
    for snapshot in sorted((directory/'istantanee').glob('*.json')):
        sha=hashlib.sha256(snapshot.read_bytes()).hexdigest()
        identity=hashlib.sha256(('didattica:'+key+':'+snapshot.stem).encode()).hexdigest()
        drive.upload(snapshot,'registro-'+key+'-'+snapshot.stem[:16]+'.json',archive,identity,sha)
        snapshots+=1
    summary=json.loads((directory/'riepilogo-statistico.json').read_text())
    result={'anno_scolastico':year,'cartella_drive_id':target,'istantanee_drive_id':archive,'file':files,'istantanee':snapshots,'snapshot_sha256':status['snapshot_sha256'],'conteggi':status['conteggi'],'valutazioni_documentate':summary['valutazioni_documentate']}
    private_write(directory/'drive-archivio.json',result)
    return result

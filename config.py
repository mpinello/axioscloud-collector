"""Literal private configuration. Never source .env in a shell."""
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
from axios_http import Stop

KEYS={'AXIOS_CUSTOMER_ID','AXIOS_USERNAME','AXIOS_PASSWORD','AXIOS_STUDENT_NAME','AXIOS_SCHOOL_YEAR','AXIOS_CLASS_LABEL','DATA_DIR','COLLECT_COMMUNICATIONS','COLLECT_ACADEMIC','ALLOW_MARK_READ','DRIVE_UPLOAD','GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REFRESH_TOKEN','GOOGLE_DRIVE_FOLDER_ID'}

def load_values(path):
    path=Path(path)
    if path.is_symlink():raise Stop('Il file di configurazione non deve essere un collegamento simbolico.')
    st=path.stat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode & 0o077:
        raise Stop('La configurazione deve appartenere all utente corrente e avere permessi 600.')
    values={}
    for raw in path.read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith('#'):continue
        key,sep,value=line.partition('=')
        if not sep or key not in KEYS or key in values:raise Stop('Configurazione con chiave sconosciuta, duplicata o formato non valido.')
        value=value.strip()
        if value.startswith(('"',"'")):
            if len(value)<2 or value[-1]!=value[0]:raise Stop('Virgolette non chiuse nella configurazione.')
            value=value[1:-1]
        if '\x00' in value:raise Stop('Carattere non valido nella configurazione.')
        values[key]=value
    return values

def boolean(values,key,default=False):
    value=values.get(key,str(default)).lower()
    if value not in ('true','false'):raise Stop('Le opzioni booleane devono essere true o false: '+key)
    return value=='true'

@dataclass
class Settings:
    path:Path
    values:dict
    data_dir:Path
    profile:str
    communications:bool
    academic:bool
    drive:bool
    allow_mark_read:bool

    def validate(self,run=True):
        v=self.values
        for key in ('AXIOS_CUSTOMER_ID','AXIOS_STUDENT_NAME','AXIOS_SCHOOL_YEAR'):
            if not v.get(key):raise Stop('Configurazione mancante: '+key)
        if not re.fullmatch(r'\d{11}',v['AXIOS_CUSTOMER_ID']):raise Stop('Il codice fiscale scuola deve contenere 11 cifre.')
        if not re.fullmatch(r'20\d{2}/20\d{2}',v['AXIOS_SCHOOL_YEAR']) or int(v['AXIOS_SCHOOL_YEAR'][5:])!=int(v['AXIOS_SCHOOL_YEAR'][:4])+1:
            raise Stop('Anno scolastico non valido: usare AAAA/AAAA.')
        if run:
            for key in ('AXIOS_USERNAME','AXIOS_PASSWORD'):
                if not v.get(key):raise Stop('Configurazione mancante: '+key)
            if not (self.communications or self.academic):raise Stop('Nessuna raccolta abilitata.')
            if self.communications and not self.allow_mark_read:
                raise Stop('La raccolta comunicazioni può segnare letture: impostare ALLOW_MARK_READ=true oppure disabilitare COLLECT_COMMUNICATIONS.')
            if self.drive:
                for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','GOOGLE_REFRESH_TOKEN','GOOGLE_DRIVE_FOLDER_ID'):
                    if not v.get(key):raise Stop('Drive non configurato: '+key)
        return self

def load_settings(path):
    path=Path(path).absolute();values=load_values(path)
    directory=Path(values.get('DATA_DIR','data'))
    if not directory.is_absolute():directory=path.parent/directory
    directory=directory.resolve()
    if directory==path.parent or directory==Path(directory.anchor):raise Stop('DATA_DIR deve essere una cartella dedicata ai dati.')
    profile=hashlib.sha256('|'.join(values.get(k,'').strip().casefold() for k in ('AXIOS_CUSTOMER_ID','AXIOS_USERNAME','AXIOS_STUDENT_NAME','AXIOS_SCHOOL_YEAR')).encode()).hexdigest()
    return Settings(path,values,directory,profile,boolean(values,'COLLECT_COMMUNICATIONS',True),boolean(values,'COLLECT_ACADEMIC',True),boolean(values,'DRIVE_UPLOAD'),boolean(values,'ALLOW_MARK_READ'))

def update_values(path,updates):
    path=Path(path);load_values(path)
    if set(updates)-KEYS or any('\n' in v or '\r' in v for v in updates.values()):raise Stop('Aggiornamento configurazione non valido.')
    lines=path.read_text().splitlines();found=set()
    for i,line in enumerate(lines):
        key,sep,_=line.partition('=')
        if sep and key in updates:lines[i]=key+'='+updates[key];found.add(key)
    lines.extend(k+'='+v for k,v in updates.items() if k not in found)
    fd,name=tempfile.mkstemp(prefix='.env-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as stream:stream.write('\n'.join(lines)+'\n')
        os.chmod(name,0o600);os.replace(name,path)
    finally:Path(name).unlink(missing_ok=True)

"""Read-only yearly Axios classwork archive, with source-aware classification."""
import csv
from collections import Counter
from datetime import date,datetime,timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import time
from urllib.parse import urlencode,urlsplit
from axios_http import Page,Stop,private_write
from assessment_catalog import build_catalog,export_csv,CATALOG_FIELDS,REFERENCE_FIELDS

SCHEMA=2
SOURCE={'argomenti':'FAMILY_REGISTRO_CLASSE_ARGOMENTI','compiti':'FAMILY_REGISTRO_CLASSE_COMPITI'}
FIELDS={'argomenti':{'giorno','materia','testo','inserito'},'compiti':{'giorno','materia','testo','verifica','inserito'}}

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

class Cell(Page):
    def handle_starttag(self,tag,attrs):
        if tag in ('br','p','div','li'):self.visible.append('\n')
        super().handle_starttag(tag,attrs)
    def handle_endtag(self,tag):
        super().handle_endtag(tag)
        if tag in ('p','div','li'):self.visible.append('\n')

def plain(value):
    if not isinstance(value,str):raise Stop('Cella didattica con tipo inatteso.')
    p=Cell(value)
    return '\n'.join(' '.join(line.split()) for line in ''.join(p.visible).splitlines() if line.strip())

def safe_source(row,kind):
    if set(row)!=FIELDS[kind] or not all(isinstance(v,str) for v in row.values()):
        raise Stop('Schema didattico Axios cambiato: nessuna esportazione parziale.')
    # Preserve source cells, but reject executable or authenticated links rather than archiving secrets.
    for value in row.values():
        if re.search(r'<\s*(?:script|iframe|input|form)\b',value,re.I):raise Stop('Markup inatteso in un dato didattico.')
        for n in Page(value).nodes:
            link=n['attrs'].get('href','')
            if link and (urlsplit(link).scheme not in ('http','https','mailto') or 'axioscloud.it' in (urlsplit(link).hostname or '')):
                raise Stop('Collegamento didattico inatteso: non archivio riferimenti di sessione.')
    return dict(row)

def fetch_rows(client,kind,page_size=100):
    action=SOURCE[kind]
    page=Page(client.ajax(action))
    if not page.find(id='table-'+kind):raise Stop('Sezione didattica Axios non riconosciuta.')
    selector=page.find(id='fsMateria')
    if len(selector)!=1:raise Stop('Filtro materia non riconosciuto.')
    options=[n for n in page.nodes if n['tag']=='option' and n['parent'] is selector[0]]
    if not any(n['attrs'].get('value')=='' for n in options):raise Stop('Filtro tutte le materie assente.')
    collected=[];total=None;fingerprints=set();pages=0
    while total is None or len(collected)<total:
        payload={'draw':pages+1,'start':len(collected),'length':page_size,'search':{'value':'','regex':False},'order':[],'columns':{},'iMatId':''}
        text=client.request('/Pages/APP/APP_Ajax_Get.aspx?'+urlencode({'Action':action+'_LISTA'}),json.dumps(payload).encode(),'application/x-www-form-urlencoded; charset=UTF-8',True)
        try:r=json.loads(text)
        except ValueError:raise Stop('Elenco didattico non JSON: possibile sessione scaduta.') from None
        if not isinstance(r,dict) or not isinstance(r.get('data'),list):raise Stop('Elenco didattico inatteso.')
        if any(type(r.get(k)) is not int or r[k]<0 for k in ('recordsTotal','recordsFiltered','draw')):raise Stop('Conteggi didattici non validi.')
        if r['recordsTotal']!=r['recordsFiltered'] or r['draw']!=pages+1:raise Stop('Filtro o paginazione didattica inattesi.')
        if total is None:total=r['recordsTotal']
        if total!=r['recordsTotal']:raise Stop('Elenco cambiato durante la raccolta: riprovare al prossimo ciclo.')
        rows=r['data']
        if total>20000 or len(rows)>page_size or len(collected)+len(rows)>total:raise Stop('Limite o conteggi di paginazione non coerenti.')
        if len(collected)<total and not rows:raise Stop('Pagina didattica vuota prima del termine.')
        if rows:
            marker=digest(rows)
            if marker in fingerprints:raise Stop('Pagina didattica ripetuta: storico incompleto.')
            fingerprints.add(marker)
        collected.extend(safe_source(row,kind) for row in rows);pages+=1
        if pages>200:raise Stop('Troppe pagine didattiche.')
        if len(collected)<total:time.sleep(.25)
    return collected,{'azione':action+'_LISTA','righe_attese':total,'righe_ricevute':len(collected),'pagine':pages,'tutte_le_materie':True,'completo':True}

def school_year(dashboard):
    p=Page(dashboard)
    matches=set(re.findall(r'A\.S\.\s*(20\d{2})\s*/\s*(20\d{2})',' '.join(p.visible)))
    if len(matches)!=1:raise Stop('Anno scolastico non identificabile in modo univoco.')
    a,b=next(iter(matches))
    if int(b)!=int(a)+1:raise Stop('Anno scolastico non valido.')
    return a+'/'+b

def normalize(source,year):
    events=[];raw=[];seen=Counter();a,b=map(int,year.split('/'))
    for kind in ('argomenti','compiti'):
        for row in source[kind]:
            row=safe_source(row,kind)
            try:day=datetime.strptime(plain(row['giorno']),'%d/%m/%Y').date()
            except ValueError:raise Stop('Data didattica non riconosciuta.') from None
            if not date(a,9,1)<=day<=date(b,8,31):raise Stop('Voce fuori dall anno scolastico selezionato.')
            subject=plain(row['materia']);teacher=plain(row['inserito'])
            if not subject:raise Stop('Materia mancante.')
            row_hash=digest({'anno':year,'elenco':kind,'celle':row})
            seen[row_hash]+=1;source_id=row_hash+':'+str(seen[row_hash])
            raw.append({'id_riga_archivio':source_id,'elenco':kind,'celle_originali':row})
            columns=[('testo','argomento')] if kind=='argomenti' else [('testo','compito'),('verifica','verifica')]
            for field,category in columns:
                text=plain(row[field])
                if not text:continue
                event={'id':digest([source_id,field]),'id_riga_archivio':source_id,'anno_scolastico':year,
                       'data':day.isoformat(),'ruolo_data':'lezione' if kind=='argomenti' else 'data_prevista_nel_registro',
                       'materia':subject,'materia_normalizzata':subject.casefold(),'docente':teacher,
                       'tipo':category,'testo':text,'campo_fonte':field,
                       'classificazione':'colonna_nativa_axios','data_assegnazione':None,
                       'svolgimento_confermato':None}
                events.append(event)
    events.sort(key=lambda x:(x['data'],x['tipo'],x['materia_normalizzata'],x['id']))
    raw.sort(key=lambda x:x['id_riga_archivio'])
    return events,raw

def csv_bytes(events):
    fields=['id','anno_scolastico','data','ruolo_data','tipo','materia','materia_normalizzata','docente','testo','campo_fonte','classificazione','data_assegnazione','svolgimento_confermato','id_riga_archivio']
    s=io.StringIO(newline='');w=csv.DictWriter(s,fieldnames=fields);w.writeheader()
    for e in events:
        # Spreadsheet formulas must never execute when the CSV is opened.
        w.writerow({k:("'"+v if isinstance(v,str) and v.lstrip().startswith(('=','+','-','@')) else v) for k,v in e.items() if k in fields})
    return ('\ufeff'+s.getvalue()).encode('utf-8')

def write_bytes(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_suffix(path.suffix+'.tmp');temp.write_bytes(payload);temp.chmod(0o600);temp.replace(path)

def store(root,year,events,raw,coverage,class_label='Classe'):
    directory=root/'risultati'/'didattica'/year.replace('/','-')
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    now=datetime.now(timezone.utc).isoformat()
    catalog,references=build_catalog(events)
    dataset={'schema':SCHEMA,'anno_scolastico':year,'classe':class_label,'eventi':events,'righe_originali':raw,'copertura':coverage,
             'valutazioni_documentate':catalog,'riferimenti_a_valutazioni':references,
             'limiti':['La data dei compiti/verifiche è quella prevista nel registro, non la data di assegnazione, che Axios non fornisce.',
                       'Una verifica con data passata non prova che sia stata effettivamente sostenuta.',
                       'I conteggi misurano voci registrate e giorni, non ore di lezione o singoli esercizi.',
                       'Le voci native Verifiche non esauriscono le prove: il catalogo aggiunge interrogazioni/prove esplicite dagli argomenti, abbinando per materia e data senza duplicare una stessa occasione. I riferimenti indiretti restano separati e non confermano altre prove datate.',
                       'Axios non espone ID stabili delle righe: una modifica testuale appare come nuova versione contenutistica; le istantanee conservano il prima e dopo.',
                       'Nessuna raccolta di voti, assenze, note individuali o altri alunni.']}
    fingerprint=digest(dataset)
    connection=sqlite3.connect(directory/'storico.sqlite3')
    try:
        with connection:
            connection.executescript('CREATE TABLE IF NOT EXISTS snapshots (sha256 TEXT PRIMARY KEY, created_utc TEXT NOT NULL, json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS observations (checked_utc TEXT PRIMARY KEY, sha256 TEXT NOT NULL REFERENCES snapshots(sha256)); CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, data TEXT NOT NULL, tipo TEXT NOT NULL, materia TEXT NOT NULL, json TEXT NOT NULL); CREATE TABLE IF NOT EXISTS snapshot_events (sha256 TEXT NOT NULL, event_id TEXT NOT NULL, PRIMARY KEY(sha256,event_id));')
            connection.execute('INSERT OR IGNORE INTO snapshots VALUES(?,?,?)',(fingerprint,now,canonical(dataset)))
            connection.execute('INSERT INTO observations VALUES(?,?)',(now,fingerprint))
            for e in events:
                connection.execute('INSERT OR IGNORE INTO events VALUES(?,?,?,?,?)',(e['id'],e['data'],e['tipo'],e['materia_normalizzata'],canonical(e)))
                connection.execute('INSERT OR IGNORE INTO snapshot_events VALUES(?,?)',(fingerprint,e['id']))
    finally:connection.close()
    (directory/'storico.sqlite3').chmod(0o600)
    snapshot_dir=directory/'istantanee';snapshot_dir.mkdir(mode=0o700,exist_ok=True)
    snapshot=snapshot_dir/(fingerprint+'.json')
    if not snapshot.exists():private_write(snapshot,dataset)
    private_write(directory/'registro-didattico.json',dataset)
    for name,subset in [('eventi-didattici',events)]+[(plural,[e for e in events if e['tipo']==category]) for plural,category in [('argomenti','argomento'),('compiti','compito'),('verifiche','verifica')]]:
        write_bytes(directory/(name+'.csv'),csv_bytes(subset))
    write_bytes(directory/'verifiche-e-interrogazioni.csv',export_csv(catalog,CATALOG_FIELDS))
    write_bytes(directory/'riferimenti-a-verifiche.csv',export_csv(references,REFERENCE_FIELDS))
    by_subject=Counter((e['tipo'],e['materia_normalizzata']) for e in events)
    by_month=Counter((e['tipo'],e['data'][:7]) for e in events)
    summary={'anno_scolastico':year,'snapshot_sha256':fingerprint,'conteggi':dict(Counter(e['tipo'] for e in events)),
             'valutazioni_documentate':{'occasioni_con_data':len(catalog),'colonna_verifiche_axios':sum(v['categoria']=='verifica_colonna_axios' for v in catalog),
                                       'aggiuntive_da_argomenti_o_compiti':sum(v['categoria']!='verifica_colonna_axios' for v in catalog),
                                       'riferimenti_non_conteggiati':len(references),
                                       'per_materia':dict(sorted(Counter(v['materia_normalizzata'] for v in catalog).items())),
                                       'per_mese':dict(sorted(Counter(v['data'][:7] for v in catalog).items()))},
             'giorni_con_argomenti':len({e['data'] for e in events if e['tipo']=='argomento'}),
             'per_materia':[{'tipo':t,'materia':m,'voci':n} for (t,m),n in sorted(by_subject.items())],
             'per_mese':[{'tipo':t,'mese':m,'voci':n} for (t,m),n in sorted(by_month.items())],
             'date_min_max':{kind:{'min':min((e['data'] for e in events if e['tipo']==kind),default=None),'max':max((e['data'] for e in events if e['tipo']==kind),default=None)} for kind in ('argomento','compito','verifica')},
             'nota':'Statistiche su voci, non ore; date delle verifiche pianificate, senza conferma di svolgimento.'}
    private_write(directory/'riepilogo-statistico.json',summary)
    private_write(directory/'ultima-raccolta.json',{'recuperato_utc':now,'snapshot_sha256':fingerprint,'conteggi':summary['conteggi'],'copertura':coverage,'stato':'completo'})
    readme=f'''# Registro didattico {class_label} — {year}\n\nArchivio completo delle voci disponibili nelle liste annuali Axios, per tutte le materie.\n\n- argomenti.csv: argomenti delle lezioni, per data e materia.\n- compiti.csv: compiti nella colonna nativa Compiti.\n- verifiche.csv: voci nella colonna nativa Verifiche, comprese prove orali e attività valutate (conteggio della sola colonna Axios).\n- verifiche-e-interrogazioni.csv: catalogo completo delle occasioni documentate con data, integrando interrogazioni/prove esplicite negli argomenti e abbinando per materia/data le doppie evidenze.\n- riferimenti-a-verifiche.csv: richiami a firme, restituzioni e preparazione, conservati ma non conteggiati come nuove prove senza data certa.\n- eventi-didattici.csv: tabella unica delle tre categorie.\n- registro-didattico.json: dati normalizzati e celle originali Axios.\n- riepilogo-statistico.json: conteggi per materia e mese.\n- Istantanee: versioni complete conservate quando cambia il contenuto, per non perdere rettifiche e voci rimosse.\n\nI CSV sono UTF-8 con BOM e celle protette dalle formule. Le celle originali sono nel JSON.\n\nLa classificazione segue la colonna Axios, non parole chiave: firmare una verifica o prepararsi a una verifica resta un compito se inserito come compito. Se una riga contiene entrambi i campi, genera due eventi distinti. Eventuali errori di inserimento della scuola restano documentati nel testo originale.\n\n'''+ '\n\n'.join(dataset['limiti'])+'\n'
    write_bytes(directory/'LEGGIMI.md',readme.encode())
    return {'anno_scolastico':year,'snapshot_sha256':fingerprint,'conteggi':summary['conteggi'],'directory':str(directory),'copertura':coverage}

def collect(client,dashboard,root,expected_year,class_label='Classe'):
    year=school_year(dashboard);source={};coverage={}
    if year!=expected_year:raise Stop('Anno scolastico cambiato: aggiornare la configurazione della classe prima di raccogliere.')
    for kind in SOURCE:
        source[kind],coverage[kind]=fetch_rows(client,kind)
    # Verify the paged view still has the same total and leading page before committing a snapshot.
    for kind in SOURCE:
        confirm,check=fetch_rows(client,kind)
        if source[kind]!=confirm:raise Stop('Storico modificato durante la lettura: nessun archivio parziale pubblicato.')
    previous=root/'risultati'/'didattica'/year.replace('/','-')/'ultima-raccolta.json'
    if previous.exists():
        old=json.loads(previous.read_text())
        for kind in SOURCE:
            if old['copertura'][kind]['righe_ricevute'] and not source[kind]:
                raise Stop('Elenco didattico improvvisamente vuoto: conservo il precedente archivio completo.')
    events,raw=normalize(source,year)
    result=store(root,year,events,raw,coverage,class_label)
    print('Archivio didattico completo: '+canonical(result['conteggi']),flush=True)
    return result

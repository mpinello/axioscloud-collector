"""Evidence catalogue across native exams, daily topics and homework references."""
import csv
import io
import re
from datetime import date

MENTION=re.compile(r'\b(?:verific(?:a|he)|interrogazion[ei]|prov[ae]|test|valutazion[ei]|valutat[aei])\b',re.I)
RETROSPECTIVE=re.compile(r'\b(?:firm\w*|sigl\w*|vision\w*|correzion\w*|corregg\w*|restitu\w*)\b',re.I)
PREPARATION=re.compile(r'\b(?:in vista|prepar\w*|esercit\w*|ripass\w*\s+per|studiare\s+per)\b|\bper (?:la|le|una|un|l[’\'])\s*(?:verific|prov|interrog|test)',re.I)
RELATIVE=re.compile(r'\b(?:domani|dopodomani|prossim[oa])\b',re.I)
MONTHS=('gennaio','febbraio','marzo','aprile','maggio','giugno','luglio','agosto','settembre','ottobre','novembre','dicembre')

def explicit_dates(event):
    dates=set()
    pattern=r'\bverific(?:a|he)\s+(?:del|dei giorni)\s+(\d{1,2}(?:\s*(?:[-–,/]|e)\s*\d{1,2})*)\s+('+'|'.join(MONTHS)+r')\b'
    for match in re.finditer(pattern,event['testo'],re.I):
        month=MONTHS.index(match[2].lower())+1
        year=int(event['anno_scolastico'].split('/')[0 if month>=9 else 1])
        for day in re.findall(r'\d+',match[1]):
            try:dates.add(date(year,month,int(day)).isoformat())
            except ValueError:continue
    return sorted(dates)


def build_catalog(events):
    catalog=[];references=[]
    for e in events:
        if e['tipo']=='verifica':
            catalog.append({'id':e['id'],'anno_scolastico':e['anno_scolastico'],'data':e['data'],
                            'materia':e['materia'],'materia_normalizzata':e['materia_normalizzata'],
                            'categoria':'verifica_colonna_axios','testo':e['testo'],
                            'certezza_data':'data_prevista_axios','svolgimento_individuale_confermato':None,
                            'fonti_ids':[e['id']],'annotata_anche_negli_argomenti':False})
    for e in events:
        if e['tipo']=='verifica' or not MENTION.search(e['testo']):continue
        text=e['testo']
        ref_type=('riferimento_non_valutativo' if re.search(r'\bprova\s+a\b',text,re.I) else
                  'richiamo_prove_precedenti' if RETROSPECTIVE.search(text) else
                  'preparazione' if PREPARATION.search(text) else
                  'data_relativa_da_chiarire' if RELATIVE.search(text) else None)
        matching=[v for v in catalog if v['data']==e['data'] and v['materia_normalizzata']==e['materia_normalizzata']]
        if ref_type is None and len(matching)==1:
            matching[0]['fonti_ids'].append(e['id'])
            if e['tipo']=='argomento':matching[0]['annotata_anche_negli_argomenti']=True
            continue
        if ref_type is None and not matching:
            category=('interrogazione_annotata' if re.search(r'\binterrogazion[ei]\b',text,re.I) else 'prova_annotata_negli_argomenti' if e['tipo']=='argomento' else 'prova_annunciata_nei_compiti')
            catalog.append({'id':e['id'],'anno_scolastico':e['anno_scolastico'],'data':e['data'],
                            'materia':e['materia'],'materia_normalizzata':e['materia_normalizzata'],
                            'categoria':category,'testo':text,'certezza_data':'data_annotazione_giornaliera' if e['tipo']=='argomento' else 'data_prevista_axios',
                            'svolgimento_individuale_confermato':None,'fonti_ids':[e['id']],
                            'annotata_anche_negli_argomenti':e['tipo']=='argomento'})
            continue
        cited_dates=explicit_dates(e)
        references.append({'id_fonte':e['id'],'tipo_fonte':e['tipo'],'data_riferimento':e['data'],
                           'materia':e['materia'],'categoria':ref_type or 'piu_prove_nella_stessa_data_da_abbinare',
                           'testo':text,'data_prova':cited_dates[0] if len(cited_dates)==1 else None,
                           'date_prove_citate':cited_dates,
                           'nota':'Richiamo conservato, incluse eventuali date esplicite; non sommato automaticamente alle prove perché potrebbe sovrapporsi a quelle già catalogate.'})
    for item in catalog:item['fonti_ids'].sort()
    catalog.sort(key=lambda v:(v['data'],v['materia_normalizzata'],v['id']))
    references.sort(key=lambda v:(v['data_riferimento'],v['materia'],v['id_fonte']))
    return catalog,references


def export_csv(rows,fields):
    s=io.StringIO(newline='');writer=csv.DictWriter(s,fieldnames=fields);writer.writeheader()
    for row in rows:
        values={}
        for key in fields:
            value=row.get(key)
            if isinstance(value,list):value=';'.join(value)
            if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):value="'"+value
            values[key]=value
        writer.writerow(values)
    return ('\ufeff'+s.getvalue()).encode()

CATALOG_FIELDS=('id','anno_scolastico','data','materia','categoria','testo','certezza_data','annotata_anche_negli_argomenti','svolgimento_individuale_confermato','fonti_ids')
REFERENCE_FIELDS=('id_fonte','tipo_fonte','data_riferimento','materia','categoria','testo','data_prova','date_prove_citate','nota')

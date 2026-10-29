#!/usr/bin/env python3
"""Prova locale Axios: login HTTP e primo elenco, senza dipendenze esterne."""
import getpass
import base64
import hashlib
from datetime import datetime, timezone
import http.cookiejar
import json
import os
import re
from pathlib import Path
import sys
import time
from html.parser import HTMLParser
from urllib.parse import urlencode, urljoin, urlsplit, quote
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler
from urllib.error import HTTPError, URLError

BASE = 'https://registrofamiglie.axioscloud.it'
HOST = urlsplit(BASE).hostname
OUT = Path(__file__).resolve().parent / 'data' / 'communications'
STUDENT_LABEL = ''

class Stop(Exception):
    pass

class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.nodes = []
        self.stack = []
        self.visible = []
        self.feed(text)
    def handle_starttag(self, tag, attrs):
        node = {'tag': tag, 'attrs': dict(attrs), 'text': '', 'parent': self.stack[-1] if self.stack else None}
        self.nodes.append(node)
        if tag not in {'input','img','br','hr','meta','link','source','wbr','area','base','embed','param','track','col'}:
            self.stack.append(node)
    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1, -1, -1):
            if self.stack[i]['tag'] == tag:
                del self.stack[i:]
                break
    def handle_data(self, data):
        for node in self.stack:
            node['text'] += data
        if not any(n['tag'] in ('script','style') for n in self.stack):
            self.visible.append(data)
    def find(self, **attrs):
        return [n for n in self.nodes if all(n['attrs'].get(k) == v for k,v in attrs.items())]

class LocalRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def check_url(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.hostname != HOST or p.port not in (None,443) or p.username or p.password:
        raise Stop('Il servizio propone un dominio o protocollo diverso. Prova fermata senza seguirlo.')

class Client:
    def __init__(self):
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()), LocalRedirect())
        self.token = None
        self.referer = BASE + '/'
    def request(self, path, data=None, content_type=None, ajax=False):
        url = urljoin(BASE + '/', path)
        check_url(url)
        headers = {'User-Agent':'AxiosCloudCollector/0.1.0', 'Referer':self.referer}
        if content_type:
            headers['Content-Type'] = content_type
        if ajax:
            headers['X-Requested-With'] = 'XMLHttpRequest'
            if self.token:
                headers['RVT'] = self.token
        req = Request(url, data=data, headers=headers)
        with self.opener.open(req, timeout=25) as response:
            final_url = response.geturl()
            check_url(final_url)
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise Stop('Risposta inattesa troppo grande.')
            text = raw.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
        self.referer = final_url
        page = Page(text)
        tokens = page.find(id='_AXToken')
        if tokens:
            self.token = tokens[0]['attrs'].get('value')
        return text
    def ajax(self, action, payload=None):
        path = '/Pages/APP/APP_Ajax_Get.aspx?' + urlencode({'Action':action})
        data = None if payload is None else json.dumps(payload).encode()
        text = self.request(path, data, 'application/x-www-form-urlencoded; charset=UTF-8' if data else None, True)
        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            raise Stop('Risposta AJAX inattesa: possibile sessione scaduta o passaggio aggiuntivo di accesso.') from None
        if str(result.get('errorcode')) != '0' or not isinstance(result.get('html'), str):
            raise Stop('Axios non ha restituito il contenuto previsto. Nessuna risposta grezza salvata.')
        return result['html']

    def bootstrap(self, dashboard):
        """Replicate SD.init's header -> footer -> content GET sequence."""
        dashboard_url = self.referer
        initial = Page(dashboard)
        fragments = [dashboard]
        for region in ('page-header', 'page-footer', 'page-content'):
            nodes = [n for n in initial.nodes if region in n['attrs'].get('class','').split()
                     and n['attrs'].get('data-href') and n['attrs'].get('data-action')]
            if not nodes:
                continue
            if len(nodes) != 1:
                raise Stop('Inizializzazione dashboard ambigua: prova fermata.')
            attrs = nodes[0]['attrs']
            url = urljoin(dashboard_url, attrs['data-href'])
            check_url(url)
            if urlsplit(url).path not in ('/Pages/SD/SD_Ajax_Get.aspx',
                                         '/Pages/APP/APP_Ajax_Get.aspx',
                                         '/Pages/COMMON/COMMON_Ajax_Get.aspx'):
                raise Stop('Endpoint di inizializzazione diverso da quelli verificati.')
            if urlsplit(url).query or not re.fullmatch(r'[A-Za-z0-9_]+', attrs['data-action']):
                raise Stop('Parametri di inizializzazione diversi dal previsto.')
            print('Carico la sezione '+region+' della dashboard…', flush=True)
            self.referer = dashboard_url
            fragment = self.request(url+'?'+urlencode({'Action':attrs['data-action']}), ajax=True)
            fragments.append(fragment)
        self.referer = dashboard_url
        return '\n'.join(fragments)

def collect_list(html):
    page = Page(html)
    posts = []
    seen = set()
    for n in page.nodes:
        a = n['attrs']
        ident = a.get('id','')
        if re.fullmatch(r'post-item-[0-9]+',ident) and ident not in seen:
            seen.add(ident)
            posts.append({'id':ident.removeprefix('post-item-'), 'riepilogo':' '.join(n['text'].split())})
    return posts

def private_write(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        os.chmod(temporary, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    temporary.replace(path)

def safe_text(text):
    # Queries and fragments can contain signed URLs: never persist them.
    return re.sub(r'https?://[^\s<>"\']+', lambda m: m.group(0).split('?')[0].split('#')[0], text)

def diagnostic_message(value):
    # Only a short, redacted server explanation, never the returned URL or HTML.
    text = ' '.join(Page(str(value)).visible)
    text = re.sub(r'https?://[^\s<>"\']+', '[URL omesso]', text)
    text = re.sub(r'(?i)(token|cookie|password|authorization|signature|temp_url_sig)\s*[:=]\s*[^\s,;]+', r'\1=[omesso]', text)
    text = re.sub(r'\b[A-Za-z0-9_+/=%.-]{24,}\b', '[identificativo omesso]', text)
    text = re.sub(r'\b\d{8,}\b', '[numero omesso]', text)
    return ' '.join(text.split())[:400]

def collect_details(html, post_id):
    page = Page(html)
    if page.find(name='password') or not any('saveReaderByFileLinkPost' in n['attrs'].get('class','').split()
                                             or 'modal-body' in n['attrs'].get('class','').split()
                                             or 'btn-save-response' in n['attrs'].get('class','').split()
                                             for n in page.nodes):
        raise Stop('Dettaglio non riconosciuto; possibile sessione scaduta. Raccolta interrotta.')
    attachments = []
    seen = set()
    for node in page.nodes:
        a = node['attrs']
        if 'saveReaderByFileLinkPost' not in a.get('class','').split():
            continue
        if a.get('datadwl') != '1':
            attachments.append({'tipo':'collegamento esterno', 'nome':' '.join(node['text'].split()), 'scaricato':False})
            continue
        storage = a.get('data-filename') or a.get('data-storage-filename')
        if not storage or storage in seen:
            continue
        seen.add(storage)
        name = a.get('data-source-filename','')
        try:
            name = base64.b64decode(name,validate=True).decode('utf-8')
        except (ValueError, UnicodeError):
            name = ' '.join(node['text'].split()) or storage
        attachments.append({'tipo':'file','nome':safe_text(name),'riferimento_file':storage,
                            'cartella_remota':a.get('data-folder',''), 'tipo_file':a.get('data-filetype',''),
                            'scaricato':False})
    return {'id':post_id,'testo':safe_text(' '.join(' '.join(page.visible).split())),
            'allegati':attachments,'recuperato_utc':datetime.now(timezone.utc).isoformat()}

def detail_control(html, post_id):
    for n in Page(html).nodes:
        a = n['attrs']
        if a.get('data-action') == 'BACHECA_VISUALIZZA_CIRCOLARE' and a.get('data-post-id','').lstrip('0') == post_id.lstrip('0'):
            return a
    raise Stop('Controllo dettaglio mancante per una comunicazione. Raccolta interrotta.')

def check_file_url(url):
    p = urlsplit(url)
    host = p.hostname or ''
    if (p.scheme != 'https' or p.username or p.password or p.port not in (None,443)
            or not (host == HOST or host.endswith('.zadarazios.com'))):
        raise Stop('Destinazione download diversa dallo storage Axios verificato.')

class FileRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_file_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def receive_file(url, destination, name):
    """No authenticated opener, RVT, cookies or Referer are sent to storage."""
    check_file_url(url)
    # Browser navigation percent-encodes Unicode and spaces automatically;
    # urllib expects an ASCII URL. Preserve existing escapes and signature bytes.
    url = quote(url, safe=":/?#[]@!$&'()*+,;=%-._~")
    opener = build_opener(FileRedirect())
    temp = destination.with_suffix(destination.suffix+'.part')
    destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    start = time.monotonic()
    try:
        with opener.open(Request(url,headers={'User-Agent':'AxiosCloudCollector/0.1.0'}),timeout=30) as response:
            check_file_url(response.geturl())
            mime = response.headers.get_content_type()
            if mime in ('text/html','application/xhtml+xml','application/json','application/xml','text/xml'):
                raise Stop('Lo storage ha restituito una pagina o errore invece del documento.')
            head = response.read(4096)
            probe = head.lstrip().lower()
            if not head or probe.startswith((b'<!doctype html',b'<html',b'<?xml',b'{"error')):
                raise Stop('Il contenuto ricevuto non è un documento valido.')
            is_pdf = name.lower().endswith('.pdf')
            if is_pdf and b'%PDF-' not in head[:1024]:
                raise Stop('Il file atteso come PDF non ha una firma PDF valida.')
            with temp.open('wb') as stream:
                os.chmod(temp,0o600)
                block = head
                while block:
                    count += len(block)
                    if count > 100*1024*1024 or time.monotonic()-start > 120:
                        raise Stop('Download oltre il limite di 100 MB o 120 secondi.')
                    stream.write(block); digest.update(block)
                    block = response.read(65536)
            expected = response.headers.get('Content-Length')
            if expected and expected.isdigit() and int(expected) != count:
                raise Stop('Trasferimento incompleto: dimensione diversa da quella dichiarata.')
        temp.replace(destination)
        return {'byte':count,'sha256':digest.hexdigest(),'controllo':'firma PDF' if is_pdf else 'contenuto non vuoto, non HTML/JSON/XML'}
    finally:
        temp.unlink(missing_ok=True)

def download_attachments(client, html, post_id, manifest, cancelled=False):
    results = []
    seen = set()
    for n in Page(html).nodes:
        a = n['attrs']
        if 'saveReaderByFileLinkPost' not in a.get('class','').split() or a.get('datadwl')!='1':
            continue
        filename = a.get('data-filename')
        if not filename:
            raise Stop('Riferimento allegato assente: contratto cambiato.')
        identity = '|'.join([a.get('data-root',''),a.get('data-folder',''),filename,
                             a.get('data-fifileid',''),a.get('data-filetype','')])
        key = hashlib.sha256(identity.encode()).hexdigest()
        if key in seen:
            continue
        seen.add(key)
        try:
            name = base64.b64decode(a.get('data-source-filename',''),validate=True).decode('utf-8')
        except (ValueError,UnicodeError):
            name = n['text'].strip() or filename
        name = re.sub(r'[\x00-\x1f/\\:]', '_',name).strip(' .')[:160] or 'allegato'
        previous = manifest.get(key,{})
        if cancelled and previous.get('esito') == 'storico annullato - file non presente':
            results.append(previous)
            print('  Riferimento storico annullato: file non presente, già classificato.',flush=True)
            continue
        relative = 'allegati/'+key[:16]+'-'+name
        destination = OUT / relative
        if previous.get('scaricato') and previous.get('file_locale')==relative and destination.is_file():
            actual = hashlib.sha256(destination.read_bytes()).hexdigest()
            if actual == previous.get('sha256'):
                results.append(dict(previous, gia_presente=True))
                print('  Allegato già presente e verificato.',flush=True)
                continue
        result = {'id_allegato':key,'comunicazione':post_id,'nome':name,'scaricato':False}
        stage = 'metadati'
        try:
            if not all(a.get(x) for x in ('postid','data-root','data-folder','data-source-filename')):
                raise Stop('Metadati di download incompleti.')
            source = a['data-source-filename']
            try:
                base64.b64decode(source,validate=True)
            except (ValueError,UnicodeError):
                source = base64.b64encode(source.encode()).decode()
            payload = {'fiPostId':a['postid'],'root':a['data-root'],'folder':a['data-folder'],
                       'filename':filename,'SourceFileName':a['data-source-filename']}
            file_info = {'url':'../../Handlers/SD_UploadDownloadHandler.aspx','root':a['data-root'],
                         'folder':a['data-folder'],'filename':filename,'SourceFileName':source}
            for attr,field in [('data-fifileid','fiFileId'),('data-filetype','fileType')]:
                if attr in a:
                    payload[field]=a[attr]; file_info[field]=a[attr]
            time.sleep(1)
            stage = 'registrazione lettura'
            read_response = json.loads(client.request('/Pages/SD/SD_Ajax_Post.aspx?Action=SAVE_READER_POST',
                json.dumps(payload).encode(),'json',True))
            if str(read_response.get('errorcode'))!='0':
                raise Stop('Axios non ha confermato la preparazione della lettura allegato.')
            stage = 'preparazione URL'
            prepared = json.loads(client.request('/Pages/COMMON/COMMON_Ajax_Get.aspx?action=DOWNLOAD_PREPARE_URL',
                base64.b64encode(json.dumps(file_info).encode()),'application/x-www-form-urlencoded; charset=UTF-8',True))
            if str(prepared.get('errorcode'))!='0' or not isinstance(prepared.get('json'),str):
                code = str(prepared.get('errorcode','assente'))
                result['diagnostica'] = {
                    'codice_axios':code if re.fullmatch(r'-?\d{1,8}',code) else 'non numerico/assente',
                    'tipo_risultato':type(prepared.get('json')).__name__,
                    'messaggio_presente':bool(prepared.get('errormsg')),
                    'messaggio_ripulito':diagnostic_message(prepared.get('errormsg','')),
                    'segnale_file_non_trovato':any(x in str(prepared.get('errormsg','')).lower() for x in ('non trovato','not found','non esiste','non presente'))}
                raise Stop('Axios non ha restituito un URL di download valido. Diagnostica senza segreti salvata.')
            stage = 'trasferimento file'
            checks = receive_file(prepared['json'],destination,name)
            result.update(checks,scaricato=True,file_locale=relative)
            print(f"  Allegato scaricato e verificato ({checks['byte']} byte).",flush=True)
        except (Stop, HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            result['fase_errore'] = stage
            result['classe_errore'] = type(exc).__name__
            result['errore'] = str(exc) if isinstance(exc,Stop) else ('HTTP '+str(exc.code) if isinstance(exc,HTTPError) else 'Trasferimento o risposta non riusciti; nessun URL mostrato.')
            print('  Allegato non scaricato ('+stage+', '+type(exc).__name__+'): '+result['errore'],flush=True)
            if result.get('diagnostica'):
                print('  Diagnostica: '+json.dumps(result['diagnostica']),flush=True)
        manifest[key]=result
        if cancelled and not result['scaricato'] and result.get('diagnostica',{}).get('segnale_file_non_trovato'):
            result['esito']='storico annullato - file non presente'
        private_write(OUT/'download-student.json',manifest)
        results.append(result)
    return results

def harvest(client, first, download=False, retry_missing=False):
    """Bounded crawl, checkpointed after every page and detail; no file transfers."""
    state = {'stato':'in corso','alunno':STUDENT_LABEL,'ambito':'Tutte le comunicazioni restituite dal filtro tutte, nell ambiente e anno correnti',
             'iniziato_utc':datetime.now(timezone.utc).isoformat(),'pagine':0,'comunicazioni':[],
             'allegati_scaricati':0,'limiti':['Non include automaticamente altri anni scolastici']}
    if not download:
        state['limiti'].append('Nessun trasferimento allegati')
    target = OUT / ('riprova-mancanti-student.json' if retry_missing else ('raccolta-download-student.json' if download else 'raccolta-student.json'))
    manifest_path = OUT/'download-student.json'
    manifest = json.loads(manifest_path.read_text()) if download and manifest_path.exists() else {}
    failed_posts = {v.get('comunicazione') for v in manifest.values() if not v.get('scaricato') and v.get('esito') != 'storico annullato - file non presente'}
    if retry_missing and not failed_posts:
        print('Nessun allegato mancante nel riepilogo locale. Nessun dettaglio aperto.')
        return
    private_write(target,state)
    try:
        # Same filter request issued by the web UI when switching from active to all.
        text = client.request('/Pages/SD/SD_Ajax_Get.aspx?action=BACHECA_NEW',
                              json.dumps({'fbOnlyActive':'0','filter':'','fiTypeCom':'','fiSendBy':''}).encode(),
                              'application/x-www-form-urlencoded; charset=UTF-8', True)
        known = set()
        controls = {}
        next_number = 1
        while True:
            posts = collect_list(text)
            if Page(text).find(name='password') or (not posts and state['pagine']==0 and collect_list(first)):
                raise Stop('Il filtro tutte non ha restituito un elenco riconoscibile. Nessuna completezza dichiarata.')
            added = 0
            for post in posts:
                if post['id'] in known:
                    continue
                known.add(post['id']); added += 1
                controls[post['id']] = detail_control(text, post['id'])
                post['riepilogo'] = safe_text(post['riepilogo'])
                state['comunicazioni'].append(post)
            state['pagine'] += 1
            private_write(target,state)
            print(f"Pagina {state['pagine']}: {len(state['comunicazioni'])} comunicazioni raccolte.",flush=True)
            more = [n['attrs'] for n in Page(text).nodes if 'comunicazione-change-page' in n['attrs'].get('class','').split()]
            if not more:
                break
            if len(more)!=1 or not added or state['pagine']>=100 or len(known)>1000:
                raise Stop('Paginazione ripetuta, ambigua o limite prudenziale raggiunto. Raccolta parziale salvata.')
            attrs = more[0]
            if attrs.get('data-action') != 'BACHECA_CIRCOLARE':
                raise Stop('Azione di paginazione cambiata.')
            try:
                page_number = int(attrs['data-next-page'])
            except (ValueError,KeyError):
                raise Stop('Numero pagina non riconosciuto.') from None
            if page_number <= next_number:
                raise Stop('Paginazione non progressiva; raccolta parziale salvata.')
            next_number = page_number
            time.sleep(1)
            text = client.request('/Pages/SD/SD_Ajax_Get.aspx?'+urlencode({
                'Action':'BACHECA_CIRCOLARE','Others':f'1|{page_number}||||0|'}),ajax=True)
        if retry_missing:
            state['comunicazioni'] = [p for p in state['comunicazioni'] if p['id'] in failed_posts]
            state['ambito']='Solo comunicazioni con errori download registrati nel riepilogo locale'
            private_write(target,state)
        total = len(state['comunicazioni'])
        for index,post in enumerate(state['comunicazioni'],1):
            a = controls[post['id']]
            # Match JS's undefined comment id and empty class/bacheca defaults.
            context_nodes = Page(first).find(id='selezione-classe-materia') or Page(first).find(id='selezione-bacheca')
            context = context_nodes[0]['attrs'].get('value','') if context_nodes else ''
            others = '|'.join([a['data-post-id'],a.get('data-commento-id','undefined'),
                               base64.b64encode(context.encode()).decode(),a.get('data-classe','')])
            payload = {} if 'data-lett' not in a else {'lett':a['data-lett']}
            time.sleep(1)
            detail = client.request('/Pages/SD/SD_Ajax_Get.aspx?'+urlencode({
                'Action':'BACHECA_VISUALIZZA_CIRCOLARE','Others':others}),
                json.dumps(payload).encode(),'application/x-www-form-urlencoded; charset=UTF-8',True)
            post['dettaglio'] = collect_details(detail,post['id'])
            cancelled = bool(re.search(r'\bANNULLATA\b',post['riepilogo'],re.I))
            post['stato_pubblicazione'] = 'annullata' if cancelled else 'nessun annullamento rilevato'
            if download:
                post['download'] = download_attachments(client,detail,post['id'],manifest,cancelled=cancelled)
            private_write(OUT / 'dettagli' / (post['id']+'.json'),post)
            private_write(target,state)
            print(f'Dettaglio {index}/{total} salvato.',flush=True)
        downloads = [a for p in state['comunicazioni'] for a in p.get('download',[])]
        state['allegati_scaricati'] = sum(a['scaricato'] for a in downloads)
        historical = sum(a.get('esito') == 'storico annullato - file non presente' for a in downloads)
        failed = sum(not a['scaricato'] and a.get('esito') != 'storico annullato - file non presente' for a in downloads)
        state['riferimenti_storici_non_disponibili'] = historical
        state['stato']='completata enumerazione e dettagli' if not download else ('completata con errori download' if failed else 'completata raccolta e download')
        state['terminato_utc']=datetime.now(timezone.utc).isoformat()
        private_write(target,state)
        attachments = sum(len(p['dettaglio']['allegati']) for p in state['comunicazioni'])
        if download:
            print(f"ESITO: {total} comunicazioni, {state['allegati_scaricati']} file scaricati/verificati, {historical} riferimenti storici annullati non disponibili, {failed} errori download non risolti.")
        else:
            print(f'OK: {total} comunicazioni, {attachments} riferimenti ad allegati. PDF non trasferiti.')
        print(f'Raccolta locale: {target}')
    except BaseException:
        state['stato']='parziale - esecuzione interrotta'
        private_write(target,state)
        raise

def dashboard_redirect(html):
    """Recognize a literal browser redirect, never execute returned JavaScript."""
    page = Page(html)
    targets = []
    for node in page.nodes:
        if node['tag'] == 'script' and not node['attrs'].get('src'):
            script = node['text']
            patterns = [
                r'(?:window\.)?location(?:\.href)?\s*=\s*[\'"]([^\'"\r\n]+)[\'"]',
                r'(?:window\.)?location\.(?:replace|assign)\(\s*[\'"]([^\'"\r\n]+)[\'"]\s*\)',
            ]
            for pattern in patterns:
                targets.extend(re.findall(pattern, script))
        if node['tag'] == 'meta' and node['attrs'].get('http-equiv','').lower() == 'refresh':
            match = re.search(r'url\s*=\s*(.+)', node['attrs'].get('content',''), re.I)
            if match:
                targets.append(match.group(1).strip(' \"\''))
    valid = set()
    for target in targets:
        target = target.replace('\\/', '/')
        url = urljoin(BASE + '/Pages/SD/SD_Login.aspx', target)
        check_url(url)
        if urlsplit(url).path.lower() == '/pages/sd/sd_dashboard.aspx':
            valid.add(url)
    if len(valid) > 1:
        raise Stop('Più destinazioni dashboard: navigazione ambigua, prova fermata.')
    return next(iter(valid), None)

def save_diagnostic(html, client):
    """Persist only fixed labels and counts; never source HTML, URLs or messages."""
    page = Page(html)
    names = {n['attrs'].get('name','') for n in page.nodes if n['tag']=='input'}
    lowered = html.lower()
    diagnostic = {
        'versione_prova':3,
        'pagina_login':urlsplit(client.referer).path.lower().endswith('/sd_login.aspx'),
        'pagina_dashboard':urlsplit(client.referer).path.lower().endswith('/sd_dashboard.aspx'),
        'campi_login_presenti':all(x in names for x in ('customerid','username','password')),
        'link_alunni':sum('change-alunno' in n['attrs'].get('class','').split() for n in page.nodes),
        'numero_moduli':sum(n['tag']=='form' for n in page.nodes),
        'numero_script':sum(n['tag']=='script' for n in page.nodes),
        'segnale_captcha':'captcha' in lowered,
        'segnale_otp':'one-time-code' in lowered or 'autenticazione a due fattori' in lowered,
        'segnale_scelta_ambiente':'seleziona ambiente' in lowered or 'selezione ambiente' in lowered,
        'segnale_errore_credenziali':any(x in lowered for x in ('credenziali errate','password errata','utente non trovato','credenziali non valide')),
    }
    OUT.mkdir(mode=0o700, exist_ok=True)
    path = OUT / 'diagnostica.json'
    path.write_text(json.dumps(diagnostic,indent=2)+'\n')
    path.chmod(0o600)
    print('Diagnostica senza dati di accesso: '+json.dumps(diagnostic))

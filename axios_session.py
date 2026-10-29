"""Authenticated Axios session for the selected pupil, no persisted session data."""
import re
from urllib.parse import urljoin,urlsplit,urlencode
from axios_http import Client,Page,Stop,BASE,check_url,dashboard_redirect,save_diagnostic

def login_selected(config):
    client = Client()
    print('Verifico la pagina di accesso…', flush=True)
    login = client.request('/Pages/SD/SD_Login.aspx')
    page = Page(login)
    forms = [n for n in page.nodes if n['tag']=='form' and 'login-form' in n['attrs'].get('class','').split()]
    if len(forms) != 1:
        raise Stop('Modulo di accesso diverso dal previsto; nessuna credenziale inviata.')
    login_url = urljoin(BASE + '/Pages/SD/SD_Login.aspx', forms[0]['attrs'].get('action',''))
    check_url(login_url)
    if urlsplit(login_url).path != '/Pages/SD/SD_Login.aspx':
        raise Stop('Destinazione di accesso diversa dal previsto.')
    school = config.get('AXIOS_CUSTOMER_ID','').strip()
    username = config.get('AXIOS_USERNAME','').strip()
    password = config.get('AXIOS_PASSWORD','')
    if not username or not password or not school.isdigit() or len(school)!=11:
        raise Stop('Dati mancanti o codice scuola non valido.')
    fields = {'customerid':school,'username':username,'password':password}
    # Preserve only hidden form fields; never persist authentication material.
    form_page = Page(login[login.find('<form'):login.find('</form>')+7])
    for n in form_page.nodes:
        a = n['attrs']
        if n['tag']=='input' and a.get('type')=='hidden' and a.get('name'):
            fields.setdefault(a['name'],a.get('value',''))
    print('Eseguo un solo tentativo di accesso…', flush=True)
    dashboard = client.request(login_url, urlencode(fields).encode(), 'application/x-www-form-urlencoded')
    del password, fields
    # A normal browser follows inline redirects; urllib only follows HTTP redirects.
    destination = dashboard_redirect(dashboard)
    if destination:
        print('Axios ha restituito un rinvio alla dashboard; lo seguo…', flush=True)
        dashboard = client.request(destination)
    if urlsplit(client.referer).path.lower().endswith('/sd_dashboard.aspx'):
        dashboard = client.bootstrap(dashboard)
    students = [n for n in Page(dashboard).nodes if 'change-alunno' in n['attrs'].get('class','').split()]
    if not students:
        save_diagnostic(dashboard, client)
        raise Stop('Pagina successiva al login non riconosciuta. La diagnostica distingue i passaggi senza assumere che la password sia errata. Nessun ritentativo automatico.')
    wanted=set(re.findall(r'\w+',config['AXIOS_STUDENT_NAME'].casefold()))
    if not wanted:raise Stop('Nome alunno non valido.')
    candidates = [n for n in students if wanted <= set(re.findall(r'\w+',n['text'].casefold()))]
    if len(candidates)!=1:
        raise Stop('Impossibile identificare l alunno configurato in modo univoco; nessun alunno selezionato.')
    chosen = candidates[0]['attrs']
    action = chosen.get('data-action','')
    if not action or not chosen.get('data-others') or not action.startswith('FAMILY_'):
        raise Stop('Contratto di selezione alunno diverso dal previsto.')
    # Action is taken from the unique l alunno configurato link, never from an arbitrary page control.
    if 'CHANGE' not in action and 'ALUNNO' not in action:
        raise Stop('Azione di selezione alunno non riconosciuta.')
    print('Accesso riuscito. Seleziono l alunno configurato…', flush=True)
    client.ajax(action, {'alunnoId':chosen['data-others']})
    return client, dashboard

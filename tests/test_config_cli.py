import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit,parse_qs
from config import load_settings,load_values,update_values
from collector import main,prepare
from axios_http import Stop,check_url,check_file_url

class ConfigTest(unittest.TestCase):
    def write_config(self,root,extra=''):
        p=Path(root)/'.env'
        p.write_text('AXIOS_CUSTOMER_ID=00000000000\nAXIOS_USERNAME=synthetic-user\nAXIOS_PASSWORD=not-a-real-password\nAXIOS_STUDENT_NAME=Studente Demo\nAXIOS_SCHOOL_YEAR=2028/2029\nAXIOS_CLASS_LABEL=Sezione Demo\nCOLLECT_COMMUNICATIONS=false\n'+extra)
        p.chmod(0o600);return p
    def test_permissions_and_literal_password(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.write_config(root)
            p.write_text(p.read_text().replace('not-a-real-password',"'test $HOME # literal'"))
            self.assertEqual(load_values(p)['AXIOS_PASSWORD'],'test $HOME # literal')
            p.chmod(0o644)
            with self.assertRaises(Stop):load_values(p)
    def test_update_preserves_secret_and_permissions(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.write_config(root);update_values(p,{'GOOGLE_REFRESH_TOKEN':'synthetic-token'})
            self.assertEqual(load_values(p)['AXIOS_PASSWORD'],'not-a-real-password')
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
    def test_profile_isolation(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.write_config(root);prepare(load_settings(p))
            p.write_text(p.read_text().replace('Studente Demo','Altro Studente'))
            with self.assertRaises(Stop):prepare(load_settings(p))
    def test_mark_read_consent_precedes_network(self):
        with tempfile.TemporaryDirectory() as root:
            p=self.write_config(root);p.write_text(p.read_text().replace('COLLECT_COMMUNICATIONS=false','COLLECT_COMMUNICATIONS=true'))
            with patch('collector.login_selected') as login,contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--config',str(p),'run']),1)
                login.assert_not_called()
    def test_other_student_and_year_local_pipeline(self):
        class FakeClient:
            def ajax(self,action):
                kind='argomenti' if action.endswith('ARGOMENTI') else 'compiti'
                return '<select id="fsMateria"><option value=""></option></select><table id="table-'+kind+'"></table>'
            def request(self,path,body,*args):
                payload=json.loads(body)
                row={'giorno':'17/09/2028','materia':'Materia Demo','testo':'Attività sintetica','inserito':'Docente Demo'}
                if 'COMPITI_LISTA' in path:row['verifica']='Prova sintetica'
                return json.dumps({'draw':payload['draw'],'recordsTotal':1,'recordsFiltered':1,'data':[row]})
        with tempfile.TemporaryDirectory() as root:
            p=self.write_config(root)
            with patch('collector.login_selected',return_value=(FakeClient(),'A.S. 2028/2029')),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(['--config',str(p),'run']),0)
            dataset=json.loads((Path(root)/'data/risultati/didattica/2028-2029/registro-didattico.json').read_text())
            self.assertEqual(dataset['classe'],'Sezione Demo')
            self.assertEqual(len(dataset['eventi']),3)
            self.assertEqual((Path(root)/'data/status.json').stat().st_mode & 0o777,0o600)
    def test_host_boundaries(self):
        for url in ['http://registrofamiglie.axioscloud.it/','https://registrofamiglie.axioscloud.it.evil.invalid/','https://other.invalid/']:
            with self.assertRaises(Stop):check_url(url)
        with self.assertRaises(Stop):check_file_url('https://notzadarazios.com/document.pdf')

class SelectionTest(unittest.TestCase):
    def test_ambiguous_child_never_selected(self):
        from axios_session import login_selected
        class FakeClient:
            referer='https://registrofamiglie.axioscloud.it/'
            def request(self,path,*args):
                if not args:return '<form class="login-form" action="/Pages/SD/SD_Login.aspx"></form>'
                self.referer='https://registrofamiglie.axioscloud.it/Pages/SD/SD_Dashboard.aspx'
                return '<a class="change-alunno" data-action="FAMILY_CHANGE_ALUNNO" data-others="one">Demo Uno</a><a class="change-alunno" data-action="FAMILY_CHANGE_ALUNNO" data-others="two">Demo Due</a>'
            def bootstrap(self,d):return d
            def ajax(self,*a):raise AssertionError('Must not select an ambiguous pupil')
        with patch('axios_session.Client',FakeClient),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(Stop):login_selected({'AXIOS_CUSTOMER_ID':'00000000000','AXIOS_USERNAME':'synthetic','AXIOS_PASSWORD':'synthetic','AXIOS_STUDENT_NAME':'Demo'})


class CommunicationExportTest(unittest.TestCase):
    def test_generic_manifest_and_cancelled_item(self):
        from drive_upload import publish
        class FakeDrive:
            def __init__(self,c):pass
            def refresh(self):pass
            def request(self,*args):return {'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
            def upload(self,*args):return {'id':'synthetic-file'}
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'allegati').mkdir();(root/'allegati/demo.pdf').write_bytes(b'%PDF-1.4 synthetic')
            import hashlib
            sha=hashlib.sha256((root/'allegati/demo.pdf').read_bytes()).hexdigest()
            snapshot={'stato':'completata raccolta e download','comunicazioni':[{'id':'1','riepilogo':'Sintetico','download':[{'scaricato':True,'file_locale':'allegati/demo.pdf','sha256':sha,'id_allegato':'synthetic','nome':'demo.pdf'}]},{'id':'2','riepilogo':'ANNULLATA','download':[{'scaricato':False}]}]}
            (root/'raccolta-download-student.json').write_text(json.dumps(snapshot))
            with patch('drive_upload.Drive',FakeDrive):result=publish(root,{'GOOGLE_DRIVE_FOLDER_ID':'synthetic-folder'})
            self.assertEqual(result['totale_pubblicati'],1)
            self.assertEqual(result['allegati_correnti_mancanti'],0)

if __name__=='__main__':unittest.main()

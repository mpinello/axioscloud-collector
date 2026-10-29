import json
from pathlib import Path
import tempfile
import unittest
from academic_archive import normalize,plain,Stop,fetch_rows,store

class ArchiveTest(unittest.TestCase):
    def row(self,text='',exam=''):
        return {'giorno':'28/10/2026','materia':'Matematica','testo':text,'verifica':exam,'inserito':'Docente'}
    def test_native_columns_and_multiple_events(self):
        data={'argomenti':[],'compiti':[self.row('Firmare la verifica.'),self.row('Esercitarsi per la verifica.'),self.row('', 'Prova orale'),self.row('Studio pag. 1', 'Test scritto')]}
        events,raw=normalize(data,'2026/2027')
        self.assertEqual([e['tipo'] for e in events].count('compito'),3)
        self.assertEqual([e['tipo'] for e in events].count('verifica'),2)
        self.assertTrue(all(e['svolgimento_confermato'] is None for e in events))
        self.assertEqual(len(raw),4)
    def test_duplicate_entries_not_lost_and_identity_order_independent(self):
        row=self.row('Esercizio 1')
        events,_=normalize({'argomenti':[],'compiti':[row,row]},'2026/2027')
        self.assertEqual(len({e['id'] for e in events}),2)
    def test_foreign_year_and_private_schema_rejected(self):
        row=self.row('Leggere');row['giorno']='01/09/2025'
        with self.assertRaises(Stop):normalize({'argomenti':[],'compiti':[row]},'2026/2027')
        row=self.row();row['assenze']='test'
        with self.assertRaises(Stop):normalize({'argomenti':[],'compiti':[row]},'2026/2027')
    def test_entities_and_breaks(self):
        self.assertEqual(plain('Attivit&#224; &quot;A&quot;<br>Seconda riga'),'Attività "A"\nSeconda riga')
    def test_snapshots_preserve_correction_and_unchanged_dedup(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data={'argomenti':[],'compiti':[self.row('=1+1')]}
            events,raw=normalize(data,'2026/2027');a=store(root,'2026/2027',events,raw,{})
            b=store(root,'2026/2027',events,raw,{})
            self.assertEqual(a['snapshot_sha256'],b['snapshot_sha256'])
            data['compiti'][0]['testo']='Correzione'
            events,raw=normalize(data,'2026/2027');c=store(root,'2026/2027',events,raw,{})
            self.assertNotEqual(a['snapshot_sha256'],c['snapshot_sha256'])
            self.assertEqual(len(list((Path(c['directory'])/'istantanee').glob('*.json'))),2)
    def test_truncated_pagination_stops(self):
        class Client:
            def ajax(self,action):return '<select id="fsMateria"><option value=""></option></select><table id="table-compiti"></table>'
            def request(self,*args):return json.dumps({'draw':1,'recordsTotal':3,'recordsFiltered':3,'data':[]})
        with self.assertRaises(Stop):fetch_rows(Client(),'compiti')


class DriveUpdateTest(unittest.TestCase):
    def test_existing_export_keeps_id_on_correction(self):
        from academic_drive import current_file
        import hashlib
        class Response:
            headers={'Location':'https://www.googleapis.com/upload/session'}
            def __enter__(self):return self
            def __exit__(self,*args):pass
        class Opener:
            request=None
            def open(self,request,timeout):self.request=request;return Response()
        class FakeDrive:
            token='synthetic';opener=Opener()
            def request(self,path,data=None,method=None,content_type=None):
                if path.startswith('/drive/v3/files?'):return {'files':[{'id':'same-id','mimeType':'text/csv','md5Checksum':'different','size':'1'}]}
                self.uploaded=data
                return {'id':'same-id','size':str(len(data)),'md5Checksum':hashlib.md5(data).hexdigest()}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'compiti.csv';path.write_text('correzione')
            drive=FakeDrive();result=current_file(drive,path,'folder','2026-2027')
            self.assertEqual(result['id'],'same-id')
            self.assertEqual(result['esito'],'aggiornato')
            self.assertEqual(drive.opener.request.get_method(),'PATCH')
            self.assertNotIn('parents',json.loads(drive.opener.request.data))
    def test_matching_remote_checksum_causes_no_write(self):
        from academic_drive import current_file
        import hashlib
        class FakeDrive:
            def request(self,*args):
                return {'files':[{'id':'same-id','mimeType':'text/csv','md5Checksum':hashlib.md5(b'dati').hexdigest(),'size':'4'}]}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'compiti.csv';path.write_bytes(b'dati')
            self.assertEqual(current_file(FakeDrive(),path,'folder','2026-2027')['esito'],'invariato')



class AssessmentTest(unittest.TestCase):
    def test_daily_exam_deduplicates_but_oral_is_recovered(self):
        from assessment_catalog import build_catalog
        rows={'argomenti':[{'giorno':'28/10/2026','materia':'Matematica','testo':'Verifica di geometria','inserito':'Docente'}, {'giorno':'19/10/2026','materia':'Storia','testo':'Interrogazioni: lo scavo archeologico.','inserito':'Docente'}], 'compiti':[ArchiveTest().row('', 'Verifica geometria')]}
        events,_=normalize(rows,'2026/2027');catalog,refs=build_catalog(events)
        self.assertEqual(len(catalog),2)
        self.assertEqual(len(refs),0)
        native=next(v for v in catalog if v['categoria']=='verifica_colonna_axios')
        self.assertEqual(len(native['fonti_ids']),2)
    def test_signatures_and_preparation_are_not_new_exams(self):
        from assessment_catalog import build_catalog
        rows={'argomenti':[], 'compiti':[ArchiveTest().row('Firmare le verifiche del 21-22-23 ottobre.'),ArchiveTest().row('Esercitarsi con il gioco per la verifica.') ]}
        events,_=normalize(rows,'2026/2027');catalog,refs=build_catalog(events)
        self.assertEqual(catalog,[])
        self.assertEqual(len(refs),2)
        self.assertTrue(all(r['data_prova'] is None for r in refs))

if __name__=='__main__':unittest.main()

import json,hashlib,tempfile,unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from unittest.mock import patch
from collector_health import begin,finish,publish_health,warning_codes

class HealthTest(unittest.TestCase):
 def test_stale_threshold_and_recovery(self):
  now=datetime(2026,10,30,12,tzinfo=timezone.utc)
  health={'status':'success','updated_at_utc':(now-timedelta(hours=24)).isoformat()}
  self.assertEqual(warning_codes(health,now),[])
  health['updated_at_utc']=(now-timedelta(hours=24,seconds=1)).isoformat()
  self.assertEqual(warning_codes(health,now),['stale_health'])
  self.assertEqual(warning_codes({'status':'failed','updated_at_utc':now.isoformat()},now),['failed_extraction'])
  self.assertEqual(warning_codes({'status':'success','updated_at_utc':now.isoformat()},now),[])
 def test_failed_state_survives_new_start(self):
  with tempfile.TemporaryDirectory() as root:
   root=Path(root);prior=finish(begin(root),False,'axios','axios_failed')
   (root/'health-state.json').write_text(json.dumps(prior))
   current=begin(root)
   self.assertEqual(current['last_completed_status'],'failed')
   self.assertEqual(warning_codes(current),['failed_extraction'])
 def test_future_or_invalid_timestamp(self):
  self.assertEqual(warning_codes({'status':'success','updated_at_utc':'nonsense'}),['invalid_health'])
  health={'status':'success','updated_at_utc':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
  self.assertEqual(warning_codes(health),['invalid_health'])
 def test_same_drive_id_on_success_then_failure(self):
  class FakeDrive:
   def __init__(self,c):pass
   def refresh(self):pass
   def request(self,path,data=None,method=None,content_type=None):
    if path.startswith('/drive/v3/files?') and method is None:return {'files':[{'id':'health-file','mimeType':'text/markdown'}]}
    if path.startswith('/drive/v3/files/'):return {'id':'health-file','mimeType':'text/markdown','parents':['folder']}
    return {'id':'health-file','size':str(len(data)),'md5Checksum':hashlib.md5(data).hexdigest(),'modifiedTime':'synthetic'}
  with tempfile.TemporaryDirectory() as root,patch('collector_health.Drive',FakeDrive):
   root=Path(root);h=finish(begin(root),True)
   a=publish_health(root,{'GOOGLE_DRIVE_FOLDER_ID':'folder'},h)
   h=finish(begin(root),False,'axios','axios_failed')
   b=publish_health(root,{'GOOGLE_DRIVE_FOLDER_ID':'folder'},h)
   self.assertEqual(a['file_id'],b['file_id']);self.assertEqual(b['status'],'failed')

class PublicHeartbeatTest(unittest.TestCase):
 def test_failed_login_publishes_failed_when_drive_is_enabled(self):
  from test_config_cli import ConfigTest
  from collector import main
  import contextlib,io
  published=[]
  with tempfile.TemporaryDirectory() as directory:
   path=ConfigTest().write_config(directory,'DRIVE_UPLOAD=true\nGOOGLE_CLIENT_ID=synthetic-client\nGOOGLE_CLIENT_SECRET=synthetic-secret\nGOOGLE_REFRESH_TOKEN=synthetic-refresh\nGOOGLE_DRIVE_FOLDER_ID=synthetic-folder\n')
   with patch('collector.login_selected',side_effect=RuntimeError('must-not-leak-secret')),patch('collector_health.publish_health',side_effect=lambda r,c,h:published.append(dict(h)) or {'file_id':'synthetic-file'}),contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(main(['--config',str(path),'run']),1)
   self.assertEqual([h['status'] for h in published],['running','failed'])
   self.assertNotIn('must-not-leak-secret',json.dumps(published))

if __name__=='__main__':unittest.main()

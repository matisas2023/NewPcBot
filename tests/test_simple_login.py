import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from pc_remote.auth import Account, LoginError, REMEMBER_SECONDS, create_credentials
from pc_remote.phone import public_url

class SimpleLoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.credentials=create_credentials('fixture-user','fixture-password-123!')
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'sessions.json'
    def login(self,remember=True):
        account=Account(self.credentials,self.path)
        token,session=account.login('fixture-user','fixture-password-123!','https://fixture.example',remember)
        return account,token,session
    def test_remember_survives_restart_without_storing_cookie(self):
        _,token,session=self.login()
        saved=self.path.read_text()
        self.assertNotIn(token,saved)
        self.assertNotIn('fixture-password',saved)
        self.assertIn(hashlib.sha256(token.encode()).hexdigest(),saved)
        restored=Account(self.credentials,self.path).authenticate(token,'https://fixture.example')
        self.assertEqual(restored['csrf'],session['csrf'])
        self.assertEqual(session['ttl'],REMEMBER_SECONDS)
    def test_default_session_does_not_survive_restart(self):
        _,token,_=self.login(False)
        with self.assertRaises(LoginError):
            Account(self.credentials,self.path).authenticate(token,'https://fixture.example')
    def test_logout_revokes_persisted_session(self):
        account,token,session=self.login()
        account.logout(session)
        with self.assertRaises(LoginError):
            Account(self.credentials,self.path).authenticate(token,'https://fixture.example')
    def test_password_change_invalidates_sessions(self):
        _,token,_=self.login()
        updated=create_credentials('fixture-user','different-password-123!')
        with self.assertRaises(LoginError):
            Account(updated,self.path).authenticate(token,'https://fixture.example')
    def test_expired_and_malformed_store_ignored(self):
        self.login()
        data=json.loads(self.path.read_text())
        for session in data['sessions'].values():
            session['expires_at']=time.time()-1
        self.path.write_text(json.dumps(data))
        self.assertFalse(Account(self.credentials,self.path).sessions)
        self.path.write_text('[]')
        self.assertFalse(Account(self.credentials,self.path).sessions)
    def test_phone_requires_ready_https_without_credentials(self):
        for state in ({'state':'retrying','url':'https://old.example'},
                      {'state':'online','url':'http://127.0.0.1:8765'},
                      {'state':'online','url':'https://user:secret@example.com'}):
            self.assertIsNone(public_url(state))
        self.assertEqual(public_url({'state':'online','url':'https://fixture.example'}),'https://fixture.example')

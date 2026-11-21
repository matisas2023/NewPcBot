"""Run without Telegram or desktop access: python -m unittest discover -s tests -p test_mobile_agent.py"""
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from pc_remote.server import RemoteServer, MAX_UPLOAD, APIError, PROXY_HOST
from pc_remote.auth import create_credentials, COOKIE_NAME, Account, LoginError
from http.cookies import SimpleCookie

USERNAME = "test-user"
PASSWORD = "test-only-password-123!"


class FakeBackend:
    def pointer(self, **data):
        self.calls.append(('pointer',data))

    def trash(self, path):
        self.calls.append(('trash',str(path)))
        path.unlink()

    def __init__(self):
        self.calls = []

    def status(self):
        return {"pc": "test-pc", "os": "Windows", "cpu": 10, "ram": 20, "disk": 30, "uptime": 123}

    def screenshot(self):
        self.calls.append("screenshot")
        return b"\x89PNG\r\n\x1a\n"

    def processes(self):
        return [{"pid": 987654, "name": "test.exe", "ram": 2, "created": 123}]

    def input(self, action):
        self.calls.append(("input", action))

    def system(self, action):
        self.calls.append(("system", action))

    def terminate(self, pid, created):
        self.calls.append(("terminate", pid, created))


class AgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.backend = FakeBackend()
        cls.server = RemoteServer(("127.0.0.1", 0), create_credentials(USERNAME, PASSWORD), cls.temp.name, cls.backend)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)
        cls.temp.cleanup()

    def setUp(self):
        with self.server.account.lock:
            self.server.account.attempts.clear()
        status, body, headers = self.request('/api/login', {'username':USERNAME, 'password':PASSWORD}, auth=False)
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';',1)[0]
        self.csrf = json.loads(body)['csrf']

    def request(self, path, data=None, method=None, auth=True, headers=None):
        headers = dict(headers or {})
        if auth:
            headers.setdefault('Cookie', self.cookie)
            headers.setdefault('X-CSRF-Token', self.csrf)
        if data is not None or method == 'POST':
            headers.setdefault('Origin', f'http://127.0.0.1:{self.server.server_port}')
        if data is not None and not isinstance(data, bytes):
            data = json.dumps(data).encode()
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method or ("POST" if data is not None else "GET"), path, data, headers)
        response = connection.getresponse()
        body = response.read()
        result = (response.status, body, dict(response.getheaders()))
        connection.close()
        return result

    def post(self, path, data, **kwargs):
        status, body, _ = self.request(path, data, **kwargs)
        return status, json.loads(body)

    def ticket(self, operation, payload):
        status, result = self.post('/api/confirm', {"operation": operation, "payload": payload})
        self.assertEqual(status, 200)
        return result['confirmation']

    def execute(self, operation, payload, ticket):
        return self.post('/api/execute', {"operation": operation, "payload": payload, "confirmation": ticket})

    def test_unauthenticated_api_denied(self):
        for path in ['/api/status', '/api/processes', '/api/screenshot', '/api/files']:
            self.assertEqual(self.request(path, auth=False)[0], 401)

    def test_query_token_not_accepted(self):
        self.assertEqual(self.request('/api/status?token=legacy-key', auth=False)[0], 401)

    def test_cross_site_denied(self):
        self.assertEqual(self.request('/api/status', headers={'Sec-Fetch-Site':'cross-site'})[0], 403)

    def test_authenticated_status_and_processes(self):
        code, body, headers = self.request('/api/status')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body)['pc'], 'test-pc')
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        self.assertEqual(self.request('/api/processes')[0], 200)

    def test_screen_is_not_cached(self):
        code, body, headers = self.request('/api/screenshot')
        self.assertEqual(code, 200)
        self.assertTrue(body.startswith(b'\x89PNG'))
        self.assertEqual(headers['Cache-Control'], 'no-store')

    def test_input_allowlist(self):
        self.assertEqual(self.post('/api/input', {'action':'volup'})[0], 200)
        self.assertEqual(self.post('/api/input', {'action':'run shell'})[0], 400)
        self.assertIn(('input', 'volup'), self.backend.calls)

    def test_connection_diagnostics_require_login(self):
        self.assertEqual(self.request('/api/connection',auth=False)[0],401)
        code,body,_=self.request('/api/connection')
        self.assertEqual(code,200)
        self.assertEqual(json.loads(body)['tunnel']['state'],'local')
        self.assertEqual(json.loads(body)['delete_mode'],'recycle_bin')

    def test_pointer_api_and_csrf(self):
        self.assertEqual(self.post('/api/pointer',{'dx':12,'dy':-3,'button':'right'})[0],200)
        self.assertEqual(self.post('/api/pointer',{'dx':10000})[0],400)
        self.assertEqual(self.request('/api/pointer',{'scroll':2},headers={'X-CSRF-Token':''})[0],403)

    def test_confirmation_required_and_single_use(self):
        payload = {'action':'Restart'}
        self.assertEqual(self.execute('system', payload, '')[0], 409)
        ticket = self.ticket('system', payload)
        self.assertEqual(self.execute('system', payload, ticket)[0], 200)
        self.assertEqual(self.execute('system', payload, ticket)[0], 409)

    def test_confirmation_bound_to_action(self):
        ticket = self.ticket('system', {'action':'Lock'})
        self.assertEqual(self.execute('system', {'action':'Shutdown'}, ticket)[0], 409)

    def test_confirmation_expiration(self):
        payload = {'action':'Sleep'}
        ticket = self.ticket('system', payload)
        with self.server.confirm_lock:
            self.server.confirmations[ticket] = (time.monotonic()-1, *self.server.confirmations[ticket][1:])
        self.assertEqual(self.execute('system', payload, ticket)[0], 409)

    def test_process_confirmation_and_protected_pid(self):
        self.assertEqual(self.post('/api/confirm', {'operation':'terminate', 'payload':{'pid':os.getpid(),'created':123}})[0], 400)
        payload = {'pid':987654, 'created':123}
        ticket = self.ticket('terminate', payload)
        self.assertEqual(self.execute('terminate', payload, ticket)[0], 200)
        self.assertIn(('terminate', 987654, 123), self.backend.calls)

    def test_path_traversal_denied(self):
        for path in ['../outside', '..%2Foutside', 'C%3A%2FWindows', '%5C%5Cserver%5Cshare', '%2Foutside', '%00', 'CON', 'folder/NUL.txt']:
            self.assertIn(self.request('/api/files?path='+path)[0], [400,403])

    def test_resolved_symlink_escape_denied(self):
        with tempfile.TemporaryDirectory() as outside:
            link = Path(self.temp.name) / 'link-outside'
            try:
                link.symlink_to(outside, target_is_directory=True)
            except OSError:
                self.skipTest('Symlink privilege unavailable on this host')
            try:
                with self.assertRaises(APIError):
                    self.server.file_path('link-outside')
            finally:
                link.unlink()

    def test_resolved_junction_escape_denied_without_symlink_privilege(self):
        outside = Path(self.temp.name).parent / 'outside-shared-root'
        with patch.object(Path, 'resolve', return_value=outside):
            with self.assertRaises(APIError):
                self.server.file_path('junction/file.txt')

    def test_upload_download_no_overwrite_and_delete(self):
        self.assertEqual(self.request('/api/upload?path=sample.txt', b'hello')[0], 201)
        self.assertEqual(self.request('/api/upload?path=sample.txt', b'overwrite')[0], 409)
        self.assertEqual(self.request('/api/download?path=sample.txt')[1], b'hello')
        payload = {'path':'sample.txt'}
        ticket = self.ticket('delete', payload)
        self.assertEqual(self.execute('delete', payload, ticket)[0], 200)
        self.assertFalse((Path(self.temp.name)/'sample.txt').exists())

    def test_modified_file_invalidates_confirmation(self):
        path = Path(self.temp.name)/'changed.txt'
        path.write_text('before')
        payload = {'path':'changed.txt'}
        ticket = self.ticket('delete', payload)
        path.write_text('changed contents')
        self.assertEqual(self.execute('delete', payload, ticket)[0], 409)
        self.assertTrue(path.exists())

    def test_upload_size_limit(self):
        self.assertEqual(self.request('/api/upload?path=large.bin', b'', headers={'Content-Length':str(MAX_UPLOAD+1)})[0], 413)

    def test_invalid_json(self):
        self.assertEqual(self.request('/api/input', b'not json', headers={'Content-Type':'application/json'})[0], 400)
        self.assertEqual(self.post('/api/input', ['unexpected'])[0], 400)

    def test_static_allowlist_and_assets(self):
        for path in ['/', '/app.js', '/sw.js', '/manifest.webmanifest', '/icon-192.png', '/icon-512.png']:
            status, body, headers = self.request(path, auth=False)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertEqual(self.request('/.pc-remote.json', auth=False)[0], 404)
        self.assertEqual(self.request('/../server.py', auth=False)[0], 404)

    def test_legacy_key_config_rejected(self):
        with self.assertRaises(ValueError):
            RemoteServer(('127.0.0.1',0), {'token':'old-key'}, self.temp.name)

    def test_wrong_login_and_password(self):
        for username, password in [('wrong-user', PASSWORD), (USERNAME, 'wrong-password')]:
            code, body, headers = self.request('/api/login', {'username':username,'password':password}, auth=False)
            self.assertEqual(code, 401)
            self.assertNotIn('Set-Cookie', headers)
            self.assertNotIn(PASSWORD.encode(), body)

    def test_cookie_flags_and_no_password_in_response(self):
        code, body, headers = self.request('/api/login', {'username':USERNAME,'password':PASSWORD}, auth=False)
        self.assertEqual(code, 200)
        self.assertIn('HttpOnly', headers['Set-Cookie'])
        self.assertIn('SameSite=Strict', headers['Set-Cookie'])
        self.assertNotIn('password', json.loads(body))
        self.assertNotIn('token', json.loads(body))

    def test_public_https_and_origin_validation(self):
        previous = self.server.public_origin
        self.server.public_origin = 'https://test-only.trycloudflare.com'
        public = {'Host':PROXY_HOST, 'Origin':self.server.public_origin, 'X-Forwarded-Proto':'https'}
        try:
            code, body, headers = self.request('/api/login', {'username':USERNAME,'password':PASSWORD}, auth=False, headers=public)
            self.assertEqual(code, 200)
            self.assertIn('Secure', headers['Set-Cookie'])
            public['Cookie'] = headers['Set-Cookie'].split(';',1)[0]
            self.assertEqual(self.request('/api/status', auth=False, headers=public)[0], 200)
            public['X-Forwarded-Proto'] = 'http'
            self.assertEqual(self.request('/api/status', auth=False, headers=public)[0], 403)
        finally:
            self.server.public_origin = previous

    def test_csrf_required_for_every_mutation(self):
        for path, payload in [('/api/input',{'action':'volup'}),('/api/logout',{}),('/api/confirm',{'operation':'system','payload':{'action':'Lock'}})]:
            self.assertEqual(self.request(path,payload,headers={'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('/api/upload?path=csrf.txt',b'blocked',headers={'X-CSRF-Token':''})[0],403)
        self.assertEqual(self.request('/api/input',{'action':'volup'},headers={'Origin':'https://attacker.example'})[0],403)

    def test_unknown_host_denied(self):
        self.assertEqual(self.request('/api/status',headers={'Host':'attacker.example'})[0],403)

    def test_logout_revokes_cookie(self):
        self.assertEqual(self.post('/api/logout',{})[0],200)
        self.assertEqual(self.request('/api/status')[0],401)

    def test_expired_session_denied(self):
        cookie = SimpleCookie(self.cookie)
        session = self.server.account.authenticate(cookie[COOKIE_NAME].value, f'http://127.0.0.1:{self.server.server_port}')
        with self.server.account.lock:
            self.server.account.sessions[session['id']]['expires'] = time.monotonic()-1
        self.assertEqual(self.request('/api/status')[0],401)

    def test_confirmation_cannot_be_used_by_another_session(self):
        payload = {'action':'Lock'}
        ticket = self.ticket('system',payload)
        code, body, headers = self.request('/api/login', {'username':USERNAME,'password':PASSWORD},auth=False)
        self.assertEqual(code,200)
        self.cookie = headers['Set-Cookie'].split(';',1)[0]
        self.csrf = json.loads(body)['csrf']
        self.assertEqual(self.execute('system',payload,ticket)[0],409)

    def test_login_rate_limit_not_bypassed_by_forwarded_ip(self):
        with self.server.account.lock:
            self.server.account.attempts = [time.monotonic()] * 10
        self.assertEqual(self.request('/api/login',{'username':USERNAME,'password':PASSWORD},auth=False,headers={'X-Forwarded-For':'new-address'})[0],429)


class SharedControlTests(unittest.TestCase):
    def test_system_allowlist_and_windows_command(self):
        from agent.control import execute_system_action
        with patch('agent.control.platform.system', return_value='Windows'), patch('agent.control.subprocess.run') as run:
            with self.assertRaises(ValueError):
                execute_system_action('arbitrary command')
            run.assert_not_called()
            execute_system_action('Restart')
            self.assertEqual(run.call_args.args[0][:2], ['shutdown', '/r'])

    def test_capture_uses_real_backend_or_fails(self):
        from agent.control import capture_screen
        backend = SimpleNamespace(screenshot=Mock(return_value=SimpleNamespace(save=lambda output, **kwargs: output.write(b'captured-png'))))
        with patch('agent.control.sys.platform', 'win32'), patch.dict('sys.modules', {'pyautogui':backend}):
            self.assertEqual(capture_screen(), b'captured-png')
        with patch('agent.control.sys.platform', 'win32'), patch.dict('sys.modules', {'pyautogui':None}):
            with self.assertRaises(RuntimeError):
                capture_screen()

    def test_process_reuse_does_not_terminate_new_process(self):
        from agent.control import terminate_process
        proc = SimpleNamespace(create_time=lambda:456, terminate=Mock())
        psutil = SimpleNamespace(Process=Mock(return_value=proc))
        with patch.dict('sys.modules', {'psutil':psutil}):
            with self.assertRaises(ValueError):
                terminate_process(987654,123)
        proc.terminate.assert_not_called()


class AccountTests(unittest.TestCase):
    def test_password_hash_has_random_salt(self):
        first = create_credentials(USERNAME,PASSWORD)
        second = create_credentials(USERNAME,PASSWORD)
        self.assertNotEqual(first['salt'],second['salt'])
        self.assertNotEqual(first['password_hash'],second['password_hash'])
        self.assertNotIn(PASSWORD,json.dumps(first))

    def test_weak_password_rejected(self):
        with self.assertRaises(ValueError):
            create_credentials(USERNAME,'short')

    def test_legacy_bearer_not_used(self):
        account = Account(create_credentials(USERNAME,PASSWORD))
        with self.assertRaises(LoginError):
            account.authenticate('old-key','http://localhost')

    def test_setup_migrates_old_key_and_preserves_shared_folder(self):
        from pc_remote.__main__ import setup
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'config.json'
            shared = Path(folder)/'shared'
            path.write_text(json.dumps({'token':'legacy-secret','files':str(shared)}),encoding='utf-8')
            with patch('builtins.input',return_value=USERNAME), patch('pc_remote.__main__.getpass',side_effect=[PASSWORD,PASSWORD]), patch('builtins.print'):
                setup(path)
            stored = json.loads(path.read_text(encoding='utf-8'))
            self.assertNotIn('token',stored)
            self.assertNotIn(PASSWORD,json.dumps(stored))
            self.assertEqual(stored['files'],str(shared.resolve()))
            self.assertEqual(stored['account']['username'],USERNAME)


class TunnelTests(unittest.TestCase):
    def test_official_api_url_is_not_treated_as_public_address(self):
        from pc_remote.tunnel import QuickTunnel
        server = SimpleNamespace(server_port=8765,public_origin=None)
        tunnel = QuickTunnel(server)
        process = SimpleNamespace(stdout=io.StringIO('ERR request failed https://api.trycloudflare.com/tunnel\n'),poll=Mock(return_value=1))
        tunnel.process = process
        tunnel._read()
        self.assertIsNone(tunnel.url)
        self.assertIsNone(server.public_origin)

    def test_generated_url_sets_expected_origin(self):
        from pc_remote.tunnel import QuickTunnel
        server = SimpleNamespace(server_port=8765,public_origin=None)
        tunnel = QuickTunnel(server)
        tunnel.process = SimpleNamespace(stdout=io.StringIO('| https://random-test-name.trycloudflare.com |\n'))
        tunnel._read()
        self.assertEqual(tunnel.url,'https://random-test-name.trycloudflare.com')
        self.assertEqual(server.public_origin,tunnel.url)

    def test_launcher_uses_loopback_and_fixed_host_header(self):
        from pc_remote.tunnel import QuickTunnel
        process = Mock()
        process.stdout = io.StringIO('| https://random-test-name.trycloudflare.com |\n')
        process.poll.return_value = None
        tunnel = QuickTunnel(SimpleNamespace(server_port=8765,public_origin=None))
        with patch('pc_remote.tunnel.shutil.which',return_value='cloudflared.exe'), patch('pc_remote.tunnel.subprocess.Popen',return_value=process) as launch:
            self.assertEqual(tunnel.start(),'https://random-test-name.trycloudflare.com')
            args = launch.call_args.args[0]
            self.assertIn('http://127.0.0.1:8765',args)
            self.assertIn(PROXY_HOST,args)
            tunnel.close()


if __name__ == '__main__':
    unittest.main()

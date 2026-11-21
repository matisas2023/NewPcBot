"""HTTPS reverse proxy for a public IPv4 address; the agent stays on loopback."""
import ipaddress
import json
import logging
import os
import socket
import ssl
import subprocess
import threading
import time

from .runtime import STATE_DIR, read_state

LOG = logging.getLogger(__name__)


def settings(data):
    if not isinstance(data, dict):
        raise ValueError('Direct access configuration must be an object')
    public = ipaddress.IPv4Address(data.get('public_ip', ''))
    local = ipaddress.IPv4Address(data.get('lan_ip', ''))
    if not public.is_global or not local.is_private or local.is_loopback or local.is_unspecified or local.is_link_local:
        raise ValueError('Use a public IPv4 and the PC LAN IPv4')
    host = f'pc-helper.{public}.sslip.io'
    return {'host': host, 'origin': f'https://{host}', 'lan_ip': str(local)}


def load_settings():
    return settings(read_state(STATE_DIR/'direct.json'))


def caddyfile(config, port=8765):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError('Invalid agent port')
    # Both sites explicitly bind the LAN interface, preserving other interfaces' HTTPS services.
    host, local = config['host'], config['lan_ip']
    storage = json.dumps((STATE_DIR/'caddy/certificates').as_posix())
    return f'''{{
    admin off
    persist_config off
    storage file_system {storage}
    servers {{
        protocols h1 h2
        max_header_size 32KB
        timeouts {{
            read_header 10s
            read_body 30s
            idle 60s
        }}
    }}
}}
http://{host} {{
    bind {local}
    redir https://{host}{{uri}} 308
}}
https://{host} {{
    bind {local}
    reverse_proxy 127.0.0.1:{port} {{
        header_up Host pc-helper.internal
        header_up X-Forwarded-Proto https
    }}
}}
'''


class DirectProxy:
    def __init__(self, server, config):
        self.server, self.config = server, config
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.thread = None
        self.process = None
        self.state = {'state':'connecting', 'url':None, 'retry_in':0, 'kind':'direct'}
        self.directory = STATE_DIR/'caddy'
        self.executable = self.directory/'caddy.exe'

    def snapshot(self):
        with self.lock:
            return self.state.copy()

    def update(self, ready=False, state='connecting'):
        with self.lock:
            self.state = {'state':'online' if ready else state,
                          'url':self.config['origin'] if ready else None, 'retry_in':0, 'kind':'direct'}

    def start(self):
        if not self.executable.is_file():
            raise RuntimeError('Install Caddy into .pc-helper-runtime/caddy/caddy.exe first')
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory/'Caddyfile').write_text(caddyfile(self.config,self.server.server_port),encoding='utf-8')
        self.thread = threading.Thread(target=self.run,daemon=True)
        self.thread.start()

    def certificate_ready(self):
        try:
            with socket.create_connection((self.config['lan_ip'],443),timeout=2) as raw:
                with ssl.create_default_context().wrap_socket(raw,server_hostname=self.config['host']):
                    return True
        except (OSError, ssl.SSLError):
            return False

    def run(self):
        next_router_check = 0
        try:
            while not self.done.is_set():
                with (self.directory/'proxy.log').open('ab') as output:
                    self.process = subprocess.Popen([str(self.executable),'run','--config',str(self.directory/'Caddyfile'),
                        '--adapter','caddyfile'],stdout=output,stderr=subprocess.STDOUT,
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                    while not self.done.is_set() and self.process.poll() is None:
                        if time.monotonic() >= next_router_check:
                            from .router import ensure_mappings
                            try:
                                ensure_mappings(read_state(STATE_DIR/'router.json'),self.config['lan_ip'])
                            except Exception as exc:
                                LOG.warning('Could not restore PC Helper port mappings: %s',exc)
                            next_router_check = time.monotonic()+300
                        self.update(self.certificate_ready())
                        self.done.wait(5)
                    if self.process.poll() is None:
                        self.process.terminate()
                        try:
                            self.process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            self.process.kill()
                            self.process.wait(timeout=5)
                if not self.done.is_set():
                    LOG.error('HTTPS proxy stopped; retrying in 15 seconds')
                    self.update(state='retrying')
                    self.done.wait(15)
        except OSError:
            LOG.exception('Could not run HTTPS proxy')
        finally:
            if self.process and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.update(state='stopped')

    def stop(self):
        self.done.set()
        if self.thread:
            self.thread.join(timeout=15)


def main():
    import argparse
    from .runtime import write_state
    parser = argparse.ArgumentParser(description='Configure direct HTTPS access through a public IPv4')
    parser.add_argument('--public-ip',required=True)
    parser.add_argument('--lan-ip',required=True)
    args = parser.parse_args()
    data = {'public_ip':args.public_ip,'lan_ip':args.lan_ip}
    try:
        config = settings(data)
    except ValueError as exc:
        parser.error(str(exc))
    write_state(STATE_DIR/'direct.json',data)
    print('HTTPS address:',config['origin'])
    print('Forward TCP 80/443 to the LAN IPv4, install Caddy, then start pc_remote.desktop --direct.')


if __name__ == '__main__':
    main()

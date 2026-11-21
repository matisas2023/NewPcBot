import ssl
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from pc_remote.direct import DirectProxy, caddyfile, settings
from pc_remote.desktop import startup_command
from pc_remote.router import ensure_mappings


def test_public_ip_and_lan_only():
    for public,local in [('127.0.0.1','192.168.1.2'),('100.64.1.2','192.168.1.2'),
                         ('8.8.8.8','0.0.0.0'),('8.8.8.8','127.0.0.1'),
                         ('8.8.8.8','169.254.1.2'),('8.8.8.8','8.8.4.4'),
                         ('8.8.8.8\nmalicious','192.168.1.2')]:
        with pytest.raises(ValueError):
            settings({'public_ip':public,'lan_ip':local})


def test_proxy_binds_both_sites_to_lan_and_overrides_forwarded_headers():
    config=settings({'public_ip':'8.8.8.8','lan_ip':'192.168.1.2'})
    text=caddyfile(config)
    assert text.count('bind 192.168.1.2') == 2
    assert 'admin off' in text
    assert 'reverse_proxy 127.0.0.1:8765' in text
    assert 'header_up X-Forwarded-Proto https' in text
    assert 'header_up Host pc-helper.internal' in text
    assert 'http://pc-helper.8.8.8.8.sslip.io' in text
    assert 'redir https://' in text
    assert 'tls internal' not in text


def test_qr_address_waits_for_verified_certificate():
    config=settings({'public_ip':'8.8.8.8','lan_ip':'192.168.1.2'})
    proxy=DirectProxy(SimpleNamespace(server_port=8765),config)
    assert proxy.snapshot()['url'] is None
    with patch('pc_remote.direct.socket.create_connection',side_effect=ssl.SSLError('Invalid certificate')):
        assert not proxy.certificate_ready()
    proxy.update(True)
    assert proxy.snapshot()['url'] == config['origin']
    proxy.update(state='retrying')
    assert proxy.snapshot()['url'] is None


def test_direct_startup_does_not_start_quick_tunnel():
    command=startup_command(direct=True)
    assert '--direct' in command
    assert '--public' not in command


ROUTER = {'control':'http://192.168.1.1:1900/control',
          'service':'urn:schemas-upnp-org:service:WANIPConnection:1','lan':'192.168.1.2'}


def router_response(**values):
    import io
    return io.BytesIO(('<root>'+''.join(f'<{key}>{value}</{key}>' for key,value in values.items())+'</root>').encode())


def test_router_preserves_another_computers_mapping():
    with patch('pc_remote.router.urlopen',return_value=router_response(
            NewInternalClient='192.168.1.99',NewInternalPort='443',NewEnabled='1')) as request:
        with pytest.raises(RuntimeError,match='preserved'):
            ensure_mappings(ROUTER,'192.168.1.2')
        assert request.call_count == 1
        assert b'AddPortMapping' not in request.call_args.args[0].data


def test_router_restores_missing_mapping_and_verifies_it():
    replies=[router_response(errorCode='714'), router_response(),
             router_response(NewInternalClient='192.168.1.2',NewInternalPort='80',NewEnabled='1'),
             router_response(NewInternalClient='192.168.1.2',NewInternalPort='443',NewEnabled='1')]
    with patch('pc_remote.router.urlopen',side_effect=replies) as request:
        ensure_mappings(ROUTER,'192.168.1.2')
        writes=[call.args[0].data for call in request.call_args_list if b'<u:AddPortMapping ' in call.args[0].data]
        assert len(writes)==1
        assert b'<NewExternalPort>80</NewExternalPort>' in writes[0]
        assert b'<NewInternalClient>192.168.1.2</NewInternalClient>' in writes[0]


def test_router_rejects_remote_control_endpoint_before_any_request():
    with patch('pc_remote.router.urlopen') as request:
        with pytest.raises(ValueError):
            ensure_mappings({**ROUTER,'control':'http://8.8.8.8/control'},'192.168.1.2')
        request.assert_not_called()

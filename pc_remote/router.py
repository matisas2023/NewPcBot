"""Restore only PC Helper's UPnP mappings on the explicitly configured LAN router."""
import ipaddress
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

OWNER = 'PC Helper HTTPS'


def ensure_mappings(router, lan):
    if not router:
        return
    target = urlsplit(router.get('control',''))
    gateway = ipaddress.IPv4Address(target.hostname or '')
    network = ipaddress.IPv4Network(f'{lan}/24',strict=False)
    if (target.scheme != 'http' or not gateway.is_private or gateway.is_loopback
            or gateway not in network or str(gateway)==lan or target.username or target.password
            or target.query or target.fragment or router.get('lan') != lan):
        raise ValueError('UPnP target must be the configured router on this LAN')
    kind = router.get('service')
    if kind not in {f'urn:schemas-upnp-org:service:{service}:{version}'
                    for service in ('WANIPConnection','WANPPPConnection') for version in (1,2)}:
        raise ValueError('Unsupported router service')

    def call(action, body=''):
        envelope = (f'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
                    f'<s:Body><u:{action} xmlns:u="{kind}">{body}</u:{action}></s:Body></s:Envelope>')
        request = Request(router['control'],data=envelope.encode(),headers={
            'Content-Type':'text/xml; charset="utf-8"','SOAPAction':f'"{kind}#{action}"'})
        try:
            with urlopen(request,timeout=2) as response:
                raw=response.read(65537)
        except HTTPError as exc:
            with exc:
                raw=exc.read(65537)
        if len(raw)>65536:
            raise ValueError('Router response too large')
        tree=ET.fromstring(raw)
        return {node.tag.rsplit('}',1)[-1]:node.text for node in tree.iter() if len(node)==0}

    for port in (80,443):
        query=(f'<NewRemoteHost></NewRemoteHost><NewExternalPort>{port}</NewExternalPort>'
               '<NewProtocol>TCP</NewProtocol>')
        current=call('GetSpecificPortMappingEntry',query)
        if 'NewInternalClient' in current:
            if (current['NewInternalClient'] != lan or current.get('NewInternalPort') != str(port)
                    or current.get('NewEnabled') != '1'):
                raise RuntimeError(f'Port {port} has another mapping; it was preserved')
            # An existing equivalent manual rule also needs no changes.
            continue
        if not (current.get('errorCode')=='714' or current.get('errorCode')=='501'
                and current.get('errorDescription')=='Entry not found !'):
            raise RuntimeError(f'Could not verify free port {port}')
        result=call('AddPortMapping',query+
            f'<NewInternalPort>{port}</NewInternalPort><NewInternalClient>{lan}</NewInternalClient>'
            f'<NewEnabled>1</NewEnabled><NewPortMappingDescription>{OWNER}</NewPortMappingDescription>'
            '<NewLeaseDuration>0</NewLeaseDuration>')
        if 'errorCode' in result:
            raise RuntimeError(f'Router rejected port {port}: {result["errorCode"]}')
        verified=call('GetSpecificPortMappingEntry',query)
        if verified.get('NewInternalClient') != lan or verified.get('NewInternalPort') != str(port):
            raise RuntimeError(f'Could not verify port {port}')

"""MikroTik RouterOS adapter over the REST API (RouterOS >= 7.1, `www-ssl`).

Credentials are explicit; no defaults are ever tried. Manage the router over a
wired/management link: RouterOS REST has no commit-confirm, so a Wi-Fi change
is verified by read-back instead of auto-rollback.

Only queues named ``uwz-*`` are ever created/changed/deleted by this adapter.
Property names for the `wifi` package are taken from MikroTik documentation and
are marked hardware_verified=False until tested on a real device.
"""
import base64
import json
import re
import time

from .base import (ApplyResult, Capability, Client, Lease, PingResult, RouterAdapter,
                   RouterAuthError, RouterError, RouterInfo, UnsupportedOperation,
                   WifiNetwork)
from .http import make_http
from . import validation as V

QUEUE_PREFIX = 'uwz-'
_AUTH = {'wpa2': 'wpa2-psk', 'wpa3': 'wpa3-psk', 'wpa2/wpa3': 'wpa2-psk,wpa3-psk'}


def parse_duration(s):
    """RouterOS durations like '1w2d3h4m5s' -> seconds."""
    total, units = 0, {'w': 604800, 'd': 86400, 'h': 3600, 'm': 60, 's': 1}
    found = False
    for n, u in re.findall(r'(\d+)([wdhms])', str(s or '')):
        total += int(n) * units[u]
        found = True
    return total if found else None


def _version_tuple(v):
    m = re.match(r'(\d+)\.(\d+)', str(v or ''))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


def _get(item, dotted):
    """REST may flatten nested props ('configuration.ssid') or nest them."""
    if dotted in item:
        return item[dotted]
    cur = item
    for part in dotted.split('.'):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _sec_from_auth(auth):
    a = str(auth or '')
    if not a:
        return 'open'
    has2, has3 = 'wpa2' in a, 'wpa3' in a
    return 'wpa2/wpa3' if has2 and has3 else 'wpa3' if has3 else 'wpa2' if has2 else 'other'


class RestClient:
    def __init__(self, base_url, username, password, http):
        tok = base64.b64encode(f'{username}:{password}'.encode()).decode()
        self.base, self.http = base_url, http
        self._h = {'Authorization': 'Basic ' + tok, 'Content-Type': 'application/json'}

    def request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        status, raw = self.http(method, self.base + path, self._h, data)
        try:
            payload = json.loads(raw) if raw else None
        except ValueError:
            payload = None
        if status == 401:
            raise RouterAuthError('router login failed')
        if status >= 400:
            msg = (payload or {}).get('message') or (payload or {}).get('detail') or ''
            raise RouterError(f'RouterOS {method} {path.split("?")[0]} -> {status} {msg}'[:200])
        return payload


class MikroTikAdapter(RouterAdapter):
    kind = 'mikrotik'
    vendor_label = 'MikroTik'
    hardware_verified = False

    def __init__(self, host, username, password, *, port=None, scheme='https', http=None,
                 verify_tls=True, ca_file=None, timeout=10):
        super().__init__()
        if not username or not password:
            raise RouterAuthError('credentials are required (no defaults are ever tried)')
        V.valid_host(host)
        netloc = f'{host}:{port}' if port else host
        self.rest = RestClient(f'{scheme}://{netloc}/rest', username, password,
                               http or make_http(verify_tls, ca_file, timeout))
        self._wifi_path = None

    def guidance(self):
        return {'legacy_wireless': 'RouterOS with the legacy "wireless" package: configure '
                                   'Wi-Fi manually in WinBox/WebFig (read-only here).',
                'rest_requires': 'RouterOS 7.1+ with www-ssl enabled',
                'documented_status': 'docs/ROUTER_COMPATIBILITY.md#mikrotik'}

    # ---------------------------------------------------------------- identity
    def identify(self):
        res = self.rest.request('GET', '/system/resource') or {}
        ident = self.rest.request('GET', '/system/identity') or {}
        version = res.get('version', '')
        if _version_tuple(version) < (7, 1):
            raise UnsupportedOperation(
                f'RouterOS {version or "unknown"} has no REST API (needs 7.1+)',
                {'option': 'Upgrade RouterOS, or configure the router manually / in AP mode.'})
        return RouterInfo(vendor='MikroTik', model=res.get('board-name', 'unknown'),
                          firmware=f'RouterOS {version}', hostname=ident.get('name', ''),
                          uptime_s=parse_duration(res.get('uptime')))

    def _probe(self, path):
        try:
            self.rest.request('GET', path)
            return True
        except RouterAuthError:
            raise
        except RouterError:
            return False

    def _detect(self):
        self.identify()                          # also enforces the version floor
        caps = {Capability.INFO}
        if self._probe('/interface/wifi'):
            self._wifi_path = '/interface/wifi'
            caps |= {Capability.WIFI_READ, Capability.WIFI_CONFIG}
            if self._probe('/interface/wifi/registration-table'):
                caps.add(Capability.CLIENTS)
        elif self._probe('/interface/wireless'):      # legacy package: read-only
            self._wifi_path = '/interface/wireless'
            caps.add(Capability.WIFI_READ)
            if self._probe('/interface/wireless/registration-table'):
                caps.add(Capability.CLIENTS)
        if self._probe('/ip/dhcp-server/lease'):
            caps.add(Capability.DHCP_LEASES)
        if self._probe('/queue/simple'):
            caps.add(Capability.BANDWIDTH)
        caps.add(Capability.DIAGNOSTICS)
        return caps

    # -------------------------------------------------------------------- wifi
    def list_wifi(self):
        self.require(Capability.WIFI_READ)
        legacy = self._wifi_path == '/interface/wireless'
        out = []
        for it in self.rest.request('GET', self._wifi_path) or []:
            ssid = it.get('ssid') if legacy else _get(it, 'configuration.ssid')
            sec = 'other' if legacy else _sec_from_auth(_get(it, 'security.authentication-types'))
            out.append(WifiNetwork(id=it['.id'], ssid=ssid or '', security=sec,
                                   enabled=str(it.get('disabled', 'false')) != 'true'))
        return out

    def configure_wifi(self, network_id, *, ssid=None, passphrase=None, security=None,
                       enabled=None, allow_open=False):
        self.require(Capability.WIFI_CONFIG)
        if not re.fullmatch(r'\*[0-9A-Fa-f]+', str(network_id)):
            raise V.ValidationFailed('invalid interface id')
        body = {}
        if ssid is not None:
            body['configuration.ssid'] = V.valid_ssid(ssid)
        if security is not None:
            V.valid_security(security, allow_open)
            if security == 'open':
                body['security.authentication-types'] = ''
            else:
                body['security.authentication-types'] = _AUTH[security]
        if passphrase is not None:
            if security == 'open':
                raise V.ValidationFailed('open Wi-Fi cannot have a passphrase')
            body['security.passphrase'] = V.valid_passphrase(passphrase)
        if enabled is not None:
            body['disabled'] = 'false' if enabled else 'true'
        if not body:
            raise V.ValidationFailed('nothing to change')
        if network_id not in {n.id for n in self.list_wifi()}:
            raise RouterError('unknown Wi-Fi interface id')
        self.rest.request('PATCH', f'{self._wifi_path}/{network_id}', body)
        if ssid is not None:                      # no commit-confirm in REST: verify by read-back
            now = {n.id: n for n in self.list_wifi()}.get(network_id)
            if now is None or now.ssid != ssid:
                raise RouterError('change was not reflected on the router (read-back mismatch)')
        return ApplyResult(True, True, 'applied and verified by read-back')

    # ------------------------------------------------------------------ clients
    def dhcp_leases(self):
        self.require(Capability.DHCP_LEASES)
        out = []
        for l in self.rest.request('GET', '/ip/dhcp-server/lease') or []:
            try:
                exp = parse_duration(l.get('expires-after'))
                out.append(Lease(mac=V.norm_mac(l['mac-address']), ip=V.norm_ip(l['address']),
                                 hostname=l.get('host-name', '') or '',
                                 expires_epoch=int(time.time()) + exp if exp is not None else None))
            except (KeyError, V.ValidationFailed):
                continue
        return out

    def list_clients(self):
        self.require(Capability.CLIENTS)
        by_mac = {}
        if Capability.DHCP_LEASES in self.capabilities():
            by_mac = {l.mac: l for l in self.dhcp_leases()}
        out = []
        for r in self.rest.request('GET', f'{self._wifi_path}/registration-table') or []:
            try:
                mac = V.norm_mac(r['mac-address'])
            except (KeyError, V.ValidationFailed):
                continue
            sig = None
            m = re.match(r'-?\d+', str(r.get('signal', '')))
            if m:
                sig = int(m.group(0))
            lease = by_mac.get(mac)
            out.append(Client(mac=mac, iface=r.get('interface', ''), signal_dbm=sig,
                              ip=lease.ip if lease else None,
                              hostname=(lease.hostname or None) if lease else None))
        return out

    # --------------------------------------------------------------- bandwidth
    def _resolve_ip(self, target):
        kind, val = V.target_kind(target)
        if kind == 'ip':
            return val
        lease = {l.mac: l for l in self.dhcp_leases()}.get(val)
        if lease is None:
            raise RouterError('no DHCP lease for that MAC; cannot resolve an IP to shape')
        return lease.ip

    @staticmethod
    def _qname(ip):
        return QUEUE_PREFIX + ip.replace('.', '-').replace(':', '-')

    def set_bandwidth_limit(self, target, down_kbps, up_kbps):
        self.require(Capability.BANDWIDTH)
        down, up = V.valid_kbps(down_kbps), V.valid_kbps(up_kbps)
        ip = self._resolve_ip(target)
        name = self._qname(ip)
        body = {'name': name, 'target': f'{ip}/32', 'max-limit': f'{up * 1000}/{down * 1000}',
                'comment': 'managed by UWZ gateway'}
        existing = self.rest.request('GET', f'/queue/simple?name={name}') or []
        if existing:
            self.rest.request('PATCH', f'/queue/simple/{existing[0][".id"]}',
                              {'target': body['target'], 'max-limit': body['max-limit']})
        else:
            self.rest.request('PUT', '/queue/simple', body)
        return name

    def remove_bandwidth_limit(self, target):
        self.require(Capability.BANDWIDTH)
        name = self._qname(self._resolve_ip(target))
        if not name.startswith(QUEUE_PREFIX):
            raise RouterError('refusing to touch a non-UWZ queue')
        existing = self.rest.request('GET', f'/queue/simple?name={name}') or []
        if not existing:
            return False
        self.rest.request('DELETE', f'/queue/simple/{existing[0][".id"]}')
        return True

    # ------------------------------------------------------------- diagnostics
    def ping(self, host, count=3):
        self.require(Capability.DIAGNOSTICS)
        host, count = V.valid_host(host), V.valid_count(count)
        res = self.rest.request('POST', '/ping', {'address': host, 'count': str(count)}) or []
        last = res[-1] if res else {}
        received = int(last.get('received', 0) or 0)
        return PingResult(host=host, reachable=received > 0,
                          summary=f'{received}/{last.get("sent", count)} replies'[:200])

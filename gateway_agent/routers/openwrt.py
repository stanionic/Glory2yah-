"""OpenWrt adapter (reference platform) over the documented ubus JSON-RPC API.

Needs on the router: uhttpd-mod-ubus + rpcd, and an rpcd ACL for the account
used here (least privilege: see docs/ROUTER_COMPATIBILITY.md). Credentials are
ALWAYS supplied explicitly; this module never tries default passwords.

Safety: Wi-Fi/DHCP changes use `uci apply` with a rollback timer and are only
confirmed after the router proves reachable. Otherwise OpenWrt reverts itself.
"""
import itertools
import json
import time

from .base import (ApplyResult, Capability, Client, Lease, PingResult, RouterAdapter,
                   RouterAuthError, RouterError, RouterInfo, RouterPermissionError,
                   UnsupportedOperation, WifiNetwork)
from .http import make_http
from . import validation as V

NULL_SESSION = '0' * 32
_ENC = {'wpa2': 'psk2+ccmp', 'wpa3': 'sae', 'wpa2/wpa3': 'sae-mixed', 'open': 'none'}
APPLY_TIMEOUT_S = 30


def _sec_from_enc(enc):
    enc = (enc or 'none').lower()
    if enc == 'none':
        return 'open'
    if enc.startswith('sae-mixed'):
        return 'wpa2/wpa3'
    if enc.startswith('sae'):
        return 'wpa3'
    if enc.startswith('psk2') or enc.startswith('psk-mixed'):
        return 'wpa2'
    return 'other'


class UbusClient:
    def __init__(self, url, username, password, http):
        self.url, self.username, self._password, self.http = url, username, password, http
        self.session = None
        self._ids = itertools.count(1)

    def _rpc(self, session, obj, method, args):
        body = json.dumps({'jsonrpc': '2.0', 'id': next(self._ids), 'method': 'call',
                           'params': [session, obj, method, args]}).encode()
        status, raw = self.http('POST', self.url, {'Content-Type': 'application/json'}, body)
        if status != 200:
            raise RouterError(f'ubus HTTP {status}')
        try:
            return json.loads(raw)
        except ValueError:
            raise RouterError('ubus returned invalid JSON')

    def login(self):
        r = self._rpc(NULL_SESSION, 'session', 'login',
                      {'username': self.username, 'password': self._password})
        res = r.get('result')
        if not res or res[0] != 0 or len(res) < 2 or 'ubus_rpc_session' not in res[1]:
            raise RouterAuthError('router login failed')   # never echo credentials
        self.session = res[1]['ubus_rpc_session']

    def call(self, obj, method, args=None, _retry=True):
        if self.session is None:
            self.login()
        r = self._rpc(self.session, obj, method, args or {})
        if 'error' in r:
            if r['error'].get('code') == -32002 and _retry:     # expired / denied session
                self.session = None
                return self.call(obj, method, args, _retry=False)
            raise RouterAuthError('router denied the session')
        res = r.get('result') or [9]
        code = res[0]
        if code == 0:
            return res[1] if len(res) > 1 else {}
        if code == 6:
            raise RouterPermissionError(f'permission denied for {obj}.{method} (check rpcd ACL)')
        if code == 8:
            raise UnsupportedOperation(f'{obj}.{method} not supported by this OpenWrt build')
        raise RouterError(f'ubus {obj}.{method} failed (status {code})')


class OpenWrtAdapter(RouterAdapter):
    kind = 'openwrt'
    vendor_label = 'OpenWrt'
    hardware_verified = False

    def __init__(self, host, username, password, *, port=None, scheme='https', http=None,
                 verify_tls=True, ca_file=None, timeout=10):
        super().__init__()
        if not username or not password:
            raise RouterAuthError('credentials are required (no defaults are ever tried)')
        if scheme not in ('https', 'http'):
            raise ValueError('scheme must be https or http')
        V.valid_host(host)
        netloc = f'{host}:{port}' if port else host
        self.ubus = UbusClient(f'{scheme}://{netloc}/ubus', username, password,
                               http or make_http(verify_tls, ca_file, timeout))

    # ------------------------------------------------------------ ubus helpers
    def _objects(self):
        u = self.ubus
        if u.session is None:
            u.login()
        body = json.dumps({'jsonrpc': '2.0', 'id': 0, 'method': 'list',
                           'params': [u.session, '*']}).encode()
        status, raw = u.http('POST', u.url, {'Content-Type': 'application/json'}, body)
        if status != 200:
            raise RouterError(f'ubus HTTP {status}')
        data = json.loads(raw)
        if 'error' in data:
            raise RouterPermissionError('cannot list ubus objects (check rpcd ACL)')
        return data.get('result') or {}

    def _uci_sections(self, config):
        vals = self.ubus.call('uci', 'get', {'config': config}).get('values', {})
        return vals

    # ---------------------------------------------------------------- identity
    def identify(self):
        board = self.ubus.call('system', 'board')
        info = self.ubus.call('system', 'info')
        rel = board.get('release', {})
        return RouterInfo(vendor='OpenWrt', model=board.get('model', 'unknown'),
                          firmware=rel.get('description') or rel.get('version', 'unknown'),
                          hostname=board.get('hostname', ''), uptime_s=info.get('uptime'))

    def _detect(self):
        objs = set(self._objects())
        caps = set()
        if 'system' in objs:
            caps.add(Capability.INFO)
        if 'uci' in objs:
            caps |= {Capability.WIFI_READ, Capability.WIFI_CONFIG, Capability.DHCP_CONFIG}
        if any(o.startswith('hostapd.') for o in objs):
            caps.add(Capability.CLIENTS)
        if 'luci-rpc' in objs:
            caps.add(Capability.DHCP_LEASES)
        if 'file' in objs:
            caps.add(Capability.DIAGNOSTICS)
        # Per-client bandwidth is NOT implemented for OpenWrt in this version.
        self._objs = objs
        return caps

    def guidance(self):
        return {'bandwidth': 'Per-client shaping on OpenWrt is not implemented in this '
                             'adapter; shape on the primary gateway (tc/nft) instead.',
                'documented_status': 'docs/ROUTER_COMPATIBILITY.md#openwrt'}

    # -------------------------------------------------------------------- wifi
    def list_wifi(self):
        self.require(Capability.WIFI_READ)
        out = []
        for name, sec in self._uci_sections('wireless').items():
            if sec.get('.type') == 'wifi-iface' and sec.get('mode', 'ap') == 'ap':
                out.append(WifiNetwork(id=name, ssid=sec.get('ssid', ''),
                                       security=_sec_from_enc(sec.get('encryption')),
                                       enabled=sec.get('disabled', '0') != '1'))
        return out

    def _safe_apply(self, config):
        """apply with rollback -> prove the router still answers -> confirm."""
        u = self.ubus
        try:
            u.call('uci', 'apply', {'rollback': True, 'timeout': APPLY_TIMEOUT_S})
        except UnsupportedOperation:
            u.call('uci', 'revert', {'config': config})
            raise UnsupportedOperation(
                'Safe apply (uci apply with rollback) needs OpenWrt 19.07 or newer; '
                'change refused instead of applying unsafely')
        try:
            self.identify()                     # still reachable after the change?
        except Exception as e:
            return ApplyResult(True, False,
                               f'applied but router unreachable ({type(e).__name__}); '
                               'NOT confirmed: OpenWrt will roll back automatically')
        u.call('uci', 'confirm', {})
        return ApplyResult(True, True, 'applied and confirmed')

    def configure_wifi(self, network_id, *, ssid=None, passphrase=None, security=None,
                       enabled=None, allow_open=False):
        self.require(Capability.WIFI_CONFIG)
        V.valid_section(network_id)
        sec = self._uci_sections('wireless').get(network_id)
        if not sec or sec.get('.type') != 'wifi-iface':
            raise RouterError('unknown Wi-Fi network id')
        if sec.get('mode', 'ap') != 'ap':
            raise RouterError('refusing to modify a non-AP interface (client/mesh)')
        values = {}
        if ssid is not None:
            values['ssid'] = V.valid_ssid(ssid)
        if security is not None:
            V.valid_security(security, allow_open)
            values['encryption'] = _ENC[security]
        if passphrase is not None:
            if security == 'open':
                raise V.ValidationFailed('open Wi-Fi cannot have a passphrase')
            values['key'] = V.valid_passphrase(passphrase)
        elif security not in (None, 'open') and _sec_from_enc(sec.get('encryption')) == 'open':
            raise V.ValidationFailed('a passphrase is required when enabling encryption')
        if enabled is not None:
            values['disabled'] = '0' if enabled else '1'
        if not values:
            raise V.ValidationFailed('nothing to change')
        self.ubus.call('uci', 'set', {'config': 'wireless', 'section': network_id,
                                      'values': values})
        return self._safe_apply('wireless')

    # ----------------------------------------------------------------- clients
    def dhcp_leases(self):
        self.require(Capability.DHCP_LEASES)
        res = self.ubus.call('luci-rpc', 'getDHCPLeases', {})
        out = []
        for l in res.get('dhcp_leases', []):
            try:
                out.append(Lease(mac=V.norm_mac(l['macaddr']), ip=V.norm_ip(l['ipaddr']),
                                 hostname=l.get('hostname', '') or '',
                                 expires_epoch=int(time.time()) + int(l.get('expires', 0))
                                 if l.get('expires') is not None else None))
            except (KeyError, V.ValidationFailed, ValueError):
                continue        # skip malformed rows rather than fail the whole listing
        return out

    def list_clients(self):
        self.require(Capability.CLIENTS)
        by_mac = {}
        if Capability.DHCP_LEASES in self.capabilities():
            by_mac = {l.mac: l for l in self.dhcp_leases()}
        out = []
        for obj in sorted(o for o in self._objs if o.startswith('hostapd.')):
            iface = obj.split('.', 1)[1]
            res = self.ubus.call(obj, 'get_clients', {})
            for mac, st in (res.get('clients') or {}).items():
                try:
                    mac = V.norm_mac(mac)
                except V.ValidationFailed:
                    continue
                if not st.get('assoc', True):
                    continue
                lease = by_mac.get(mac)
                out.append(Client(mac=mac, iface=iface, ip=lease.ip if lease else None,
                                  hostname=(lease.hostname or None) if lease else None))
        return out

    # -------------------------------------------------------------------- dhcp
    def configure_dhcp(self, section='lan', *, start=None, limit=None, lease_time_s=None):
        self.require(Capability.DHCP_CONFIG)
        V.valid_section(section)
        sec = self._uci_sections('dhcp').get(section)
        if not sec or sec.get('.type') != 'dhcp':
            raise RouterError('unknown DHCP section')
        values = {}
        if start is not None:
            if not isinstance(start, int) or not (2 <= start <= 253):
                raise V.ValidationFailed('start must be 2-253')
            values['start'] = str(start)
        if limit is not None:
            if not isinstance(limit, int) or not (1 <= limit <= 253):
                raise V.ValidationFailed('limit must be 1-253')
            values['limit'] = str(limit)
        if lease_time_s is not None:
            if not isinstance(lease_time_s, int) or not (120 <= lease_time_s <= 7 * 86400):
                raise V.ValidationFailed('lease time must be 120s-7d')
            values['leasetime'] = f'{lease_time_s}s'
        if not values:
            raise V.ValidationFailed('nothing to change')
        self.ubus.call('uci', 'set', {'config': 'dhcp', 'section': section, 'values': values})
        return self._safe_apply('dhcp')

    # ------------------------------------------------------------- diagnostics
    def ping(self, host, count=3):
        self.require(Capability.DIAGNOSTICS)
        host, count = V.valid_host(host), V.valid_count(count)
        # argv list, never a shell string: no injection surface.
        res = self.ubus.call('file', 'exec', {'command': '/bin/ping',
                                              'params': ['-c', str(count), '-W', '2', host]})
        ok = res.get('code') == 0
        tail = (res.get('stdout') or '').strip().splitlines()[-1:] or ['']
        return PingResult(host=host, reachable=ok, summary=tail[0][:200])

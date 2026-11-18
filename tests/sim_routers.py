"""SIMULATED routers for adapter tests. These model the documented APIs; they are
NOT real hardware, which is why every adapter reports hardware_verified=False."""
import base64
import copy
import json
import re


class FakeOpenWrt:
    def __init__(self, user='apiuser', password='correct-horse-battery', objects=None,
                 apply_supported=True, denied=()):
        self.user, self.password = user, password
        self.objects = objects if objects is not None else [
            'system', 'uci', 'hostapd.phy0-ap0', 'luci-rpc', 'file']
        self.apply_supported, self.denied = apply_supported, set(denied)
        self.sessions, self.calls, self.now = set(), [], 0
        self.break_after_apply = False
        self.broken = False
        self.pending = None
        self.uci = {
            'wireless': {
                'default_radio0': {'.type': 'wifi-iface', '.name': 'default_radio0',
                                   'mode': 'ap', 'ssid': 'OpenWrt', 'encryption': 'none',
                                   'device': 'radio0'},
                'sta0': {'.type': 'wifi-iface', '.name': 'sta0', 'mode': 'sta',
                         'ssid': 'Upstream', 'encryption': 'psk2'},
                'radio0': {'.type': 'wifi-device', '.name': 'radio0'}},
            'dhcp': {'lan': {'.type': 'dhcp', '.name': 'lan', 'start': '100',
                             'limit': '150', 'leasetime': '12h'}}}
        self.staged = {}
        self.clients = {'AA:BB:CC:00:00:01': {'assoc': True, 'authorized': True},
                        'AA:BB:CC:00:00:02': {'assoc': False},
                        'not-a-mac': {'assoc': True}}
        self.leases = [{'macaddr': 'aa:bb:cc:00:00:01', 'ipaddr': '192.168.1.50',
                        'hostname': 'phone', 'expires': 3000},
                       {'macaddr': 'garbage', 'ipaddr': '999.1.1.1'}]
        self.reachable = {'8.8.8.8', '192.168.1.1'}
        self.expire_next = False

    # ---- rollback timer
    def tick(self, seconds):
        self.now += seconds
        if self.pending and self.now - self.pending['t0'] >= self.pending['timeout']:
            self.uci = self.pending['snap']
            self.pending, self.broken = None, False

    # ---- HTTP entry point (matches the adapter's `http` callable)
    def http(self, method, url, headers, body):
        assert url.endswith('/ubus') and method == 'POST'
        req = json.loads(body)
        self.calls.append(req)
        if self.broken and req['method'] == 'call' and req['params'][1] != 'uci':
            return 500, b'router down'
        if req['method'] == 'list':
            if req['params'][0] not in self.sessions:
                return 200, json.dumps({'jsonrpc': '2.0', 'id': req['id'],
                                        'error': {'code': -32002, 'message': 'Access denied'}}).encode()
            return 200, json.dumps({'jsonrpc': '2.0', 'id': req['id'],
                                    'result': {o: {} for o in self.objects}}).encode()
        sess, obj, meth, args = req['params']
        return 200, json.dumps({'jsonrpc': '2.0', 'id': req['id'],
                                'result': self._call(sess, obj, meth, args)}
                               if not self._need_login(sess, obj, meth)
                               else {'jsonrpc': '2.0', 'id': req['id'],
                                     'error': {'code': -32002, 'message': 'Access denied'}}).encode()

    def _need_login(self, sess, obj, meth):
        if (obj, meth) == ('session', 'login'):
            return False
        if self.expire_next:
            self.expire_next, self.sessions = False, set()
        return sess not in self.sessions

    def _call(self, sess, obj, meth, args):
        if (obj, meth) == ('session', 'login'):
            if args.get('username') == self.user and args.get('password') == self.password:
                tok = f'sess{len(self.sessions) + 1:028d}'
                self.sessions.add(tok)
                return [0, {'ubus_rpc_session': tok}]
            return [6]
        if obj in self.denied:
            return [6]
        if obj == 'system' and meth == 'board':
            return [0, {'hostname': 'ap-1', 'model': 'Sim Router v1',
                        'release': {'description': 'OpenWrt 23.05.3 r23809'}}]
        if obj == 'system' and meth == 'info':
            return [0, {'uptime': 12345}]
        if obj == 'uci':
            return self._uci(meth, args)
        if obj.startswith('hostapd.') and meth == 'get_clients':
            return [0, {'freq': 2412, 'clients': self.clients}]
        if obj == 'luci-rpc' and meth == 'getDHCPLeases':
            return [0, {'dhcp_leases': self.leases}]
        if obj == 'file' and meth == 'exec':
            host = args['params'][-1]
            return [0, {'code': 0 if host in self.reachable else 1,
                        'stdout': '3 packets transmitted, 3 received, 0% packet loss'}]
        return [4]

    def _uci(self, meth, a):
        if meth == 'get':
            return [0, {'values': copy.deepcopy(self.uci[a['config']])}]
        if meth == 'set':
            self.staged.setdefault(a['config'], {}).setdefault(a['section'], {}).update(a['values'])
            return [0, {}]
        if meth == 'revert':
            self.staged.pop(a['config'], None)
            return [0, {}]
        if meth == 'apply':
            if not self.apply_supported:
                return [8]
            snap = copy.deepcopy(self.uci)
            for cfg, secs in self.staged.items():
                for name, vals in secs.items():
                    self.uci[cfg][name].update(vals)
            self.staged = {}
            self.pending = {'snap': snap, 't0': self.now, 'timeout': a.get('timeout', 30)}
            self.broken = self.break_after_apply
            return [0, {}]
        if meth == 'confirm':
            self.pending = None
            return [0, {}]
        return [8]

    def sets(self):
        return [c for c in self.calls if c['method'] == 'call' and c['params'][1:3] == ['uci', 'set']]


class FakeRouterOS:
    def __init__(self, user='api', password='mt-secret-pass', version='7.14.3 (stable)',
                 legacy_wireless=False, ignore_patch=False):
        self.auth = 'Basic ' + base64.b64encode(f'{user}:{password}'.encode()).decode()
        self.resource = {'board-name': 'hAP ax2', 'version': version, 'uptime': '1d2h3m4s'}
        self.legacy, self.ignore_patch = legacy_wireless, ignore_patch
        self.wifi = [{'.id': '*1', 'name': 'wifi1', 'configuration.ssid': 'MT-Guest',
                      'security.authentication-types': 'wpa2-psk', 'disabled': 'false'}]
        self.legacy_if = [{'.id': '*A', 'name': 'wlan1', 'ssid': 'OldNet', 'disabled': 'false'}]
        self.reg = [{'mac-address': 'AA:BB:CC:00:00:01', 'interface': 'wifi1', 'signal': '-55'}]
        self.leases = [{'mac-address': 'AA:BB:CC:00:00:01', 'address': '10.0.0.20',
                        'host-name': 'phone', 'expires-after': '9m30s'}]
        self.queues = [{'.id': '*Q0', 'name': 'admin-queue', 'target': '10.9.9.9/32',
                        'max-limit': '1000000/1000000'}]
        self.calls, self._n = [], 0

    def http(self, method, url, headers, body):
        self.calls.append((method, url, body))
        if headers.get('Authorization') != self.auth:
            return 401, json.dumps({'error': 401, 'message': 'Unauthorized'}).encode()
        path = url.split('/rest', 1)[1]
        pure, _, query = path.partition('?')
        data = json.loads(body) if body else None
        ok = lambda x: (200, json.dumps(x).encode())
        bad = lambda: (400, json.dumps({'error': 400, 'message': 'no such command'}).encode())
        if pure == '/system/resource':
            return ok(self.resource)
        if pure == '/system/identity':
            return ok({'name': 'mt-1'})
        if pure == '/interface/wifi':
            return bad() if self.legacy else ok(self.wifi)
        if pure == '/interface/wifi/registration-table':
            return bad() if self.legacy else ok(self.reg)
        if pure == '/interface/wireless':
            return ok(self.legacy_if) if self.legacy else bad()
        if pure == '/interface/wireless/registration-table':
            return ok(self.reg) if self.legacy else bad()
        if pure.startswith('/interface/wifi/') and method == 'PATCH':
            if not self.ignore_patch:
                for it in self.wifi:
                    if it['.id'] == pure.rsplit('/', 1)[1]:
                        it.update(data)
            return ok({})
        if pure == '/ip/dhcp-server/lease':
            return ok(self.leases)
        if pure == '/queue/simple':
            if method == 'GET':
                name = dict(p.split('=') for p in query.split('&') if p).get('name')
                return ok([q for q in self.queues if not name or q['name'] == name])
            if method == 'PUT':
                self._n += 1
                self.queues.append(dict(data, **{'.id': f'*N{self._n}'}))
                return ok({'ret': f'*N{self._n}'})
        if pure.startswith('/queue/simple/'):
            qid = pure.rsplit('/', 1)[1]
            if method == 'PATCH':
                [q.update(data) for q in self.queues if q['.id'] == qid]
                return ok({})
            if method == 'DELETE':
                self.queues = [q for q in self.queues if q['.id'] != qid]
                return ok({})
        if pure == '/ping' and method == 'POST':
            n = int(data['count'])
            return ok([{'sent': str(i + 1), 'received': str(i + 1)} for i in range(n)])
        return bad()

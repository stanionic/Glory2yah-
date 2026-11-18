"""Phase 5: router adapters (against SIMULATED routers) + cloud router inventory."""
import inspect
import json
import logging
import os
import sys
import uuid

import pytest

os.environ.setdefault('FLASK_ENV', 'testing')
os.environ.setdefault('SECRET_KEY', 'uwz-tests-secret')
os.environ.setdefault('WTF_CSRF_ENABLED', 'False')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for p in (ROOT, os.path.join(ROOT, 'tests')):
    if p not in sys.path:
        sys.path.insert(0, p)

from sim_routers import FakeOpenWrt, FakeRouterOS
from gateway_agent.routers import (ADAPTERS, Capability, RouterAuthError, RouterError,
                                   RouterPermissionError, UnsupportedOperation,
                                   ValidationFailed, create_adapter, discover, inventory,
                                   load_routers)
from gateway_agent.routers.mikrotik import MikroTikAdapter, parse_duration
from gateway_agent.routers.openwrt import OpenWrtAdapter
from gateway_agent.routers.unsupported import TPLinkAdapter, GenericAdapter

PASS_OW, PASS_MT = 'correct-horse-battery', 'mt-secret-pass'
WIFI_PW = 'My-Wifi-Passphrase-42'


def ow(sim=None, **kw):
    sim = sim or FakeOpenWrt()
    return OpenWrtAdapter('192.168.1.1', sim.user, PASS_OW, http=sim.http, **kw), sim


def mt(sim=None):
    sim = sim or FakeRouterOS()
    return MikroTikAdapter('10.0.0.1', 'api', PASS_MT, http=sim.http), sim


# ================================ OpenWrt ===================================
def test_openwrt_identify_and_capability_detection():
    a, sim = ow()
    info = a.identify()
    assert info.vendor == 'OpenWrt' and info.model == 'Sim Router v1' and info.uptime_s == 12345
    caps = a.capabilities()
    assert {Capability.INFO, Capability.WIFI_CONFIG, Capability.CLIENTS,
            Capability.DHCP_LEASES, Capability.DIAGNOSTICS} <= caps
    assert Capability.BANDWIDTH not in caps            # never claimed for OpenWrt here
    with pytest.raises(UnsupportedOperation) as e:
        a.set_bandwidth_limit('192.168.1.50', 1000, 500)
    assert 'bandwidth' in e.value.guidance


def test_openwrt_capabilities_follow_what_the_router_actually_exposes():
    a, _ = ow(FakeOpenWrt(objects=['system', 'uci']))
    caps = a.capabilities()
    assert Capability.CLIENTS not in caps and Capability.DHCP_LEASES not in caps
    assert Capability.DIAGNOSTICS not in caps
    with pytest.raises(UnsupportedOperation):
        a.list_clients()
    with pytest.raises(UnsupportedOperation):
        a.ping('8.8.8.8')


def test_no_default_credentials_anywhere():
    for cls in (OpenWrtAdapter, MikroTikAdapter):
        sig = inspect.signature(cls.__init__).parameters
        assert sig['username'].default is inspect.Parameter.empty
        assert sig['password'].default is inspect.Parameter.empty
        with pytest.raises(RouterAuthError):
            cls('192.168.1.1', '', '')
    sim = FakeOpenWrt()
    for guess in ('admin', 'root', 'password', ''):
        bad = OpenWrtAdapter('192.168.1.1', 'root', guess or 'x', http=sim.http)
        with pytest.raises(RouterAuthError):
            bad.identify()


def test_login_failure_never_echoes_credentials():
    sim = FakeOpenWrt()
    a = OpenWrtAdapter('192.168.1.1', 'apiuser', 'wrong-password-123', http=sim.http)
    with pytest.raises(RouterAuthError) as e:
        a.identify()
    assert 'wrong-password-123' not in str(e.value)


def test_openwrt_lists_only_ap_interfaces_with_security_mapping():
    a, _ = ow()
    nets = a.list_wifi()
    assert [n.id for n in nets] == ['default_radio0']          # sta + radio excluded
    assert nets[0].security == 'open' and nets[0].enabled


def test_openwrt_configure_wifi_applies_with_rollback_and_confirms():
    a, sim = ow()
    r = a.configure_wifi('default_radio0', ssid='Glory2Yah WiFi', passphrase=WIFI_PW,
                         security='wpa2')
    assert r.applied and r.confirmed and sim.pending is None
    sec = sim.uci['wireless']['default_radio0']
    assert (sec['ssid'], sec['encryption'], sec['key']) == ('Glory2Yah WiFi', 'psk2+ccmp', WIFI_PW)
    apply_call = [c for c in sim.calls if c['method'] == 'call' and c['params'][2] == 'apply'][0]
    assert apply_call['params'][3] == {'rollback': True, 'timeout': 30}
    assert a.list_wifi()[0].security == 'wpa2'


def test_openwrt_bad_config_is_not_confirmed_and_router_rolls_itself_back():
    a, sim = ow()
    sim.break_after_apply = True                    # the change knocks the router offline
    r = a.configure_wifi('default_radio0', ssid='Broken', passphrase=WIFI_PW, security='wpa2')
    assert r.applied and not r.confirmed and sim.pending is not None
    assert not any(c['params'][2] == 'confirm' for c in sim.calls if c['method'] == 'call')
    sim.tick(31)                                    # rollback timer expires
    assert sim.uci['wireless']['default_radio0']['ssid'] == 'OpenWrt'
    assert sim.uci['wireless']['default_radio0']['encryption'] == 'none'


def test_openwrt_old_firmware_without_safe_apply_refuses_instead_of_applying_blind():
    a, sim = ow(FakeOpenWrt(apply_supported=False))
    with pytest.raises(UnsupportedOperation) as e:
        a.configure_wifi('default_radio0', ssid='NoRollback', passphrase=WIFI_PW, security='wpa2')
    assert '19.07' in str(e.value)
    assert sim.uci['wireless']['default_radio0']['ssid'] == 'OpenWrt' and sim.staged == {}


@pytest.mark.parametrize('kw', [
    dict(ssid='x' * 33), dict(ssid=''), dict(ssid='bad\x00name'),
    dict(security='wpa2', passphrase='short'), dict(security='wpa2', passphrase='é' * 12),
    dict(security='open'),                                        # needs allow_open
    dict(security='open', allow_open=True, passphrase=WIFI_PW),   # open + key is nonsense
    dict(security='wpa2'),                                        # encrypting an open net w/o key
    dict(security='wep'), dict(),
])
def test_openwrt_invalid_wifi_input_is_refused_before_touching_the_router(kw):
    a, sim = ow()
    with pytest.raises(ValidationFailed):
        a.configure_wifi('default_radio0', **kw)
    assert sim.sets() == [] and sim.staged == {}


def test_openwrt_refuses_non_ap_and_unknown_sections():
    a, sim = ow()
    with pytest.raises(RouterError):
        a.configure_wifi('sta0', ssid='Hijack')               # client/mesh uplink: never touched
    with pytest.raises(RouterError):
        a.configure_wifi('radio0', ssid='NotAnIface')
    with pytest.raises(ValidationFailed):
        a.configure_wifi('default_radio0; reboot', ssid='X')
    assert sim.sets() == []


def test_open_wifi_allowed_only_when_explicit():
    a, sim = ow()
    a.configure_wifi('default_radio0', ssid='Free WiFi', security='open', allow_open=True)
    assert sim.uci['wireless']['default_radio0']['encryption'] == 'none'


def test_wifi_passphrase_never_leaks_into_errors_or_logs(caplog):
    caplog.set_level(logging.DEBUG)
    a, sim = ow(FakeOpenWrt(apply_supported=False))
    with pytest.raises(UnsupportedOperation) as e:
        a.configure_wifi('default_radio0', ssid='Leaky', passphrase=WIFI_PW, security='wpa2')
    assert WIFI_PW not in str(e.value) and WIFI_PW not in repr(e.value)
    assert WIFI_PW not in caplog.text
    assert WIFI_PW not in repr(a.ubus.__dict__.get('url', '')) and PASS_OW not in repr(a.list_wifi())


def test_openwrt_session_expiry_triggers_one_transparent_relogin():
    a, sim = ow()
    a.identify()
    sim.expire_next = True
    assert a.identify().model == 'Sim Router v1'
    assert len([c for c in sim.calls if c['params'][1:3] == ['session', 'login']]) == 2


def test_openwrt_acl_denial_is_a_clear_permission_error():
    a, _ = ow(FakeOpenWrt(denied=['luci-rpc']))
    a.capabilities()
    with pytest.raises(RouterPermissionError) as e:
        a.dhcp_leases()
    assert 'ACL' in str(e.value)


def test_openwrt_clients_join_leases_and_skip_bad_rows():
    a, _ = ow()
    cl = a.list_clients()
    assert [c.mac for c in cl] == ['aa:bb:cc:00:00:01']            # not-a-mac + disassociated dropped
    assert cl[0].ip == '192.168.1.50' and cl[0].hostname == 'phone' and cl[0].iface == 'phy0-ap0'
    assert [l.mac for l in a.dhcp_leases()] == ['aa:bb:cc:00:00:01']


def test_openwrt_dhcp_config_validated_and_applied_safely():
    a, sim = ow()
    r = a.configure_dhcp('lan', start=50, limit=100, lease_time_s=3600)
    assert r.confirmed
    assert sim.uci['dhcp']['lan'] | {} and sim.uci['dhcp']['lan']['leasetime'] == '3600s'
    for bad in (dict(start=1), dict(start=254), dict(limit=0), dict(lease_time_s=5), dict()):
        with pytest.raises(ValidationFailed):
            a.configure_dhcp('lan', **bad)
    with pytest.raises(RouterError):
        a.configure_dhcp('wan6', start=10)


def test_openwrt_ping_uses_argv_and_rejects_injection():
    a, sim = ow()
    assert a.ping('8.8.8.8', 3).reachable and not a.ping('1.2.3.4').reachable
    ex = [c for c in sim.calls if c['method'] == 'call' and c['params'][1:3] == ['file', 'exec']][0]
    assert isinstance(ex['params'][3]['params'], list) and ex['params'][3]['command'] == '/bin/ping'
    n = len(sim.calls)
    for evil in ('8.8.8.8; reboot', '$(id)', '8.8.8.8 -f', 'a b', '`x`', '', '-c1'):
        with pytest.raises(ValidationFailed):
            a.ping(evil)
    with pytest.raises(ValidationFailed):
        a.ping('8.8.8.8', 11)
    assert len(sim.calls) == n                                   # nothing reached the router


# ================================ MikroTik ==================================
def test_mikrotik_identify_and_capabilities():
    a, _ = mt()
    info = a.identify()
    assert info.vendor == 'MikroTik' and info.model == 'hAP ax2' and info.uptime_s == 93784
    assert {Capability.WIFI_CONFIG, Capability.CLIENTS, Capability.DHCP_LEASES,
            Capability.BANDWIDTH, Capability.DIAGNOSTICS} <= a.capabilities()
    assert parse_duration('1w2d3h4m5s') == 604800 + 172800 + 10800 + 240 + 5
    assert parse_duration('') is None


def test_mikrotik_old_routeros_is_unsupported_with_guidance():
    a, _ = mt(FakeRouterOS(version='6.49.10 (long-term)'))
    with pytest.raises(UnsupportedOperation) as e:
        a.identify()
    assert 'REST' in str(e.value) and e.value.guidance


def test_mikrotik_bad_credentials_rejected_without_echo():
    sim = FakeRouterOS()
    a = MikroTikAdapter('10.0.0.1', 'api', 'nope-nope-nope', http=sim.http)
    with pytest.raises(RouterAuthError) as e:
        a.identify()
    assert 'nope-nope-nope' not in str(e.value)


def test_mikrotik_legacy_wireless_is_read_only_with_manual_guidance():
    a, _ = mt(FakeRouterOS(legacy_wireless=True))
    caps = a.capabilities()
    assert Capability.WIFI_READ in caps and Capability.WIFI_CONFIG not in caps
    assert a.list_wifi()[0].ssid == 'OldNet'
    with pytest.raises(UnsupportedOperation) as e:
        a.configure_wifi('*A', ssid='NewName')
    assert 'legacy_wireless' in e.value.guidance


def test_mikrotik_configure_wifi_patches_and_verifies_by_readback():
    a, sim = mt()
    r = a.configure_wifi('*1', ssid='Glory2Yah WiFi', passphrase=WIFI_PW, security='wpa2/wpa3')
    assert r.confirmed
    it = sim.wifi[0]
    assert it['configuration.ssid'] == 'Glory2Yah WiFi'
    assert it['security.authentication-types'] == 'wpa2-psk,wpa3-psk'
    assert a.list_wifi()[0].security == 'wpa2/wpa3'
    for bad in ('wifi1', '*', '*1;x', '1'):
        with pytest.raises(ValidationFailed):
            a.configure_wifi(bad, ssid='X')
    with pytest.raises(RouterError):
        a.configure_wifi('*FF', ssid='Ghost')
    with pytest.raises(ValidationFailed):
        a.configure_wifi('*1', security='wpa2', passphrase='tiny')


def test_mikrotik_detects_change_that_did_not_take_effect():
    a, _ = mt(FakeRouterOS(ignore_patch=True))
    with pytest.raises(RouterError) as e:
        a.configure_wifi('*1', ssid='Not Applied')
    assert 'read-back' in str(e.value)


def test_mikrotik_clients_signal_and_lease_join():
    a, _ = mt()
    c = a.list_clients()[0]
    assert (c.mac, c.ip, c.hostname, c.signal_dbm, c.iface) == (
        'aa:bb:cc:00:00:01', '10.0.0.20', 'phone', -55, 'wifi1')


def test_mikrotik_bandwidth_is_idempotent_and_only_touches_uwz_queues():
    a, sim = mt()
    name = a.set_bandwidth_limit('AA:BB:CC:00:00:01', down_kbps=5000, up_kbps=1000)
    assert name == 'uwz-10-0-0-20'
    q = [x for x in sim.queues if x['name'] == name]
    assert len(q) == 1 and q[0]['max-limit'] == '1000000/5000000' and q[0]['target'] == '10.0.0.20/32'
    a.set_bandwidth_limit('10.0.0.20', 8000, 2000)                 # same client, by IP: update
    q = [x for x in sim.queues if x['name'] == name]
    assert len(q) == 1 and q[0]['max-limit'] == '2000000/8000000'
    assert a.remove_bandwidth_limit('10.0.0.20') is True
    assert a.remove_bandwidth_limit('10.0.0.20') is False
    assert [x['name'] for x in sim.queues] == ['admin-queue']      # admin queue untouched
    assert not any(c[0] == 'DELETE' and '*Q0' in c[1] for c in sim.calls)


def test_mikrotik_bandwidth_validation():
    a, sim = mt()
    for down, up in ((10, 1000), (1000, 10), (2_000_000, 1000), (True, 1000), ('9', 1000)):
        with pytest.raises(ValidationFailed):
            a.set_bandwidth_limit('10.0.0.20', down, up)
    with pytest.raises(RouterError):
        a.set_bandwidth_limit('AA:BB:CC:99:99:99', 1000, 1000)     # no lease: cannot resolve
    with pytest.raises(ValidationFailed):
        a.set_bandwidth_limit('not-a-target', 1000, 1000)
    assert [x['name'] for x in sim.queues] == ['admin-queue']


def test_mikrotik_ping():
    a, _ = mt()
    r = a.ping('8.8.8.8', 3)
    assert r.reachable and '3/3' in r.summary
    with pytest.raises(ValidationFailed):
        a.ping('8.8.8.8; /system reboot')


# ======================= unsupported vendors / generic =======================
@pytest.mark.parametrize('kind', ['tplink', 'tenda', 'dlink', 'asus', 'generic'])
def test_unsupported_vendors_are_honest_and_offer_real_options(kind):
    a = create_adapter(kind, '192.168.0.1')
    assert a.support_level == 'unsupported' and a.hardware_verified is False
    assert a.identify().model == 'unknown'
    with pytest.raises(UnsupportedOperation) as e:
        a.configure_wifi('x', ssid='Nope')
    g = e.value.guidance
    assert {'openwrt_firmware', 'access_point_mode', 'manual_instructions'} <= set(g)
    assert 'Table of Hardware' in g['openwrt_firmware']
    with pytest.raises(UnsupportedOperation):
        a.list_clients()


def test_generic_only_offers_reachability():
    assert GenericAdapter('192.168.0.1').capabilities() == {Capability.DIAGNOSTICS}
    assert TPLinkAdapter('192.168.0.1').capabilities() == set()


def test_registry_lists_all_documented_adapters():
    assert set(ADAPTERS) == {'openwrt', 'mikrotik', 'tplink', 'tenda', 'dlink', 'asus', 'generic'}
    with pytest.raises(ValueError):
        create_adapter('huawei', '1.2.3.4')


# ============================ config loading / inventory =====================
def test_load_routers_takes_passwords_only_from_env_and_isolates_failures():
    sim_ow, sim_mt = FakeOpenWrt(), FakeRouterOS()
    cfg = [
        {'ref': 'ap1', 'kind': 'openwrt', 'host': '192.168.1.1', 'username': 'apiuser',
         'password_env': 'UWZ_AP1_PASS'},
        {'ref': 'ap2', 'kind': 'mikrotik', 'host': '10.0.0.1', 'username': 'api',
         'password_env': 'UWZ_AP2_PASS'},
        {'ref': 'bad-inline', 'kind': 'openwrt', 'host': '1.1.1.1', 'username': 'u',
         'password': 'inline-secret'},
        {'ref': 'no-env', 'kind': 'openwrt', 'host': '1.1.1.2', 'username': 'u',
         'password_env': 'UWZ_MISSING'},
        {'ref': 'ap1', 'kind': 'generic', 'host': '1.1.1.3'},
        {'ref': 'bad ref!', 'kind': 'generic', 'host': '1.1.1.4'},
        {'ref': 'tp', 'kind': 'tplink', 'host': '192.168.0.2'},
    ]
    sims = {'192.168.1.1': sim_ow, '10.0.0.1': sim_mt}
    ads, errs = load_routers(cfg, {'UWZ_AP1_PASS': PASS_OW, 'UWZ_AP2_PASS': PASS_MT},
                             http_factory=lambda e: (sims[e['host']].http if e['host'] in sims else None))
    assert set(ads) == {'ap1', 'ap2', 'tp'}
    assert 'inline' in errs['bad-inline'] and 'UWZ_MISSING' in errs['no-env']
    assert 'duplicate' in errs['ap1'] and 'invalid ref' in errs['bad ref!']
    assert 'inline-secret' not in json.dumps(errs)


def test_inventory_has_no_secrets_and_reports_honest_status():
    a_ow, _ = ow()
    a_mt, _ = mt()
    down = OpenWrtAdapter('192.168.1.9', 'apiuser', PASS_OW,
                          http=lambda *a, **k: (_ for _ in ()).throw(
                              __import__('gateway_agent.routers', fromlist=['x']).RouterConnectionError('down')))
    inv = inventory({'ap1': a_ow, 'mt1': a_mt, 'old': down, 'tp': TPLinkAdapter('192.168.0.2')},
                    {'broken': 'inline "password" refused'})
    by = {i['ref']: i for i in inv}
    assert by['ap1']['status'] == 'ONLINE' and by['mt1']['status'] == 'ONLINE'
    assert by['old']['status'] == 'OFFLINE' and by['old']['error']
    assert by['tp']['status'] == 'UNSUPPORTED' and by['broken']['status'] == 'OFFLINE'
    assert all(i['hardware_verified'] is False for i in inv)
    blob = json.dumps(inv)
    for secret in (PASS_OW, PASS_MT, 'apiuser'):
        assert secret not in blob


def test_discover_is_a_passive_fingerprint_and_never_logs_in():
    seen = []

    def http_openwrt(method, url, headers, body):
        seen.append((method, url))
        return (200, b'{"jsonrpc":"2.0","error":{"code":-32002}}') if url.endswith('/ubus') else (404, b'')

    def http_mt(method, url, headers, body):
        seen.append((method, url))
        return (401, b'{"error":401}') if '/rest/' in url else (404, b'')

    assert discover('1.1.1.1', http_openwrt) == 'openwrt'
    assert discover('1.1.1.1', http_mt) == 'mikrotik'
    assert discover('1.1.1.1', lambda *a: (404, b'')) == 'generic'
    assert not any('login' in str(s) for s in seen)

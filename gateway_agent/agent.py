"""Gateway agent core: enroll, heartbeat, and resilient event synchronization."""
import os
import time

from . import __version__, keys
from .client import CloudClient, CloudRejected, CloudUnreachable
from .license import LicenseManager
from .portal.engine import VoucherEngine
from .routers import inventory
from .timeguard import TrustedClock
from .store import PENDING, REJECTED, SYNCED, Store

BATCH = 100


class GatewayAgent:
    def __init__(self, data_dir, cloud_url, transport=None, now_fn=time.time, portal_url=None,
                 clock=None):
        os.makedirs(data_dir, mode=0o700, exist_ok=True)
        self.store = Store(os.path.join(data_dir, 'gateway.db'))
        self.key = keys.load_or_create(data_dir)
        self.client = CloudClient(cloud_url, self.key, self.store.get('gateway_uid'),
                                  transport=transport, now_fn=now_fn)
        self.now_fn = now_fn
        self.routers, self.router_errors = {}, {}
        # Trusted time (cloud-anchored + monotonic) drives expiry; the wall clock only signs requests.
        self.clock = clock or TrustedClock(self.store, wall=now_fn)
        self.engine = VoucherEngine(self.store, self.clock.now)
        self.license = LicenseManager(self.store, self.clock)
        self.engine.license = self.license
        self.portal_url = portal_url          # LAN URL of this gateway's portal, shown to the cloud
        self.store.set('cloud_base_url', self.client.base_url)

    @property
    def enrolled(self):
        return bool(self.store.get('gateway_uid'))

    def enroll(self, token):
        out = self.client.enroll(token, keys.public_b64(self.key), __version__)
        self.store.set('gateway_uid', out['gateway_uid'])
        self.store.set('vendor_uid', out['vendor_uid'])
        self.store.set('cloud_public_key', out['cloud_public_key'])   # for licenses (Phase 8)
        self.client.gateway_uid = out['gateway_uid']
        return out

    def _clock_brief(self):
        st = self.clock.status()
        return {'skew_s': st['skew_s'], 'rollbacks': st['rollbacks']}

    def _sync_trust(self, hb):
        """Install the signed license, re-anchor trusted time on the cloud, log anomalies."""
        lic = hb.get('license')
        if lic:
            ok, why = self.license.install(lic)
            if not ok:
                self.store.set('last_error', f'license rejected: {why}')
        epoch = hb.get('server_epoch')
        # refuse a stale/replayed response: it cannot be earlier than a signed issue time
        if isinstance(epoch, int) and epoch >= self.clock.floor - 600:
            self.clock.sync_with_cloud(epoch)
        self.store.set('last_cloud_ok_epoch', int(self.clock.now()))
        self._report_clock_anomalies()

    def _report_clock_anomalies(self):
        for a in self.clock.observe():
            self.record_event('gateway.event', a)

    def set_routers(self, adapters, errors=None):
        self.routers, self.router_errors = adapters, errors or {}

    def report_routers(self):
        """Send the router inventory (no credentials). Best-effort; offline is fine."""
        if not self.routers and not self.router_errors:
            return None
        inv = inventory(self.routers, self.router_errors)
        self.store.set('router_inventory', inv)           # local copy works offline too
        self.client.report_routers(inv)
        return len(inv)

    def sync_policy(self):
        """Pull packages/vouchers/portal config (paginated) into the local engine."""
        cursor, pages = 0, 0
        while pages < 100:
            pol = self.client.sync_policy(cursor)
            self.engine.sync_from_cloud(pol)
            cursor, pages = pol.get('next_cursor'), pages + 1
            if not cursor:
                break
        return pages

    def maintain(self, access=None, usage=None):
        """Local housekeeping that needs NO network: data-quota enforcement from usage
        counters, session expiry, and queuing usage reports for the next sync."""
        self._report_clock_anomalies()                  # even offline: detect and queue tampering
        exhausted = []
        if usage is not None:
            exhausted = self.engine.record_usage(usage.read())
        devices = self.engine.expire_due() + exhausted
        self.engine.flush_usage()
        if access:
            for mac in dict.fromkeys(devices):
                try:
                    access.deauthorize(mac)
                except Exception as e:          # keep going: one bad device must not block others
                    self.store.set('last_error', f'deauthorize failed: {type(e).__name__}')
        return devices

    def record_event(self, type_, payload):
        """Local operation producing a sync event. Works with no network at all."""
        return self.store.enqueue(type_, payload)

    def status(self):
        return {'enrolled': self.enrolled, 'gateway_uid': self.store.get('gateway_uid'),
                'pending_events': self.store.count(PENDING),
                'rejected_events': self.store.count(REJECTED),
                'last_cloud_ok_epoch': self.store.get('last_cloud_ok_epoch'),
                'cloud_clock_offset_s': self.store.get('cloud_clock_offset_s'),
                'access': self.store.get('access'),
                'license': self.license.state(), 'clock': self.clock.status(),
                'revoked': self.store.get('revoked', False)}

    def run_once(self):
        """One sync cycle. NEVER raises on network failure: offline is normal."""
        if not self.enrolled:
            return {'online': False, 'error': 'not enrolled'}
        try:
            hb = self.client.heartbeat(self.portal_url, self._clock_brief())
        except CloudUnreachable as e:
            self.store.set('last_error', str(e)[:200])
            return {'online': False, 'pending': self.store.count(PENDING)}
        except CloudRejected as e:
            if e.status == 403:
                self.store.set('revoked', True)     # stop trying; admin action needed
            self.store.set('last_error', str(e)[:200])
            return {'online': True, 'authorized': False, 'error': str(e)}
        self.store.set('revoked', False)
        self._sync_trust(hb)
        # Cloud clock vs device clock, kept for rollback/tamper checks (Phase 8).
        self.store.set('cloud_clock_offset_s', hb['server_epoch'] - int(self.now_fn()))
        self.store.set('access', hb['access'])
        try:
            self.report_routers()
        except (CloudUnreachable, CloudRejected) as e:
            self.store.set('last_error', str(e)[:200])
        try:
            self.sync_policy()
        except (CloudUnreachable, CloudRejected) as e:
            self.store.set('last_error', str(e)[:200])
        sent = rejected = 0
        while True:
            batch = self.store.pending(BATCH)
            if not batch:
                break
            ids = [e['event_id'] for e in batch]
            try:
                res = self.client.sync(batch)
            except CloudUnreachable as e:
                self.store.bump_attempts(ids, str(e))
                break
            except CloudRejected as e:
                self.store.bump_attempts(ids, str(e))
                break
            # Mark synced ONLY what the cloud acknowledged. A crash before this
            # line just means a harmless re-send (the cloud de-duplicates).
            bad = {r['event_id']: r['reason'] for r in res.get('rejected', []) if r.get('event_id')}
            ok = [i for i in res.get('acked', []) if i in ids]
            self.store.mark(ok, SYNCED)
            for eid, reason in bad.items():
                self.store.mark([eid], REJECTED, reason)
            sent += len(ok)
            rejected += len(bad)
            if not ok and not bad:
                break   # no progress: avoid a hot loop
        return {'online': True, 'authorized': True, 'synced': sent, 'rejected': rejected,
                'pending': self.store.count(PENDING), 'access': hb['access']}

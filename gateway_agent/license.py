"""Offline subscription license: signed by the cloud, verified here with the PUBLIC key.

Payload (Ed25519-signed, same envelope as tickets):
  v, k='license', lid, vendor, gw, iat, trial_exp, sub_exp, eff (latest end),
  grace (days), status (ACTIVE | SUSPENDED)

State (computed with the TRUSTED clock, never the wall clock):
  ACTIVE          now < eff                      new sales allowed
  GRACE           now < eff + grace days         new sales allowed (offline tolerance)
  EXPIRED         later / no plan                NO new activations; paid sessions continue
  SUSPENDED       explicit cloud suspension      NO new activations; paid sessions continue
  UNTRUSTED_CLOCK clock rolled back since sync   NO new activations until the next cloud sync
Local administration and history are never removed in any state.
"""
import base64
import json
import re

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

_LID = re.compile(r'^lc_[0-9a-f]{16}$')


def _b64u_decode(s):
    return base64.urlsafe_b64decode(s + '=' * (-len(s) % 4))


class LicenseManager:
    def __init__(self, store, clock):
        self.store, self.clock = store, clock

    def _verify(self, token):
        try:
            if not isinstance(token, str) or len(token) > 2048 or token.count('.') != 1:
                return None
            body, sig = token.split('.')
            Ed25519PublicKey.from_public_bytes(base64.b64decode(self.store.get('cloud_public_key'))).verify(
                _b64u_decode(sig), body.encode())
            p = json.loads(_b64u_decode(body))
            return p if isinstance(p, dict) else None
        except Exception:
            return None

    def install(self, token):
        """Returns (ok, reason). Rejects bad signatures, other gateways/vendors and any
        license OLDER than the installed one (replay / downgrade)."""
        p = self._verify(token)
        if p is None:
            return False, 'bad_signature'
        ints = lambda *ks: all(isinstance(p.get(k), int) and not isinstance(p.get(k), bool) for k in ks)
        ok = (p.get('v') == 1 and p.get('k') == 'license' and isinstance(p.get('lid'), str)
              and _LID.match(p['lid']) and p.get('status') in ('ACTIVE', 'SUSPENDED')
              and ints('iat', 'grace') and 0 <= p['grace'] <= 30
              and all(p.get(k) is None or isinstance(p.get(k), int) for k in ('eff', 'trial_exp', 'sub_exp')))
        if not ok:
            return False, 'malformed'
        if p.get('gw') != self.store.get('gateway_uid') or p.get('vendor') != self.store.get('vendor_uid'):
            return False, 'wrong_binding'
        cur = self.store.get('license')
        if cur and p['iat'] < cur['iat']:
            return False, 'older_than_installed'
        self.store.set('license', {k: p.get(k) for k in (
            'lid', 'iat', 'eff', 'trial_exp', 'sub_exp', 'grace', 'status')} | {'token': token})
        self.clock.raise_floor(p['iat'])
        return True, 'ok'

    def state(self):
        lic, now = self.store.get('license'), self.clock.now()
        last_ok = self.store.get('last_cloud_ok_epoch')
        base = {'last_cloud_verification': last_ok, 'effective_until': None, 'grace_ends': None,
                'seconds_left': None}
        if not lic:
            return dict(base, state='NONE', can_sell=False, reason='no license installed')
        grace_ends = None if lic['eff'] is None else lic['eff'] + lic['grace'] * 86400
        base.update(effective_until=lic['eff'], grace_ends=grace_ends,
                    seconds_left=None if lic['eff'] is None else int(lic['eff'] - now),
                    trial_expires=lic.get('trial_exp'), subscription_expires=lic.get('sub_exp'))
        if self.clock.rollback_since_sync:
            return dict(base, state='UNTRUSTED_CLOCK', can_sell=False,
                        reason='clock moved backwards: new sales paused until the next cloud sync')
        if lic['status'] != 'ACTIVE':
            return dict(base, state='SUSPENDED', can_sell=False, reason='suspended by the platform')
        if lic['eff'] is None:
            return dict(base, state='EXPIRED', can_sell=False, reason='no active plan')
        if now < lic['eff']:
            return dict(base, state='ACTIVE', can_sell=True, reason='ok')
        if now < grace_ends:
            return dict(base, state='GRACE', can_sell=True,
                        reason='license expired: renew before the grace period ends')
        return dict(base, state='EXPIRED', can_sell=False,
                    reason='license and grace period ended: renew to resume new sales')

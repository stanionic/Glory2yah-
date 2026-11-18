"""Gateway-level access control (who may pass) and device identification."""
import re
import subprocess

from ..routers.validation import norm_ip, norm_mac


class AccessError(Exception):
    pass


class AccessController:
    def authorize(self, mac, ip, grant):
        raise NotImplementedError

    def deauthorize(self, mac):
        raise NotImplementedError


class RecordingController(AccessController):
    """No-op controller that records calls (tests, dry runs)."""
    def __init__(self):
        self.calls = []

    def authorize(self, mac, ip, grant):
        self.calls.append(('authorize', mac, ip, dict(grant)))

    def deauthorize(self, mac):
        self.calls.append(('deauthorize', mac))


class NdsctlController(AccessController):
    """Nodogsplash `ndsctl auth|deauth <mac>` (documented CLI). UNVERIFIED on real
    hardware: the redirect/FAS wiring must be validated in Phase 10."""
    def __init__(self, run=subprocess.run, binary='/usr/bin/ndsctl', timeout=5):
        self._run, self.binary, self.timeout = run, binary, timeout

    def _call(self, verb, mac):
        mac = norm_mac(mac)                              # validated: no injection surface
        try:
            r = self._run([self.binary, verb, mac], capture_output=True, text=True,
                          timeout=self.timeout, check=False, shell=False)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise AccessError(f'ndsctl {verb} failed: {type(e).__name__}')
        if r.returncode != 0:
            raise AccessError(f'ndsctl {verb} exited with {r.returncode}')

    def authorize(self, mac, ip, grant):
        self._call('auth', mac)

    def deauthorize(self, mac):
        self._call('deauth', mac)


class ArpMacResolver:
    """Derive the client MAC from its IP using the kernel neighbour table.
    The portal NEVER trusts a MAC supplied in the request."""
    def __init__(self, path='/proc/net/arp'):
        self.path = path

    def resolve(self, ip):
        try:
            ip = norm_ip(ip)
            with open(self.path) as fh:
                lines = fh.read().splitlines()[1:]
        except (OSError, ValueError, Exception):
            return None
        for line in lines:
            f = line.split()
            if len(f) >= 4 and f[0] == ip and f[2] != '0x0' and f[3] != '00:00:00:00:00:00':
                try:
                    return norm_mac(f[3])
                except Exception:
                    return None
        return None


class NdsctlUsage:
    """Per-client byte counters from ``ndsctl json`` (nodogsplash). UNVERIFIED on real
    hardware: field names and the unit (kBytes) must be confirmed in Phase 10."""
    def __init__(self, run=subprocess.run, binary='/usr/bin/ndsctl', timeout=5, unit_bytes=1024):
        self._run, self.binary, self.timeout, self.unit = run, binary, timeout, unit_bytes

    def read(self):
        import json
        try:
            r = self._run([self.binary, 'json'], capture_output=True, text=True,
                          timeout=self.timeout, check=False, shell=False)
            if r.returncode != 0:
                return {}
            data = json.loads(r.stdout)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return {}
        clients = data.get('clients', {}) if isinstance(data, dict) else {}
        rows = clients.values() if isinstance(clients, dict) else clients
        out = {}
        for c in rows:
            try:
                out[norm_mac(c['mac'])] = (int(c['downloaded']) * self.unit,
                                           int(c['uploaded']) * self.unit)
            except Exception:
                continue
        return out

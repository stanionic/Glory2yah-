"""Trusted time for a gateway that may be offline for days.

The device wall clock is NOT trusted (routers often have no RTC, and anyone with
shell access can change it). Trusted time T is built like this:

* after a cloud sync: T = server_time_at_sync + (monotonic_now - monotonic_at_sync).
  The monotonic clock cannot be set, so changing the wall clock has no effect;
* after a reboot (monotonic restarts) with no cloud yet: T continues from the
  highest time ever trusted (``high_water``, persisted) or the wall clock if that
  is later, then advances by the monotonic clock. Setting the wall clock back
  before a reboot therefore neither freezes time nor moves it backwards;
* a signed license's issue time is a hard floor (``raise_floor``).

Wall-clock steps BACKWARDS larger than ``tolerance`` are recorded as rollbacks;
until the next successful cloud sync the gateway refuses NEW sales (existing
sessions are untouched). Known limit: time spent powered off is not counted.
Persistence is throttled to protect flash storage on small routers.
"""
import threading
import time
import uuid

_PROCESS_ID = uuid.uuid4().hex


def read_boot_id():
    try:
        with open('/proc/sys/kernel/random/boot_id') as fh:
            return fh.read().strip() or None
    except OSError:
        return None


class TrustedClock:
    TOLERANCE_S = 120          # NTP-sized corrections are not rollbacks
    PERSIST_EVERY_S = 300      # flash-wear vs. exposure trade-off

    def __init__(self, store, wall=time.time, mono=time.monotonic, boot_id=read_boot_id,
                 tolerance=TOLERANCE_S):
        self.store, self.wall, self.mono, self.tolerance = store, wall, mono, tolerance
        self._boot = boot_id() or _PROCESS_ID      # without a boot id every process start counts as a boot
        self._lock = threading.RLock()
        st = store.get('clock') or {}
        self.high_water = float(st.get('high_water', 0))
        self.floor = float(st.get('floor', 0))
        self.max_wall = st.get('max_wall')
        self.anchor = st.get('anchor')
        self.rollbacks = int(st.get('rollbacks', 0))
        self.rollback_since_sync = bool(st.get('rollback_since_sync', False))
        self.last_anomaly = st.get('last_anomaly')
        self._base = None
        self._saved_high = self.high_water

    # ------------------------------------------------------------------ core
    def now(self):
        with self._lock:
            m = self.mono()
            a = self.anchor
            if a and a.get('boot') == self._boot and m >= a['mono']:
                t = a['server'] + (m - a['mono'])
            else:
                if self._base is None:
                    self._base = {'t0': max(self.wall(), self.high_water), 'mono0': m}
                t = self._base['t0'] + (m - self._base['mono0'])
            return max(t, self.floor)

    def sync_with_cloud(self, server_epoch):
        """Re-anchor on the cloud's time. A good sync also clears a rollback flag."""
        with self._lock:
            self.anchor = {'server': float(server_epoch), 'mono': self.mono(), 'boot': self._boot}
            self._base = None
            self.high_water = max(self.high_water, float(server_epoch))
            self.rollback_since_sync = False
            self.max_wall = self.wall()
            self._persist()

    def raise_floor(self, epoch):
        """A signed license's issue time: trusted time can never be earlier."""
        with self._lock:
            self.floor = max(self.floor, float(epoch))
            self.high_water = max(self.high_water, self.floor)
            self._persist()

    def observe(self):
        """Call regularly (even offline). Returns newly detected anomalies."""
        with self._lock:
            t, w, found = self.now(), self.wall(), []
            if self.max_wall is not None and w < self.max_wall - self.tolerance:
                self.rollbacks += 1
                self.rollback_since_sync = True
                self.last_anomaly = {'kind': 'clock_rollback', 'delta_s': int(self.max_wall - w),
                                     'trusted_time': int(t)}
                found.append(dict(self.last_anomaly))
                self.max_wall = w                      # new baseline: do not re-flag the same step
            else:
                self.max_wall = w if self.max_wall is None else max(self.max_wall, w)
            if t > self.high_water:
                self.high_water = t
            if found or self.high_water - self._saved_high >= self.PERSIST_EVERY_S:
                self._persist()
            return found

    # ---------------------------------------------------------------- status
    def status(self):
        with self._lock:
            t = self.now()
            anchored = bool(self.anchor and self.anchor.get('boot') == self._boot)
            return {'trusted_now': int(t), 'wall_now': int(self.wall()),
                    'skew_s': int(self.wall() - t), 'anchored': anchored,
                    'rollbacks': self.rollbacks, 'rollback_since_sync': self.rollback_since_sync,
                    'last_anomaly': self.last_anomaly}

    def _persist(self):
        self.store.set('clock', {'high_water': self.high_water, 'floor': self.floor,
                                 'max_wall': self.max_wall, 'anchor': self.anchor,
                                 'rollbacks': self.rollbacks,
                                 'rollback_since_sync': self.rollback_since_sync,
                                 'last_anomaly': self.last_anomaly})
        self._saved_high = self.high_water

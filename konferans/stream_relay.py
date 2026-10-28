"""Server-side live-relay gateway for KONFERANS rooms.

Turns the "Kòmanse Live" stream key into a *real* broadcast:

  owner's browser (canvas-composited video + mixed audio)
        │  MediaRecorder → WebM chunks
        ▼  Socket.IO binary event 'stream_chunk'
  this module (one ffmpeg subprocess per room, reading WebM from stdin)
        │  re-mux / re-encode → FLV
        ▼
  rtmp(s)://<ingest>/<stream_key>   (YouTube / TikTok / custom RTMP)

The raw stream key is used only in-memory to build the ingest URL — it is
never persisted (routes.py only ever stores a masked copy). If ffmpeg is not
installed (or FFMPEG_PATH is unset) the gateway reports it and the caller
falls back to the previous banner-only behaviour, so nothing regresses.
"""
import os
import shutil
import subprocess
import threading
from datetime import datetime

# Max accepted size of a single binary chunk (10 MB) — guards against abuse.
MAX_CHUNK_BYTES = 10 * 1024 * 1024

# Encoding is CPU-bound, so we allow ONE live broadcast at a time on the box.
MAX_CONCURRENT_BROADCASTS = 1

# room_id -> _StreamBroadcaster
_broadcasters = {}
_registry_lock = threading.Lock()

_ffmpeg_cache = None


def _ffmpeg_binary():
    """Resolve the ffmpeg executable.

    Order: explicit FFMPEG_PATH, then PATH, then the static binary shipped by
    the `imageio-ffmpeg` wheel. Render's Python runtime has no system ffmpeg,
    so the bundled binary is what makes a real RTMP broadcast possible there.
    """
    global _ffmpeg_cache
    if _ffmpeg_cache:
        return _ffmpeg_cache

    explicit = (os.environ.get('FFMPEG_PATH') or '').strip().strip('"')
    if explicit and os.path.isfile(explicit):
        _ffmpeg_cache = explicit
        return _ffmpeg_cache

    found = shutil.which('ffmpeg')
    if found:
        _ffmpeg_cache = found
        return _ffmpeg_cache

    try:
        import imageio_ffmpeg
        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and os.path.isfile(bundled):
            _ffmpeg_cache = bundled
            return _ffmpeg_cache
    except Exception:
        pass

    return None


def build_rtmp_url(ingest_url, stream_key):
    """Combine an ingest server URL and a stream key into a full RTMP(S) URL.

    'rtmp://a.rtmp.youtube.com/live2' + 'abcd-1234' ->
    'rtmp://a.rtmp.youtube.com/live2/abcd-1234'
    Trailing '/' on the ingest and leading '/' on the key are normalised so
    Facebook ('…/rtmp/') and others that already include the key path work too.
    """
    ingest = (ingest_url or '').strip().rstrip('/')
    key = (stream_key or '').strip().lstrip('/')
    if not key:
        return ingest
    return f"{ingest}/{key}"


class _StreamBroadcaster:
    """One ffmpeg publisher for a room, fed with WebM bytes from the browser."""

    def __init__(self, room_id, url):
        self.room_id = room_id
        self.url = url
        self.proc = None
        self.alive = False
        self.started_at = datetime.utcnow()
        self.bytes_in = 0
        self.last_error = None
        self._lock = threading.Lock()

    def start(self):
        ffmpeg = _ffmpeg_binary()
        if not ffmpeg:
            self.last_error = (
                "ffmpeg pa enstale sou sèvè a — enstale l oswa mete FFMPEG_PATH "
                "pou lanse difizyon RTMP reyèl."
            )
            return False, self.last_error

        # Read a continuous (fragmented) WebM stream from stdin, publish FLV to RTMP.
        # Tuned for a LOW-CPU box: 720p30, ultrafast x264, 2s keyframe interval
        # (what Facebook asks for). Only one broadcast runs at a time.
        cmd = [
            ffmpeg, '-hide_banner', '-loglevel', 'error',
            '-f', 'webm', '-i', 'pipe:0',
            '-vf', 'scale=-2:720',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'zerolatency',
            '-pix_fmt', 'yuv420p', '-r', '30',
            '-g', '60', '-keyint_min', '60', '-sc_threshold', '0',
            '-b:v', '1200k', '-maxrate', '1500k', '-bufsize', '3000k',
            '-c:a', 'aac', '-ar', '44100', '-ac', '2', '-b:a', '128k',
            '-f', 'flv', self.url,
        ]
        try:
            self.proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception as e:  # pragma: no cover - environment specific
            self.last_error = f"ffmpeg launch failed: {e}"
            return False, self.last_error

        self.alive = True
        threading.Thread(target=self._drain_stderr, daemon=True).start()
        return True, None

    def _drain_stderr(self):
        try:
            for line in iter(self.proc.stderr.readline, b''):
                if not line:
                    break
                self.last_error = line.decode('utf-8', 'replace').strip() or self.last_error
        except Exception:
            pass

    def feed(self, chunk):
        """Write one WebM chunk to ffmpeg's stdin. Returns False once broken."""
        if chunk is None:
            return False
        if isinstance(chunk, (bytes, bytearray, memoryview)):
            data = bytes(chunk)
        else:
            try:
                data = bytes(chunk)
            except Exception:
                return False
        if not data:
            return self.alive
        with self._lock:
            if not self.alive or not self.proc or self.proc.poll() is not None:
                self.alive = False
                return False
            try:
                self.proc.stdin.write(data)
                self.proc.stdin.flush()
                self.bytes_in += len(data)
                return True
            except (BrokenPipeError, OSError, ValueError):
                self.alive = False
                return False

    def stop(self):
        with self._lock:
            proc, self.proc, self.alive = self.proc, None, False
        if not proc:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def start_broadcaster(room_id, ingest_url, stream_key):
    """Spawn the ffmpeg publisher for a room. Returns (ok, error, info)."""
    stop_broadcaster(room_id)  # never leak a previous process for the same room

    # CPU guard: encoding is the expensive part, so only one live at a time.
    with _registry_lock:
        running = [r for r, b in _broadcasters.items() if b.alive]
    if len(running) >= MAX_CONCURRENT_BROADCASTS:
        return False, (
            "Yon lòt difizyon Live deja ap kouri — sèvè a pa gen ase CPU pou de (2) an menm tan."
        ), None

    url = build_rtmp_url(ingest_url, stream_key)
    if not url:
        return False, 'Pa gen URL ingest/Stream Key valid.', None
    b = _StreamBroadcaster(room_id, url)
    ok, err = b.start()
    if not ok:
        return False, err, None
    with _registry_lock:
        _broadcasters[room_id] = b
    return True, None, {'relay': True, 'ffmpeg': _ffmpeg_binary()}


def feed_chunk(room_id, chunk):
    """Forward a browser MediaRecorder chunk to the room's ffmpeg publisher."""
    if chunk is None:
        return False
    if len(chunk) > MAX_CHUNK_BYTES:
        return False
    with _registry_lock:
        b = _broadcasters.get(room_id)
    if not b:
        return False
    ok = b.feed(chunk)
    if not ok:
        # publisher died (bad key, network, platform rejected) — drop it
        stop_broadcaster(room_id)
    return ok


def stop_broadcaster(room_id):
    """Terminate the ffmpeg publisher (called on stop / disconnect)."""
    with _registry_lock:
        b = _broadcasters.pop(room_id, None)
    if b:
        b.stop()
        return True
    return False


def broadcaster_active(room_id):
    with _registry_lock:
        b = _broadcasters.get(room_id)
    return bool(b and b.alive)


def relay_available():
    """True when ffmpeg can be located (used to warn the UI early)."""
    return bool(_ffmpeg_binary())

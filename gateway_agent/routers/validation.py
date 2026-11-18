"""Strict input validation. Values reach router config APIs, so be conservative."""
import ipaddress
import re

from .base import ValidationFailed

_MAC = re.compile(r'^([0-9A-Fa-f]{2})([:-]?)(?:([0-9A-Fa-f]{2})\2){4}([0-9A-Fa-f]{2})$')
_HOST = re.compile(r'^(?=.{1,253}$)([A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)(\.[A-Za-z0-9]([A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)*$')
SECURITY = ('open', 'wpa2', 'wpa3', 'wpa2/wpa3')


def norm_mac(value):
    s = str(value or '').strip()
    if not re.fullmatch(r'[0-9A-Fa-f]{2}([:-][0-9A-Fa-f]{2}){5}|[0-9A-Fa-f]{12}', s):
        raise ValidationFailed('invalid MAC address')
    s = re.sub(r'[^0-9A-Fa-f]', '', s).lower()
    return ':'.join(s[i:i + 2] for i in range(0, 12, 2))


def norm_ip(value):
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError:
        raise ValidationFailed('invalid IP address')


def target_kind(value):
    """A bandwidth/client target is a MAC or an IP; return (kind, normalized)."""
    try:
        return 'ip', norm_ip(value)
    except ValidationFailed:
        return 'mac', norm_mac(value)


def valid_ssid(ssid):
    if not isinstance(ssid, str) or not (1 <= len(ssid.encode('utf-8')) <= 32):
        raise ValidationFailed('SSID must be 1-32 bytes')
    if any(ord(c) < 32 or ord(c) == 127 for c in ssid):
        raise ValidationFailed('SSID contains control characters')
    return ssid


def valid_passphrase(p):
    if not isinstance(p, str):
        raise ValidationFailed('passphrase required')
    if re.fullmatch(r'[0-9A-Fa-f]{64}', p):
        return p
    if not (8 <= len(p) <= 63) or any(not (32 <= ord(c) < 127) for c in p):
        raise ValidationFailed('passphrase must be 8-63 printable ASCII characters')
    return p


def valid_security(sec, allow_open=False):
    if sec not in SECURITY:
        raise ValidationFailed(f'security must be one of {SECURITY}')
    if sec == 'open' and not allow_open:
        raise ValidationFailed('open Wi-Fi requires allow_open=True')
    return sec


def valid_host(host):
    h = str(host or '').strip()
    try:
        return norm_ip(h)
    except ValidationFailed:
        pass
    if not _HOST.match(h):
        raise ValidationFailed('invalid host')
    return h


def valid_count(n, lo=1, hi=10):
    if not isinstance(n, int) or isinstance(n, bool) or not (lo <= n <= hi):
        raise ValidationFailed(f'count must be {lo}-{hi}')
    return n


def valid_kbps(n):
    if not isinstance(n, int) or isinstance(n, bool) or not (64 <= n <= 1_000_000):
        raise ValidationFailed('speed must be 64-1000000 kbps')
    return n


def valid_section(name):
    if not re.fullmatch(r'[A-Za-z0-9_]{1,64}', str(name or '')):
        raise ValidationFailed('invalid config section name')
    return name

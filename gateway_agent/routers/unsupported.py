"""Vendors with no automated adapter. We do NOT pretend compatibility: each one
reports 'unsupported' and the real options available to the vendor."""
import socket

from .base import (Capability, PingResult, RouterAdapter, RouterInfo, UnsupportedOperation)
from . import validation as V

OPTIONS = {
    'openwrt_firmware': (
        'Check your EXACT model and hardware revision in the OpenWrt Table of Hardware '
        '(openwrt.org). Flashing is at your own risk, may void the warranty, and is only '
        'an option if the model is officially listed. Then use the OpenWrt adapter.'),
    'access_point_mode': (
        'Put the router in Access Point mode: disable its DHCP server and NAT, connect a '
        'LAN port to the local switch, and set the SSID/password in its own web page. '
        'The UWZ gateway does the routing, captive portal and accounting.'),
    'manual_instructions': (
        '1) Log in to the router locally. 2) Set Wi-Fi name and WPA2/WPA3 password. '
        '3) Disable DHCP + NAT (AP mode). 4) Plug a LAN port into the UWZ network switch. '
        '5) Give the router a fixed address outside the gateway DHCP range.'),
}


class UnsupportedVendorAdapter(RouterAdapter):
    support_level = 'unsupported'

    def __init__(self, host=None, *_, **__):
        super().__init__()
        self.host = host

    def guidance(self):
        return dict(OPTIONS, documented_status='unsupported: no automated management')

    def identify(self):
        return RouterInfo(vendor=self.vendor_label, model='unknown', firmware='unknown')

    def _detect(self):
        return set()


class TPLinkAdapter(UnsupportedVendorAdapter):
    kind, vendor_label = 'tplink', 'TP-Link'


class TendaAdapter(UnsupportedVendorAdapter):
    kind, vendor_label = 'tenda', 'Tenda'


class DLinkAdapter(UnsupportedVendorAdapter):
    kind, vendor_label = 'dlink', 'D-Link'


class AsusAdapter(UnsupportedVendorAdapter):
    kind, vendor_label = 'asus', 'ASUS'


class GenericAdapter(UnsupportedVendorAdapter):
    """Unknown router: only a reachability check (TCP connect), nothing else."""
    kind, vendor_label = 'generic', 'Generic'

    def _detect(self):
        return {Capability.DIAGNOSTICS} if self.host else set()

    def ping(self, host=None, count=3):
        self.require(Capability.DIAGNOSTICS)
        target = V.valid_host(host or self.host)
        for port in (443, 80):
            try:
                with socket.create_connection((target, port), timeout=2):
                    return PingResult(target, True, f'tcp/{port} reachable')
            except OSError:
                continue
        return PingResult(target, False, 'no response on tcp/443 or tcp/80')

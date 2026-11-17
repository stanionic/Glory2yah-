"""Router Adapter contract. No adapter may assume a feature exists: capabilities
are DETECTED, and anything missing raises UnsupportedOperation with guidance."""
import enum
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Set


class Capability(str, enum.Enum):
    INFO = 'info'
    WIFI_READ = 'wifi_read'
    WIFI_CONFIG = 'wifi_config'
    CLIENTS = 'clients'
    DHCP_LEASES = 'dhcp_leases'
    DHCP_CONFIG = 'dhcp_config'
    BANDWIDTH = 'bandwidth'
    DIAGNOSTICS = 'diagnostics'


class RouterError(Exception):
    pass


class RouterAuthError(RouterError):
    pass


class RouterPermissionError(RouterError):
    pass


class RouterConnectionError(RouterError):
    pass


class UnsupportedOperation(RouterError):
    def __init__(self, message, guidance=None):
        super().__init__(message)
        self.guidance = guidance or {}


class ValidationFailed(ValueError):
    pass


@dataclass
class RouterInfo:
    vendor: str
    model: str
    firmware: str
    hostname: str = ''
    uptime_s: Optional[int] = None


@dataclass
class WifiNetwork:
    id: str
    ssid: str
    security: str          # open | wpa2 | wpa3 | wpa2/wpa3 | other
    enabled: bool


@dataclass
class Client:
    mac: str
    iface: str = ''
    ip: Optional[str] = None
    hostname: Optional[str] = None
    signal_dbm: Optional[int] = None


@dataclass
class Lease:
    mac: str
    ip: str
    hostname: str = ''
    expires_epoch: Optional[int] = None


@dataclass
class ApplyResult:
    applied: bool
    confirmed: bool
    detail: str = ''


@dataclass
class PingResult:
    host: str
    reachable: bool
    summary: str = ''


class RouterAdapter(ABC):
    kind = 'base'
    vendor_label = 'Unknown'
    support_level = 'implemented'      # implemented | unsupported
    hardware_verified = False          # flip ONLY after a documented real-hardware test

    def __init__(self):
        self._caps: Optional[Set[Capability]] = None

    # ---- discovery / identity
    @abstractmethod
    def identify(self) -> RouterInfo: ...

    @abstractmethod
    def _detect(self) -> Set[Capability]: ...

    def capabilities(self, refresh=False) -> Set[Capability]:
        if self._caps is None or refresh:
            self._caps = set(self._detect())
        return self._caps

    def require(self, cap: Capability):
        if cap not in self.capabilities():
            raise UnsupportedOperation(
                f'{self.kind}: capability "{cap.value}" is not available on this router',
                self.guidance())

    def guidance(self):
        return {'documented_status': 'see docs/ROUTER_COMPATIBILITY.md'}

    # ---- operations (default: unsupported; adapters override what they support)
    def list_wifi(self) -> List[WifiNetwork]:
        self.require(Capability.WIFI_READ); raise NotImplementedError

    def configure_wifi(self, network_id, *, ssid=None, passphrase=None, security=None,
                       enabled=None, allow_open=False) -> ApplyResult:
        self.require(Capability.WIFI_CONFIG); raise NotImplementedError

    def list_clients(self) -> List[Client]:
        self.require(Capability.CLIENTS); raise NotImplementedError

    def dhcp_leases(self) -> List[Lease]:
        self.require(Capability.DHCP_LEASES); raise NotImplementedError

    def configure_dhcp(self, section='lan', *, start=None, limit=None,
                       lease_time_s=None) -> ApplyResult:
        self.require(Capability.DHCP_CONFIG); raise NotImplementedError

    def set_bandwidth_limit(self, target, down_kbps, up_kbps) -> str:
        self.require(Capability.BANDWIDTH); raise NotImplementedError

    def remove_bandwidth_limit(self, target) -> bool:
        self.require(Capability.BANDWIDTH); raise NotImplementedError

    def ping(self, host, count=3) -> PingResult:
        self.require(Capability.DIAGNOSTICS); raise NotImplementedError

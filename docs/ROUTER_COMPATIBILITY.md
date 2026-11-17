# UWZ router compatibility

> **Read this first.** Every adapter below was written against the vendor's
> *documented* API and tested **only against simulators** (`tests/sim_routers.py`).
> No adapter has been run on real hardware yet, so each one reports
> `hardware_verified: false` to the cloud. Do not rely on a feature in production
> until it has been tested on your exact model and firmware, then flip the flag
> in the adapter class and record the test below.

## Support matrix

| Platform | Status | Wi-Fi config | Clients | DHCP leases | DHCP config | Per-client bandwidth | Ping |
|---|---|---|---|---|---|---|---|
| OpenWrt (reference) | implemented, simulated only | yes (safe apply) | yes | yes | yes | **no** (shape on the gateway) | yes |
| MikroTik RouterOS 7.1+ (`wifi` package) | implemented, simulated only | yes (read-back check) | yes | yes | no | yes (`uwz-*` queues only) | yes |
| MikroTik legacy `wireless` package | read-only | **no** | yes | yes | no | yes | yes |
| MikroTik RouterOS < 7.1 | **unsupported** (no REST API) | – | – | – | – | – | – |
| TP-Link, Tenda, D-Link, ASUS, other | **unsupported** | – | – | – | – | – | – |

Capabilities are **detected at runtime** from what the router exposes. A missing
capability raises `UnsupportedOperation` with guidance; it is never faked.

## If your router is unsupported

1. **Compatible firmware**: look up the exact model *and hardware revision* in the
   OpenWrt Table of Hardware. Flashing is at your own risk and may void the
   warranty. Only proceed if the model is officially listed.
2. **Access Point mode**: disable the router's DHCP and NAT, plug a LAN port into
   the local switch, set SSID/password in its own web page. The UWZ gateway does
   routing, captive portal and accounting.
3. **Manual configuration**: follow the steps the adapter returns in `guidance()`.

## Security rules (enforced in code and tests)

* No default credentials are ever tried; username and password are mandatory.
* Passwords come **only** from environment variables (`password_env`); an inline
  `password` in the config is refused. Credentials are never sent to the cloud.
* TLS verification is on by default; disabling it is an explicit opt-in for LAN
  routers with self-signed certificates.
* Inputs (SSID, WPA key, MAC/IP, speeds, hosts) are validated before any call.
  Open Wi-Fi requires `allow_open=True`.
* Only AP-mode Wi-Fi interfaces are modified (never a client/mesh uplink).
* `discover()` is a passive fingerprint; it never logs in or guesses passwords.

## OpenWrt

Requires `uhttpd-mod-ubus` and `rpcd`. Create a **dedicated least-privilege rpcd
user** rather than using `root`. Example ACL (verify the exact syntax for your
release): grant `read`/`write` on the `uci` configs `wireless` and `dhcp`, `read`
on `system`, `luci-rpc` (`getDHCPLeases`), `hostapd.*` (`get_clients`), and
`exec` of `/bin/ping` only on `file`.

Wi-Fi and DHCP changes use `uci apply` with a 30 s rollback timer. The adapter
confirms only if the router still answers afterwards; otherwise OpenWrt reverts
by itself. Releases older than 19.07 lack this and are **refused**, not applied
unsafely. WPA3 (`sae`) needs a full `wpad` build; if it is missing the change is
not confirmed and rolls back.

**Unverified assumptions to check on hardware:** `uci apply`/`confirm` argument
names, `hostapd.*.get_clients` output shape, `luci-rpc` availability, rpcd ACL.

## MikroTik

Requires RouterOS 7.1+ with `www-ssl` enabled and an API user restricted by group.
Manage the router over a wired/management link: REST has no commit-confirm, so a
Wi-Fi change is verified by read-back instead of auto-rollback. The adapter only
creates, updates or deletes queues named `uwz-*`.

**Unverified assumptions to check on hardware:** flattened property names such as
`configuration.ssid` and `security.authentication-types`, the `/rest/ping`
endpoint, and `registration-table` fields.

## Hardware test log

| Date | Platform / model / firmware | Tester | Features verified | Notes |
|---|---|---|---|---|
| – | *none yet* | – | – | – |

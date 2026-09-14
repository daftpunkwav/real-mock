"""URL/SSRF filtering, DNS pinning, and a secure HTTP client.

- Traverse multiple A records + IPv6 + a port allowlist
- DNS pinning: resolve once, then connect to the fixed IP to mitigate DNS-rebinding TOCTOU

``_resolve_all`` and all policy validation functions remain in this module (monkeypatch invariant: tests patch
``realmock.platform.core.security.url._resolve_all``); the three pinning components live in :mod:`.url_pin`.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

import httpx  # noqa: F401 - retain the module-level reference so tests can patch realmock.platform.core.security.url.httpx

# The pin section was moved to url_pin.py; re-export it here to preserve ``realmock.platform.core.security.url.*``
# Both import paths are available (security/__init__ and test take these symbols through this module)
from .url_pin import (  # noqa: F401
    PinnedHostTransport,
    PinnedHttpTarget,
    make_pinned_async_client,
)

logger = logging.getLogger(__name__)

# Networks denied by default: loopback, link-local, private, CGNAT, multicast, reserved, and IPv6 equivalents
_DEFAULT_BLOCKED_NETS = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT/operator shared
    ipaddress.ip_network("192.0.0.0/24"),  # IANA Special Case
    ipaddress.ip_network("224.0.0.0/4"),  # multicast
    ipaddress.ip_network("240.0.0.0/4"),  # reserved
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),  # IPv6 multicast
    ipaddress.ip_network("::ffff:0:0/96"),  # IPv4-mapped IPv6
]

_LOOPBACK_NETS = (
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("::1/128"),
)

# Allowed external ports: dev mode can allow any port; only HTTP/HTTPS during production period.
_DEFAULT_ALLOWED_PORTS = frozenset({80, 443})

# 198.18.0.0/15 (RFC 2544 benchmark reserved range): proxy TUN fake-ip mode maps public domain names
# After parsing this segment, the TCP connection is taken over by the proxy and forwarded to the real target, not the real intranet, and is allowed globally.
_PROVIDER_NETWORKS = (ipaddress.ip_network("198.18.0.0/15"),)
# List of provider hosts allowed to fall in the fake-ip segment (listed by domain list, no prefix wildcarding)
FAKEIP_ALLOWED_HOSTS = frozenset(
    {
        "api.xiaomimimo.com",
        "token-plan-cn.xiaomimimo.com",
        "token-plan-sgp.xiaomimimo.com",
        "token-plan-ams.xiaomimimo.com",
    }
)


class UnsafeURLError(ValueError):
    """The incoming URL hits the security policy."""


def _resolve_all(hostname: str) -> list[ipaddress._BaseAddress]:
    """Resolve a hostname/literal to all candidate IP addresses.

    - Return IPv4 / IPv6 literals directly;
    - For hostnames, return the complete set of SOCK_STREAM results from getaddrinfo.
    """
    try:
        return [ipaddress.ip_address(hostname.strip("[]"))]
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, OSError):
        raise ValueError(f"Unable to resolve host: {hostname!r}")
    out: list[ipaddress._BaseAddress] = []
    seen: set[str] = set()
    for info in infos:
        addr = str(info[4][0])
        if addr in seen:
            continue
        seen.add(addr)
        try:
            out.append(ipaddress.ip_address(addr))
        except ValueError:
            continue
    return out


def _is_loopback_ip(ip: ipaddress._BaseAddress) -> bool:
    return any(ip in net for net in _LOOPBACK_NETS)


def _ip_is_safe(ip: ipaddress._BaseAddress, *, allow_local: bool) -> bool:
    """Whether an individual resolved address is allowed for outbound access.

    ``allow_local=True`` additionally permits only loopback; private networks / metadata remain blocked.
    The fake-IP range (198.18.0.0/15) is always allowed; see the `_PROVIDER_NETWORKS` comment.
    """
    if allow_local and _is_loopback_ip(ip):
        return True
    for net in _PROVIDER_NETWORKS:
        if ip in net:
            return True
    for net in _DEFAULT_BLOCKED_NETS:
        if ip in net:
            return False
    try:
        if getattr(ip, "is_private", False):
            return False
        if getattr(ip, "is_multicast", False) or getattr(ip, "is_reserved", False):
            return False
        if getattr(ip, "is_unspecified", False):
            return False
    except Exception:
        logger.debug("IP security attribute check failed ip=%r, process as allowed", ip, exc_info=True)
    return True


def _all_ips_safe(ips: list[ipaddress._BaseAddress], *, allow_local: bool) -> bool:
    if not ips:
        return False
    return all(_ip_is_safe(ip, allow_local=allow_local) for ip in ips)


def is_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    timeout: float = 3.0,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> bool:
    """Validate whether ``url`` is an HTTP/HTTPS URL that is safe for outbound requests.

    - Allow only the http(s) schemes; reject http when ``require_https=True``;
    - Multiple A records: reject if **any** address is unsafe;
    - When ``allow_local=False``, reject nonstandard ports (only 80/443 by default);
    - When ``allow_local=True``, allow loopback while still rejecting private networks/metadata endpoints.
    """
    if not url:
        return False
    try:
        parsed = urlparse(url.strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False
    if require_https and parsed.scheme != "https":
        return False
    if not parsed.hostname:
        return False

    if not allow_local:
        port = parsed.port
        if port is not None and port not in (allowed_ports or _DEFAULT_ALLOWED_PORTS):
            return False

    try:
        ips = _resolve_all(parsed.hostname)
    except ValueError:
        return False
    trusted = trusted_hosts if trusted_hosts is not None else FAKEIP_ALLOWED_HOSTS
    hostname = parsed.hostname.lower()
    if hostname in trusted:
        return all(
            _ip_is_safe(ip, allow_local=allow_local)
            or any(ip in network for network in _PROVIDER_NETWORKS)
            for ip in ips
        )
    return _all_ips_safe(ips, allow_local=allow_local)


def assert_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> None:
    """Throws :class:`UnsafeURLError` when unsafe."""
    if not is_safe_http_url(
        url,
        allow_local=allow_local,
        require_https=require_https,
        allowed_ports=allowed_ports,
        trusted_hosts=trusted_hosts,
    ):
        raise UnsafeURLError(f"URL denied by policy: {url!r}")


def pin_safe_http_url(
    url: str,
    *,
    allow_local: bool = False,
    require_https: bool = False,
    allowed_ports: frozenset[int] | None = None,
    trusted_hosts: frozenset[str] | None = None,
) -> "PinnedHttpTarget":
    """Single DNS resolution → verify all candidates → pin the first secure IP."""
    if not url:
        raise UnsafeURLError("URL is empty")
    try:
        parsed = urlparse(url.strip())
    except Exception as e:
        raise UnsafeURLError(f"URL parsing failed: {url!r}") from e

    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(f"URL protocol is not secure: {url!r}")
    if require_https and parsed.scheme != "https":
        raise UnsafeURLError(f"Production environment requirements HTTPS: {url!r}")
    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError(f"URL is missing hostname: {url!r}")

    if not allow_local:
        port = parsed.port
        if port is not None and port not in (allowed_ports or _DEFAULT_ALLOWED_PORTS):
            raise UnsafeURLError(f"URL port is not allowed: {url!r}")

    try:
        ips = _resolve_all(hostname)
    except ValueError as e:
        raise UnsafeURLError(str(e)) from e
    if not ips:
        raise UnsafeURLError(f"Unable to resolve host: {hostname!r}")
    trusted = trusted_hosts if trusted_hosts is not None else FAKEIP_ALLOWED_HOSTS
    hostname_key = hostname.lower()
    ips_safe = _all_ips_safe(ips, allow_local=allow_local)
    if hostname_key in trusted:
        ips_safe = all(
            _ip_is_safe(ip, allow_local=allow_local)
            or any(ip in network for network in _PROVIDER_NETWORKS)
            for ip in ips
        )
    if not ips_safe:
        raise UnsafeURLError(f"URL denied by policy: {url!r}")

    return PinnedHttpTarget(
        original_url=url.strip(),
        hostname=hostname,
        pinned_ip=str(ips[0]),
        scheme=parsed.scheme,
        port=parsed.port,
    )


def is_localhost_family(host: str) -> bool:
    """Check whether the host hits the default blocked networks; rate-limit trust chain see ratelimit._peer_is_trusted_proxy."""
    if not host:
        return False
    try:
        ips = _resolve_all(host)
    except ValueError:
        return False
    for ip in ips:
        for net in _DEFAULT_BLOCKED_NETS:
            if ip in net:
                return True
    return False

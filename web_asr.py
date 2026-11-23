"""Resolve the optional browser-facing speech service origin for the web chat."""

import os
import re
from ipaddress import IPv6Address, ip_address


_ORIGIN = re.compile(
    r"(https?)://(\[[0-9a-f:.]+\]|[a-z0-9.-]+)(?::([0-9]{1,5}))?/?",
    re.ASCII | re.IGNORECASE,
)
_HOST_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")


def browser_asr_origin() -> str:
    """Return a validated HTTP(S) origin, or an empty string to disable dictation."""
    origin = os.getenv("ASR_URL", "").strip()
    match = _ORIGIN.fullmatch(origin)
    if not match:
        return ""
    scheme, host, port_text = match.groups()
    scheme, host = scheme.lower(), host.lower()
    port = int(port_text) if port_text else (443 if scheme == "https" else 80)
    if not 1 <= port <= 65535:
        return ""

    if host.startswith("["):
        try:
            host = f"[{IPv6Address(host[1:-1])}]"
        except ValueError:
            return ""
    else:
        try:
            host = str(ip_address(host))
        except ValueError:
            labels = host.removesuffix(".").split(".")
            if len(host) > 253 or not all(_HOST_LABEL.fullmatch(label) for label in labels):
                return ""
            # Browsers interpret numeric final labels as IPv4, including legacy forms.
            if re.fullmatch(r"(?:[0-9]+|0x[0-9a-f]*)", labels[-1]):
                return ""

    default_port = 443 if scheme == "https" else 80
    return f"{scheme}://{host}" + (f":{port}" if port != default_port else "")

"""Small, dependency-free checks for outgoing Hoymiles API requests."""

import re
from urllib.parse import urlsplit


def trusted_hoymiles_url(url: str) -> bool:
    """Only send the account token to HTTPS endpoints owned by Hoymiles."""
    # urlsplit strips some control characters; reject them before parsing.
    if not isinstance(url, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in url) or "\\" in url:
        return False
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        return (
            parsed.scheme == "https"
            and host is not None
            and (host == "hoymiles.com" or host.endswith(".hoymiles.com"))
            and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label) for label in host.split("."))
            and not parsed.fragment
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False


# Production API hosts explicitly listed in the inspected Android DNS manager.
# Static/CDN, telemetry-only and test hosts are deliberately not login targets.
AUTH_REDIRECT_HOSTS = frozenset({"euapi.hoymiles.com", "neapi.hoymiles.com", "indapi.hoymiles.com"})
AUTH_PATHS = frozenset({"/iam/pub/3/auth/pre-insp", "/iam/pub/3/auth/login"})


def trusted_auth_base(value: str) -> bool:
    """Routing responses may name only an exact production authentication base."""
    return isinstance(value, str) and value in {
        f"https://{host}{suffix}" for host in AUTH_REDIRECT_HOSTS for suffix in ("", "/")
    }


def trusted_auth_redirect(source: str, target: str) -> bool:
    """Allow one same-operation auth reroute, not arbitrary token forwarding."""
    if not isinstance(target, str) or len(target) > 4096:
        return False
    if not trusted_hoymiles_url(source) or not trusted_hoymiles_url(target):
        return False
    origin, destination = urlsplit(source), urlsplit(target)
    return (
        origin.hostname in AUTH_REDIRECT_HOSTS
        and destination.hostname in AUTH_REDIRECT_HOSTS
        and origin.path in AUTH_PATHS
        and destination.path == origin.path
        # Observed manufacturer 307 target (2026-11-06) adds this exact marker.
        # Match the raw query so duplicates, extra keys and encodings stay out.
        and not origin.query and destination.query in ("", "times=1")
        and target != source
    )

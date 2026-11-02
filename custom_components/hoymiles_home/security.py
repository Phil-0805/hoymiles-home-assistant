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

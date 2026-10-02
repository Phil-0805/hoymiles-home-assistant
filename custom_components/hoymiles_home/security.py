"""Small, dependency-free checks for outgoing Hoymiles API requests."""

from urllib.parse import urlsplit


def trusted_hoymiles_url(url: str) -> bool:
    """Only send the account token to HTTPS endpoints owned by Hoymiles."""
    try:
        parsed = urlsplit(url)
        host = parsed.hostname
        return (
            parsed.scheme == "https"
            and host is not None
            and (host == "hoymiles.com" or host.endswith(".hoymiles.com"))
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
        )
    except ValueError:
        return False

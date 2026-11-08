"""Send selected issue events to ntfy without logging event or transport data."""

import http.client
import json
import os
from pathlib import Path
import re
import ssl
import unicodedata
from urllib.parse import urlsplit


REPOSITORY = "Phil-0805/hoymiles-home-assistant"
OWNER = "phil-0805"
REPOSITORY_URL = "https://github.com/" + REPOSITORY


def text(value, limit):
    """Bound untrusted plain text and remove control/format characters."""
    if not isinstance(value, str):
        raise ValueError
    value = "".join(" " if unicodedata.category(c).startswith("C") else c
                    for c in value[:limit * 4])
    return " ".join(value.split())[:limit]


def positive_integer(value):
    if type(value) is not int or not 0 < value < 2**63:
        raise ValueError
    return value


def notification(event_name, event):
    """Return a message, or None for events deliberately outside our scope."""
    if event["repository"]["full_name"] != REPOSITORY:
        raise ValueError
    if event_name == "workflow_dispatch":
        return {"title": "GitHub: Testbenachrichtigung",
                "message": "Der manuelle ntfy-Test war erfolgreich.",
                "click": REPOSITORY_URL}
    if (event_name, event.get("action")) not in {
        ("issues", "opened"), ("issue_comment", "created")
    }:
        return None
    if event["sender"]["login"].casefold() == OWNER:
        return None
    issue = event["issue"]
    if "pull_request" in issue:
        return None
    number = positive_integer(issue["number"])
    actor = text(event["sender"]["login"], 80)
    title = text(issue["title"], 180)
    link = f"{REPOSITORY_URL}/issues/{number}"
    if event_name == "issues":
        label = "Neues Issue"
        body = text(issue.get("body") or "", 600)
    else:
        label = "Neuer Issue-Kommentar"
        comment = event["comment"]
        link += f"#issuecomment-{positive_integer(comment['id'])}"
        body = text(comment["body"], 600)
    return {"title": f"GitHub: {label} #{number}",
            "message": f"{actor}: {title}\n\n{body}", "click": link}


def configuration(env):
    """Validate secrets without including their values in errors."""
    url, token, topic = (env.get(name, "") for name in
                         ("NTFY_URL", "NTFY_TOKEN", "NTFY_TOPIC"))
    if not all((url, token, topic)):
        raise ValueError
    if (len(url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 for c in url)
            or any(c in url for c in "\\%?#")):
        raise ValueError
    parts = urlsplit(url)
    if (parts.scheme != "https" or not parts.hostname or parts.username is not None
            or parts.password is not None or parts.path not in ("", "/")
            or parts.port not in (None, 443)):
        raise ValueError
    if (not 1 <= len(token) <= 4096
            or any(not 33 <= ord(c) <= 126 for c in token)
            or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", topic) is None):
        raise ValueError
    return parts.hostname, token, topic


def send(message, env):
    host, token, topic = configuration(env)
    payload = json.dumps({**message, "topic": topic}, ensure_ascii=False).encode("utf-8")
    # HTTPSConnection neither follows redirects nor uses environment proxies.
    connection = http.client.HTTPSConnection(
        host, port=443, timeout=15, context=ssl.create_default_context())
    try:
        connection.request("POST", "/", body=payload, headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + token,
        })
        response = connection.getresponse()
        # Never read/log the response body or a redirect Location header.
        if not 200 <= response.status < 300:
            raise ValueError
    finally:
        connection.close()


def main(env=None):
    env = os.environ if env is None else env
    try:
        if (env.get("GITHUB_REPOSITORY") != REPOSITORY
                or env.get("GITHUB_REF") != "refs/heads/main"):
            raise ValueError
        # Bound file reads, including in local invocations with synthetic data.
        with Path(env["GITHUB_EVENT_PATH"]).open("rb") as stream:
            raw = stream.read(2 * 1024 * 1024 + 1)
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError
        message = notification(env["GITHUB_EVENT_NAME"], json.loads(raw))
        if message is None:
            print("Notification skipped.")
            return 0
        send(message, env)
    except Exception:
        # Exception strings and tracebacks can contain credentials and URLs.
        print("Notification failed; check configuration and service availability.")
        return 1
    print("Notification sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

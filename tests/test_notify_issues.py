"""Synthetic notification tests: no real secrets, DNS lookups or HTTP requests."""

from contextlib import redirect_stdout, redirect_stderr
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import ssl
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("notify_issues", ROOT / "scripts/notify_issues.py")
notify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(notify)

# Reserved .invalid namespace and deliberately synthetic credentials only.
SECRETS = {"NTFY_URL": "https://notify.invalid/", "NTFY_TOKEN": "synthetic-token",
           "NTFY_TOPIC": "synthetic-topic"}


def event(action="opened"):
    return {"repository": {"full_name": notify.REPOSITORY}, "action": action,
            "sender": {"login": "contributor"},
            "issue": {"number": 42, "title": "Synthetic issue", "body": "Details",
                      "state": "closed", "created_at": "2020-01-01T00:00:00Z"},
            "comment": {"id": 123, "body": "Synthetic comment"}}


class TestIssueNotifications(unittest.TestCase):
    def setUp(self):
        # All tests fail closed if a send accidentally attempts to use the network.
        self.transport = patch.object(notify.http.client, "HTTPSConnection")
        self.factory = self.transport.start()
        self.addCleanup(self.transport.stop)
        self.connection = self.factory.return_value
        self.connection.getresponse.return_value.status = 200

    def run_main(self, payload=None, name="issues", secrets=None, **overrides):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(event() if payload is None else payload), encoding="utf-8")
            env = {"GITHUB_EVENT_PATH": str(path), "GITHUB_EVENT_NAME": name,
                   "GITHUB_REPOSITORY": notify.REPOSITORY, "GITHUB_REF": "refs/heads/main",
                   **(SECRETS if secrets is None else secrets), **overrides}
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                result = notify.main(env)
            return result, output.getvalue()

    def test_new_issue(self):
        message = notify.notification("issues", event())
        self.assertIn("Neues Issue #42", message["title"])
        self.assertEqual(message["click"], notify.REPOSITORY_URL + "/issues/42")
        self.assertIn("contributor: Synthetic issue", message["message"])

    def test_comment_on_old_closed_issue(self):
        message = notify.notification("issue_comment", event("created"))
        self.assertIn("Neuer Issue-Kommentar", message["title"])
        self.assertEqual(message["click"], notify.REPOSITORY_URL + "/issues/42#issuecomment-123")
        self.assertIn("Synthetic comment", message["message"])

    def test_owner_issue_and_comment_skipped_without_secrets(self):
        for name, action in (("issues", "opened"), ("issue_comment", "created")):
            for owner in ("Phil-0805", "PHIL-0805"):
                with self.subTest(name=name, owner=owner):
                    payload = event(action)
                    payload["sender"]["login"] = owner
                    self.assertEqual(self.run_main(payload, name, secrets={}),
                                     (0, "Notification skipped.\n"))
        self.factory.assert_not_called()

    def test_other_people_commenting_on_owner_issue_are_not_suppressed(self):
        payload = event("created")
        payload["issue"]["user"] = {"login": "Phil-0805"}
        self.assertIsNotNone(notify.notification("issue_comment", payload))

    def test_manual_owner_test_sends(self):
        payload = event()
        payload["sender"]["login"] = "Phil-0805"
        self.assertEqual(self.run_main(payload, "workflow_dispatch")[0], 0)
        self.connection.request.assert_called_once()
        sent = json.loads(self.connection.request.call_args.kwargs["body"])
        self.assertIn("Testbenachrichtigung", sent["title"])

    def test_pr_comments_and_pr_shaped_issues_skipped(self):
        for name, action in (("issue_comment", "created"), ("issues", "opened")):
            payload = event(action)
            payload["issue"]["pull_request"] = {}
            self.assertEqual(self.run_main(payload, name, secrets={})[0], 0)
        self.factory.assert_not_called()

    def test_only_two_automatic_event_action_pairs(self):
        for name in ("issues", "issue_comment", "pull_request", "pull_request_target",
                     "pull_request_review", "pull_request_review_comment", "push"):
            for action in ("opened", "created", "edited", "deleted", "closed", "reopened", "submitted"):
                if (name, action) in (("issues", "opened"), ("issue_comment", "created")):
                    continue
                with self.subTest(name=name, action=action):
                    self.assertIsNone(notify.notification(name, event(action)))

    def test_missing_each_secret_and_empty_secret(self):
        for key in SECRETS:
            for value in (None, ""):
                secrets = dict(SECRETS)
                if value is None:
                    del secrets[key]
                else:
                    secrets[key] = value
                with self.subTest(key=key, value=value):
                    self.assertEqual(self.run_main(secrets=secrets)[0], 1)
        self.factory.assert_not_called()

    def test_invalid_configuration(self):
        invalid = {
            "NTFY_URL": ["http://notify.invalid", "https://user:pass@notify.invalid/",
                         "https://notify.invalid/topic", "https://notify.invalid/?a=b",
                         "https://notify.invalid/#fragment", "https://notify.invalid/?",
                         "https://notify.invalid/#", "https://notify.invalid:8443/",
                         "https://notify.invalid:bad/", "https:///", "https://notify.invalid/\r\nX: y",
                         " https://notify.invalid/", "https://notify.invalid\\other/",
                         "https://notify%2einvalid/"],
            "NTFY_TOKEN": ["secret\r\nX: injected", "secret\n", "secret token", "x" * 4097],
            "NTFY_TOPIC": ["x\r\nX: y", "../other", "with space", "x" * 65],
        }
        for key, values in invalid.items():
            for value in values:
                with self.subTest(key=key, index=values.index(value)):
                    self.assertEqual(self.run_main(secrets={**SECRETS, key: value})[0], 1)
        self.factory.assert_not_called()

    def test_json_serialization_and_no_header_injection(self):
        payload = event("created")
        malicious = '"\\\r\nAuthorization: injected\n$(touch /tmp/never) `false` ä 😀 ::error::'
        payload["issue"]["title"] = malicious
        payload["sender"]["login"] = malicious
        payload["comment"]["body"] = malicious
        self.assertEqual(self.run_main(payload, "issue_comment")[0], 0)
        request = self.connection.request.call_args
        self.assertEqual(request.args, ("POST", "/"))
        self.assertEqual(request.kwargs["headers"], {
            "Content-Type": "application/json", "Authorization": "Bearer synthetic-token"})
        body = json.loads(request.kwargs["body"])
        self.assertIn("$(touch /tmp/never)", body["message"])
        self.assertIn("ä 😀", body["message"])
        self.assertNotIn("\r", body["message"])
        self.assertEqual(set(body), {"title", "message", "click", "topic"})

    def test_message_size_is_bounded_even_for_non_ascii(self):
        payload = event("created")
        for mapping, key in ((payload["sender"], "login"), (payload["issue"], "title"),
                             (payload["comment"], "body")):
            mapping[key] = "😀" * 10000
        self.assertEqual(self.run_main(payload, "issue_comment")[0], 0)
        body = self.connection.request.call_args.kwargs["body"]
        self.assertLess(len(body), 4096)
        self.assertLess(len(json.loads(body)["message"].encode("utf-8")), 4096)

    def test_untrusted_links_are_never_used(self):
        payload = event("created")
        payload["issue"]["html_url"] = "https://untrusted.invalid/"
        payload["comment"]["html_url"] = "https://untrusted.invalid/"
        self.assertEqual(notify.notification("issue_comment", payload)["click"],
                         notify.REPOSITORY_URL + "/issues/42#issuecomment-123")

    def test_invalid_numeric_link_identifiers(self):
        for value in (True, False, 0, -1, 1.5, "42", "1\nX: y", 2**63):
            for location, field in (("issue", "number"), ("comment", "id")):
                payload = event("created")
                payload[location][field] = value
                with self.subTest(location=location, value=value):
                    self.assertEqual(self.run_main(payload, "issue_comment")[0], 1)
        self.factory.assert_not_called()

    def test_no_redirect_or_retry_for_any_http_error(self):
        for status in (301, 302, 303, 307, 308, 400, 401, 403, 404, 429, 500, 503):
            self.connection.reset_mock()
            self.factory.reset_mock()
            self.connection.getresponse.return_value.status = status
            with self.subTest(status=status):
                result, output = self.run_main()
                self.assertEqual(result, 1)
                self.factory.assert_called_once()
                self.connection.request.assert_called_once()
                self.connection.close.assert_called_once()
                self.connection.getresponse.return_value.getheader.assert_not_called()
                self.connection.getresponse.return_value.read.assert_not_called()
                self.assertNotIn(str(status), output)

    def test_verified_tls_timeout_and_no_response_read(self):
        self.run_main()
        args = self.factory.call_args
        self.assertEqual(args.args, ("notify.invalid",))
        self.assertEqual(args.kwargs["port"], 443)
        self.assertEqual(args.kwargs["timeout"], 15)
        context = args.kwargs["context"]
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.connection.getresponse.return_value.read.assert_not_called()
        self.connection.close.assert_called_once()

    def test_exceptions_never_leak_to_stdout_or_stderr(self):
        for method in (self.connection.request, self.connection.getresponse,
                       self.connection.close, self.factory):
            method.side_effect = RuntimeError(" ".join(SECRETS.values()) + " Authorization: private")
            with self.subTest(method=method._mock_name):
                result, output = self.run_main()
                self.assertEqual(result, 1)
                self.assertEqual(output, "Notification failed; check configuration and service availability.\n")
                for secret in SECRETS.values():
                    self.assertNotIn(secret, output)
            method.side_effect = None

    def test_success_does_not_log_secrets_or_event_text(self):
        result, output = self.run_main()
        self.assertEqual((result, output), (0, "Notification sent.\n"))

    def test_wrong_repository_or_dispatch_branch_cannot_send(self):
        for overrides in ({"GITHUB_REPOSITORY": "someone/other"},
                          {"GITHUB_REF": "refs/heads/untrusted"}):
            self.assertEqual(self.run_main(name="workflow_dispatch", **overrides)[0], 1)
        payload = event()
        payload["repository"]["full_name"] = "someone/other"
        self.assertEqual(self.run_main(payload)[0], 1)
        self.factory.assert_not_called()

    def test_malformed_payloads_fail_neutrally(self):
        for payload in ({}, [], None, {"repository": {}},
                        {**event(), "issue": None}, {**event(), "sender": {"login": None}}):
            if payload is None:
                payload = {**event(), "issue": {"number": True}}
            with self.subTest(payload_type=type(payload).__name__):
                result, output = self.run_main(payload)
                self.assertEqual(result, 1)
                self.assertTrue(output.startswith("Notification failed;"))
        self.factory.assert_not_called()

    def test_oversized_event_rejected(self):
        payload = deepcopy(event())
        payload["issue"]["body"] = "x" * (2 * 1024 * 1024)
        self.assertEqual(self.run_main(payload)[0], 1)
        self.factory.assert_not_called()

    def test_null_issue_body_allowed(self):
        payload = event()
        payload["issue"]["body"] = None
        self.assertEqual(self.run_main(payload)[0], 0)


if __name__ == "__main__":
    unittest.main()

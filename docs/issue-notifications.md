# Issue notifications

The optional `Issue notifications` workflow sends a notification for a newly
opened issue or a new comment on an issue, including old and closed issues.
It ignores pull requests, PR comments and events performed by `Phil-0805`.
The manual test is exempt from the owner filter.

Configure these repository Actions secrets yourself:

- `NTFY_URL`: HTTPS root address of the ntfy server, without a topic, query,
  credentials or fragment. Only the default HTTPS port 443 is supported.
- `NTFY_TOKEN`: ntfy access token. Prefer a token restricted to publishing to
  the intended topic.
- `NTFY_TOPIC`: target topic, 1–64 ASCII letters, digits, underscores or hyphens.

Never put their values in repository files, issues, screenshots or logs.
The topic must require authentication on the server; a secret topic name alone
does not enforce access control. The runner must be able to reach the HTTPS server.

After the workflow is merged into `main`, choose **Actions → Issue notifications
→ Run workflow**, selecting `main`. This sends one real test notification, even
when started by the owner. No production message is sent by the unit tests.

Messages contain the event type, issue number, actor, issue title, a limited
plain-text excerpt and a clickable GitHub link. Event text is JSON data, never
shell code or HTTP headers. No external images or attachment fetches are requested.
Delivery uses verified HTTPS, a 15-second socket timeout and no redirects,
proxies or automatic retries. The job has a two-minute overall timeout.
Errors use a fixed message without response bodies or exception details.

Only the protected `main` branch is checked out; credentials are not persisted.
Secrets are exposed only to the Python send step. The workflow needs only
`contents: read`; it does not use `pull_request_target` or modify GitHub data.
Existing validation and release workflows remain unchanged.

GitHub runner queues can delay delivery. This is best-effort notification,
not a durable delivery queue: failed sends are not retried automatically, and
manually rerunning a successful run can send the notification again.

Run the synthetic tests with:

```sh
python3 -m unittest discover -s tests -p test_notify_issues.py -v
```

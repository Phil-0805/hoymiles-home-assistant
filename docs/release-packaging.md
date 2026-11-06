# HACS ZIP releases and download counts — prepared for b6

Prepared for the v0.5.2b6 candidate. The maintainer authorized publication after
reviewing the login-redirect feedback and passing checks. Existing releases stay
unchanged.

`hacs.json` declares `zip_release: true` and `filename: hoymiles_home.zip`.
The release workflow builds this asset from Git-tracked integration files, with
paths relative to `custom_components/hoymiles_home`, plus the repository LICENSE. It creates a draft release,
uploads the ZIP, then publishes. Upload failure leaves the release unpublished.
Published tags/releases remain untouched; the existing release-exists guard also
leaves drafts unchanged, so a failed draft requires explicit maintainer handling.

HACS can use the asset's GitHub `download_count` for its Downloads column. This
counts package requests, including updates/re-downloads, rather than unique users
or active installations. Depending on the displayed release and cached catalog,
the UI does not necessarily show a lifetime repository total. Old source/archive
downloads cannot be reconstructed by adding ZIP assets to future releases.
No integration telemetry or personal usage reporting is added.

The tradeoff is maintaining correct package creation/upload for every future
release. Packaging tests verify root paths, file contents, deterministic output,
exclusion of untracked files and rejection of symlinks. CI/HACS validation must
also pass before the eventual b6 publication.

References checked 2026-11-05:
- https://contributors.home-assistant.io/marketplace/guides/releases/#ship-a-zip-file
- https://contributors.home-assistant.io/marketplace/reference/hacs-json/
- https://github.com/hacs/integration/blob/main/custom_components/hacs/repositories/base.py

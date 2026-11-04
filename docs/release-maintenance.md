# Release maintenance

CI runs tests, HACS validation and Hassfest before creating a release. Published
version tags are never moved. Stable versions publish from `main`; the configured
beta branches (including `beta/v0.5.2`) publish prereleases.

Stable publication additionally requires the repository Actions secret
`RELEASE_READINESS_JSON`. Store the approval privately, with this structure:

```json
{
  "schema_version": 1,
  "target_version": "<stable version>",
  "candidate_commit": "<full 40-character release commit SHA>",
  "maintainer_approved": true,
  "limitations_reviewed": true
}
```

Set the secret only after reviewing the exact candidate and the limitations in
its release notes. An approval for another version or commit cannot be reused.
Missing or malformed approval blocks publication. This decision accepts the
published limitations; it does not claim that untested hardware was verified.
Keep account information, working notes and device evidence out of the record.

For a local check, save the record outside tracked files and run:

```sh
python scripts/check_release_readiness.py --version <version> --commit <sha> --record <private-file>
```

The workflow skips existing releases before checking approval. Changing source
files alone does not update an already published version. Prepare a new version
and matching release notes when publishing changes.

The required `setup-tests` check aggregates both HA version jobs and fails if
either version fails or is skipped. The release workflow also tests both Core
versions before publication. Keep this stable check name when changing the matrix.

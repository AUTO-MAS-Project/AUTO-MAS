# Release-chain hardening report

Date: 2026-07-23

Scope: local changes under `.github/workflows/**` in the
`all-plugins-integration` worktree. No commit, push, release, signing request,
MirrorChyan upload, CNB write, or frozen r6 modification was performed.

## Implemented controls

- Release metadata is parsed by `release-metadata.mjs`. Release tags and
  prerelease state are strictly validated before any output is written.
- Multiline `GITHUB_OUTPUT` records use a random 192-bit delimiter that is
  regenerated if it collides with an exact payload line. Changelog tests cover a
  standalone `EOF`, shell substitutions, backticks, quotes, PowerShell
  metacharacters, and workflow-expression text.
- Shell, PowerShell, and Inno Setup values cross process boundaries through
  environment variables or files rather than direct interpolation into `run`
  blocks.
- Workflow permissions are job-scoped. Only the release job has
  `contents: write`; build, CNB, MirrorChyan, and repository-sync jobs have
  read-only permissions appropriate to their GitHub API use.
- Every GitHub action is pinned to a reviewed 40-character commit. The
  `tencentcom/git-sync` container that receives `GIT_PASSWORD` is pinned to its
  full Docker manifest digest. Resolution evidence is recorded in
  `ACTION_PINS.md`.
- GitHub-hosted runner families are fixed to `windows-2025`, `ubuntu-24.04`, and
  `macos-15` rather than migrating `*-latest` aliases. Inno Setup is installed
  as the approved Chocolatey package version `6.7.1` from the explicit
  community source with checksum enforcement.
- CNB triggering no longer installs floating `requests`/`tqdm` packages before
  receiving `CNB_TOKEN`. It uses Python 3.12 standard-library HTTP code with a
  60-second timeout and a 1 MiB response limit.
- SignPath is followed immediately by fail-closed Authenticode verification for
  the main executable and both setup executables. The signature must be
  `Valid`, and the certificate subject and thumbprint must match the selected
  release/test allowlists. Missing alpha/test allowlists are an intentional
  hard failure.
- Wheelhouse and full-environment ZIP ingress has HTTPS download and compressed,
  entry-count, per-file, and total-expanded-size limits. Traversal, absolute
  paths, alternate data streams, duplicate canonical paths, Windows device
  names, symlinks, reparse points, and special files are rejected before the
  staging directory is promoted. The environment archive must have exactly one
  top-level `environment` directory.
- The legacy manual GitHub-to-CNB helper now uses the same 1 GiB / 4096-entry /
  2 GiB-expanded / 512 MiB-file budget model, bounded request timeouts,
  staging-directory extraction, and exact dependency pins. It no longer calls
  `ZipFile.extractall()` or overwrites an existing download/extraction target.
- Artifact upload is fail-closed. The published set is exactly four expected
  `*-x64.zip` files plus `SHA256SUMS.txt`, and downstream release/mirror jobs
  recheck the manifest.

## Local verification evidence

| Command                                                                                                                        | Exit | Result                                                                                                                                                                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------ | ---: | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `node --test .github/workflows/scripts/release-metadata.test.mjs .github/workflows/scripts/release-workflow-security.test.mjs` |    0 | 13/13 passed; includes YAML parsing of five workflows, immutable pins, runner/toolchain versions, permissions, hostile metadata, exact artifacts, signing order, CNB dependency isolation, and automated/manual archive contracts |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .github\workflows\scripts\Test-ArchiveSafety.ps1`                     |    0 | benign ZIP accepted; traversal, ADS, Unix symlink, Windows reparse point, per-file overflow, and entry-count overflow rejected                                                                                                    |
| `powershell.exe -NoProfile -ExecutionPolicy Bypass -File .github\workflows\scripts\Test-AuthenticodeSignaturePolicy.ps1`       |    0 | missing alpha/test identity and prerelease/policy mismatch both fail closed                                                                                                                                                       |
| `py -3.12 .github/workflows/scripts/Verify-ManualReleaseSafety.py`                                                             |    0 | 7/7 passed; benign extraction plus traversal, ADS/device name, canonical duplicate, symlink, budget and existing-destination rejection                                                                                            |
| `py -3.12 -m pip install --dry-run --ignore-installed -r .github\workflows\requirements.txt`                                  |    0 | exact seven-wheel Windows x64 / CPython 3.12 dependency closure resolved and every downloaded wheel matched its reviewed SHA-256                                                                                                  |
| PowerShell AST parse of the archive and Authenticode scripts                                                                   |    0 | all four PowerShell files parsed without errors                                                                                                                                                                                   |
| `py -3.12 .github/workflows/scripts/Verify-CnbTriggerContract.py`                                                              |    0 | 2/2 passed; request contract and oversized-response rejection verified without network                                                                                                                                            |
| Live metadata generation against `res/version.json`                                                                            |    0 | `v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1`, prerelease `true`, `test-signing`, random delimiter validated                                                                                                                          |
| `git diff --check -- .github/workflows`                                                                                        |    0 | no whitespace errors; Git only reported the repository's LF-to-CRLF checkout warning                                                                                                                                              |
| local Prettier `--check` over the touched YAML/Markdown/MJS set                                                                |    0 | all ten release-chain YAML/Markdown/MJS files match the repository Prettier configuration after a targeted formatting pass                                                                                                        |

Archive-test evidence from the final run was retained at:

`C:\Users\qiyin\AppData\Local\Temp\auto-mas-archive-safety-1bc1e392b00b4f24a9f259de21be0dd9`

Live-metadata evidence was retained at:

`C:\Users\qiyin\AppData\Local\Temp\auto-mas-release-metadata-live-26a7ac67cad540d3bc502fedee04da6b`

## Residual risk and external validation

Code-scoped P1 found by this audit: none remaining in the active release
workflow after the controls above.

Treat the following as release-blocking external P1 until a real protected
GitHub Actions run proves them:

- Configure all four repository variables documented in `ACTION_PINS.md` with
  independently verified SignPath certificate subjects and thumbprints. The
  values were not available locally and were deliberately not invented.
- Confirm SignPath organization/project/policy secrets, `CNB_TOKEN`,
  `MirrorChyanUploadToken`, and the CNB repository password are present and
  minimally scoped.
- Supply real wheelhouse/environment URLs and SHA-256 values, then confirm the
  hosted Windows runner accepts both archives within the declared budgets.
- Inspect the resulting main executable, Lite setup, and Full setup signatures,
  the exact five-file artifact set, release creation, MirrorChyan upload, and
  CNB trigger in the protected repository environment.

Residual P2:

- A branch/tag push can succeed before the GitHub Release action fails, leaving
  recoverable partial external state that needs an operator rerun or cleanup.

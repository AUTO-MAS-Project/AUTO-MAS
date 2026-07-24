# GitHub Actions immutable pins

Resolved on 2026-07-23 from each action's official GitHub repository. The workflow
uses the commit SHA, while the comment keeps the human-readable tag that was
resolved. Re-resolve and review upstream changes before changing any pin.

| Action                                          | Verified ref                 | Immutable commit                                                          |
| ----------------------------------------------- | ---------------------------- | ------------------------------------------------------------------------- |
| `SignPath/github-action-submit-signing-request` | `v2.0`                       | `3f9250c56651ff692d6729a2fbb0603a42d7d322`                                |
| `softprops/action-gh-release`                   | `v2.6.2`                     | `3bb12739c298aeb8a4eeaf626c5b8d85266b0e65`                                |
| `astral-sh/setup-uv`                            | `v8.1.0`                     | `08807647e7069bb48b6ef5acd8ec9567f424441b`                                |
| `MirrorChyan/uploading-action`                  | `v1`                         | `1ae1dddee41454a0a048d7f5b10ec11f2e5a89c4`                                |
| `MirrorChyan/release-note-action`               | `v1`                         | `f392b50c411981ee6d33c8ed5e91d66d84d56202`                                |
| `actions/checkout`                              | `v4`                         | `11d5960a326750d5838078e36cf38b85af677262`                                |
| `actions/setup-node`                            | `v4`                         | `49933ea5288caeca8642d1e84afbd3f7d6820020`                                |
| `actions/upload-artifact`                       | `v4`                         | `ea165f8d65b6e75b540449e92b4886f43607fa02`                                |
| `actions/download-artifact`                     | `v4`                         | `d3f86a106a0bac45b974a628896c90dbdf5c8093`                                |
| `actions/cache`                                 | `v4`                         | `0057852bfaa89a56745cba8c7296529d2fc39830`                                |
| `actions/setup-python`                          | `v5`                         | `a26af69be951a213d495a4c3e4e4022e16d87065`                                |
| `actions/github-script`                         | `v7`                         | `f28e40c7f34bde8b3046d885e986cb6290c5673b`                                |
| `tencentcom/git-sync`                           | `latest` observed 2026-07-23 | `sha256:b7c4672616ddea5b89948dcd034610b29d37d8430e74b4bc83b421c963c25f77` |

Primary-source evidence is the corresponding official commit page, for example:

- <https://github.com/SignPath/github-action-submit-signing-request/commit/3f9250c56651ff692d6729a2fbb0603a42d7d322>
- <https://github.com/softprops/action-gh-release/commit/3bb12739c298aeb8a4eeaf626c5b8d85266b0e65>
- <https://github.com/astral-sh/setup-uv/commit/08807647e7069bb48b6ef5acd8ec9567f424441b>
- <https://github.com/MirrorChyan/uploading-action/commit/1ae1dddee41454a0a048d7f5b10ec11f2e5a89c4>
- <https://github.com/MirrorChyan/release-note-action/commit/f392b50c411981ee6d33c8ed5e91d66d84d56202>
- <https://hub.docker.com/v2/repositories/tencentcom/git-sync/tags?page_size=100>

## Runner and installer toolchain pins

- Runner OS families are fixed to `windows-2025`, `ubuntu-24.04`, and
  `macos-15`. GitHub documents these labels in the official
  [`actions/runner-images` image table](https://github.com/actions/runner-images#available-images).
  The labels prevent `*-latest` OS migrations; the hosted image contents still
  receive GitHub's regular servicing updates and must be verified by a protected
  workflow run.
- Inno Setup is fixed to Chocolatey package `innosetup` version `6.7.1`, using
  the explicit community source and `--require-checksums`. Chocolatey's approved
  package record publishes the upstream installer SHA-256
  `4D11E8050B6185E0D49BD9E8CC661A7A59F44959A621D31D11033124C4E8A7B0`:
  <https://community.chocolatey.org/packages/InnoSetup/6.7.1>.

## Legacy manual uploader dependency snapshot

`.github/workflows/requirements.txt` contains an exact seven-package dependency
closure rather than lower bounds. Every requirement also pins the reviewed
Windows x64 / CPython 3.12 wheel SHA-256. `requests==2.34.2` and its four
dependencies match the reviewed host `uv.lock`; `tqdm==4.69.0` and its Windows
dependency `colorama==0.4.6` are fixed explicitly. The direct versions and wheel
hashes were checked against their official PyPI records:

- <https://pypi.org/project/requests/2.34.2/>
- <https://pypi.org/project/tqdm/4.69.0/>

This snapshot is only for the retained manual GitHub-to-CNB helper. The active
CNB trigger uses the Python standard library and does not install these packages
after receiving `CNB_TOKEN`.

## Required SignPath certificate allowlists

The build intentionally fails closed when any selected policy lacks an explicit
certificate identity. Configure these GitHub repository variables as JSON arrays:

- `SIGNPATH_RELEASE_CERTIFICATE_SUBJECT_ALLOWLIST_JSON`
- `SIGNPATH_RELEASE_CERTIFICATE_THUMBPRINT_ALLOWLIST_JSON`
- `SIGNPATH_TEST_CERTIFICATE_SUBJECT_ALLOWLIST_JSON`
- `SIGNPATH_TEST_CERTIFICATE_THUMBPRINT_ALLOWLIST_JSON`

The test policy is mandatory for every SemVer prerelease, including alpha builds.
Thumbprints must be 40 hexadecimal characters. Subjects and thumbprints must match
the certificate returned by SignPath exactly (subject matching is case-insensitive).
Do not copy a value from an unverified build log.

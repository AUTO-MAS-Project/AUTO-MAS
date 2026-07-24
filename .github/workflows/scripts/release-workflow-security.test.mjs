import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "..", "..", "..");
const requireFromFrontend = createRequire(
  resolve(repositoryRoot, "frontend", "package.json"),
);
const { load: parseYaml } = requireFromFrontend("js-yaml");

const workflowPaths = [
  ".github/workflows/build-app.yml",
  ".github/workflows/check-version-json.yml",
  ".github/workflows/mirrorchyan.yml",
  ".github/workflows/mirrorchyan-release-note.yml",
  ".github/workflows/sync-cnb.yml",
];
const workflowTexts = new Map(
  workflowPaths.map((path) => [
    path,
    readFileSync(resolve(repositoryRoot, path), "utf8"),
  ]),
);
const workflows = new Map(
  [...workflowTexts].map(([path, content]) => [path, parseYaml(content)]),
);

const immutablePins = new Map([
  ["actions/checkout", "11d5960a326750d5838078e36cf38b85af677262"],
  ["actions/setup-node", "49933ea5288caeca8642d1e84afbd3f7d6820020"],
  ["actions/upload-artifact", "ea165f8d65b6e75b540449e92b4886f43607fa02"],
  ["actions/download-artifact", "d3f86a106a0bac45b974a628896c90dbdf5c8093"],
  ["actions/cache", "0057852bfaa89a56745cba8c7296529d2fc39830"],
  ["actions/setup-python", "a26af69be951a213d495a4c3e4e4022e16d87065"],
  ["actions/github-script", "f28e40c7f34bde8b3046d885e986cb6290c5673b"],
  ["astral-sh/setup-uv", "08807647e7069bb48b6ef5acd8ec9567f424441b"],
  [
    "signpath/github-action-submit-signing-request",
    "3f9250c56651ff692d6729a2fbb0603a42d7d322",
  ],
  ["softprops/action-gh-release", "3bb12739c298aeb8a4eeaf626c5b8d85266b0e65"],
  ["MirrorChyan/uploading-action", "1ae1dddee41454a0a048d7f5b10ec11f2e5a89c4"],
  [
    "MirrorChyan/release-note-action",
    "f392b50c411981ee6d33c8ed5e91d66d84d56202",
  ],
]);
const immutableDockerPins = new Map([
  [
    "tencentcom/git-sync",
    "sha256:b7c4672616ddea5b89948dcd034610b29d37d8430e74b4bc83b421c963c25f77",
  ],
]);

function allSteps(workflow) {
  return Object.values(workflow.jobs ?? {}).flatMap((job) => job.steps ?? []);
}

function extractRunBlocks(workflowText) {
  const lines = workflowText.split(/\r?\n/);
  const blocks = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(\s*)run:\s*\|\s*$/);
    if (!match) {
      continue;
    }
    const indentation = match[1].length;
    const block = [];
    for (index += 1; index < lines.length; index += 1) {
      const line = lines[index];
      if (line.trim() === "") {
        block.push(line);
        continue;
      }
      const nextIndentation = line.match(/^\s*/)[0].length;
      if (nextIndentation <= indentation) {
        index -= 1;
        break;
      }
      block.push(line);
    }
    blocks.push(block.join("\n"));
  }
  return blocks;
}

test("all release-chain actions are pinned to reviewed immutable identities", () => {
  for (const [workflowPath, workflow] of workflows) {
    for (const step of allSteps(workflow)) {
      if (!step.uses) {
        continue;
      }
      if (step.uses.startsWith("docker://")) {
        const match = step.uses.match(
          /^docker:\/\/([^@]+)@(sha256:[0-9a-f]{64})$/,
        );
        assert.ok(
          match,
          `${workflowPath} has a mutable Docker action ref: ${step.uses}`,
        );
        assert.equal(
          match[2],
          immutableDockerPins.get(match[1]),
          `${workflowPath} has an unreviewed image digest for ${match[1]}`,
        );
        continue;
      }
      const match = step.uses.match(/^([^@]+)@([0-9a-f]{40})$/);
      assert.ok(
        match,
        `${workflowPath} has a mutable action ref: ${step.uses}`,
      );
      assert.equal(
        match[2],
        immutablePins.get(match[1]),
        `${workflowPath} has an unreviewed commit for ${match[1]}`,
      );
    }
  }
});

test("permissions are job-scoped and minimal for the release chain", () => {
  const buildWorkflow = workflows.get(".github/workflows/build-app.yml");
  assert.equal(buildWorkflow.permissions, undefined);
  assert.deepEqual(buildWorkflow.jobs.build.permissions, {
    actions: "read",
    contents: "read",
  });
  assert.deepEqual(buildWorkflow.jobs.release.permissions, {
    actions: "read",
    contents: "write",
  });
  assert.deepEqual(buildWorkflow.jobs.cnb.permissions, { contents: "read" });
  assert.deepEqual(buildWorkflow.jobs.mirror.permissions, { actions: "read" });

  for (const path of [
    ".github/workflows/mirrorchyan.yml",
    ".github/workflows/mirrorchyan-release-note.yml",
  ]) {
    const workflow = workflows.get(path);
    assert.equal(workflow.permissions, undefined);
    assert.deepEqual(workflow.jobs.mirrorchyan.permissions, {
      contents: "read",
    });
  }

  const syncWorkflow = workflows.get(".github/workflows/sync-cnb.yml");
  assert.equal(syncWorkflow.permissions, undefined);
  assert.deepEqual(syncWorkflow.jobs.sync.permissions, { contents: "read" });

  const versionWorkflow = workflows.get(
    ".github/workflows/check-version-json.yml",
  );
  assert.deepEqual(versionWorkflow.permissions, {
    contents: "read",
    "pull-requests": "read",
  });
});

test("runner families and the installer toolchain are version-pinned", () => {
  const expectedRunners = new Map([
    [".github/workflows/build-app.yml:build", "windows-2025"],
    [".github/workflows/build-app.yml:cnb", "ubuntu-24.04"],
    [".github/workflows/build-app.yml:release", "ubuntu-24.04"],
    [".github/workflows/build-app.yml:mirror", "macos-15"],
    [
      ".github/workflows/check-version-json.yml:check-version-json",
      "ubuntu-24.04",
    ],
    [".github/workflows/mirrorchyan.yml:mirrorchyan", "macos-15"],
    [".github/workflows/mirrorchyan-release-note.yml:mirrorchyan", "macos-15"],
    [".github/workflows/sync-cnb.yml:sync", "ubuntu-24.04"],
  ]);

  for (const [workflowPath, workflow] of workflows) {
    for (const [jobName, job] of Object.entries(workflow.jobs ?? {})) {
      assert.equal(
        job["runs-on"],
        expectedRunners.get(`${workflowPath}:${jobName}`),
        `${workflowPath}:${jobName} has an unexpected runner image`,
      );
      assert.equal(
        String(job["runs-on"]).endsWith("-latest"),
        false,
        `${workflowPath}:${jobName} uses a migrating runner alias`,
      );
    }
  }

  const buildText = workflowTexts.get(".github/workflows/build-app.yml");
  assert.ok(
    buildText.includes(
      "choco install innosetup --version=6.7.1 --source=https://community.chocolatey.org/api/v2/ --yes --no-progress --limit-output --require-checksums",
    ),
  );
});

test("CNB trigger has no third-party Python install before receiving its token", () => {
  const workflow = workflows.get(".github/workflows/build-app.yml");
  const cnbSteps = workflow.jobs.cnb.steps;
  assert.equal(
    cnbSteps.some((step) => step.run?.includes("pip install")),
    false,
  );
  assert.equal(
    cnbSteps.some((step) => step.uses?.startsWith("astral-sh/setup-uv@")),
    false,
  );
  const setupPython = cnbSteps.find((step) =>
    step.uses?.startsWith("actions/setup-python@"),
  );
  assert.equal(setupPython.with?.["python-version"], "3.12");

  const triggerSource = readFileSync(
    resolve(repositoryRoot, ".github/workflows/cnb_trigger.py"),
    "utf8",
  );
  assert.equal(triggerSource.includes("import requests"), false);
  assert.ok(
    triggerSource.includes("urllib.request.urlopen(request, timeout=60)"),
  );
});

test("untrusted workflow expressions are never interpolated into run scripts", () => {
  for (const [workflowPath, text] of workflowTexts) {
    for (const block of extractRunBlocks(text)) {
      assert.equal(
        block.includes("${{"),
        false,
        `${workflowPath} interpolates an expression directly into a run block`,
      );
    }
  }
});

test("artifact publication is exact and fail-closed", () => {
  const workflow = workflows.get(".github/workflows/build-app.yml");
  const uploadSteps = allSteps(workflow).filter((step) =>
    step.uses?.startsWith("actions/upload-artifact@"),
  );
  assert.equal(uploadSteps.length, 4);
  for (const step of uploadSteps) {
    assert.equal(
      step.with?.["if-no-files-found"],
      "error",
      `${step.name} is not fail-closed`,
    );
  }

  const buildUpload = uploadSteps.find(
    (step) => step.with?.name === "build-artifacts",
  );
  assert.ok(buildUpload);
  const publishedPaths = buildUpload.with.path.trim().split(/\r?\n/);
  assert.equal(publishedPaths.length, 5);
  assert.ok(publishedPaths.includes("SHA256SUMS.txt"));
  assert.equal(
    publishedPaths.filter((path) => path.endsWith("-x64.zip")).length,
    4,
  );
});

test("both signing phases are followed by allowlisted Authenticode verification", () => {
  const workflow = workflows.get(".github/workflows/build-app.yml");
  const names = workflow.jobs.build.steps.map((step) => step.name);
  const mainSigning = names.indexOf("签名主程序");
  const mainVerification = names.indexOf("验证主程序签名身份");
  const setupSigning = names.indexOf("签名安装程序");
  const setupVerification = names.indexOf("验证安装程序签名身份");
  assert.ok(mainSigning >= 0 && mainVerification === mainSigning + 1);
  assert.ok(setupSigning >= 0 && setupVerification === setupSigning + 1);

  const text = workflowTexts.get(".github/workflows/build-app.yml");
  for (const variable of [
    "SIGNPATH_RELEASE_CERTIFICATE_SUBJECT_ALLOWLIST_JSON",
    "SIGNPATH_RELEASE_CERTIFICATE_THUMBPRINT_ALLOWLIST_JSON",
    "SIGNPATH_TEST_CERTIFICATE_SUBJECT_ALLOWLIST_JSON",
    "SIGNPATH_TEST_CERTIFICATE_THUMBPRINT_ALLOWLIST_JSON",
  ]) {
    assert.ok(
      text.includes(variable),
      `missing fail-closed signing allowlist: ${variable}`,
    );
  }
  assert.ok(text.includes("Test-AuthenticodeSignaturePolicy.ps1"));
});

test("wheelhouse and environment ingress share explicit archive budgets", () => {
  const text = workflowTexts.get(".github/workflows/build-app.yml");
  assert.equal((text.match(/Expand-VerifiedZip/g) ?? []).length, 2);
  for (const contract of [
    "AUTO_MAS_ARCHIVE_MAX_BYTES: 1073741824",
    "AUTO_MAS_ARCHIVE_MAX_ENTRIES: 4096",
    "AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES: 2147483648",
    "AUTO_MAS_ARCHIVE_MAX_FILE_BYTES: 536870912",
  ]) {
    assert.ok(text.includes(contract), `missing archive contract: ${contract}`);
  }
  assert.equal(text.includes("tar.exe -xf"), false);
  assert.equal(text.includes("Invoke-WebRequest -Uri"), false);
  assert.ok(text.includes("$topLevelEntries.Count -ne 1"));
  assert.ok(text.includes("$topLevelEntries[0].Name -cne 'environment'"));
});

test("legacy manual release helper is bounded and dependency-pinned", () => {
  const uploader = readFileSync(
    resolve(
      repositoryRoot,
      ".github/workflows/github_download_and_cnb_upload.py",
    ),
    "utf8",
  );
  const archiveSafety = readFileSync(
    resolve(
      repositoryRoot,
      ".github/workflows/scripts/manual_release_safety.py",
    ),
    "utf8",
  );
  const cnbRelease = readFileSync(
    resolve(repositoryRoot, ".github/workflows/cnb_release.py"),
    "utf8",
  );
  const requirements = readFileSync(
    resolve(repositoryRoot, ".github/workflows/requirements.txt"),
    "utf8",
  )
    .split(/\r?\n/u)
    .map((line) => line.trim())
    .filter((line) => line && !line.startsWith("#"));

  assert.deepEqual(requirements, [
    "certifi==2026.7.22 --hash=sha256:62f22742b58a1a33014a2b6b706588a8d7e2a88ae7bd1a6ebe8c992928483775",
    "charset-normalizer==3.4.9 --hash=sha256:4b3dac63058cc36820b0dd072f89898604e2d39686fe05321729d00d8ac185a0",
    "colorama==0.4.6 --hash=sha256:4f1d9991f5acc0ca119f9d443620b77f9d6b33703e51011c16baf57afb285fc6",
    "idna==3.18 --hash=sha256:7f952cbe720b688055e3f87de14f5c3e5fdaa8bc3928985c4077ca689de849a2",
    "requests==2.34.2 --hash=sha256:2a0d60c172f83ac6ab31e4554906c0f3b3588d37b5cb939b1c061f4907e278e0",
    "tqdm==4.69.0 --hash=sha256:9979978912be667a6ef21fd5d8abf54e324e63d82f7f43c360792ebc2bc4e622",
    "urllib3==2.7.0 --hash=sha256:9fb4c81ebbb1ce9531cce37674bbc6f1360472bc18ca9a553ede278ef7276897",
  ]);
  assert.ok(uploader.includes("extract_zip_safely("));
  assert.ok(uploader.includes("REQUEST_TIMEOUT_SECONDS = (10, 60)"));
  assert.ok(uploader.includes("ARTIFACT_ARCHIVE_BUDGETS = ArchiveBudgets()"));
  assert.equal(uploader.includes("extractall("), false);
  assert.equal(archiveSafety.includes("extractall("), false);
  assert.ok(
    archiveSafety.includes("max_archive_bytes: int = 1024 * 1024 * 1024"),
  );
  assert.ok(archiveSafety.includes("max_entries: int = 4096"));
  assert.ok(
    archiveSafety.includes("max_expanded_bytes: int = 2 * 1024 * 1024 * 1024"),
  );
  assert.ok(archiveSafety.includes("max_file_bytes: int = 512 * 1024 * 1024"));
  assert.ok(cnbRelease.includes("CNB_REQUEST_TIMEOUT_SECONDS = (10, 60)"));
  assert.ok(cnbRelease.includes("CNB_UPLOAD_TIMEOUT_SECONDS = (10, 15 * 60)"));
  assert.equal(
    (cnbRelease.match(/timeout=CNB_(?:REQUEST|UPLOAD)_TIMEOUT_SECONDS/g) ?? [])
      .length,
    5,
  );
});

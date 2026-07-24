import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDirectory = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDirectory, "..", "..", "..");
const workflowPath = ".github/workflows/build-experimental-alpha.yml";
const workflowText = readFileSync(
  resolve(repositoryRoot, workflowPath),
  "utf8",
);
const requireFromFrontend = createRequire(
  resolve(repositoryRoot, "frontend", "package.json"),
);
const { load: parseYaml } = requireFromFrontend("js-yaml");
const workflow = parseYaml(workflowText);

const actionPins = new Map([
  ["actions/checkout", "11d5960a326750d5838078e36cf38b85af677262"],
  ["actions/setup-node", "49933ea5288caeca8642d1e84afbd3f7d6820020"],
  ["actions/upload-artifact", "ea165f8d65b6e75b540449e92b4886f43607fa02"],
  ["actions/cache", "0057852bfaa89a56745cba8c7296529d2fc39830"],
  ["astral-sh/setup-uv", "08807647e7069bb48b6ef5acd8ec9567f424441b"],
]);

const runBlocks = (text) => {
  const lines = text.split(/\r?\n/u);
  const blocks = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(\s*)run:\s*\|\s*$/u);
    if (!match) continue;
    const indent = match[1].length;
    const block = [];
    for (index += 1; index < lines.length; index += 1) {
      const line = lines[index];
      if (line.trim().length !== 0 && line.match(/^\s*/u)[0].length <= indent) {
        index -= 1;
        break;
      }
      block.push(line);
    }
    blocks.push(block.join("\n"));
  }
  return blocks;
};

test("Alpha workflow is manual, scoped and Full-only", () => {
  assert.ok(workflow.on?.workflow_dispatch);
  assert.equal(workflow.on?.push, undefined);
  assert.equal(workflow.on?.pull_request, undefined);
  const job = workflow.jobs?.["alpha-full"];
  assert.ok(job);
  assert.equal(job["runs-on"], "windows-2025");
  assert.deepEqual(job.permissions, { actions: "read", contents: "read" });
  assert.match(job.if, /integration\/dev-v2-dev-all-plugins/u);
  assert.match(workflowText, /AUTO-MAS-v6-Experimental-Alpha-Full-Setup/u);
  assert.match(workflowText, /AUTO-MAS-v6-Experimental-Alpha\.exe/u);
  assert.match(workflowText, /source-provenance\.json/u);
  assert.match(
    workflowText,
    /auto-mas\.experimental-alpha\.source-provenance\/v2/u,
  );
  assert.doesNotMatch(
    workflowText,
    /auto-mas\.experimental-alpha\.source-provenance\/v1/u,
  );
  assert.match(workflowText, /EVIDENCE_INDEX\.json/u);
  assert.match(workflowText, /MANUAL_TEST_CARDS\.md/u);
  assert.match(workflowText, /verify_offline_first_start\.ps1/u);
  assert.match(workflowText, /verify_wheelhouse_snapshot\.py/u);
  assert.match(workflowText, /environment\\python\\python\.exe/u);
  assert.match(workflowText, /environment\\git\\bin\\git\.exe/u);
  assert.match(
    workflowText,
    /jrsoftware\/issrc\/683ee7eabfbce807f901c5da83fc5ff1a3ecb693\/Files\/Languages\/ChineseSimplified\.isl/u,
  );
  assert.match(
    workflowText,
    /6753be2c5e2740d859900fd902824db2ec568da5c5b52486524c9762d778b0b0/u,
  );
  assert.match(
    workflowText,
    /generate-experimental-alpha-installer\.mjs prepare/u,
  );
  assert.match(
    workflowText,
    /generate-experimental-alpha-installer\.mjs finalize/u,
  );
  assert.doesNotMatch(workflowText, /AUTO-MAS-Lite/u);
  assert.doesNotMatch(
    workflowText,
    /MirrorChyan|CNB|create-release|GitHub Release/u,
  );
  assert.doesNotMatch(workflowText, /D116A92A-E174-4699-B777-61C5FD837B19/u);
  assert.doesNotMatch(workflowText, /win-unpacked\\AUTO-MAS\.exe/u);
  assert.doesNotMatch(workflowText, /verify_r6_upgrade_rollback\.ps1/u);
  const checkout = (job.steps ?? []).find((step) =>
    step.uses?.startsWith("actions\/checkout@"),
  );
  assert.equal(checkout.with?.ref, "${{ github.sha }}");
  assert.equal(checkout.with?.["fetch-depth"], 1);
  assert.equal(job.env?.AUTO_MAS_EXPECTED_GIT_SHA, "${{ github.sha }}");
  assert.match(job.env?.AUTO_MAS_ALPHA_PROVENANCE_ROOT, /runner\.temp/u);
  for (const key of [
    "AUTO_MAS_RELEASE_OUTPUT_ROOT",
    "ALPHA_ARTIFACT_ROOT",
    "AUTO_MAS_ENVIRONMENT_ARCHIVE",
  ]) {
    assert.match(
      job.env?.[key],
      /runner\.temp/u,
      `${key} must stay outside checkout`,
    );
    assert.doesNotMatch(job.env?.[key], /github\.workspace/u);
  }
  assert.match(
    workflowText,
    /generate-experimental-alpha-installer\.mjs verify-stage/u,
  );
});

test("Alpha workflow actions and shell interpolation remain pinned and safe", () => {
  const steps = workflow.jobs?.["alpha-full"]?.steps ?? [];
  for (const step of steps) {
    if (!step.uses) continue;
    const match = step.uses.match(/^([^@]+)@([0-9a-f]{40})$/u);
    assert.ok(match, `mutable or malformed action reference: ${step.uses}`);
    assert.equal(
      match[2],
      actionPins.get(match[1]),
      `unexpected action pin for ${match[1]}`,
    );
  }
  for (const block of runBlocks(workflowText)) {
    assert.equal(
      block.includes("${{"),
      false,
      "workflow expression interpolated into a run block",
    );
  }
});

test("Alpha workflow uploads exactly one evidence-bearing Actions artifact", () => {
  const uploadSteps = (workflow.jobs?.["alpha-full"]?.steps ?? []).filter(
    (step) => step.uses?.startsWith("actions/upload-artifact@"),
  );
  assert.equal(uploadSteps.length, 1);
  assert.equal(uploadSteps[0].with?.name, "auto-mas-v6-experimental-alpha");
  assert.equal(uploadSteps[0].with?.path, "${{ env.ALPHA_ARTIFACT_ROOT }}");
  assert.equal(uploadSteps[0].with?.["if-no-files-found"], "error");
  assert.equal(uploadSteps[0].with?.["retention-days"], 30);
});

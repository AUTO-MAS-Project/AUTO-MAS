import assert from "node:assert/strict";
import { existsSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";

import {
  appendGithubOutput,
  buildReleaseMetadata,
  validateVersionTag,
  writeReleaseMetadata,
} from "./release-metadata.mjs";

function parseMultilineOutput(text, name) {
  const header = text.match(new RegExp(`(?:^|\\n)${name}<<([^\\r\\n]+)\\n`));
  assert.ok(header, `missing ${name} output`);
  const delimiter = header[1];
  const valueStart = header.index + header[0].length;
  const terminator = `\n${delimiter}\n`;
  const valueEnd = text.indexOf(terminator, valueStart);
  assert.notEqual(valueEnd, -1, `missing ${name} terminator`);
  return { delimiter, value: text.slice(valueStart, valueEnd) };
}

test("writes an unguessable delimiter and preserves hostile changelog text exactly", () => {
  const root = mkdtempSync(join(tmpdir(), "auto-mas-release-metadata-"));
  const versionPath = join(root, "version.json");
  const outputPath = join(root, "github-output.txt");
  const metadataDirectory = join(root, "metadata");
  const markerPath = join(root, "must-not-exist");
  const hostileEntries = [
    "EOF",
    "AUTO_MAS_deadbeef",
    "$(New-Item injected)",
    "`touch injected`",
    '"; Write-Output PWNED; #',
    "${{ secrets.SIGNPATH_API_TOKEN }}",
    `two lines\nEOF\nthird line`,
  ];
  writeFileSync(
    versionPath,
    JSON.stringify({
      version: "v6.0.0-alpha.SECURITY.1",
      version_info: {
        "v6.0.0-alpha.SECURITY.1": {
          Security: hostileEntries,
        },
      },
    }),
    "utf8",
  );

  const metadata = writeReleaseMetadata({
    versionPath,
    githubOutputPath: outputPath,
    metadataDirectory,
  });
  const output = readFileSync(outputPath, "utf8");
  const parsed = parseMultilineOutput(output, "version_changelog");

  assert.notEqual(parsed.delimiter, "EOF");
  assert.ok(parsed.delimiter.startsWith("AUTO_MAS_"));
  assert.equal(parsed.value, metadata.changelog);
  assert.ok(parsed.value.includes("\n- EOF\n"));
  assert.ok(parsed.value.includes("${{ secrets.SIGNPATH_API_TOKEN }}"));
  assert.equal(
    readFileSync(join(metadataDirectory, "RELEASE_NOTES.md"), "utf8"),
    metadata.changelog,
  );
  assert.equal(existsSync(markerPath), false);
});

test("rejects unsafe release tags before writing outputs", () => {
  for (const tag of [
    "v1.2",
    "v1.2.3;echo-pwned",
    "v1.2.3/../../main",
    "v1.2.3 beta",
    "v01.2.3",
    "v1.2.3+build",
    "v1.2.3-",
  ]) {
    assert.throws(() => validateVersionTag(tag));
  }
  assert.equal(
    validateVersionTag("v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1"),
    "v6.0.0-alpha.NEXUS-OVERDRIVE.20260722.1",
  );
});

test("derives only the two approved signing policies", () => {
  const stable = buildReleaseMetadata({
    version: "v6.0.0",
    version_info: { "v6.0.0": { Fixes: ["stable"] } },
  });
  const alpha = buildReleaseMetadata({
    version: "v6.0.0-alpha.1",
    version_info: { "v6.0.0-alpha.1": { Fixes: ["alpha"] } },
  });
  assert.deepEqual(
    [
      stable.isPrerelease,
      stable.signingPolicy,
      alpha.isPrerelease,
      alpha.signingPolicy,
    ],
    [false, "release-signing", true, "test-signing"],
  );
});

test("single-line outputs reject line injection", () => {
  const root = mkdtempSync(join(tmpdir(), "auto-mas-release-output-"));
  const outputPath = join(root, "github-output.txt");
  assert.throws(() =>
    appendGithubOutput(outputPath, "version_tag", "v1.2.3\nPWNED=true"),
  );
  assert.equal(existsSync(outputPath), false);
});

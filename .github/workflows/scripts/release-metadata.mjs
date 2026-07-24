import { randomBytes } from "node:crypto";
import {
  mkdirSync,
  readFileSync,
  writeFileSync,
  appendFileSync,
} from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const VERSION_TAG_PATTERN =
  /^v?(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?$/;
const MAX_VERSION_TAG_LENGTH = 128;
const MAX_CHANGELOG_BYTES = 1024 * 1024;

function assertPlainObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
}

function assertSafeText(value, label) {
  if (typeof value !== "string") {
    throw new Error(`${label} must be a string`);
  }
  if (value.includes("\0")) {
    throw new Error(`${label} must not contain NUL`);
  }
}

export function validateVersionTag(value) {
  assertSafeText(value, "version");
  if (value.length === 0 || value.length > MAX_VERSION_TAG_LENGTH) {
    throw new Error(
      `version must be between 1 and ${MAX_VERSION_TAG_LENGTH} characters`,
    );
  }
  if (!VERSION_TAG_PATTERN.test(value)) {
    throw new Error(
      `version is not an allowed AUTO-MAS release tag: ${JSON.stringify(value)}`,
    );
  }
  return value;
}

export function buildReleaseMetadata(versionDocument) {
  assertPlainObject(versionDocument, "version document");
  const versionTag = validateVersionTag(versionDocument.version);
  assertPlainObject(versionDocument.version_info, "version_info");

  const mergedSections = new Map();
  for (const [releaseName, releaseInfo] of Object.entries(
    versionDocument.version_info,
  )) {
    assertSafeText(releaseName, "version_info release name");
    assertPlainObject(releaseInfo, `version_info.${releaseName}`);
    for (const [sectionName, entries] of Object.entries(releaseInfo)) {
      assertSafeText(sectionName, `version_info.${releaseName} section name`);
      if (sectionName.includes("\r") || sectionName.includes("\n")) {
        throw new Error(
          `version_info.${releaseName} section name must be single-line`,
        );
      }
      if (!Array.isArray(entries)) {
        throw new Error(
          `version_info.${releaseName}.${sectionName} must be an array`,
        );
      }
      const target = mergedSections.get(sectionName) ?? [];
      for (const [index, entry] of entries.entries()) {
        assertSafeText(
          entry,
          `version_info.${releaseName}.${sectionName}[${index}]`,
        );
        target.push(entry.replace(/\r\n?/g, "\n"));
      }
      mergedSections.set(sectionName, target);
    }
  }

  let markdown = `<!--${JSON.stringify(versionDocument.version_info)}-->\n`;
  for (const [sectionName, entries] of mergedSections.entries()) {
    markdown += `## ${sectionName}\n`;
    for (const entry of entries) {
      markdown += `- ${entry}\n`;
    }
  }
  markdown = markdown.replace(/\r\n?/g, "\n");
  if (Buffer.byteLength(markdown, "utf8") > MAX_CHANGELOG_BYTES) {
    throw new Error(
      `release changelog exceeds ${MAX_CHANGELOG_BYTES} UTF-8 bytes`,
    );
  }

  const normalizedVersionTag = versionTag.replace(/^v/, "");
  const isPrerelease = normalizedVersionTag.includes("-");
  return {
    versionTag,
    isPrerelease,
    signingPolicy: isPrerelease ? "test-signing" : "release-signing",
    changelog: markdown,
  };
}

function createDelimiter(value) {
  const lines = new Set(value.replace(/\r\n?/g, "\n").split("\n"));
  for (;;) {
    const delimiter = `AUTO_MAS_${randomBytes(24).toString("hex")}`;
    if (!lines.has(delimiter)) {
      return delimiter;
    }
  }
}

export function appendGithubOutput(
  outputPath,
  name,
  value,
  { multiline = false } = {},
) {
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
    throw new Error(`invalid GitHub output name: ${JSON.stringify(name)}`);
  }
  assertSafeText(value, `GitHub output ${name}`);
  if (!multiline) {
    if (value.includes("\r") || value.includes("\n")) {
      throw new Error(
        `single-line GitHub output ${name} contains a line break`,
      );
    }
    appendFileSync(outputPath, `${name}=${value}\n`, "utf8");
    return;
  }

  const normalizedValue = value.replace(/\r\n?/g, "\n");
  const delimiter = createDelimiter(normalizedValue);
  appendFileSync(
    outputPath,
    `${name}<<${delimiter}\n${normalizedValue}\n${delimiter}\n`,
    "utf8",
  );
}

export function writeReleaseMetadata({
  versionPath,
  githubOutputPath,
  metadataDirectory,
}) {
  if (!githubOutputPath) {
    throw new Error("GITHUB_OUTPUT is required");
  }
  const versionDocument = JSON.parse(readFileSync(versionPath, "utf8"));
  const metadata = buildReleaseMetadata(versionDocument);

  mkdirSync(dirname(githubOutputPath), { recursive: true });
  mkdirSync(metadataDirectory, { recursive: true });
  appendGithubOutput(githubOutputPath, "version_tag", metadata.versionTag);
  appendGithubOutput(
    githubOutputPath,
    "is_prerelease",
    String(metadata.isPrerelease),
  );
  appendGithubOutput(
    githubOutputPath,
    "signing_policy",
    metadata.signingPolicy,
  );
  appendGithubOutput(
    githubOutputPath,
    "version_changelog",
    metadata.changelog,
    { multiline: true },
  );

  writeFileSync(
    resolve(metadataDirectory, "RELEASE_NOTES.md"),
    metadata.changelog,
    "utf8",
  );
  writeFileSync(
    resolve(metadataDirectory, "release-metadata.json"),
    `${JSON.stringify(
      {
        version_tag: metadata.versionTag,
        is_prerelease: metadata.isPrerelease,
        signing_policy: metadata.signingPolicy,
      },
      null,
      2,
    )}\n`,
    "utf8",
  );
  return metadata;
}

function readArgument(name) {
  const index = process.argv.indexOf(name);
  if (index === -1 || index === process.argv.length - 1) {
    throw new Error(`missing required argument: ${name}`);
  }
  return process.argv[index + 1];
}

const currentFile = fileURLToPath(import.meta.url);
if (process.argv[1] && resolve(process.argv[1]) === resolve(currentFile)) {
  writeReleaseMetadata({
    versionPath: resolve(readArgument("--version-file")),
    githubOutputPath: resolve(readArgument("--github-output")),
    metadataDirectory: resolve(readArgument("--metadata-dir")),
  });
}

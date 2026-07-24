const { spawnSync } = require('node:child_process')
const { createHash } = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')
const { experimentalAlphaIdentity } = require('./scripts/experimental-alpha-release-identity.cjs')
const {
  assertWheelhouseProvenanceMatchesDirectory,
} = require('./scripts/alpha-wheelhouse-provenance.cjs')

const frontendDirectory = __dirname
const packageJson = require('./package.json')
const defaultFrozenReleaseDirectory = path.resolve(
  frontendDirectory,
  '..',
  '..',
  '..',
  '..',
  '_alpha_build',
  'a1',
  'release-nexus-a1-r6'
)

const pathEntryExists = value => {
  try {
    fs.lstatSync(value)
    return true
  } catch (error) {
    if (error?.code === 'ENOENT') return false
    throw error
  }
}

const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const SHA256_PATTERN = /^[0-9a-f]{64}$/iu
const GIT_SHA_PATTERN = /^[0-9a-f]{40}$/iu
const ALPHA_SOURCE_PROVENANCE_SCHEMA = 'auto-mas.experimental-alpha.source-provenance/v2'
const ALPHA_CI_GATES_SCHEMA = 'auto-mas.experimental-alpha.ci-gates/v1'
const ALPHA_EVIDENCE_FILENAMES = Object.freeze([
  'ALPHA_README.md',
  'RELEASE_NOTES.md',
  'KNOWN_GAPS.md',
  'MANUAL_TEST_CARDS.md',
  'OFFLINE_FIRST_START.md',
  'CI_GATES.json',
])

const sha256File = filePath => createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')

const requireExperimentalAlphaSnapshotPolicy = () => {
  const snapshotPath = path.resolve(frontendDirectory, '..', 'res', 'integration-snapshot.json')
  let snapshot
  try {
    snapshot = JSON.parse(fs.readFileSync(snapshotPath, 'utf8'))
  } catch (error) {
    throw new Error(`Experimental Alpha snapshot policy cannot be read: ${error.message}`)
  }
  if (!isRecord(snapshot)) {
    throw new Error('Experimental Alpha snapshot policy must be a JSON object')
  }
  if (snapshot.version !== packageJson.version) {
    throw new Error('Experimental Alpha snapshot version must equal frontend package.json version')
  }
  const policy = snapshot.release_policy
  if (!isRecord(policy)) {
    throw new Error('Experimental Alpha snapshot must declare release_policy')
  }
  if (policy.channel !== experimentalAlphaIdentity.releaseChannel) {
    throw new Error(
      'Experimental Alpha snapshot release_policy.channel does not match package identity'
    )
  }
  if (policy.embedded_updater !== 'manual-only') {
    throw new Error(
      'Experimental Alpha snapshot must set release_policy.embedded_updater to manual-only'
    )
  }
  return Object.freeze({
    channel: policy.channel,
    embeddedUpdater: policy.embedded_updater,
  })
}

const requireAlphaSourceProvenance = () => {
  const provenancePath = requireAbsoluteEnvironmentPath('AUTO_MAS_ALPHA_PROVENANCE_FILE')
  let provenance
  try {
    provenance = JSON.parse(fs.readFileSync(provenancePath, 'utf8'))
  } catch (error) {
    throw new Error(`Experimental Alpha source provenance cannot be read: ${error.message}`)
  }
  if (!isRecord(provenance) || provenance.schema !== ALPHA_SOURCE_PROVENANCE_SCHEMA) {
    throw new Error('Experimental Alpha source provenance has an unexpected schema')
  }
  if (!isRecord(provenance.git) || !GIT_SHA_PATTERN.test(provenance.git.head_sha ?? '')) {
    throw new Error('Experimental Alpha source provenance must contain a valid Git HEAD')
  }
  if (!['clean', 'dirty-captured'].includes(provenance.git.worktree_state)) {
    throw new Error('Experimental Alpha source provenance must declare the captured worktree state')
  }
  if (
    !isRecord(provenance.source_input_tree) ||
    !SHA256_PATTERN.test(provenance.source_input_tree.sha256 ?? '')
  ) {
    throw new Error('Experimental Alpha source provenance must contain an input tree SHA256')
  }
  assertWheelhouseProvenanceMatchesDirectory(provenance.external_wheelhouse, wheelhouseDirectory)
  const expectedGitSha = process.env.AUTO_MAS_EXPECTED_GIT_SHA?.trim().toLowerCase()
  if (expectedGitSha && provenance.git.head_sha.toLowerCase() !== expectedGitSha) {
    throw new Error(
      'Experimental Alpha source provenance Git HEAD does not match AUTO_MAS_EXPECTED_GIT_SHA'
    )
  }
  return Object.freeze({
    path: provenancePath,
    sha256: sha256File(provenancePath),
    document: provenance,
  })
}

const realpath = value =>
  typeof fs.realpathSync.native === 'function'
    ? fs.realpathSync.native(value)
    : fs.realpathSync(value)

const canonicalizeFilesystemPath = value => {
  const resolvedPath = path.resolve(value)
  const missingSegments = []
  let existingAncestor = resolvedPath
  while (!pathEntryExists(existingAncestor)) {
    const parentDirectory = path.dirname(existingAncestor)
    if (parentDirectory === existingAncestor) {
      throw new Error(`Cannot resolve an existing ancestor for path: ${resolvedPath}`)
    }
    missingSegments.unshift(path.basename(existingAncestor))
    existingAncestor = parentDirectory
  }
  let canonicalAncestor
  try {
    canonicalAncestor = realpath(existingAncestor)
  } catch (error) {
    throw new Error(`Cannot resolve physical path ${existingAncestor}: ${error}`)
  }
  return path.resolve(canonicalAncestor, ...missingSegments)
}

const normalizePathForComparison = value => {
  const normalized = path.normalize(value)
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized
}

const isSameOrNested = (parentPath, candidatePath) => {
  const parentKey = normalizePathForComparison(parentPath)
  const candidateKey = normalizePathForComparison(candidatePath)
  const relative = path.relative(parentKey, candidateKey)
  return (
    relative === '' ||
    (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
  )
}

const requireAbsoluteEnvironmentPath = name => {
  const value = process.env[name]?.trim()
  if (!value) throw new Error(`${name} is required for an integration release`)
  if (!path.isAbsolute(value)) throw new Error(`${name} must be an absolute path`)
  return canonicalizeFilesystemPath(value)
}

const requireAlphaEvidenceSource = () => {
  const evidenceDirectory = canonicalizeFilesystemPath(
    path.resolve(frontendDirectory, '..', 'docs', 'experimental-alpha')
  )
  const directoryStats = fs.lstatSync(evidenceDirectory)
  if (directoryStats.isSymbolicLink() || !directoryStats.isDirectory()) {
    throw new Error('Experimental Alpha evidence source must be a regular directory')
  }

  for (const filename of ALPHA_EVIDENCE_FILENAMES) {
    const candidate = path.join(evidenceDirectory, filename)
    if (!pathEntryExists(candidate)) {
      throw new Error(`Experimental Alpha evidence source is missing: ${filename}`)
    }
    const stats = fs.lstatSync(candidate)
    if (stats.isSymbolicLink() || !stats.isFile()) {
      throw new Error(`Experimental Alpha evidence source must be a regular file: ${filename}`)
    }
  }

  let ciGates
  try {
    ciGates = JSON.parse(fs.readFileSync(path.join(evidenceDirectory, 'CI_GATES.json'), 'utf8'))
  } catch (error) {
    throw new Error(`Experimental Alpha CI gates cannot be read: ${error.message}`)
  }
  if (!isRecord(ciGates) || ciGates.schema !== ALPHA_CI_GATES_SCHEMA) {
    throw new Error('Experimental Alpha CI gates have an unexpected schema')
  }
  return Object.freeze({ directory: evidenceDirectory })
}

const wheelhouseDirectory = requireAbsoluteEnvironmentPath('AUTO_MAS_WHEELHOUSE_ROOT')
const outputDirectory = requireAbsoluteEnvironmentPath('AUTO_MAS_RELEASE_OUTPUT_ROOT')
const protectedReleaseDirectories = [
  ...(pathEntryExists(defaultFrozenReleaseDirectory) ? [defaultFrozenReleaseDirectory] : []),
  ...(process.env.AUTO_MAS_PROTECTED_RELEASE_ROOTS ?? '')
    .split(path.delimiter)
    .map(value => value.trim())
    .filter(Boolean),
].map(canonicalizeFilesystemPath)

if (!fs.existsSync(wheelhouseDirectory) || !fs.statSync(wheelhouseDirectory).isDirectory()) {
  throw new Error(`AUTO_MAS_WHEELHOUSE_ROOT is not a directory: ${wheelhouseDirectory}`)
}
if (
  normalizePathForComparison(outputDirectory) ===
  normalizePathForComparison(path.parse(outputDirectory).root)
) {
  throw new Error('AUTO_MAS_RELEASE_OUTPUT_ROOT cannot be a filesystem root')
}
if (pathEntryExists(outputDirectory)) {
  throw new Error(`AUTO_MAS_RELEASE_OUTPUT_ROOT already exists: ${outputDirectory}`)
}
if (
  isSameOrNested(wheelhouseDirectory, outputDirectory) ||
  isSameOrNested(outputDirectory, wheelhouseDirectory)
) {
  throw new Error('Release output must not overlap the wheelhouse')
}
if (
  protectedReleaseDirectories.some(
    protectedDirectory =>
      isSameOrNested(protectedDirectory, outputDirectory) ||
      isSameOrNested(outputDirectory, protectedDirectory)
  )
) {
  throw new Error('Release output must not overlap a protected release directory')
}
if (typeof packageJson.version !== 'string' || !/^v?6\..*alpha/iu.test(packageJson.version)) {
  throw new Error('electron-builder.integration.cjs only packages v6 alpha releases')
}
const experimentalAlphaSnapshotPolicy = requireExperimentalAlphaSnapshotPolicy()
const experimentalAlphaSourceProvenance = requireAlphaSourceProvenance()
const experimentalAlphaEvidenceSource = requireAlphaEvidenceSource()

const validation = spawnSync(
  process.execPath,
  [
    path.join(frontendDirectory, 'scripts', 'validate-wheelhouse.mjs'),
    '--wheelhouse',
    wheelhouseDirectory,
    '--require-snapshot-contract',
  ],
  {
    cwd: frontendDirectory,
    env: process.env,
    shell: false,
    stdio: 'inherit',
    timeout: 10 * 60_000,
  }
)
if (validation.error) {
  if (validation.error.code === 'ETIMEDOUT') {
    throw new Error('Integration wheelhouse validation timed out after 600000 ms')
  }
  throw new Error(`Integration wheelhouse validation failed to start: ${validation.error.message}`)
}
if (validation.status !== 0) {
  throw new Error(
    `Integration wheelhouse validation failed with exit code ${validation.status ?? '<unknown>'}`
  )
}

const baseBuild = packageJson.build
const matchingResources = baseBuild.extraResources.filter(
  resource => resource.to === 'integration-snapshot/plugins/wheels'
)
if (matchingResources.length !== 1) {
  throw new Error('package.json must declare exactly one bundled wheelhouse resource')
}
const matchingScriptResources = baseBuild.extraResources.filter(
  resource => resource.to === 'integration-snapshot/scripts'
)
if (matchingScriptResources.length !== 1) {
  throw new Error('package.json must declare exactly one bundled scripts resource')
}

module.exports = {
  ...baseBuild,
  appId: experimentalAlphaIdentity.appId,
  productName: experimentalAlphaIdentity.productName,
  artifactName: `${experimentalAlphaIdentity.artifactStem}-\${version}-\${arch}.\${ext}`,
  extraMetadata: {
    ...baseBuild.extraMetadata,
    productName: experimentalAlphaIdentity.productName,
    autoMasReleaseChannel: experimentalAlphaSnapshotPolicy.channel,
    autoMasEmbeddedUpdatePolicy: experimentalAlphaSnapshotPolicy.embeddedUpdater,
    autoMasSourceInputTreeSha256:
      experimentalAlphaSourceProvenance.document.source_input_tree.sha256,
    autoMasWheelhouseTreeSha256:
      experimentalAlphaSourceProvenance.document.external_wheelhouse.tree_sha256,
  },
  directories: {
    ...baseBuild.directories,
    output: outputDirectory,
  },
  win: {
    ...baseBuild.win,
    executableName: experimentalAlphaIdentity.executableName,
    // Alpha 不发布到正式签名渠道；禁用 rcedit/winCodeSign 可让无符号链接权限的测试机构建 --dir。
    signAndEditExecutable: false,
  },
  nsis: {
    ...baseBuild.nsis,
    oneClick: false,
    allowToChangeInstallationDirectory: false,
    deleteAppDataOnUninstall: false,
    shortcutName: experimentalAlphaIdentity.productName,
    uninstallDisplayName: experimentalAlphaIdentity.productName,
  },
  extraResources: [
    ...baseBuild.extraResources.map(resource => {
      if (resource.to === 'integration-snapshot/plugins/wheels') {
        return { ...resource, from: wheelhouseDirectory }
      }
      if (resource.to === 'integration-snapshot/scripts') {
        return {
          ...resource,
          filter: ['verify_offline_first_start.ps1', 'verify_wheelhouse_snapshot.py'],
        }
      }
      return resource
    }),
    {
      from: experimentalAlphaSourceProvenance.path,
      to: 'integration-snapshot/source-provenance.json',
    },
    {
      from: experimentalAlphaEvidenceSource.directory,
      to: 'integration-snapshot/evidence',
      filter: [...ALPHA_EVIDENCE_FILENAMES],
    },
  ],
}

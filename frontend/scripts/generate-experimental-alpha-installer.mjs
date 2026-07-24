#!/usr/bin/env node

import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import wheelhouseProvenance from './alpha-wheelhouse-provenance.cjs'

const require = createRequire(import.meta.url)
const {
  experimentalAlphaIdentity,
  assertExperimentalAlphaIdentity,
} = require('./experimental-alpha-release-identity.cjs')

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')
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
const MANIFEST_SCHEMA = 'auto-mas.experimental-alpha.release-manifest/v1'
const SOURCE_PROVENANCE_SCHEMA = 'auto-mas.experimental-alpha.source-provenance/v2'
const EVIDENCE_INDEX_SCHEMA = 'auto-mas.experimental-alpha.evidence-index/v1'
const ALPHA_CI_GATES_SCHEMA = 'auto-mas.experimental-alpha.ci-gates/v1'
const SHA256_PATTERN = /^[0-9a-f]{64}$/iu
const GIT_SHA_PATTERN = /^[0-9a-f]{40}$/iu
const SAFE_VERSION_PATTERN = /^[0-9A-Za-z][0-9A-Za-z._-]{0,119}$/u
const isRecord = value => value !== null && typeof value === 'object' && !Array.isArray(value)
const ALPHA_EVIDENCE_FILENAMES = Object.freeze([
  'ALPHA_README.md',
  'RELEASE_NOTES.md',
  'KNOWN_GAPS.md',
  'MANUAL_TEST_CARDS.md',
  'OFFLINE_FIRST_START.md',
  'CI_GATES.json',
])
const EVIDENCE_INDEX_FILENAME = 'EVIDENCE_INDEX.json'
const stageEvidenceRelativePath = filename => `resources/integration-snapshot/evidence/${filename}`
const STAGE_EVIDENCE_INDEXED_PATHS = Object.freeze([
  'resources/app.asar',
  'resources/integration-snapshot/manifest.json',
  'resources/integration-snapshot/source-provenance.json',
  'resources/integration-snapshot/plugins/wheels/manifest.json',
  'resources/integration-snapshot/plugins/wheels/runtime-lock.json',
  'resources/integration-snapshot/scripts/verify_offline_first_start.ps1',
  'resources/integration-snapshot/scripts/verify_wheelhouse_snapshot.py',
  ...ALPHA_EVIDENCE_FILENAMES.map(stageEvidenceRelativePath),
])
const toPosixPath = value => value.split(path.sep).join('/')

const normalizePathForComparison = value => {
  const normalized = path.normalize(value)
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized
}

const isSameOrNested = (parentPath, candidatePath) => {
  const relative = path.relative(
    normalizePathForComparison(parentPath),
    normalizePathForComparison(candidatePath)
  )
  return (
    relative === '' ||
    (!relative.startsWith(`..${path.sep}`) && relative !== '..' && !path.isAbsolute(relative))
  )
}

const ensureFreshDirectory = directory => {
  if (fs.existsSync(directory)) {
    throw new Error(`Alpha artifact output already exists: ${directory}`)
  }
  fs.mkdirSync(directory, { recursive: true })
}

const requireArgument = (value, name) => {
  if (typeof value !== 'string' || value.trim().length === 0) {
    throw new Error(`${name} requires a non-empty value`)
  }
  return value.trim()
}

const requireSafeVersion = value => {
  const version = requireArgument(value, '--version')
  if (!SAFE_VERSION_PATTERN.test(version) || version.includes('..')) {
    throw new Error('--version must be a safe release filename component')
  }
  return version
}

const requireSha256 = (value, name) => {
  const hash = requireArgument(value, name).toLowerCase()
  if (!SHA256_PATTERN.test(hash)) throw new Error(`${name} must be a SHA-256 hexadecimal value`)
  return hash
}

const requireGitSha = value => {
  const hash = requireArgument(value, '--git-sha').toLowerCase()
  if (!GIT_SHA_PATTERN.test(hash)) throw new Error('--git-sha must be a 40 character commit SHA')
  return hash
}

const splitSafeStageRelativePath = relativePath => {
  const segments = relativePath.split('/')
  if (!relativePath || segments.some(segment => !segment || segment === '.' || segment === '..')) {
    throw new Error(`Alpha stage path must be a safe relative path: ${relativePath}`)
  }
  return segments
}

const requireRegularStagePath = (stageDirectory, relativePath, expectedType) => {
  const stageStats = fs.lstatSync(stageDirectory)
  if (stageStats.isSymbolicLink() || !stageStats.isDirectory()) {
    throw new Error(`Alpha win-unpacked stage must be a regular directory: ${stageDirectory}`)
  }
  const segments = splitSafeStageRelativePath(relativePath)
  let candidate = stageDirectory
  for (const [index, segment] of segments.entries()) {
    candidate = path.join(candidate, segment)
    if (!fs.existsSync(candidate)) {
      throw new Error(`Alpha Full stage is missing required file: ${relativePath}`)
    }
    const stats = fs.lstatSync(candidate)
    if (stats.isSymbolicLink()) {
      throw new Error(`Alpha Full stage refuses symbolic links: ${relativePath}`)
    }
    const isFinalPath = index === segments.length - 1
    if (!isFinalPath && !stats.isDirectory()) {
      throw new Error(`Alpha Full stage requires a regular directory: ${relativePath}`)
    }
    if (
      isFinalPath &&
      ((expectedType === 'file' && !stats.isFile()) ||
        (expectedType === 'directory' && !stats.isDirectory()))
    ) {
      throw new Error(`Alpha Full stage requires a regular ${expectedType}: ${relativePath}`)
    }
  }
  return candidate
}

const requireRegularStageFile = (stageDirectory, relativePath) =>
  requireRegularStagePath(stageDirectory, relativePath, 'file')

const requireRegularStageDirectory = (stageDirectory, relativePath) =>
  requireRegularStagePath(stageDirectory, relativePath, 'directory')

const requireStageDirectory = stageDirectory => {
  const resolved = path.resolve(requireArgument(stageDirectory, '--stage'))
  if (!fs.existsSync(resolved)) {
    throw new Error(`Alpha win-unpacked stage does not exist: ${resolved}`)
  }
  const stageStats = fs.lstatSync(resolved)
  if (stageStats.isSymbolicLink() || !stageStats.isDirectory()) {
    throw new Error(`Alpha win-unpacked stage must be a regular directory: ${resolved}`)
  }
  const identity = assertExperimentalAlphaIdentity()
  const requiredPaths = [
    `${identity.executableName}.exe`,
    'resources/app.asar',
    'resources/integration-snapshot/manifest.json',
    'resources/integration-snapshot/source-provenance.json',
    'resources/integration-snapshot/plugins/wheels/manifest.json',
    'resources/integration-snapshot/plugins/wheels/runtime-lock.json',
    'resources/integration-snapshot/scripts/verify_offline_first_start.ps1',
    'resources/integration-snapshot/scripts/verify_wheelhouse_snapshot.py',
    ...ALPHA_EVIDENCE_FILENAMES.map(stageEvidenceRelativePath),
    'environment/python/python.exe',
    'environment/python/Scripts/uv.exe',
    'environment/git/bin/git.exe',
    'resources/assets/AUTO-MAS.ico',
  ]
  for (const relativePath of requiredPaths) {
    requireRegularStageFile(resolved, relativePath)
  }
  return resolved
}

const ensureSafeOutputDirectory = (outputDirectory, stageDirectory, protectedDirectories) => {
  const resolved = path.resolve(requireArgument(outputDirectory, '--output'))
  const root = path.parse(resolved).root
  if (normalizePathForComparison(resolved) === normalizePathForComparison(root)) {
    throw new Error('Alpha artifact output cannot be a filesystem root')
  }
  if (isSameOrNested(stageDirectory, resolved) || isSameOrNested(resolved, stageDirectory)) {
    throw new Error('Alpha artifact output must not overlap win-unpacked')
  }
  for (const protectedDirectory of protectedDirectories) {
    if (
      fs.existsSync(protectedDirectory) &&
      (isSameOrNested(path.resolve(protectedDirectory), resolved) ||
        isSameOrNested(resolved, path.resolve(protectedDirectory)))
    ) {
      throw new Error(
        `Alpha artifact output must not overlap protected release directory: ${protectedDirectory}`
      )
    }
  }
  return resolved
}

const toInnoValue = value => {
  if (/["\r\n]/u.test(value)) {
    throw new Error('Inno value contains an unsafe quote or newline')
  }
  return value
}

export const fullInstallerFilename = version =>
  `${experimentalAlphaIdentity.artifactStem}-Full-Setup-${requireSafeVersion(version)}-x64.exe`

export const fullArchiveFilename = version =>
  `${experimentalAlphaIdentity.artifactStem}-Full-${requireSafeVersion(version)}-x64.zip`

export const sha256SumsFilename = version =>
  `${experimentalAlphaIdentity.artifactStem}-SHA256SUMS-${requireSafeVersion(version)}.txt`

export const createInstallerScript = ({ stageDirectory, artifactDirectory, version }) => {
  const identity = assertExperimentalAlphaIdentity()
  const installerBaseName = path.basename(fullInstallerFilename(version), '.exe')
  const stage = toInnoValue(stageDirectory)
  const output = toInnoValue(artifactDirectory)
  return `#define MyAppName "${identity.productName}"
#define MyAppVersion "${toInnoValue(version)}"
#define MyAppPublisher "AUTO-MAS Team"
#define MyAppURL "https://auto-mas.top/"
#define MyAppExeName "${identity.executableName}.exe"
#define MyAppPath "${stage}"

[Setup]
AppId={{${identity.innoAppId}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\\${identity.installDirectoryName}
UninstallDisplayIcon={app}\\{#MyAppExeName}
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
PrivilegesRequired=admin
OutputDir=${output}
OutputBaseFilename=${installerBaseName}
SetupIconFile={#MyAppPath}\\resources\\assets\\AUTO-MAS.ico
SolidCompression=yes
WizardStyle=modern
AppMutex=${identity.installerMutex}
CloseApplications=yes
CloseApplicationsFilter={#MyAppExeName}

[Languages]
Name: "Chinese"; MessagesFile: "compiler:Languages\\ChineseSimplified.isl"
Name: "English"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#MyAppPath}\\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"
Name: "{autodesktop}\\{#MyAppName}"; Filename: "{app}\\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall runascurrentuser
`
}

const sha256File = filePath => createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')

const requireStageSourceProvenance = stageDirectory => {
  const provenancePath = requireRegularStageFile(
    stageDirectory,
    'resources/integration-snapshot/source-provenance.json'
  )
  let provenance
  try {
    provenance = JSON.parse(fs.readFileSync(provenancePath, 'utf8'))
  } catch (error) {
    throw new Error(`Alpha stage source provenance cannot be read: ${error.message}`)
  }
  if (
    !isRecord(provenance) ||
    provenance.schema !== SOURCE_PROVENANCE_SCHEMA ||
    !isRecord(provenance.git) ||
    !GIT_SHA_PATTERN.test(provenance.git.head_sha ?? '') ||
    !isRecord(provenance.source_input_tree) ||
    !SHA256_PATTERN.test(provenance.source_input_tree.sha256 ?? '')
  ) {
    throw new Error('Alpha stage source provenance has an unexpected schema or identity')
  }
  if (!['clean', 'dirty-captured'].includes(provenance.git.worktree_state)) {
    throw new Error('Alpha stage source provenance must declare its captured worktree state')
  }
  wheelhouseProvenance.assertWheelhouseProvenanceMatchesDirectory(
    provenance.external_wheelhouse,
    path.join(stageDirectory, 'resources', 'integration-snapshot', 'plugins', 'wheels'),
    { requirePathMatch: false }
  )
  return {
    path: provenancePath,
    sha256: sha256File(provenancePath),
    document: provenance,
  }
}

const writeNewJson = (targetPath, document) => {
  if (fs.existsSync(targetPath))
    throw new Error(`Refusing to overwrite Alpha evidence: ${targetPath}`)
  fs.writeFileSync(targetPath, `${JSON.stringify(document, null, 2)}\n`, 'utf8')
}

const writeNewText = (targetPath, value) => {
  if (fs.existsSync(targetPath))
    throw new Error(`Refusing to overwrite Alpha evidence: ${targetPath}`)
  fs.writeFileSync(targetPath, value, 'utf8')
}

const requireStageEvidenceBundle = stageDirectory => {
  const directory = requireRegularStageDirectory(
    stageDirectory,
    'resources/integration-snapshot/evidence'
  )
  const files = ALPHA_EVIDENCE_FILENAMES.map(filename => ({
    filename,
    relativePath: stageEvidenceRelativePath(filename),
    path: requireRegularStageFile(stageDirectory, stageEvidenceRelativePath(filename)),
  }))
  let ciGates
  try {
    ciGates = JSON.parse(fs.readFileSync(path.join(directory, 'CI_GATES.json'), 'utf8'))
  } catch (error) {
    throw new Error(`Alpha Full stage CI gates cannot be read: ${error.message}`)
  }
  if (!isRecord(ciGates) || ciGates.schema !== ALPHA_CI_GATES_SCHEMA) {
    throw new Error('Alpha Full stage CI gates have an unexpected schema')
  }
  return { directory, files }
}

const requireEvidenceIndexDocument = (document, label) => {
  if (!isRecord(document) || document.schema !== EVIDENCE_INDEX_SCHEMA) {
    throw new Error(`${label} has an unexpected schema`)
  }
  const provenance = document.source_provenance
  if (
    !isRecord(provenance) ||
    !SHA256_PATTERN.test(provenance.sha256 ?? '') ||
    !GIT_SHA_PATTERN.test(provenance.git_head_sha ?? '') ||
    !['clean', 'dirty-captured'].includes(provenance.worktree_state) ||
    !SHA256_PATTERN.test(provenance.source_input_tree_sha256 ?? '') ||
    !SHA256_PATTERN.test(provenance.wheelhouse_tree_sha256 ?? '')
  ) {
    throw new Error(`${label} has invalid source provenance`)
  }
  if (
    !Array.isArray(document.files) ||
    document.files.length !== STAGE_EVIDENCE_INDEXED_PATHS.length
  ) {
    throw new Error(`${label} must contain the exact Alpha evidence file set`)
  }
  const indexedPaths = document.files.map(file => file?.path)
  if (JSON.stringify(indexedPaths) !== JSON.stringify(STAGE_EVIDENCE_INDEXED_PATHS)) {
    throw new Error(`${label} must contain the exact Alpha evidence file set`)
  }
  for (const file of document.files) {
    if (
      !isRecord(file) ||
      !SHA256_PATTERN.test(file.sha256 ?? '') ||
      !Number.isSafeInteger(file.size_bytes) ||
      file.size_bytes < 0
    ) {
      throw new Error(`${label} has an invalid evidence file entry`)
    }
  }
  return document
}

const readEvidenceIndexDocument = (indexPath, label) => {
  let document
  try {
    document = JSON.parse(fs.readFileSync(indexPath, 'utf8'))
  } catch (error) {
    throw new Error(`${label} cannot be read: ${error.message}`)
  }
  return requireEvidenceIndexDocument(document, label)
}

export const verifyStageEvidenceIndex = stageDirectory => {
  const stage = requireStageDirectory(stageDirectory)
  const indexPath = requireRegularStageFile(
    stage,
    stageEvidenceRelativePath(EVIDENCE_INDEX_FILENAME)
  )
  const document = readEvidenceIndexDocument(indexPath, 'Alpha staged evidence index')
  const sourceProvenance = requireStageSourceProvenance(stage)
  if (
    document.source_provenance.sha256 !== sourceProvenance.sha256 ||
    document.source_provenance.git_head_sha !==
      sourceProvenance.document.git.head_sha.toLowerCase() ||
    document.source_provenance.worktree_state !== sourceProvenance.document.git.worktree_state ||
    document.source_provenance.source_input_tree_sha256 !==
      sourceProvenance.document.source_input_tree.sha256 ||
    document.source_provenance.wheelhouse_tree_sha256 !==
      sourceProvenance.document.external_wheelhouse.tree_sha256
  ) {
    throw new Error('Alpha staged evidence index does not match source provenance')
  }
  for (const indexedFile of document.files) {
    const candidate = requireRegularStageFile(stage, indexedFile.path)
    const actualSize = fs.lstatSync(candidate).size
    const actualSha256 = sha256File(candidate)
    if (actualSize !== indexedFile.size_bytes || actualSha256 !== indexedFile.sha256) {
      throw new Error(`Alpha staged evidence does not match index: ${indexedFile.path}`)
    }
  }
  return {
    stageDirectory: stage,
    indexPath,
    sha256: sha256File(indexPath),
    document,
  }
}

const createStageEvidenceIndex = (stageDirectory, sourceProvenance) => {
  requireStageEvidenceBundle(stageDirectory)
  const indexRelativePath = stageEvidenceRelativePath(EVIDENCE_INDEX_FILENAME)
  const indexPath = path.join(stageDirectory, ...indexRelativePath.split('/'))
  if (fs.existsSync(indexPath)) {
    throw new Error(`Refusing to overwrite Alpha evidence index: ${indexPath}`)
  }
  const files = STAGE_EVIDENCE_INDEXED_PATHS.map(relativePath => {
    const candidate = requireRegularStageFile(stageDirectory, relativePath)
    return {
      path: toPosixPath(relativePath),
      sha256: sha256File(candidate),
      size_bytes: fs.statSync(candidate).size,
    }
  })
  const document = {
    schema: EVIDENCE_INDEX_SCHEMA,
    source_provenance: {
      sha256: sourceProvenance.sha256,
      git_head_sha: sourceProvenance.document.git.head_sha.toLowerCase(),
      worktree_state: sourceProvenance.document.git.worktree_state,
      source_input_tree_sha256: sourceProvenance.document.source_input_tree.sha256,
      wheelhouse_tree_sha256: sourceProvenance.document.external_wheelhouse.tree_sha256,
    },
    files,
  }
  writeNewJson(indexPath, document)
  return verifyStageEvidenceIndex(stageDirectory)
}

const copyStageEvidenceToArtifacts = (stageDirectory, artifactDirectory) => {
  requireRegularStageDirectory(stageDirectory, 'resources/integration-snapshot/evidence')
  const destinationDirectory = path.join(artifactDirectory, 'evidence')
  if (fs.existsSync(destinationDirectory)) {
    throw new Error(`Refusing to overwrite Alpha artifact evidence: ${destinationDirectory}`)
  }
  fs.mkdirSync(destinationDirectory)
  for (const filename of [...ALPHA_EVIDENCE_FILENAMES, EVIDENCE_INDEX_FILENAME]) {
    const sourcePath = requireRegularStageFile(stageDirectory, stageEvidenceRelativePath(filename))
    fs.copyFileSync(
      sourcePath,
      path.join(destinationDirectory, filename),
      fs.constants.COPYFILE_EXCL
    )
  }
  return path.join(destinationDirectory, EVIDENCE_INDEX_FILENAME)
}

const requireRegularArtifactDirectory = (artifactDirectory, relativePath = '') => {
  const candidate = relativePath
    ? path.join(artifactDirectory, ...relativePath.split('/'))
    : artifactDirectory
  if (!fs.existsSync(candidate)) {
    throw new Error(`Alpha artifact directory is missing: ${relativePath || candidate}`)
  }
  const stats = fs.lstatSync(candidate)
  if (stats.isSymbolicLink() || !stats.isDirectory()) {
    throw new Error(`Alpha artifact requires a regular directory: ${relativePath || candidate}`)
  }
  return candidate
}

const requireRegularArtifactFile = (artifactDirectory, relativePath) => {
  const candidate = path.join(artifactDirectory, ...relativePath.split('/'))
  if (!fs.existsSync(candidate)) {
    throw new Error(`Alpha evidence artifact is missing: ${relativePath}`)
  }
  const stats = fs.lstatSync(candidate)
  if (stats.isSymbolicLink() || !stats.isFile()) {
    throw new Error(`Alpha evidence artifact requires a regular file: ${relativePath}`)
  }
  return candidate
}

export const verifyArtifactEvidenceBundle = artifactDirectory => {
  const artifact = path.resolve(requireArgument(artifactDirectory, '--artifact'))
  const evidenceDirectory = requireRegularArtifactDirectory(artifact, 'evidence')
  const expectedFiles = [...ALPHA_EVIDENCE_FILENAMES, EVIDENCE_INDEX_FILENAME].sort()
  const actualFiles = fs
    .readdirSync(evidenceDirectory, { withFileTypes: true })
    .map(entry => entry.name)
    .sort()
  if (JSON.stringify(actualFiles) !== JSON.stringify(expectedFiles)) {
    throw new Error('Alpha artifact evidence must contain exactly the staged evidence files')
  }
  const indexPath = requireRegularArtifactFile(artifact, `evidence/${EVIDENCE_INDEX_FILENAME}`)
  const document = readEvidenceIndexDocument(indexPath, 'Alpha artifact evidence index')
  for (const filename of ALPHA_EVIDENCE_FILENAMES) {
    const indexedFile = document.files.find(
      file => file.path === stageEvidenceRelativePath(filename)
    )
    const candidate = requireRegularArtifactFile(artifact, `evidence/${filename}`)
    if (
      !indexedFile ||
      fs.lstatSync(candidate).size !== indexedFile.size_bytes ||
      sha256File(candidate) !== indexedFile.sha256
    ) {
      throw new Error(`Alpha artifact evidence does not match index: ${filename}`)
    }
  }
  return {
    artifactDirectory: artifact,
    evidenceDirectory,
    indexPath,
    sha256: sha256File(indexPath),
    document,
  }
}

const prepareExperimentalAlphaRelease = ({
  stageDirectory,
  artifactDirectory,
  version,
  wheelhouseSha256,
  environmentSha256,
  gitSha,
  portableOnly,
  protectedDirectories = [defaultFrozenReleaseDirectory],
}) => {
  const stage = requireStageDirectory(stageDirectory)
  const output = ensureSafeOutputDirectory(artifactDirectory, stage, protectedDirectories)
  const normalizedVersion = requireSafeVersion(version)
  const normalizedGitSha = requireGitSha(gitSha)
  const sourceProvenance = requireStageSourceProvenance(stage)
  if (sourceProvenance.document.git.head_sha.toLowerCase() !== normalizedGitSha) {
    throw new Error('Alpha stage source provenance Git HEAD does not match --git-sha')
  }
  ensureFreshDirectory(output)
  const stageEvidenceIndex = createStageEvidenceIndex(stage, sourceProvenance)
  const verifiedStageEvidence = verifyStageEvidenceIndex(stage)
  if (verifiedStageEvidence.sha256 !== stageEvidenceIndex.sha256) {
    throw new Error('Alpha staged evidence changed before artifact copying')
  }
  const artifactEvidenceIndexPath = copyStageEvidenceToArtifacts(stage, output)
  const artifactEvidence = verifyArtifactEvidenceBundle(output)
  if (
    artifactEvidence.indexPath !== artifactEvidenceIndexPath ||
    artifactEvidence.sha256 !== stageEvidenceIndex.sha256
  ) {
    throw new Error('Alpha artifact evidence index does not match the staged evidence index')
  }
  const installerScriptPath = portableOnly
    ? undefined
    : path.join(output, 'experimental-alpha-full.iss')
  const preparedManifestPath = path.join(output, 'alpha-release-manifest.prepared.json')
  if (installerScriptPath) {
    writeNewText(
      installerScriptPath,
      createInstallerScript({
        stageDirectory: stage,
        artifactDirectory: output,
        version: normalizedVersion,
      })
    )
  }
  const manifest = {
    schema: MANIFEST_SCHEMA,
    status: 'prepared',
    distribution_mode: portableOnly ? 'portable-only' : 'installer-and-portable',
    identity: assertExperimentalAlphaIdentity(),
    version: normalizedVersion,
    git_sha: normalizedGitSha,
    source_head_sha: sourceProvenance.document.git.head_sha.toLowerCase(),
    source_state: sourceProvenance.document.git.worktree_state,
    source_provenance_sha256: sourceProvenance.sha256,
    source_input_tree_sha256: sourceProvenance.document.source_input_tree.sha256,
    release_tool_sha256: sha256File(fileURLToPath(import.meta.url)),
    wheelhouse_tree_sha256: sourceProvenance.document.external_wheelhouse.tree_sha256,
    stage_app_asar_sha256: sha256File(path.join(stage, 'resources', 'app.asar')),
    wheelhouse_archive_sha256: requireSha256(wheelhouseSha256, '--wheelhouse-sha256'),
    environment_archive_sha256: requireSha256(environmentSha256, '--environment-sha256'),
    snapshot_manifest_sha256: sha256File(
      path.join(stage, 'resources', 'integration-snapshot', 'manifest.json')
    ),
    wheelhouse_manifest_sha256: sha256File(
      path.join(stage, 'resources', 'integration-snapshot', 'plugins', 'wheels', 'manifest.json')
    ),
    runtime_lock_sha256: sha256File(
      path.join(
        stage,
        'resources',
        'integration-snapshot',
        'plugins',
        'wheels',
        'runtime-lock.json'
      )
    ),
    evidence: {
      stage_index_path: stageEvidenceRelativePath(EVIDENCE_INDEX_FILENAME),
      artifact_index_path: `evidence/${EVIDENCE_INDEX_FILENAME}`,
      index_sha256: stageEvidenceIndex.sha256,
      indexed_file_count: stageEvidenceIndex.document.files.length,
    },
    signing: {
      status: 'not-requested',
      note: 'Experimental Alpha workflow does not publish through the stable signing or updater channel.',
    },
    executable_resource_editing: {
      status: 'disabled',
      note: 'Experimental Alpha disables rcedit/winCodeSign resource editing for unsigned test builds.',
    },
    expected_artifacts: portableOnly
      ? {
          archive: fullArchiveFilename(normalizedVersion),
          sha256_sums: sha256SumsFilename(normalizedVersion),
          evidence_index: `evidence/${EVIDENCE_INDEX_FILENAME}`,
        }
      : {
          installer: fullInstallerFilename(normalizedVersion),
          archive: fullArchiveFilename(normalizedVersion),
          sha256_sums: sha256SumsFilename(normalizedVersion),
          evidence_index: `evidence/${EVIDENCE_INDEX_FILENAME}`,
        },
    full_stage_required_files: [
      `${experimentalAlphaIdentity.executableName}.exe`,
      'resources/app.asar',
      'resources/integration-snapshot/manifest.json',
      'resources/integration-snapshot/source-provenance.json',
      'resources/integration-snapshot/plugins/wheels/manifest.json',
      'resources/integration-snapshot/plugins/wheels/runtime-lock.json',
      'resources/integration-snapshot/scripts/verify_offline_first_start.ps1',
      'resources/integration-snapshot/scripts/verify_wheelhouse_snapshot.py',
      ...ALPHA_EVIDENCE_FILENAMES.map(stageEvidenceRelativePath),
      'environment/python/python.exe',
      'environment/python/Scripts/uv.exe',
      'environment/git/bin/git.exe',
      'resources/assets/AUTO-MAS.ico',
    ],
  }
  writeNewJson(preparedManifestPath, manifest)
  return {
    installerScriptPath,
    preparedManifestPath,
    evidenceIndexPath: artifactEvidenceIndexPath,
    artifactDirectory: output,
    manifest,
  }
}

export const prepareExperimentalAlphaInstaller = options =>
  prepareExperimentalAlphaRelease({ ...options, portableOnly: false })

export const prepareExperimentalAlphaPortable = options =>
  prepareExperimentalAlphaRelease({ ...options, portableOnly: true })

export const finalizeExperimentalAlphaInstaller = ({ preparedManifestPath }) => {
  const preparedPath = path.resolve(requireArgument(preparedManifestPath, '--prepared-manifest'))
  if (!fs.existsSync(preparedPath)) {
    throw new Error(`Prepared Alpha release manifest does not exist: ${preparedPath}`)
  }
  const preparedStats = fs.lstatSync(preparedPath)
  if (preparedStats.isSymbolicLink() || !preparedStats.isFile()) {
    throw new Error(`Prepared Alpha release manifest must be a regular file: ${preparedPath}`)
  }
  const prepared = JSON.parse(fs.readFileSync(preparedPath, 'utf8'))
  if (prepared?.schema !== MANIFEST_SCHEMA || prepared?.status !== 'prepared') {
    throw new Error('Prepared Alpha release manifest has an unexpected schema or state')
  }
  assertExperimentalAlphaIdentity(prepared.identity)
  const portableOnly = prepared.distribution_mode === 'portable-only'
  if (
    !portableOnly &&
    prepared.distribution_mode !== 'installer-and-portable' &&
    prepared.distribution_mode != null
  ) {
    throw new Error('Prepared Alpha release manifest has an unsupported distribution mode')
  }
  const artifactDirectory = path.dirname(preparedPath)
  requireRegularArtifactDirectory(artifactDirectory)
  const installerPath = portableOnly
    ? undefined
    : path.join(artifactDirectory, prepared.expected_artifacts.installer)
  const archivePath = path.join(artifactDirectory, prepared.expected_artifacts.archive)
  if (installerPath) {
    requireRegularArtifactFile(artifactDirectory, path.basename(installerPath))
  }
  requireRegularArtifactFile(artifactDirectory, path.basename(archivePath))
  const manifestPath = path.join(artifactDirectory, 'alpha-release-manifest.json')
  const sumsPath = path.join(artifactDirectory, prepared.expected_artifacts.sha256_sums)
  const installerScriptPath = portableOnly
    ? undefined
    : path.join(artifactDirectory, 'experimental-alpha-full.iss')
  if (installerScriptPath) {
    requireRegularArtifactFile(artifactDirectory, path.basename(installerScriptPath))
  }
  const artifactEvidence = verifyArtifactEvidenceBundle(artifactDirectory)
  const evidenceIndexPath = artifactEvidence.indexPath
  if (artifactEvidence.sha256 !== prepared.evidence?.index_sha256) {
    throw new Error('Alpha artifact evidence index does not match the prepared release manifest')
  }
  const artifacts = [
    ...(installerPath
      ? [
          {
            filename: path.basename(installerPath),
            sha256: sha256File(installerPath),
            size_bytes: fs.statSync(installerPath).size,
          },
        ]
      : []),
    {
      filename: path.basename(archivePath),
      sha256: sha256File(archivePath),
      size_bytes: fs.statSync(archivePath).size,
    },
  ]
  const checksumFiles = [
    ...artifacts,
    {
      filename: path.basename(manifestPath),
      path: manifestPath,
    },
    ...(installerScriptPath
      ? [
          {
            filename: path.basename(installerScriptPath),
            path: installerScriptPath,
          },
        ]
      : []),
    {
      filename: toPosixPath(prepared.expected_artifacts.evidence_index),
      path: evidenceIndexPath,
    },
  ]
  const manifest = {
    ...prepared,
    status: 'packaged',
    artifacts,
    checksum_coverage: {
      filename: path.basename(sumsPath),
      files: checksumFiles.map(file => file.filename),
    },
  }
  writeNewJson(manifestPath, manifest)
  const checksumEntries = checksumFiles.map(file => ({
    filename: file.filename,
    sha256: file.sha256 ?? sha256File(file.path),
  }))
  writeNewText(
    sumsPath,
    checksumEntries.map(item => `${item.sha256} *${item.filename}`).join('\n') + '\n'
  )
  return { manifestPath, sumsPath, evidenceIndexPath, manifest }
}

const readOptions = argv => {
  const [command, ...rest] = argv
  if (!['prepare', 'prepare-portable', 'verify-stage', 'finalize'].includes(command)) {
    throw new Error(
      'Usage: generate-experimental-alpha-installer.mjs <prepare|prepare-portable|verify-stage|finalize> [options]'
    )
  }
  const options = { command }
  for (let index = 0; index < rest.length; index += 1) {
    const argument = rest[index]
    if (!argument.startsWith('--')) throw new Error(`Unsupported argument: ${argument}`)
    const key = argument.slice(2)
    const value = rest[index + 1]
    if (!value || value.startsWith('--')) throw new Error(`${argument} requires a value`)
    if (Object.hasOwn(options, key)) throw new Error(`${argument} was supplied more than once`)
    options[key] = value
    index += 1
  }
  return options
}

const main = () => {
  const options = readOptions(process.argv.slice(2))
  const result =
    options.command === 'prepare' || options.command === 'prepare-portable'
      ? (options.command === 'prepare'
          ? prepareExperimentalAlphaInstaller
          : prepareExperimentalAlphaPortable)({
          stageDirectory: options.stage,
          artifactDirectory: options.output,
          version: options.version,
          wheelhouseSha256: options['wheelhouse-sha256'],
          environmentSha256: options['environment-sha256'],
          gitSha: options['git-sha'],
        })
      : options.command === 'verify-stage'
        ? verifyStageEvidenceIndex(options.stage)
        : finalizeExperimentalAlphaInstaller({ preparedManifestPath: options['prepared-manifest'] })
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`)
}

const currentFile = fileURLToPath(import.meta.url)
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(currentFile)) {
  main()
}

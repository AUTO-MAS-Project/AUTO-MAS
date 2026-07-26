import path from 'node:path'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'

const require = createRequire(import.meta.url)
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const repositoryDirectory = path.resolve(scriptDirectory, '..', '..')

export const ARCHIVE_SAFETY_DEFAULTS = Object.freeze({
  maxArchiveBytes: 1024 * 1024 * 1024,
  maxEntries: 4096,
  maxExpandedBytes: 2 * 1024 * 1024 * 1024,
  maxFileBytes: 512 * 1024 * 1024,
})

const readPositiveIntegerLimit = (env, name, defaultValue) => {
  const rawValue = env[name]?.trim()
  if (!rawValue) return defaultValue
  if (!/^[1-9]\d*$/u.test(rawValue)) {
    throw new Error(`${name} must be a positive decimal integer`)
  }
  const value = Number(rawValue)
  if (!Number.isSafeInteger(value)) {
    throw new Error(`${name} exceeds the JavaScript safe integer range`)
  }
  return value
}

export const readArchiveSafetyLimits = (env = process.env) => ({
  maxArchiveBytes: readPositiveIntegerLimit(
    env,
    'AUTO_MAS_ARCHIVE_MAX_BYTES',
    ARCHIVE_SAFETY_DEFAULTS.maxArchiveBytes
  ),
  maxEntries: readPositiveIntegerLimit(
    env,
    'AUTO_MAS_ARCHIVE_MAX_ENTRIES',
    ARCHIVE_SAFETY_DEFAULTS.maxEntries
  ),
  maxExpandedBytes: readPositiveIntegerLimit(
    env,
    'AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES',
    ARCHIVE_SAFETY_DEFAULTS.maxExpandedBytes
  ),
  maxFileBytes: readPositiveIntegerLimit(
    env,
    'AUTO_MAS_ARCHIVE_MAX_FILE_BYTES',
    ARCHIVE_SAFETY_DEFAULTS.maxFileBytes
  ),
})

const pathEntryExists = value => {
  try {
    fs.lstatSync(value)
    return true
  } catch (error) {
    if (error?.code === 'ENOENT') return false
    throw error
  }
}

const realpath = value =>
  typeof fs.realpathSync.native === 'function'
    ? fs.realpathSync.native(value)
    : fs.realpathSync(value)

export const canonicalizeFilesystemPath = (value, cwd = process.cwd()) => {
  const resolvedPath = path.resolve(cwd, value)
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

export const normalizePathForComparison = value => {
  const normalized = path.normalize(value)
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized
}

const isSameOrNestedCanonical = (parentPath, candidatePath) => {
  const parentKey = normalizePathForComparison(parentPath)
  const candidateKey = normalizePathForComparison(candidatePath)
  const relative = path.relative(parentKey, candidateKey)
  return (
    relative === '' ||
    (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
  )
}

export const pathsOverlapPhysically = (leftPath, rightPath) => {
  const canonicalLeft = canonicalizeFilesystemPath(leftPath)
  const canonicalRight = canonicalizeFilesystemPath(rightPath)
  return (
    isSameOrNestedCanonical(canonicalLeft, canonicalRight) ||
    isSameOrNestedCanonical(canonicalRight, canonicalLeft)
  )
}

export const assertExtractedDirectorySafe = (directory, limits = readArchiveSafetyLimits()) => {
  const canonicalRoot = canonicalizeFilesystemPath(directory)
  const rootStats = fs.statSync(canonicalRoot)
  if (!rootStats.isDirectory()) {
    throw new Error(`Extracted artifact root is not a directory: ${directory}`)
  }

  let entryCount = 0
  let expandedBytes = 0
  const pendingDirectories = [canonicalRoot]
  while (pendingDirectories.length > 0) {
    const currentDirectory = pendingDirectories.pop()
    for (const entry of fs.readdirSync(currentDirectory, { withFileTypes: true })) {
      const entryPath = path.join(currentDirectory, entry.name)
      const entryStats = fs.lstatSync(entryPath)
      entryCount += 1
      if (entryCount > limits.maxEntries) {
        throw new Error(
          `Extracted artifact exceeds AUTO_MAS_ARCHIVE_MAX_ENTRIES (${limits.maxEntries})`
        )
      }
      if (entry.isSymbolicLink() || entryStats.isSymbolicLink()) {
        throw new Error(`Extracted artifact contains a symbolic link or junction: ${entryPath}`)
      }

      let canonicalEntry
      try {
        canonicalEntry = realpath(entryPath)
      } catch (error) {
        throw new Error(`Cannot resolve extracted artifact entry ${entryPath}: ${error}`)
      }
      if (
        normalizePathForComparison(canonicalEntry) !==
        normalizePathForComparison(path.resolve(entryPath))
      ) {
        throw new Error(
          `Extracted artifact contains a filesystem link or reparse point: ${entryPath}`
        )
      }
      if (!isSameOrNestedCanonical(canonicalRoot, canonicalEntry)) {
        throw new Error(`Extracted artifact entry escapes its physical root: ${entryPath}`)
      }

      if (entryStats.isDirectory()) {
        pendingDirectories.push(entryPath)
      } else if (entryStats.isFile()) {
        if (entryStats.size > limits.maxFileBytes) {
          throw new Error(
            `Extracted artifact file exceeds AUTO_MAS_ARCHIVE_MAX_FILE_BYTES (${limits.maxFileBytes}): ${entryPath}`
          )
        }
        expandedBytes += entryStats.size
        if (expandedBytes > limits.maxExpandedBytes) {
          throw new Error(
            `Extracted artifact exceeds AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES (${limits.maxExpandedBytes})`
          )
        }
      } else {
        throw new Error(`Extracted artifact contains an unsupported filesystem entry: ${entryPath}`)
      }
    }
  }

  return { canonicalRoot, entryCount, expandedBytes }
}

const readRequiredOption = (argv, index, optionName) => {
  const value = argv[index + 1]
  if (!value || value.startsWith('--')) {
    throw new Error(`${optionName} requires a non-empty path`)
  }
  return value
}

export const parseValidationOptions = (
  argv,
  env = process.env,
  cwd = process.cwd(),
  repositoryRoot = repositoryDirectory
) => {
  let cliWheelhouse
  let snapshotManifest
  let requireSnapshotContract = false
  let help = false

  const setWheelhouse = value => {
    if (cliWheelhouse != null) throw new Error('Wheelhouse path was provided more than once')
    if (!value.trim()) throw new Error('--wheelhouse requires a non-empty path')
    cliWheelhouse = value
  }
  const setSnapshotManifest = value => {
    if (snapshotManifest != null) {
      throw new Error('Snapshot manifest path was provided more than once')
    }
    if (!value.trim()) throw new Error('--snapshot requires a non-empty path')
    snapshotManifest = value
    requireSnapshotContract = true
  }

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--help' || argument === '-h') {
      help = true
    } else if (argument === '--require-snapshot-contract') {
      requireSnapshotContract = true
    } else if (argument === '--wheelhouse') {
      setWheelhouse(readRequiredOption(argv, index, argument))
      index += 1
    } else if (argument.startsWith('--wheelhouse=')) {
      setWheelhouse(argument.slice('--wheelhouse='.length))
    } else if (argument === '--snapshot') {
      setSnapshotManifest(readRequiredOption(argv, index, argument))
      index += 1
    } else if (argument.startsWith('--snapshot=')) {
      setSnapshotManifest(argument.slice('--snapshot='.length))
    } else if (!argument.startsWith('-')) {
      // Keep the historical positional wheelhouse argument for the legacy validator.
      setWheelhouse(argument)
    } else {
      throw new Error(`Unsupported validate-wheelhouse argument: ${argument}`)
    }
  }

  const environmentWheelhouse = env.AUTO_MAS_WHEELHOUSE_ROOT?.trim()
  const resolvedCliWheelhouse = cliWheelhouse
    ? canonicalizeFilesystemPath(cliWheelhouse, cwd)
    : undefined
  const resolvedEnvironmentWheelhouse = environmentWheelhouse
    ? canonicalizeFilesystemPath(environmentWheelhouse, cwd)
    : undefined
  if (
    resolvedCliWheelhouse &&
    resolvedEnvironmentWheelhouse &&
    normalizePathForComparison(resolvedCliWheelhouse) !==
      normalizePathForComparison(resolvedEnvironmentWheelhouse)
  ) {
    throw new Error('--wheelhouse and AUTO_MAS_WHEELHOUSE_ROOT resolve to different directories')
  }

  const explicitWheelhouse = resolvedCliWheelhouse ?? resolvedEnvironmentWheelhouse
  if (requireSnapshotContract && !explicitWheelhouse && !help) {
    throw new Error('Integration validation requires --wheelhouse or AUTO_MAS_WHEELHOUSE_ROOT')
  }

  return {
    wheelhouseDirectory:
      explicitWheelhouse ??
      canonicalizeFilesystemPath(path.resolve(repositoryRoot, 'plugins', 'wheels')),
    snapshotManifestPath: snapshotManifest
      ? path.resolve(cwd, snapshotManifest)
      : path.resolve(repositoryRoot, 'res', 'integration-snapshot.json'),
    requireSnapshotContract,
    help,
  }
}

const normalizeDistributionName = name =>
  name
    .trim()
    .toLowerCase()
    .replace(/[-_.]+/g, '-')

const parsePinnedRequirement = (value, source) => {
  const match = value
    .trim()
    .match(/^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]+\])?\s*==\s*([^;\s]+)(?:\s*;.*)?$/)
  if (!match) {
    throw new Error(`${source} must use an exact name==version requirement: ${value}`)
  }
  return [normalizeDistributionName(match[1]), match[2]]
}

const addUniqueRequirement = (target, requirement, source) => {
  const [name, version] = parsePinnedRequirement(requirement, source)
  const previous = target.get(name)
  if (previous != null && previous !== version) {
    throw new Error(`${source} declares conflicting versions for ${name}: ${previous}/${version}`)
  }
  target.set(name, version)
}

const readRequirementsFile = filePath => {
  const result = new Map()
  for (const [index, rawLine] of fs.readFileSync(filePath, 'utf8').split(/\r?\n/u).entries()) {
    const line = rawLine.replace(/\s+#.*$/u, '').trim()
    if (line) addUniqueRequirement(result, line, `${filePath}:${index + 1}`)
  }
  return result
}

const readPyProjectDependencies = filePath => {
  const result = new Map()
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/u)
  let inProject = false
  let inDependencies = false

  for (const [index, rawLine] of lines.entries()) {
    const line = rawLine.trim()
    if (!inDependencies && /^\[[^\]]+\]$/u.test(line)) {
      inProject = line === '[project]'
      continue
    }
    if (!inDependencies) {
      if (inProject && /^dependencies\s*=\s*\[/u.test(line)) inDependencies = true
      continue
    }
    if (/^\]/u.test(line)) break

    const match = line.match(/^"((?:\\.|[^"\\])*)"\s*,?(?:\s*#.*)?$/u)
    if (!match) {
      if (line && !line.startsWith('#')) {
        throw new Error(`${filePath}:${index + 1} contains an unsupported dependency entry`)
      }
      continue
    }
    const requirement = JSON.parse(`"${match[1]}"`)
    addUniqueRequirement(result, requirement, `${filePath}:${index + 1}`)
  }

  if (!inDependencies || result.size === 0) {
    throw new Error(`${filePath} does not contain a non-empty [project].dependencies array`)
  }
  return result
}

export const readPinnedPluginBootstrapRequirements = filePath => {
  const source = fs.readFileSync(filePath, 'utf8')
  const sectionHeader = /^\[tool\.auto-mas\.plugin-bootstrap\]\s*$/mu.exec(source)
  if (!sectionHeader) {
    throw new Error(`${filePath} does not contain [tool.auto-mas.plugin-bootstrap]`)
  }
  const remainingSource = source.slice(sectionHeader.index + sectionHeader[0].length)
  const nextSection = /^\[[^\]]+\]\s*$/mu.exec(remainingSource)
  const sectionSource =
    nextSection == null ? remainingSource : remainingSource.slice(0, nextSection.index)
  const packagesMatch = sectionSource.match(/packages\s*=\s*\[([\s\S]*?)\]/u)
  if (!packagesMatch) {
    throw new Error(`${filePath} does not contain plugin-bootstrap packages`)
  }

  const result = new Map()
  for (const entry of packagesMatch[1].matchAll(/\{([^{}]+)\}/gu)) {
    const nameMatch = entry[1].match(/\bname\s*=\s*"([^"]+)"/u)
    const versionMatch = entry[1].match(/\bversion\s*=\s*"([^"]+)"/u)
    if (!nameMatch || !versionMatch) continue
    addUniqueRequirement(
      result,
      `${nameMatch[1]}==${versionMatch[1]}`,
      `${filePath} plugin-bootstrap`
    )
  }
  if (result.size === 0) {
    throw new Error(`${filePath} does not contain pinned plugin-bootstrap packages`)
  }
  return result
}

export const assertPinnedPluginBootstrapMatchesRuntimeLock = (
  pinnedRequirements,
  runtimePlugins,
  source = 'plugin-bootstrap'
) => {
  const lockedPlugins = new Map(
    runtimePlugins.map(entry => [normalizeDistributionName(entry.distribution), entry.version])
  )
  const mismatches = []
  for (const [name, version] of pinnedRequirements) {
    const lockedVersion = lockedPlugins.get(name)
    if (lockedVersion !== version) {
      mismatches.push(`${name} expected ${version}, got ${lockedVersion ?? '<missing>'}`)
    }
  }
  if (mismatches.length > 0) {
    throw new Error(
      `${source} and bundled runtime lock are inconsistent:\n- ${mismatches.join('\n- ')}`
    )
  }
}

const assertRequirementsInclude = (expected, actual, expectedSource, actualSource) => {
  const mismatches = []
  for (const [name, version] of expected) {
    const actualVersion = actual.get(name)
    if (actualVersion !== version)
      mismatches.push(`${name} expected ${version}, got ${actualVersion ?? '<missing>'}`)
  }
  if (mismatches.length > 0) {
    throw new Error(
      `${expectedSource} and ${actualSource} are inconsistent:\n- ${mismatches.join('\n- ')}`
    )
  }
}

export const validateWheelhouse = (options, repositoryRoot = repositoryDirectory) => {
  assertExtractedDirectorySafe(options.wheelhouseDirectory)

  const validationModulePath = path.resolve(
    scriptDirectory,
    '..',
    'dist-electron',
    'services',
    'bundledArtifactValidation.js'
  )
  if (!fs.existsSync(validationModulePath)) {
    throw new Error('Wheelhouse validation module is missing; run yarn build:main first')
  }
  const {
    assertBundledSnapshotMarker,
    readAndVerifyBundledRuntimeLock,
    verifyBundledSnapshotWheelhouseContract,
  } = require(validationModulePath)

  let runtimeLock
  if (options.requireSnapshotContract) {
    let snapshotMarker
    try {
      snapshotMarker = JSON.parse(
        fs.readFileSync(options.snapshotManifestPath, 'utf8').replace(/^\uFEFF/, '')
      )
    } catch (error) {
      throw new Error(`Integration snapshot marker is invalid: ${error}`)
    }
    const packageJson = JSON.parse(
      fs.readFileSync(path.resolve(scriptDirectory, '..', 'package.json'), 'utf8')
    )
    assertBundledSnapshotMarker(snapshotMarker, packageJson.version)

    let snapshotVersion
    const snapshotVersionPath = path.join(
      path.dirname(options.snapshotManifestPath),
      'version.json'
    )
    try {
      snapshotVersion = JSON.parse(
        fs.readFileSync(snapshotVersionPath, 'utf8').replace(/^\uFEFF/, '')
      )
    } catch (error) {
      throw new Error(`Integration snapshot version file is invalid: ${error}`)
    }
    if (
      snapshotVersion?.version !== snapshotMarker.version ||
      snapshotVersion.version_info == null ||
      typeof snapshotVersion.version_info !== 'object' ||
      !Object.prototype.hasOwnProperty.call(snapshotVersion.version_info, snapshotMarker.version)
    ) {
      throw new Error('Integration snapshot marker version does not match res/version.json')
    }
    runtimeLock = verifyBundledSnapshotWheelhouseContract(
      options.wheelhouseDirectory,
      snapshotMarker.wheelhouse_contract
    )
  } else {
    runtimeLock = readAndVerifyBundledRuntimeLock(options.wheelhouseDirectory)
  }

  const pyprojectPath = path.resolve(repositoryRoot, 'pyproject.toml')
  const requirementsPath = path.resolve(repositoryRoot, 'requirements.txt')
  const projectDependencies = readPyProjectDependencies(pyprojectPath)
  const pluginBootstrapRequirements = readPinnedPluginBootstrapRequirements(pyprojectPath)
  const requirementsDependencies = readRequirementsFile(requirementsPath)
  assertRequirementsInclude(
    projectDependencies,
    requirementsDependencies,
    pyprojectPath,
    requirementsPath
  )

  const lockedHostDependencies = new Map(
    runtimeLock.host_runtime.map(entry => [
      normalizeDistributionName(entry.distribution),
      entry.version,
    ])
  )
  for (const [name, version] of projectDependencies) {
    const lockedVersion = lockedHostDependencies.get(name)
    if (lockedVersion !== version) {
      throw new Error(
        `Bundled runtime lock is stale for host dependency ${name}: expected ${version}, got ${lockedVersion ?? '<missing>'}`
      )
    }
  }
  assertPinnedPluginBootstrapMatchesRuntimeLock(
    pluginBootstrapRequirements,
    runtimeLock.plugins,
    pyprojectPath
  )

  return {
    hostDependencyCount: projectDependencies.size,
    pinnedPluginBootstrapCount: pluginBootstrapRequirements.size,
    pluginDistributionCount: runtimeLock.plugins.length,
    entryPointCount: runtimeLock.expected_plugin_entry_points.length,
  }
}

const printUsage = () => {
  console.log(`Usage:
  node scripts/validate-wheelhouse.mjs [wheelhouse]
  node scripts/validate-wheelhouse.mjs --wheelhouse <path> --require-snapshot-contract [--snapshot <path>]

AUTO_MAS_WHEELHOUSE_ROOT may be used instead of --wheelhouse. The strict snapshot
mode deliberately requires an explicit wheelhouse and fails on conflicting inputs.
Every validation also rejects linked entries and enforces the shared
AUTO_MAS_ARCHIVE_MAX_ENTRIES, AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES, and
AUTO_MAS_ARCHIVE_MAX_FILE_BYTES safety limits.`)
}

const isMainModule =
  process.argv[1] != null && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (isMainModule) {
  try {
    const options = parseValidationOptions(process.argv.slice(2))
    if (options.help) {
      printUsage()
    } else {
      const result = validateWheelhouse(options)
      console.log(
        `Validated complete integration wheelhouse: ${result.hostDependencyCount} host dependencies, ${result.pluginDistributionCount} plugin distributions, ${result.entryPointCount} entry points${options.requireSnapshotContract ? ' (snapshot contract bound)' : ''}`
      )
    }
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  }
}

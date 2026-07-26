import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import wheelhouseProvenance from './alpha-wheelhouse-provenance.cjs'

export const ALPHA_SOURCE_PROVENANCE_SCHEMA = 'auto-mas.experimental-alpha.source-provenance/v2'

const SHA256_PATTERN = /^[0-9a-f]{64}$/iu
const GIT_SHA_PATTERN = /^[0-9a-f]{40}$/iu
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const defaultRepositoryRoot = path.resolve(scriptDirectory, '..', '..')

const excludesPythonCache = relativePath =>
  relativePath.split('/').includes('__pycache__') || /\.py[oc]$/iu.test(relativePath)

const excludesPluginBuildOutput = relativePath => {
  const segments = relativePath.split('/')
  return (
    excludesPythonCache(relativePath) ||
    segments.includes('build') ||
    segments.includes('dist') ||
    segments.some(segment => segment.endsWith('.egg-info'))
  )
}

/** Traceable Alpha payload and build-input families, after renderer outputs exist. */
export const ALPHA_SOURCE_INPUTS = Object.freeze([
  { source: 'frontend/dist/index.html' },
  { source: 'frontend/dist/assets' },
  { source: 'frontend/dist-electron' },
  { source: 'frontend/public' },
  { source: 'frontend/src/assets' },
  { source: 'frontend/electron' },
  { source: 'frontend/package.json' },
  { source: 'frontend/yarn.lock' },
  { source: 'frontend/.yarnrc.yml' },
  { source: 'frontend/vite.config.ts' },
  { source: 'frontend/tsconfig.app.json' },
  { source: 'frontend/tsconfig.electron.json' },
  { source: 'frontend/electron-builder.integration.cjs' },
  { source: 'frontend/scripts/build-integration-release.mjs' },
  { source: 'frontend/scripts/alpha-wheelhouse-provenance.cjs' },
  { source: 'frontend/scripts/generate-experimental-alpha-installer.mjs' },
  { source: 'frontend/scripts/experimental-alpha-release-identity.cjs' },
  { source: 'frontend/scripts/validate-wheelhouse.mjs' },
  { source: 'app', exclude: excludesPythonCache },
  { source: 'res' },
  { source: 'docs/experimental-alpha' },
  { source: 'scripts/verify_offline_first_start.ps1' },
  { source: 'scripts/verify_wheelhouse_snapshot.py' },
  { source: 'plugins/auto_mas_core', exclude: excludesPluginBuildOutput },
  {
    source: 'plugins/browser',
    exclude: relativePath =>
      excludesPluginBuildOutput(relativePath) || relativePath.split('/').includes('tests'),
  },
  { source: 'plugins/ok_script_adapter', exclude: excludesPluginBuildOutput },
  { source: 'plugins/okww_adapter', exclude: excludesPluginBuildOutput },
  { source: 'main.py' },
  { source: 'pyproject.toml' },
  { source: 'requirements.txt' },
  { source: 'LICENSE' },
  { source: 'README.md' },
])

const toPosixPath = value => value.split(path.sep).join('/')

const hashBuffer = value => createHash('sha256').update(value).digest('hex')

const hashFile = filePath => hashBuffer(fs.readFileSync(filePath))

const assertRegularPath = (absolutePath, relativePath) => {
  const stats = fs.lstatSync(absolutePath)
  if (stats.isSymbolicLink()) {
    throw new Error(`Alpha source provenance refuses symbolic links: ${relativePath}`)
  }
  if (!stats.isDirectory() && !stats.isFile()) {
    throw new Error(
      `Alpha source provenance requires regular files or directories: ${relativePath}`
    )
  }
  return stats
}

const collectDirectoryFiles = (rootDirectory, sourceRoot, input, entries) => {
  const directoryEntries = fs
    .readdirSync(rootDirectory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name, 'en'))
  for (const entry of directoryEntries) {
    const absolutePath = path.join(rootDirectory, entry.name)
    const relativeToInput = toPosixPath(path.relative(sourceRoot, absolutePath))
    const sourcePath = toPosixPath(path.relative(input.repositoryRoot, absolutePath))
    if (entry.isSymbolicLink()) {
      throw new Error(`Alpha source provenance refuses symbolic links: ${sourcePath}`)
    }
    if (entry.isDirectory()) {
      collectDirectoryFiles(absolutePath, sourceRoot, input, entries)
      continue
    }
    if (!entry.isFile()) {
      throw new Error(`Alpha source provenance requires regular files: ${sourcePath}`)
    }
    if (input.include && !input.include(relativeToInput)) continue
    if (input.exclude?.(relativeToInput)) continue

    const sizeBytes = fs.statSync(absolutePath).size
    entries.push({
      path: sourcePath,
      size_bytes: sizeBytes,
      sha256: hashFile(absolutePath),
    })
  }
}

/** Collects the stable, filtered file manifest for the actual Alpha packaging inputs. */
export const collectAlphaSourceInputManifest = (
  repositoryRoot = defaultRepositoryRoot,
  sourceInputs = ALPHA_SOURCE_INPUTS
) => {
  const resolvedRoot = path.resolve(repositoryRoot)
  const entries = []
  for (const specification of sourceInputs) {
    const source = specification?.source
    if (typeof source !== 'string' || !source || path.isAbsolute(source) || source.includes('..')) {
      throw new Error('Alpha source provenance input source must be a safe relative path')
    }
    const absolutePath = path.join(resolvedRoot, ...source.split('/'))
    if (!fs.existsSync(absolutePath)) {
      throw new Error(`Alpha source provenance input is missing: ${source}`)
    }
    const stats = assertRegularPath(absolutePath, source)
    const input = { ...specification, repositoryRoot: resolvedRoot }
    if (stats.isFile()) {
      const relativePath = toPosixPath(source)
      if ((!input.include || input.include('')) && !input.exclude?.('')) {
        entries.push({
          path: relativePath,
          size_bytes: stats.size,
          sha256: hashFile(absolutePath),
        })
      }
      continue
    }
    collectDirectoryFiles(absolutePath, absolutePath, input, entries)
  }

  entries.sort((left, right) => left.path.localeCompare(right.path, 'en'))
  const duplicate = entries.find(
    (entry, index) => index > 0 && entry.path === entries[index - 1].path
  )
  if (duplicate)
    throw new Error(`Alpha source provenance has duplicate input path: ${duplicate.path}`)

  const canonicalEntries = entries
    .map(entry => `${entry.path}\0${entry.size_bytes}\0${entry.sha256}\n`)
    .join('')
  return {
    sha256: hashBuffer(Buffer.from(canonicalEntries, 'utf8')),
    file_count: entries.length,
    total_bytes: entries.reduce((total, entry) => total + entry.size_bytes, 0),
    files: entries,
  }
}

const runGit = (repositoryRoot, argumentsList) => {
  const result = spawnSync('git', ['-C', repositoryRoot, ...argumentsList], {
    encoding: 'buffer',
    maxBuffer: 64 * 1024 * 1024,
    shell: false,
    windowsHide: true,
  })
  if (result.error) throw new Error(`Unable to inspect Git provenance: ${result.error.message}`)
  if (result.status !== 0) {
    const stderr = Buffer.from(result.stderr ?? '')
      .toString('utf8')
      .trim()
    throw new Error(
      `Git provenance command failed: git ${argumentsList.join(' ')}${stderr ? `: ${stderr}` : ''}`
    )
  }
  return Buffer.from(result.stdout ?? '')
}

/** Reads Git state without changing it; dirty state is captured, never labelled clean. */
export const readAlphaGitState = repositoryRoot => {
  const headSha = runGit(repositoryRoot, ['rev-parse', 'HEAD'])
    .toString('utf8')
    .trim()
    .toLowerCase()
  if (!GIT_SHA_PATTERN.test(headSha)) throw new Error('Git HEAD must be a 40 character commit SHA')
  const status = runGit(repositoryRoot, ['status', '--porcelain=v1', '-z'])
  const diff = runGit(repositoryRoot, ['diff', '--binary', 'HEAD'])
  return {
    head_sha: headSha,
    worktree_state: status.length === 0 ? 'clean' : 'dirty-captured',
    status_sha256: hashBuffer(status),
    tracked_diff_sha256: hashBuffer(diff),
    status_entry_count:
      status.length === 0 ? 0 : status.toString('utf8').split('\0').filter(Boolean).length,
  }
}

const requireExpectedGitSha = value => {
  if (value == null || value === '') return undefined
  const normalized = String(value).trim().toLowerCase()
  if (!GIT_SHA_PATTERN.test(normalized)) {
    throw new Error('Expected Alpha Git SHA must be a 40 character hexadecimal value')
  }
  return normalized
}

/** Creates a provenance document without writing it, which keeps unit tests deterministic. */
export const createAlphaSourceProvenanceDocument = ({
  repositoryRoot = defaultRepositoryRoot,
  expectedGitSha,
  gitState = readAlphaGitState(repositoryRoot),
  sourceInputs = ALPHA_SOURCE_INPUTS,
  wheelhouseDirectory,
} = {}) => {
  const expected = requireExpectedGitSha(expectedGitSha)
  if (!gitState || !GIT_SHA_PATTERN.test(gitState.head_sha ?? '')) {
    throw new Error('Alpha source provenance requires a valid Git HEAD SHA')
  }
  if (!['clean', 'dirty-captured'].includes(gitState.worktree_state)) {
    throw new Error('Alpha source provenance must record a clean or dirty-captured worktree state')
  }
  if (expected && expected !== gitState.head_sha.toLowerCase()) {
    throw new Error(
      `Expected Alpha Git SHA ${expected} does not match actual HEAD ${gitState.head_sha}`
    )
  }

  const inputTree = collectAlphaSourceInputManifest(repositoryRoot, sourceInputs)
  if (typeof wheelhouseDirectory !== 'string' || !wheelhouseDirectory.trim()) {
    throw new Error('Alpha source provenance requires the selected wheelhouse directory')
  }
  return {
    schema: ALPHA_SOURCE_PROVENANCE_SCHEMA,
    git: {
      ...gitState,
      head_sha: gitState.head_sha.toLowerCase(),
    },
    source_input_tree: inputTree,
    external_wheelhouse: wheelhouseProvenance.collectWheelhouseProvenance(wheelhouseDirectory),
    build_environment: {
      node: process.version,
      platform: process.platform,
      arch: process.arch,
    },
  }
}

const writeNewJson = (outputPath, document) => {
  const resolvedOutput = path.resolve(outputPath)
  if (fs.existsSync(resolvedOutput)) {
    throw new Error(`Refusing to overwrite Alpha source provenance: ${resolvedOutput}`)
  }
  const parentDirectory = path.dirname(resolvedOutput)
  if (!fs.existsSync(parentDirectory) || !fs.statSync(parentDirectory).isDirectory()) {
    throw new Error(`Alpha source provenance output parent does not exist: ${parentDirectory}`)
  }
  fs.writeFileSync(resolvedOutput, `${JSON.stringify(document, null, 2)}\n`, 'utf8')
  return resolvedOutput
}

const isSameOrNestedPath = (parentPath, candidatePath) => {
  const relative = path.relative(parentPath, candidatePath)
  return (
    relative === '' ||
    (relative !== '..' && !relative.startsWith(`..${path.sep}`) && !path.isAbsolute(relative))
  )
}

/** Captures a fresh source provenance sidecar. The output must be outside the Git worktree. */
export const captureAlphaSourceProvenance = ({
  outputPath,
  repositoryRoot = defaultRepositoryRoot,
  expectedGitSha,
  sourceInputs,
  wheelhouseDirectory,
} = {}) => {
  if (typeof outputPath !== 'string' || !outputPath.trim()) {
    throw new Error('Alpha source provenance requires a non-empty output path')
  }
  const resolvedRepositoryRoot = path.resolve(repositoryRoot)
  const resolvedOutputPath = path.resolve(outputPath)
  if (isSameOrNestedPath(resolvedRepositoryRoot, resolvedOutputPath)) {
    throw new Error('Alpha source provenance output must be outside the Git worktree')
  }
  const document = createAlphaSourceProvenanceDocument({
    repositoryRoot: resolvedRepositoryRoot,
    expectedGitSha,
    sourceInputs,
    wheelhouseDirectory,
  })
  const writtenPath = writeNewJson(resolvedOutputPath, document)
  return { output_path: writtenPath, document }
}

/** Fails closed if a concurrent writer changes any packaged source input during build. */
export const assertSameAlphaSourceInputTree = (before, after) => {
  const beforeHash = before?.source_input_tree?.sha256
  const afterHash = after?.source_input_tree?.sha256
  if (!SHA256_PATTERN.test(beforeHash ?? '') || !SHA256_PATTERN.test(afterHash ?? '')) {
    throw new Error('Alpha source provenance comparison requires two valid input tree hashes')
  }
  if (beforeHash !== afterHash) {
    throw new Error(
      `Alpha source input tree changed during packaging: before=${beforeHash}, after=${afterHash}`
    )
  }
  return beforeHash
}

/** Fails closed if either packaged source or the selected wheelhouse changes. */
export const assertSameAlphaPackagingInputs = (before, after) => {
  const sourceHash = assertSameAlphaSourceInputTree(before, after)
  const beforeWheelhouse = before?.external_wheelhouse?.tree_sha256
  const afterWheelhouse = after?.external_wheelhouse?.tree_sha256
  if (!SHA256_PATTERN.test(beforeWheelhouse ?? '') || !SHA256_PATTERN.test(afterWheelhouse ?? '')) {
    throw new Error('Alpha provenance comparison requires two wheelhouse tree hashes')
  }
  if (beforeWheelhouse !== afterWheelhouse) {
    throw new Error(
      `Alpha wheelhouse changed during packaging: before=${beforeWheelhouse}, after=${afterWheelhouse}`
    )
  }
  return { source_input_tree_sha256: sourceHash, wheelhouse_tree_sha256: beforeWheelhouse }
}

const parseOptions = argv => {
  const options = {}
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (
      argument === '--output' ||
      argument === '--expected-git-sha' ||
      argument === '--repository-root' ||
      argument === '--wheelhouse'
    ) {
      const value = argv[index + 1]
      if (!value || value.startsWith('--')) throw new Error(`${argument} requires a value`)
      options[argument.slice(2)] = value
      index += 1
    } else {
      throw new Error(`Unsupported Alpha source provenance argument: ${argument}`)
    }
  }
  return options
}

const currentFile = fileURLToPath(import.meta.url)
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve(currentFile)) {
  try {
    const options = parseOptions(process.argv.slice(2))
    const result = captureAlphaSourceProvenance({
      outputPath: options.output,
      expectedGitSha: options['expected-git-sha'] ?? process.env.AUTO_MAS_EXPECTED_GIT_SHA,
      repositoryRoot: options['repository-root'] ?? defaultRepositoryRoot,
      wheelhouseDirectory: options.wheelhouse ?? process.env.AUTO_MAS_WHEELHOUSE_ROOT,
    })
    process.stdout.write(
      `${JSON.stringify(
        {
          output_path: result.output_path,
          git: result.document.git,
          source_input_tree_sha256: result.document.source_input_tree.sha256,
          source_input_file_count: result.document.source_input_tree.file_count,
          source_input_total_bytes: result.document.source_input_tree.total_bytes,
          wheelhouse_tree_sha256: result.document.external_wheelhouse.tree_sha256,
        },
        null,
        2
      )}\n`
    )
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : String(error)}\n`)
    process.exitCode = 1
  }
}

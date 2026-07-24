#!/usr/bin/env node

import { spawn } from 'node:child_process'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  assertExtractedDirectorySafe,
  canonicalizeFilesystemPath,
  normalizePathForComparison,
  pathsOverlapPhysically,
  readArchiveSafetyLimits,
} from './validate-wheelhouse.mjs'
import {
  assertSameAlphaPackagingInputs,
  captureAlphaSourceProvenance,
} from './capture-alpha-source-provenance.mjs'

const require = createRequire(import.meta.url)
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
const defaultAlphaProvenanceDirectory = path.resolve(
  frontendDirectory,
  '..',
  '..',
  '..',
  '..',
  '_alpha_build',
  'a1',
  'alpha-source-provenance'
)

const RELEASE_STEP_TIMEOUTS = Object.freeze({
  typescript: 5 * 60_000,
  wheelhouse: 10 * 60_000,
  renderer: 10 * 60_000,
  rendererValidation: 60_000,
  package: 45 * 60_000,
})

const readOption = (argv, index, optionName) => {
  const value = argv[index + 1]
  if (!value || value.startsWith('--')) {
    throw new Error(`${optionName} requires a non-empty path`)
  }
  return value
}

const resolveUnambiguousPath = (name, cliValue, environmentValue, cwd) => {
  const resolvedCli = cliValue ? canonicalizeFilesystemPath(cliValue, cwd) : undefined
  const resolvedEnvironment = environmentValue?.trim()
    ? canonicalizeFilesystemPath(environmentValue.trim(), cwd)
    : undefined
  if (
    resolvedCli &&
    resolvedEnvironment &&
    normalizePathForComparison(resolvedCli) !== normalizePathForComparison(resolvedEnvironment)
  ) {
    throw new Error(`--${name} and its environment variable resolve to different paths`)
  }
  return resolvedCli ?? resolvedEnvironment
}

export const parseIntegrationReleaseOptions = (argv, env = process.env, cwd = process.cwd()) => {
  let cliWheelhouse
  let cliOutput
  let help = false
  let dryRun = false
  let unpackedOnly = false

  const setOnce = (name, currentValue, value) => {
    if (currentValue != null) throw new Error(`--${name} was provided more than once`)
    if (!value.trim()) throw new Error(`--${name} requires a non-empty path`)
    return value
  }

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index]
    if (argument === '--help' || argument === '-h') {
      help = true
    } else if (argument === '--dry-run') {
      dryRun = true
    } else if (argument === '--unpacked-only') {
      unpackedOnly = true
    } else if (argument === '--wheelhouse') {
      cliWheelhouse = setOnce('wheelhouse', cliWheelhouse, readOption(argv, index, argument))
      index += 1
    } else if (argument.startsWith('--wheelhouse=')) {
      cliWheelhouse = setOnce('wheelhouse', cliWheelhouse, argument.slice('--wheelhouse='.length))
    } else if (argument === '--output') {
      cliOutput = setOnce('output', cliOutput, readOption(argv, index, argument))
      index += 1
    } else if (argument.startsWith('--output=')) {
      cliOutput = setOnce('output', cliOutput, argument.slice('--output='.length))
    } else {
      throw new Error(`Unsupported integration release argument: ${argument}`)
    }
  }

  const wheelhouseDirectory = resolveUnambiguousPath(
    'wheelhouse',
    cliWheelhouse,
    env.AUTO_MAS_WHEELHOUSE_ROOT,
    cwd
  )
  const outputDirectory = resolveUnambiguousPath(
    'output',
    cliOutput,
    env.AUTO_MAS_RELEASE_OUTPUT_ROOT,
    cwd
  )
  if (!help && !wheelhouseDirectory) {
    throw new Error('Provide --wheelhouse or AUTO_MAS_WHEELHOUSE_ROOT')
  }
  if (!help && !outputDirectory) {
    throw new Error('Provide --output or AUTO_MAS_RELEASE_OUTPUT_ROOT')
  }

  return { wheelhouseDirectory, outputDirectory, help, dryRun, unpackedOnly }
}

const pathEntryExists = value => {
  try {
    fs.lstatSync(value)
    return true
  } catch (error) {
    if (error?.code === 'ENOENT') return false
    throw error
  }
}

export const resolveProtectedReleaseDirectories = (env = process.env) => {
  const candidates = [
    ...(pathEntryExists(defaultFrozenReleaseDirectory) ? [defaultFrozenReleaseDirectory] : []),
    ...(env.AUTO_MAS_PROTECTED_RELEASE_ROOTS ?? '')
      .split(path.delimiter)
      .map(value => value.trim())
      .filter(Boolean),
  ]
  const uniqueDirectories = new Map()
  for (const candidate of candidates) {
    const canonicalDirectory = canonicalizeFilesystemPath(candidate)
    uniqueDirectories.set(normalizePathForComparison(canonicalDirectory), canonicalDirectory)
  }
  return [...uniqueDirectories.values()]
}

export const prepareAlphaSourceProvenancePaths = (
  outputDirectory,
  env = process.env,
  repositoryRoot = path.resolve(frontendDirectory, '..')
) => {
  const provenanceRoot = path.resolve(
    env.AUTO_MAS_ALPHA_PROVENANCE_ROOT?.trim() || defaultAlphaProvenanceDirectory
  )
  const canonicalRepositoryRoot = canonicalizeFilesystemPath(repositoryRoot)
  const canonicalProvenanceRoot = canonicalizeFilesystemPath(provenanceRoot)
  if (pathsOverlapPhysically(canonicalRepositoryRoot, canonicalProvenanceRoot)) {
    throw new Error('Alpha source provenance must be stored outside the Git worktree')
  }
  if (pathEntryExists(canonicalProvenanceRoot)) {
    if (!fs.statSync(canonicalProvenanceRoot).isDirectory()) {
      throw new Error('Alpha source provenance root must be a directory')
    }
  } else {
    fs.mkdirSync(canonicalProvenanceRoot, { recursive: true })
  }

  const outputFingerprint = createHash('sha256')
    .update(normalizePathForComparison(canonicalizeFilesystemPath(outputDirectory)))
    .digest('hex')
    .slice(0, 16)
  const prefix = `alpha-source-provenance-${outputFingerprint}`
  const paths = {
    pre: path.join(canonicalProvenanceRoot, `${prefix}.pre.json`),
    post: path.join(canonicalProvenanceRoot, `${prefix}.post.json`),
  }
  for (const candidate of Object.values(paths)) {
    if (pathEntryExists(candidate)) {
      throw new Error(`Refusing to overwrite Alpha source provenance: ${candidate}`)
    }
  }
  return paths
}

const assertCiAlphaSourceProvenanceClean = (provenance, environment) => {
  if (
    environment.AUTO_MAS_EXPECTED_GIT_SHA?.trim() &&
    provenance.document.git.worktree_state !== 'clean'
  ) {
    throw new Error(
      `CI Alpha source provenance must be clean, got: ${provenance.document.git.worktree_state}`
    )
  }
}

export const assertReleasePathsSafe = (
  { wheelhouseDirectory, outputDirectory },
  env = process.env
) => {
  const canonicalWheelhouse = canonicalizeFilesystemPath(wheelhouseDirectory)
  const canonicalOutput = canonicalizeFilesystemPath(outputDirectory)
  if (!fs.existsSync(canonicalWheelhouse) || !fs.statSync(canonicalWheelhouse).isDirectory()) {
    throw new Error(`Wheelhouse directory does not exist: ${canonicalWheelhouse}`)
  }
  if (pathEntryExists(canonicalOutput)) {
    throw new Error(`Integration release output already exists: ${canonicalOutput}`)
  }
  if (
    normalizePathForComparison(canonicalOutput) ===
    normalizePathForComparison(path.parse(canonicalOutput).root)
  ) {
    throw new Error('Integration release output cannot be a filesystem root')
  }
  if (pathsOverlapPhysically(canonicalWheelhouse, canonicalOutput)) {
    throw new Error('Integration release output must not overlap the wheelhouse')
  }
  if (
    resolveProtectedReleaseDirectories(env).some(protectedDirectory =>
      pathsOverlapPhysically(protectedDirectory, canonicalOutput)
    )
  ) {
    throw new Error('Integration release output must not overlap a protected release directory')
  }
  assertExtractedDirectorySafe(canonicalWheelhouse, readArchiveSafetyLimits(env))
  return { wheelhouseDirectory: canonicalWheelhouse, outputDirectory: canonicalOutput }
}

const resolvePackageBin = (packageName, binName = packageName) => {
  const packageJsonPath = require.resolve(`${packageName}/package.json`)
  const packageDirectory = path.dirname(packageJsonPath)
  const packageJson = JSON.parse(fs.readFileSync(packageJsonPath, 'utf8'))
  const relativeBin =
    typeof packageJson.bin === 'string' ? packageJson.bin : packageJson.bin?.[binName]
  if (typeof relativeBin !== 'string' || !relativeBin) {
    throw new Error(`${packageName} does not declare the ${binName} executable`)
  }
  return path.resolve(packageDirectory, relativeBin)
}

export const createIntegrationReleaseCommandPlan = options => {
  const validationScript = path.join(scriptDirectory, 'validate-wheelhouse.mjs')
  const builderConfig = path.join(frontendDirectory, 'electron-builder.integration.cjs')
  return [
    {
      label: 'Electron TypeScript build',
      command: process.execPath,
      args: [
        resolvePackageBin('typescript', 'tsc'),
        '-p',
        path.join(frontendDirectory, 'tsconfig.electron.json'),
      ],
      timeoutMs: RELEASE_STEP_TIMEOUTS.typescript,
    },
    {
      label: 'strict integration wheelhouse validation',
      command: process.execPath,
      args: [
        validationScript,
        '--wheelhouse',
        options.wheelhouseDirectory,
        '--require-snapshot-contract',
      ],
      timeoutMs: RELEASE_STEP_TIMEOUTS.wheelhouse,
    },
    {
      label: 'renderer build',
      command: process.execPath,
      args: [resolvePackageBin('vite', 'vite'), 'build', '--emptyOutDir=false'],
      timeoutMs: RELEASE_STEP_TIMEOUTS.renderer,
    },
    {
      label: 'renderer chunk graph validation',
      command: process.execPath,
      args: [path.join(scriptDirectory, 'verify-renderer-chunks.mjs')],
      timeoutMs: RELEASE_STEP_TIMEOUTS.rendererValidation,
    },
    {
      label: 'Windows x64 integration package',
      command: process.execPath,
      args: [
        resolvePackageBin('electron-builder', 'electron-builder'),
        '--win',
        '--x64',
        '--publish',
        'never',
        '--config',
        builderConfig,
        ...(options.unpackedOnly ? ['--dir'] : []),
      ],
      timeoutMs: RELEASE_STEP_TIMEOUTS.package,
    },
  ]
}

export const prepareIntegrationRendererOutput = (
  rendererOutputDirectory = path.join(frontendDirectory, 'dist')
) => {
  for (const relativePath of ['index.html', 'assets']) {
    fs.rmSync(path.join(rendererOutputDirectory, relativePath), {
      recursive: true,
      force: true,
    })
  }
}

const terminateProcessTree = child => {
  if (child.pid == null) return Promise.resolve()
  if (process.platform === 'win32') {
    return new Promise((resolve, reject) => {
      const killer = spawn('taskkill.exe', ['/pid', String(child.pid), '/T', '/F'], {
        stdio: 'ignore',
        windowsHide: true,
        shell: false,
      })
      let finished = false
      const finishKiller = error => {
        if (finished) return
        finished = true
        clearTimeout(killerDeadline)
        killer.unref()
        if (error) reject(error)
        else resolve()
      }
      const killerDeadline = setTimeout(() => {
        killer.kill('SIGKILL')
        finishKiller(new Error('taskkill.exe did not exit within 5000 ms'))
      }, 5000)
      killer.once('error', error => finishKiller(error))
      killer.once('close', code => {
        if (code === 0) finishKiller()
        else finishKiller(new Error(`taskkill.exe exited with code ${code ?? '<unknown>'}`))
      })
    })
  }
  child.kill('SIGKILL')
  return Promise.resolve()
}

const detachStuckChild = child => {
  try {
    child.kill('SIGKILL')
  } catch {
    // The final error still reports that the tree did not exit.
  }
  child.stdin?.destroy()
  child.stdout?.destroy()
  child.stderr?.destroy()
  child.unref()
}

export const runReleaseCommand = (
  step,
  env = process.env,
  processControl = { terminate: terminateProcessTree, graceMs: 10_000 }
) => {
  return new Promise((resolve, reject) => {
    const child = spawn(step.command, step.args, {
      cwd: frontendDirectory,
      env,
      shell: false,
      stdio: 'inherit',
      windowsHide: true,
    })
    let settled = false
    let timedOut = false
    let terminationDeadline

    const finish = error => {
      if (settled) return
      settled = true
      clearTimeout(timeout)
      if (terminationDeadline) clearTimeout(terminationDeadline)
      if (error) reject(error)
      else resolve()
    }

    child.once('error', error => {
      finish(new Error(`${step.label} failed to start: ${error.message}`))
    })
    child.once('close', (code, signal) => {
      if (timedOut) {
        finish(new Error(`${step.label} timed out after ${step.timeoutMs} ms`))
      } else if (code !== 0) {
        finish(
          new Error(
            `${step.label} failed with exit code ${code ?? '<unknown>'}${signal ? ` (signal ${signal})` : ''}`
          )
        )
      } else {
        finish()
      }
    })

    const timeout = setTimeout(() => {
      timedOut = true
      void Promise.resolve(processControl.terminate(child)).catch(() => {
        try {
          child.kill('SIGKILL')
        } catch {
          // The grace deadline below detaches every remaining handle.
        }
      })
      terminationDeadline = setTimeout(() => {
        detachStuckChild(child)
        finish(new Error(`${step.label} timed out and its process tree did not exit`))
      }, processControl.graceMs)
    }, step.timeoutMs)
  })
}

const formatCommandPlan = plan =>
  plan.map(step => ({
    label: step.label,
    command: step.command,
    args: step.args,
    timeoutMs: step.timeoutMs,
    shell: false,
  }))

const printUsage = () => {
  console.log(`Usage:
  yarn release:integration --wheelhouse <complete-wheelhouse> --output <new-directory>
  yarn release:integration --wheelhouse <complete-wheelhouse> --output <new-directory> --unpacked-only
  yarn release:integration --wheelhouse <complete-wheelhouse> --output <new-directory> --dry-run

Environment alternative:
  AUTO_MAS_WHEELHOUSE_ROOT=<complete-wheelhouse>
  AUTO_MAS_RELEASE_OUTPUT_ROOT=<new-directory>
  AUTO_MAS_PROTECTED_RELEASE_ROOTS=<path-delimited-read-only-release-roots>

Both inputs are explicit. The output must not exist, and the selected wheelhouse is
bound to res/integration-snapshot.json before electron-builder can package it.
--unpacked-only produces win-unpacked for an external signing/installer pipeline.
--dry-run validates paths and extracted-tree budgets, then prints the exact
non-shell command plan without writing output.

Archive ingress and this extracted-tree gate share these optional positive-integer
limits: AUTO_MAS_ARCHIVE_MAX_BYTES, AUTO_MAS_ARCHIVE_MAX_ENTRIES,
AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES, and AUTO_MAS_ARCHIVE_MAX_FILE_BYTES.
The archive-byte limit is enforced by the download/extraction ingress; this script
revalidates entries, expanded bytes, single-file bytes, and filesystem links.`)
}

const main = async () => {
  const options = parseIntegrationReleaseOptions(process.argv.slice(2))
  if (options.help) {
    printUsage()
    return
  }
  const safePaths = assertReleasePathsSafe(options)
  const safeOptions = { ...options, ...safePaths }

  const packageJson = JSON.parse(
    fs.readFileSync(path.join(frontendDirectory, 'package.json'), 'utf8')
  )
  if (typeof packageJson.version !== 'string' || !/^v?6\..*alpha/iu.test(packageJson.version)) {
    throw new Error('The integration release command is restricted to v6 alpha packages')
  }

  const releaseEnvironment = {
    ...process.env,
    AUTO_MAS_WHEELHOUSE_ROOT: safeOptions.wheelhouseDirectory,
    AUTO_MAS_RELEASE_OUTPUT_ROOT: safeOptions.outputDirectory,
  }
  const commandPlan = createIntegrationReleaseCommandPlan(safeOptions)
  if (safeOptions.dryRun) {
    console.log(JSON.stringify(formatCommandPlan(commandPlan), null, 2))
    return
  }
  const provenancePaths = prepareAlphaSourceProvenancePaths(safeOptions.outputDirectory)
  let preProvenance
  for (const step of commandPlan) {
    if (step.label === 'renderer build') {
      prepareIntegrationRendererOutput()
    }
    if (step.label === 'Windows x64 integration package') {
      preProvenance = captureAlphaSourceProvenance({
        outputPath: provenancePaths.pre,
        repositoryRoot: path.resolve(frontendDirectory, '..'),
        expectedGitSha: releaseEnvironment.AUTO_MAS_EXPECTED_GIT_SHA,
        wheelhouseDirectory: safeOptions.wheelhouseDirectory,
      })
      assertCiAlphaSourceProvenanceClean(preProvenance, releaseEnvironment)
      releaseEnvironment.AUTO_MAS_ALPHA_PROVENANCE_FILE = preProvenance.output_path
    }
    await runReleaseCommand(step, releaseEnvironment)
  }

  if (!preProvenance) {
    throw new Error('Alpha source provenance was not captured before Electron packaging')
  }
  const postProvenance = captureAlphaSourceProvenance({
    outputPath: provenancePaths.post,
    repositoryRoot: path.resolve(frontendDirectory, '..'),
    expectedGitSha: releaseEnvironment.AUTO_MAS_EXPECTED_GIT_SHA,
    wheelhouseDirectory: safeOptions.wheelhouseDirectory,
  })
  assertCiAlphaSourceProvenanceClean(postProvenance, releaseEnvironment)
  const packagingInputs = assertSameAlphaPackagingInputs(
    preProvenance.document,
    postProvenance.document
  )
  console.log(
    `Alpha source provenance verified: source=${packagingInputs.source_input_tree_sha256}, wheelhouse=${packagingInputs.wheelhouse_tree_sha256} (${preProvenance.document.git.worktree_state})`
  )
}

const isMainModule =
  process.argv[1] != null && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (isMainModule) {
  main().catch(error => {
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  })
}

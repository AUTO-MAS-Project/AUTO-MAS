import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import {
  assertReleasePathsSafe,
  createIntegrationReleaseCommandPlan,
  parseIntegrationReleaseOptions,
  prepareAlphaSourceProvenancePaths,
  prepareIntegrationRendererOutput,
  resolveProtectedReleaseDirectories,
  runReleaseCommand,
} from './build-integration-release.mjs'
import {
  ARCHIVE_SAFETY_DEFAULTS,
  assertExtractedDirectorySafe,
  canonicalizeFilesystemPath,
  parseValidationOptions,
  readArchiveSafetyLimits,
} from './validate-wheelhouse.mjs'
import wheelhouseProvenance from './alpha-wheelhouse-provenance.cjs'

const testDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(testDirectory, '..')
const builderConfigPath = path.join(frontendDirectory, 'electron-builder.integration.cjs')
const integrationSnapshotPath = path.join(
  frontendDirectory,
  '..',
  'res',
  'integration-snapshot.json'
)

const createAlphaSourceProvenance = (directory, wheelhouseDirectory) => {
  const provenancePath = path.join(directory, 'alpha-source-provenance.json')
  fs.mkdirSync(path.dirname(provenancePath), { recursive: true })
  if (!fs.existsSync(provenancePath)) {
    fs.writeFileSync(
      provenancePath,
      JSON.stringify({
        schema: 'auto-mas.experimental-alpha.source-provenance/v2',
        git: {
          head_sha: 'a'.repeat(40),
          worktree_state: 'clean',
        },
        source_input_tree: {
          sha256: 'b'.repeat(64),
        },
        external_wheelhouse: wheelhouseProvenance.collectWheelhouseProvenance(wheelhouseDirectory),
      })
    )
  }
  return provenancePath
}

const createDirectoryLink = (target, linkPath) => {
  try {
    fs.symlinkSync(target, linkPath, process.platform === 'win32' ? 'junction' : 'dir')
    return true
  } catch (error) {
    if (['EPERM', 'EACCES', 'ENOTSUP'].includes(error?.code)) return false
    throw error
  }
}

const loadBuilderConfig = (wheelhouseDirectory, outputDirectory, additionalEnvironment = {}) => {
  const provenancePath =
    additionalEnvironment.AUTO_MAS_ALPHA_PROVENANCE_FILE ??
    createAlphaSourceProvenance(
      path.join(path.dirname(outputDirectory), 'provenance'),
      wheelhouseDirectory
    )
  return spawnSync(
    process.execPath,
    [
      '-e',
      `const childProcess = require('node:child_process')
childProcess.spawnSync = () => ({ status: 0 })
const config = require(${JSON.stringify(builderConfigPath)})
process.stdout.write(JSON.stringify({
  appId: config.appId,
  productName: config.productName,
  artifactName: config.artifactName,
  extraMetadata: config.extraMetadata,
  directories: config.directories,
  win: config.win,
  nsis: config.nsis,
  extraResources: config.extraResources,
}))`,
    ],
    {
      cwd: frontendDirectory,
      encoding: 'utf8',
      env: {
        ...process.env,
        AUTO_MAS_WHEELHOUSE_ROOT: wheelhouseDirectory,
        AUTO_MAS_RELEASE_OUTPUT_ROOT: outputDirectory,
        AUTO_MAS_ALPHA_PROVENANCE_FILE: provenancePath,
        ...additionalEnvironment,
      },
      shell: false,
      windowsHide: true,
    }
  )
}

describe('integration release CLI', () => {
  let temporaryDirectory
  let wheelhouseDirectory
  let outputDirectory

  beforeEach(() => {
    temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-release-cli-'))
    wheelhouseDirectory = path.join(temporaryDirectory, 'wheel house')
    outputDirectory = path.join(temporaryDirectory, 'release output')
    fs.mkdirSync(wheelhouseDirectory)
    fs.writeFileSync(path.join(wheelhouseDirectory, 'package-1.0-py3-none-any.whl'), 'wheel')
    fs.writeFileSync(path.join(wheelhouseDirectory, 'manifest.json'), '{"schema_version":3}')
    fs.writeFileSync(path.join(wheelhouseDirectory, 'runtime-lock.json'), '{"schema_version":1}')
  })

  afterEach(() => {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true })
  })

  it('accepts explicit CLI paths without splitting path contents into commands', () => {
    const options = parseIntegrationReleaseOptions(
      ['--wheelhouse', wheelhouseDirectory, '--output', outputDirectory],
      {},
      temporaryDirectory
    )

    expect(options).toMatchObject({ wheelhouseDirectory, outputDirectory, help: false })
    const validationStep = createIntegrationReleaseCommandPlan(options).find(step =>
      step.label.includes('validation')
    )
    expect(validationStep.args).toContain(wheelhouseDirectory)
    expect(validationStep.args.filter(argument => argument === wheelhouseDirectory)).toHaveLength(1)
    expect(validationStep.timeoutMs).toBeGreaterThan(0)
  })

  it('supports a read-only dry run and an unpacked-only signing handoff', () => {
    const options = parseIntegrationReleaseOptions(
      [
        '--wheelhouse',
        wheelhouseDirectory,
        '--output',
        outputDirectory,
        '--dry-run',
        '--unpacked-only',
      ],
      {},
      temporaryDirectory
    )
    const packageStep = createIntegrationReleaseCommandPlan(options).at(-1)

    expect(options).toMatchObject({ dryRun: true, unpackedOnly: true })
    expect(packageStep.args).toContain('--dir')
    expect(packageStep.timeoutMs).toBeGreaterThanOrEqual(30 * 60_000)
  })

  it('cleans only renderer-owned outputs and preserves unrelated package directories', () => {
    const rendererOutputDirectory = path.join(temporaryDirectory, 'renderer-output')
    fs.mkdirSync(path.join(rendererOutputDirectory, 'assets'), { recursive: true })
    fs.mkdirSync(path.join(rendererOutputDirectory, 'win-unpacked'), { recursive: true })
    fs.writeFileSync(path.join(rendererOutputDirectory, 'index.html'), 'stale')
    fs.writeFileSync(path.join(rendererOutputDirectory, 'assets', 'stale.js'), 'stale')
    fs.writeFileSync(path.join(rendererOutputDirectory, 'win-unpacked', 'app.asar'), 'preserve')

    prepareIntegrationRendererOutput(rendererOutputDirectory)

    expect(fs.existsSync(path.join(rendererOutputDirectory, 'index.html'))).toBe(false)
    expect(fs.existsSync(path.join(rendererOutputDirectory, 'assets'))).toBe(false)
    expect(
      fs.readFileSync(path.join(rendererOutputDirectory, 'win-unpacked', 'app.asar'), 'utf8')
    ).toBe('preserve')

    const rendererStep = createIntegrationReleaseCommandPlan({
      wheelhouseDirectory,
      outputDirectory,
    }).find(step => step.label === 'renderer build')
    expect(rendererStep.args).toContain('--emptyOutDir=false')
    const rendererValidationStep = createIntegrationReleaseCommandPlan({
      wheelhouseDirectory,
      outputDirectory,
    }).find(step => step.label === 'renderer chunk graph validation')
    expect(rendererValidationStep.args.at(-1)).toMatch(/verify-renderer-chunks\.mjs$/u)
    expect(rendererValidationStep.timeoutMs).toBeGreaterThan(0)
  })

  it('accepts the environment-only release contract', () => {
    expect(
      parseIntegrationReleaseOptions(
        [],
        {
          AUTO_MAS_WHEELHOUSE_ROOT: wheelhouseDirectory,
          AUTO_MAS_RELEASE_OUTPUT_ROOT: outputDirectory,
        },
        temporaryDirectory
      )
    ).toMatchObject({ wheelhouseDirectory, outputDirectory })
  })

  it('treats Windows path casing as the same explicit release input', () => {
    if (process.platform !== 'win32') return

    expect(
      parseIntegrationReleaseOptions(
        ['--wheelhouse', wheelhouseDirectory, '--output', outputDirectory],
        {
          AUTO_MAS_WHEELHOUSE_ROOT: wheelhouseDirectory.toUpperCase(),
          AUTO_MAS_RELEASE_OUTPUT_ROOT: outputDirectory.toUpperCase(),
        },
        temporaryDirectory
      )
    ).toMatchObject({ wheelhouseDirectory, outputDirectory })
  })

  it('canonicalizes CLI and environment paths through physical ancestors', () => {
    const physicalDirectory = path.join(temporaryDirectory, 'physical')
    const linkedDirectory = path.join(temporaryDirectory, 'linked')
    const linkedWheelhouse = path.join(temporaryDirectory, 'linked-wheelhouse')
    fs.mkdirSync(physicalDirectory)
    if (!createDirectoryLink(physicalDirectory, linkedDirectory)) return
    if (!createDirectoryLink(wheelhouseDirectory, linkedWheelhouse)) return

    const options = parseIntegrationReleaseOptions(
      [
        '--wheelhouse',
        linkedWheelhouse,
        '--output',
        path.join(linkedDirectory, 'missing', 'release'),
      ],
      {
        AUTO_MAS_WHEELHOUSE_ROOT: wheelhouseDirectory,
        AUTO_MAS_RELEASE_OUTPUT_ROOT: path.join(physicalDirectory, 'missing', 'release'),
      },
      temporaryDirectory
    )

    expect(options.wheelhouseDirectory).toBe(canonicalizeFilesystemPath(wheelhouseDirectory))
    expect(options.outputDirectory).toBe(
      canonicalizeFilesystemPath(path.join(physicalDirectory, 'missing', 'release'))
    )
  })

  it('rejects ambiguous or unsupported release arguments', () => {
    expect(() =>
      parseIntegrationReleaseOptions(
        ['--wheelhouse', wheelhouseDirectory, '--output', outputDirectory, '--publish'],
        {},
        temporaryDirectory
      )
    ).toThrow('Unsupported integration release argument')
    expect(() =>
      parseIntegrationReleaseOptions(
        ['--wheelhouse', wheelhouseDirectory, '--output', outputDirectory],
        { AUTO_MAS_WHEELHOUSE_ROOT: path.join(temporaryDirectory, 'different') },
        temporaryDirectory
      )
    ).toThrow('resolve to different paths')
  })

  it('refuses an existing or overlapping output directory', () => {
    expect(() =>
      assertReleasePathsSafe({
        wheelhouseDirectory,
        outputDirectory: path.join(wheelhouseDirectory, 'package'),
      })
    ).toThrow('must not overlap')
    expect(() =>
      assertReleasePathsSafe({
        wheelhouseDirectory,
        outputDirectory: path.join(wheelhouseDirectory, '..release'),
      })
    ).toThrow('must not overlap')

    fs.mkdirSync(outputDirectory)
    expect(() => assertReleasePathsSafe({ wheelhouseDirectory, outputDirectory })).toThrow(
      'output already exists'
    )
  })

  it('rejects a physically overlapping output through a junction ancestor', () => {
    const linkedWheelhouse = path.join(temporaryDirectory, 'wheelhouse-link')
    if (!createDirectoryLink(wheelhouseDirectory, linkedWheelhouse)) return

    expect(() =>
      assertReleasePathsSafe({
        wheelhouseDirectory,
        outputDirectory: path.join(linkedWheelhouse, 'missing', 'release'),
      })
    ).toThrow('must not overlap')
  })

  it('refuses output inside an explicitly protected release root', () => {
    const protectedDirectory = path.join(temporaryDirectory, 'frozen-r6')
    fs.mkdirSync(protectedDirectory)
    const environment = {
      AUTO_MAS_PROTECTED_RELEASE_ROOTS: protectedDirectory,
    }

    expect(resolveProtectedReleaseDirectories(environment)).toContain(
      canonicalizeFilesystemPath(protectedDirectory)
    )
    expect(() =>
      assertReleasePathsSafe(
        {
          wheelhouseDirectory,
          outputDirectory: path.join(protectedDirectory, 'new-alpha-output'),
        },
        environment
      )
    ).toThrow('protected release directory')

    const directBuilder = loadBuilderConfig(
      wheelhouseDirectory,
      path.join(protectedDirectory, 'direct-builder-output'),
      environment
    )
    expect(directBuilder.status).not.toBe(0)
    expect(directBuilder.stderr).toContain('protected release directory')
  })

  it('stores Alpha source provenance outside the Git worktree without overwriting evidence', () => {
    const repositoryRoot = path.join(temporaryDirectory, 'repository')
    const provenanceRoot = path.join(temporaryDirectory, 'provenance')
    fs.mkdirSync(repositoryRoot)

    const paths = prepareAlphaSourceProvenancePaths(
      outputDirectory,
      { AUTO_MAS_ALPHA_PROVENANCE_ROOT: provenanceRoot },
      repositoryRoot
    )

    expect(paths.pre).toMatch(/\.pre\.json$/u)
    expect(paths.post).toMatch(/\.post\.json$/u)
    expect(fs.existsSync(provenanceRoot)).toBe(true)
    expect(() =>
      prepareAlphaSourceProvenancePaths(
        outputDirectory,
        { AUTO_MAS_ALPHA_PROVENANCE_ROOT: path.join(repositoryRoot, 'provenance') },
        repositoryRoot
      )
    ).toThrow('outside the Git worktree')
  })

  it('enforces extracted entry, expanded-size, and single-file budgets before output exists', () => {
    fs.writeFileSync(path.join(wheelhouseDirectory, 'one.whl'), '123456')
    fs.writeFileSync(path.join(wheelhouseDirectory, 'two.whl'), 'abcdef')

    expect(() =>
      assertReleasePathsSafe(
        { wheelhouseDirectory, outputDirectory },
        { AUTO_MAS_ARCHIVE_MAX_ENTRIES: '1' }
      )
    ).toThrow('AUTO_MAS_ARCHIVE_MAX_ENTRIES')
    expect(fs.existsSync(outputDirectory)).toBe(false)

    expect(() =>
      assertReleasePathsSafe(
        { wheelhouseDirectory, outputDirectory },
        { AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES: '10' }
      )
    ).toThrow('AUTO_MAS_ARCHIVE_MAX_EXPANDED_BYTES')
    expect(fs.existsSync(outputDirectory)).toBe(false)

    expect(() =>
      assertReleasePathsSafe(
        { wheelhouseDirectory, outputDirectory },
        { AUTO_MAS_ARCHIVE_MAX_FILE_BYTES: '5' }
      )
    ).toThrow('AUTO_MAS_ARCHIVE_MAX_FILE_BYTES')
    expect(fs.existsSync(outputDirectory)).toBe(false)
  })

  it('accepts a legal extracted tree and rejects links inside it when links are available', () => {
    const nestedDirectory = path.join(wheelhouseDirectory, 'nested')
    fs.mkdirSync(nestedDirectory)
    fs.writeFileSync(path.join(nestedDirectory, 'legal.whl'), 'wheel')

    expect(
      assertExtractedDirectorySafe(wheelhouseDirectory, {
        ...ARCHIVE_SAFETY_DEFAULTS,
        maxEntries: 10,
        maxExpandedBytes: 100,
        maxFileBytes: 100,
      })
    ).toMatchObject({ entryCount: 5, expandedBytes: 50 })

    const outsideDirectory = path.join(temporaryDirectory, 'outside')
    fs.mkdirSync(outsideDirectory)
    if (!createDirectoryLink(outsideDirectory, path.join(wheelhouseDirectory, 'escape'))) return
    expect(() => assertExtractedDirectorySafe(wheelhouseDirectory)).toThrow(
      'symbolic link or junction'
    )
  })

  it('rejects invalid archive safety limit overrides', () => {
    expect(() => readArchiveSafetyLimits({ AUTO_MAS_ARCHIVE_MAX_BYTES: '-1' })).toThrow(
      'positive decimal integer'
    )
    expect(() => readArchiveSafetyLimits({ AUTO_MAS_ARCHIVE_MAX_ENTRIES: '0' })).toThrow(
      'positive decimal integer'
    )
    expect(() =>
      readArchiveSafetyLimits({ AUTO_MAS_ARCHIVE_MAX_FILE_BYTES: '9007199254740992' })
    ).toThrow('safe integer range')
  })

  it('makes the direct builder config refuse existing output and accept a fresh staging root', () => {
    fs.mkdirSync(outputDirectory)
    const existingOutput = loadBuilderConfig(wheelhouseDirectory, outputDirectory)
    expect(existingOutput.status).not.toBe(0)
    expect(existingOutput.stderr).toContain('AUTO_MAS_RELEASE_OUTPUT_ROOT already exists')

    const freshOutput = path.join(temporaryDirectory, 'fresh', 'release')
    const freshStaging = loadBuilderConfig(wheelhouseDirectory, freshOutput)
    expect(freshStaging.status).toBe(0)
    expect(JSON.parse(freshStaging.stdout)).toMatchObject({
      appId: 'top.auto-mas.experimental-alpha',
      productName: 'AUTO-MAS v6 Experimental Alpha',
      artifactName: 'AUTO-MAS-v6-Experimental-Alpha-${version}-${arch}.${ext}',
      extraMetadata: {
        productName: 'AUTO-MAS v6 Experimental Alpha',
        autoMasReleaseChannel: 'experimental-alpha',
        autoMasSourceInputTreeSha256: 'b'.repeat(64),
        autoMasWheelhouseTreeSha256:
          wheelhouseProvenance.collectWheelhouseProvenance(wheelhouseDirectory).tree_sha256,
      },
      directories: {
        output: canonicalizeFilesystemPath(freshOutput),
      },
      win: {
        executableName: 'AUTO-MAS-v6-Experimental-Alpha',
        signAndEditExecutable: false,
      },
      nsis: {
        oneClick: false,
        allowToChangeInstallationDirectory: false,
        deleteAppDataOnUninstall: false,
        shortcutName: 'AUTO-MAS v6 Experimental Alpha',
        uninstallDisplayName: 'AUTO-MAS v6 Experimental Alpha',
      },
    })
  })

  it('requires the Alpha builder and snapshot to agree on a manual-only release policy', () => {
    const snapshot = JSON.parse(fs.readFileSync(integrationSnapshotPath, 'utf8'))
    const freshOutput = path.join(temporaryDirectory, 'policy', 'release')
    const builder = loadBuilderConfig(wheelhouseDirectory, freshOutput)

    expect(builder.status).toBe(0)
    expect(snapshot.release_policy).toMatchObject({
      channel: 'experimental-alpha',
      embedded_updater: 'manual-only',
    })
    expect(JSON.parse(builder.stdout).extraMetadata).toMatchObject({
      autoMasReleaseChannel: snapshot.release_policy.channel,
      autoMasEmbeddedUpdatePolicy: snapshot.release_policy.embedded_updater,
    })
  })

  it('rejects an Alpha builder when the snapshot release policy is incomplete', () => {
    const builderSource = fs.readFileSync(builderConfigPath, 'utf8')

    expect(builderSource).toContain('experimentalAlphaSnapshotPolicy')
    expect(builderSource).toContain('autoMasEmbeddedUpdatePolicy')
    expect(builderSource).toContain('Experimental Alpha snapshot must declare release_policy')
    expect(builderSource).toContain("policy.embedded_updater !== 'manual-only'")
    expect(builderSource).toContain('policy.channel !== experimentalAlphaIdentity.releaseChannel')
    expect(builderSource).not.toContain(
      'autoMasReleaseChannel: experimentalAlphaIdentity.releaseChannel'
    )
    expect(builderSource).toContain('AUTO_MAS_ALPHA_PROVENANCE_FILE')
    expect(builderSource).toContain('source-provenance.json')
    expect(builderSource).toContain("'docs', 'experimental-alpha'")
    expect(builderSource).toContain('ALPHA_EVIDENCE_FILENAMES')
    expect(builderSource).toContain('auto-mas.experimental-alpha.ci-gates/v1')
    expect(builderSource).toContain("'verify_offline_first_start.ps1'")
    expect(builderSource).toContain("'verify_wheelhouse_snapshot.py'")
  })

  it('ships only safe Alpha verification scripts', () => {
    const builder = loadBuilderConfig(wheelhouseDirectory, outputDirectory)
    expect(builder.status).toBe(0)
    const scriptsResource = JSON.parse(builder.stdout).extraResources.find(
      resource => resource.to === 'integration-snapshot/scripts'
    )

    expect(scriptsResource.filter).toEqual([
      'verify_offline_first_start.ps1',
      'verify_wheelhouse_snapshot.py',
    ])
  })

  it('ships the complete Alpha evidence template bundle', () => {
    const builder = loadBuilderConfig(wheelhouseDirectory, outputDirectory)
    expect(builder.status).toBe(0)
    const evidenceResource = JSON.parse(builder.stdout).extraResources.find(
      resource => resource.to === 'integration-snapshot/evidence'
    )

    expect(evidenceResource.filter).toEqual([
      'ALPHA_README.md',
      'RELEASE_NOTES.md',
      'KNOWN_GAPS.md',
      'MANUAL_TEST_CARDS.md',
      'OFFLINE_FIRST_START.md',
      'CI_GATES.json',
    ])
    expect(evidenceResource.from).toContain(path.join('docs', 'experimental-alpha'))
  })

  it('requires a readable Alpha source provenance file', () => {
    const result = loadBuilderConfig(wheelhouseDirectory, outputDirectory, {
      AUTO_MAS_ALPHA_PROVENANCE_FILE: path.join(temporaryDirectory, 'missing-provenance.json'),
    })

    expect(result.status).not.toBe(0)
    expect(result.stderr).toContain('Experimental Alpha source provenance cannot be read')
  })

  it('rejects source provenance captured from another wheelhouse', () => {
    const otherWheelhouse = path.join(temporaryDirectory, 'other-wheelhouse')
    fs.mkdirSync(otherWheelhouse)
    fs.writeFileSync(path.join(otherWheelhouse, 'other-1.0-py3-none-any.whl'), 'other')
    fs.writeFileSync(path.join(otherWheelhouse, 'manifest.json'), '{"schema_version":3}')
    fs.writeFileSync(path.join(otherWheelhouse, 'runtime-lock.json'), '{"schema_version":1}')
    const provenancePath = createAlphaSourceProvenance(
      path.join(temporaryDirectory, 'other-provenance'),
      otherWheelhouse
    )

    const result = loadBuilderConfig(wheelhouseDirectory, outputDirectory, {
      AUTO_MAS_ALPHA_PROVENANCE_FILE: provenancePath,
    })

    expect(result.status).not.toBe(0)
    expect(result.stderr).toContain('captured from a different directory')
  })

  it('makes the direct builder config reject junction overlap', () => {
    const linkedWheelhouse = path.join(temporaryDirectory, 'builder-wheelhouse-link')
    if (!createDirectoryLink(wheelhouseDirectory, linkedWheelhouse)) return

    const result = loadBuilderConfig(
      wheelhouseDirectory,
      path.join(linkedWheelhouse, 'missing', 'release')
    )
    expect(result.status).not.toBe(0)
    expect(result.stderr).toContain('Release output must not overlap the wheelhouse')
  })

  it('bounds a stuck child process and rejects on timeout', async () => {
    await expect(
      runReleaseCommand({
        label: 'stuck release test child',
        command: process.execPath,
        args: ['-e', 'setInterval(() => {}, 1000)'],
        timeoutMs: 100,
      })
    ).rejects.toThrow('timed out')
  })

  it('still exits when Windows tree termination itself fails', async () => {
    const startedAt = Date.now()
    await expect(
      runReleaseCommand(
        {
          label: 'failed tree termination test child',
          command: process.execPath,
          args: ['-e', 'setInterval(() => {}, 1000)'],
          timeoutMs: 50,
        },
        process.env,
        {
          terminate: async () => {
            throw new Error('injected taskkill failure')
          },
          graceMs: 100,
        }
      )
    ).rejects.toThrow('timed out')
    expect(Date.now() - startedAt).toBeLessThan(2000)
  })
})

describe('strict wheelhouse validation CLI', () => {
  it('requires an explicit wheelhouse in snapshot-contract mode', () => {
    expect(() =>
      parseValidationOptions(['--require-snapshot-contract'], {}, 'C:\\work', 'C:\\repository')
    ).toThrow('requires --wheelhouse or AUTO_MAS_WHEELHOUSE_ROOT')
  })

  it('uses AUTO_MAS_WHEELHOUSE_ROOT and rejects a conflicting CLI value', () => {
    const cwd = path.resolve('validation-test-root')
    const environmentPath = path.join(cwd, 'c2')
    expect(
      parseValidationOptions(
        ['--require-snapshot-contract'],
        { AUTO_MAS_WHEELHOUSE_ROOT: environmentPath },
        cwd,
        cwd
      ).wheelhouseDirectory
    ).toBe(environmentPath)
    expect(() =>
      parseValidationOptions(
        ['--wheelhouse', path.join(cwd, 'other'), '--require-snapshot-contract'],
        { AUTO_MAS_WHEELHOUSE_ROOT: environmentPath },
        cwd,
        cwd
      )
    ).toThrow('resolve to different directories')
  })

  it('treats Windows wheelhouse casing as one canonical directory', () => {
    if (process.platform !== 'win32') return
    const temporaryDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-validation-case-'))
    try {
      const wheelhouseDirectory = path.join(temporaryDirectory, 'Wheel House')
      fs.mkdirSync(wheelhouseDirectory)
      expect(
        parseValidationOptions(
          ['--wheelhouse', wheelhouseDirectory.toUpperCase(), '--require-snapshot-contract'],
          { AUTO_MAS_WHEELHOUSE_ROOT: wheelhouseDirectory.toLowerCase() },
          temporaryDirectory,
          temporaryDirectory
        ).wheelhouseDirectory
      ).toBe(canonicalizeFilesystemPath(wheelhouseDirectory))
    } finally {
      fs.rmSync(temporaryDirectory, { recursive: true, force: true })
    }
  })

  it('keeps the legacy default wheelhouse outside strict mode', () => {
    const repositoryRoot = path.resolve('legacy-repository')
    expect(parseValidationOptions([], {}, repositoryRoot, repositoryRoot)).toMatchObject({
      wheelhouseDirectory: path.join(repositoryRoot, 'plugins', 'wheels'),
      requireSnapshotContract: false,
    })
  })
})

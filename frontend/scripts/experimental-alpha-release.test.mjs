import { createRequire } from 'node:module'
import { createHash } from 'node:crypto'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { afterEach, describe, expect, it } from 'vitest'

import {
  createInstallerScript,
  finalizeExperimentalAlphaInstaller,
  fullArchiveFilename,
  fullInstallerFilename,
  prepareExperimentalAlphaInstaller,
  prepareExperimentalAlphaPortable,
  sha256SumsFilename,
  verifyArtifactEvidenceBundle,
  verifyStageEvidenceIndex,
} from './generate-experimental-alpha-installer.mjs'
import wheelhouseProvenance from './alpha-wheelhouse-provenance.cjs'

const require = createRequire(import.meta.url)
const { experimentalAlphaIdentity } = require('./experimental-alpha-release-identity.cjs')
const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')
const alphaEvidenceFilenames = [
  'ALPHA_README.md',
  'RELEASE_NOTES.md',
  'KNOWN_GAPS.md',
  'MANUAL_TEST_CARDS.md',
  'OFFLINE_FIRST_START.md',
  'CI_GATES.json',
]

const temporaryDirectories = []

const sha256File = filePath => createHash('sha256').update(fs.readFileSync(filePath)).digest('hex')

const makeTemporaryDirectory = () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-alpha-release-'))
  temporaryDirectories.push(directory)
  return directory
}

const writeRequiredFullStage = directory => {
  const files = [
    `${experimentalAlphaIdentity.executableName}.exe`,
    'resources/app.asar',
    'resources/integration-snapshot/manifest.json',
    'resources/integration-snapshot/source-provenance.json',
    'resources/integration-snapshot/plugins/wheels/manifest.json',
    'resources/integration-snapshot/plugins/wheels/runtime-lock.json',
    'resources/integration-snapshot/plugins/wheels/package-1.0-py3-none-any.whl',
    'resources/integration-snapshot/scripts/verify_offline_first_start.ps1',
    'resources/integration-snapshot/scripts/verify_wheelhouse_snapshot.py',
    ...alphaEvidenceFilenames.map(
      filename => `resources/integration-snapshot/evidence/${filename}`
    ),
    'environment/python/python.exe',
    'environment/python/Scripts/uv.exe',
    'environment/git/bin/git.exe',
    'resources/assets/AUTO-MAS.ico',
  ]
  for (const relativePath of files) {
    const target = path.join(directory, ...relativePath.split('/'))
    fs.mkdirSync(path.dirname(target), { recursive: true })
    fs.writeFileSync(target, relativePath)
  }
  fs.writeFileSync(
    path.join(directory, 'resources', 'integration-snapshot', 'source-provenance.json'),
    JSON.stringify({
      schema: 'auto-mas.experimental-alpha.source-provenance/v2',
      git: {
        head_sha: 'c'.repeat(40),
        worktree_state: 'dirty-captured',
      },
      source_input_tree: {
        sha256: 'd'.repeat(64),
      },
      external_wheelhouse: wheelhouseProvenance.collectWheelhouseProvenance(
        path.join(directory, 'resources', 'integration-snapshot', 'plugins', 'wheels')
      ),
    })
  )
  fs.writeFileSync(
    path.join(directory, 'resources', 'integration-snapshot', 'evidence', 'CI_GATES.json'),
    JSON.stringify({ schema: 'auto-mas.experimental-alpha.ci-gates/v1' })
  )
}

afterEach(() => {
  while (temporaryDirectories.length > 0) {
    fs.rmSync(temporaryDirectories.pop(), { recursive: true, force: true })
  }
})

describe('experimental Alpha release identity', () => {
  it('has a dedicated app, installer and artifact identity', () => {
    expect(experimentalAlphaIdentity).toMatchObject({
      appId: 'top.auto-mas.experimental-alpha',
      executableName: 'AUTO-MAS-v6-Experimental-Alpha',
      releaseChannel: 'experimental-alpha',
      artifactStem: 'AUTO-MAS-v6-Experimental-Alpha',
    })
    expect(experimentalAlphaIdentity.innoAppId).not.toBe('D116A92A-E174-4699-B777-61C5FD837B19')
    expect(experimentalAlphaIdentity.executableName).not.toBe('AUTO-MAS')
    const builderSource = fs.readFileSync(
      path.join(frontendDirectory, 'electron-builder.integration.cjs'),
      'utf8'
    )
    expect(builderSource).toContain('experimental-alpha-release-identity.cjs')
    expect(builderSource).not.toContain("appId: 'top.auto-mas.experimental-alpha'")
    expect(builderSource).toContain('signAndEditExecutable: false')
  })

  it('prepares and finalizes exact Full-only artifacts', () => {
    const root = makeTemporaryDirectory()
    const stageDirectory = path.join(root, 'win-unpacked')
    const artifactDirectory = path.join(root, 'alpha-artifacts')
    fs.mkdirSync(stageDirectory)
    writeRequiredFullStage(stageDirectory)

    const prepared = prepareExperimentalAlphaInstaller({
      stageDirectory,
      artifactDirectory,
      version: 'v6.0.0-alpha.test.1',
      wheelhouseSha256: 'a'.repeat(64),
      environmentSha256: 'b'.repeat(64),
      gitSha: 'c'.repeat(40),
      protectedDirectories: [],
    })
    const stagedEvidence = verifyStageEvidenceIndex(stageDirectory)
    expect(stagedEvidence.document.files).toHaveLength(13)

    const installerText = fs.readFileSync(prepared.installerScriptPath, 'utf8')
    expect(installerText).toContain(`AppId={{${experimentalAlphaIdentity.innoAppId}}`)
    expect(installerText).toContain(
      `MyAppExeName "${experimentalAlphaIdentity.executableName}.exe"`
    )
    expect(installerText).toContain(
      `OutputBaseFilename=${path.basename(fullInstallerFilename('v6.0.0-alpha.test.1'), '.exe')}`
    )
    expect(installerText).toContain('CloseApplications=yes')
    expect(installerText).toContain('CloseApplicationsFilter={#MyAppExeName}')
    expect(installerText).not.toContain('*.dll')
    expect(installerText).not.toContain('AUTO-MAS-Lite')

    const installer = path.join(artifactDirectory, fullInstallerFilename('v6.0.0-alpha.test.1'))
    const archive = path.join(artifactDirectory, fullArchiveFilename('v6.0.0-alpha.test.1'))
    fs.writeFileSync(installer, 'installer')
    fs.writeFileSync(archive, 'archive')
    const finalized = finalizeExperimentalAlphaInstaller({
      preparedManifestPath: prepared.preparedManifestPath,
    })

    expect(finalized.manifest.status).toBe('packaged')
    expect(finalized.manifest.signing.status).toBe('not-requested')
    expect(finalized.manifest.source_state).toBe('dirty-captured')
    expect(finalized.manifest.source_input_tree_sha256).toBe('d'.repeat(64))
    expect(finalized.manifest.wheelhouse_tree_sha256).toMatch(/^[0-9a-f]{64}$/u)
    expect(finalized.manifest.stage_app_asar_sha256).toMatch(/^[0-9a-f]{64}$/u)
    expect(finalized.manifest.evidence).toMatchObject({
      artifact_index_path: 'evidence/EVIDENCE_INDEX.json',
      indexed_file_count: 13,
    })
    expect(fs.existsSync(prepared.evidenceIndexPath)).toBe(true)
    expect(
      JSON.parse(
        fs.readFileSync(
          path.join(
            stageDirectory,
            'resources',
            'integration-snapshot',
            'evidence',
            'EVIDENCE_INDEX.json'
          ),
          'utf8'
        )
      )
    ).toMatchObject({
      schema: 'auto-mas.experimental-alpha.evidence-index/v1',
      files: expect.arrayContaining([
        expect.objectContaining({ path: 'resources/app.asar' }),
        expect.objectContaining({ path: 'resources/integration-snapshot/evidence/CI_GATES.json' }),
      ]),
    })
    expect(path.basename(finalized.sumsPath)).toBe(sha256SumsFilename('v6.0.0-alpha.test.1'))
    const sums = fs.readFileSync(finalized.sumsPath, 'utf8')
    expect(sums).toContain(fullInstallerFilename('v6.0.0-alpha.test.1'))
    expect(sums).toContain('*alpha-release-manifest.json')
    expect(sums).toContain('*experimental-alpha-full.iss')
    expect(sums).toContain('*evidence/EVIDENCE_INDEX.json')
    const checksumEntries = Object.fromEntries(
      sums
        .trim()
        .split('\n')
        .map(line => {
          const match = line.match(/^([0-9a-f]{64}) \*(.+)$/u)
          expect(match).not.toBeNull()
          return [match[2], match[1]]
        })
    )
    const expectedChecksumFiles = [
      fullInstallerFilename('v6.0.0-alpha.test.1'),
      fullArchiveFilename('v6.0.0-alpha.test.1'),
      'alpha-release-manifest.json',
      'experimental-alpha-full.iss',
      'evidence/EVIDENCE_INDEX.json',
    ]
    expect(Object.keys(checksumEntries).sort()).toEqual(expectedChecksumFiles.sort())
    for (const filename of expectedChecksumFiles) {
      expect(sha256File(path.join(artifactDirectory, ...filename.split('/')))).toBe(
        checksumEntries[filename]
      )
    }
    expect(Object.keys(checksumEntries)).not.toContain(path.basename(finalized.sumsPath))
    expect(verifyArtifactEvidenceBundle(artifactDirectory).sha256).toBe(
      finalized.manifest.evidence.index_sha256
    )
  })

  it('prepares and finalizes a portable-only Full artifact without an installer', () => {
    const root = makeTemporaryDirectory()
    const stageDirectory = path.join(root, 'win-unpacked')
    const artifactDirectory = path.join(root, 'alpha-artifacts')
    fs.mkdirSync(stageDirectory)
    writeRequiredFullStage(stageDirectory)

    const prepared = prepareExperimentalAlphaPortable({
      stageDirectory,
      artifactDirectory,
      version: 'v6.0.0-alpha.test.2',
      wheelhouseSha256: 'a'.repeat(64),
      environmentSha256: 'b'.repeat(64),
      gitSha: 'c'.repeat(40),
      protectedDirectories: [],
    })

    expect(prepared.manifest.distribution_mode).toBe('portable-only')
    expect(prepared.manifest.release_tool_sha256).toMatch(/^[0-9a-f]{64}$/u)
    expect(prepared.manifest.expected_artifacts).not.toHaveProperty('installer')
    expect(prepared.installerScriptPath).toBeUndefined()
    expect(fs.existsSync(path.join(artifactDirectory, 'experimental-alpha-full.iss'))).toBe(false)

    const archive = path.join(artifactDirectory, fullArchiveFilename('v6.0.0-alpha.test.2'))
    fs.writeFileSync(archive, 'archive')
    const finalized = finalizeExperimentalAlphaInstaller({
      preparedManifestPath: prepared.preparedManifestPath,
    })

    expect(finalized.manifest.status).toBe('packaged')
    expect(finalized.manifest.distribution_mode).toBe('portable-only')
    expect(finalized.manifest.artifacts).toEqual([
      expect.objectContaining({
        filename: fullArchiveFilename('v6.0.0-alpha.test.2'),
      }),
    ])
    const sums = fs.readFileSync(finalized.sumsPath, 'utf8')
    expect(sums).toContain(fullArchiveFilename('v6.0.0-alpha.test.2'))
    expect(sums).not.toContain('Full-Setup')
    expect(sums).not.toContain('experimental-alpha-full.iss')
    expect(sums).toContain('*alpha-release-manifest.json')
    expect(sums).toContain('*evidence/EVIDENCE_INDEX.json')
  })

  it('rejects a staged wheelhouse changed after source provenance capture', () => {
    const root = makeTemporaryDirectory()
    const stageDirectory = path.join(root, 'win-unpacked')
    fs.mkdirSync(stageDirectory)
    writeRequiredFullStage(stageDirectory)
    fs.writeFileSync(
      path.join(
        stageDirectory,
        'resources',
        'integration-snapshot',
        'plugins',
        'wheels',
        'package-1.0-py3-none-any.whl'
      ),
      'tampered wheel'
    )

    expect(() =>
      prepareExperimentalAlphaInstaller({
        stageDirectory,
        artifactDirectory: path.join(root, 'alpha-artifacts'),
        version: 'v6.0.0-alpha.test.1',
        wheelhouseSha256: 'a'.repeat(64),
        environmentSha256: 'b'.repeat(64),
        gitSha: 'c'.repeat(40),
        protectedDirectories: [],
      })
    ).toThrow('do not match captured provenance')
  })

  it('fails closed when staged or copied evidence changes after preparation', () => {
    const root = makeTemporaryDirectory()
    const stageDirectory = path.join(root, 'win-unpacked')
    const artifactDirectory = path.join(root, 'alpha-artifacts')
    fs.mkdirSync(stageDirectory)
    writeRequiredFullStage(stageDirectory)
    const prepared = prepareExperimentalAlphaInstaller({
      stageDirectory,
      artifactDirectory,
      version: 'v6.0.0-alpha.test.1',
      wheelhouseSha256: 'a'.repeat(64),
      environmentSha256: 'b'.repeat(64),
      gitSha: 'c'.repeat(40),
      protectedDirectories: [],
    })
    const stagedDocument = path.join(
      stageDirectory,
      'resources',
      'integration-snapshot',
      'evidence',
      'KNOWN_GAPS.md'
    )
    fs.writeFileSync(stagedDocument, 'tampered stage evidence')
    expect(() => verifyStageEvidenceIndex(stageDirectory)).toThrow('does not match index')
    fs.writeFileSync(stagedDocument, 'resources/integration-snapshot/evidence/KNOWN_GAPS.md')
    expect(verifyStageEvidenceIndex(stageDirectory).document.files).toHaveLength(13)

    fs.writeFileSync(
      path.join(artifactDirectory, fullInstallerFilename('v6.0.0-alpha.test.1')),
      'installer'
    )
    fs.writeFileSync(
      path.join(artifactDirectory, fullArchiveFilename('v6.0.0-alpha.test.1')),
      'archive'
    )
    fs.writeFileSync(
      path.join(artifactDirectory, 'evidence', 'KNOWN_GAPS.md'),
      'tampered copied evidence'
    )
    expect(() => verifyArtifactEvidenceBundle(artifactDirectory)).toThrow('does not match index')
    expect(() =>
      finalizeExperimentalAlphaInstaller({ preparedManifestPath: prepared.preparedManifestPath })
    ).toThrow('does not match index')
  })

  it('refuses incomplete Full stages and output overlapping win-unpacked', () => {
    const root = makeTemporaryDirectory()
    const stageDirectory = path.join(root, 'win-unpacked')
    fs.mkdirSync(stageDirectory)
    expect(() =>
      prepareExperimentalAlphaInstaller({
        stageDirectory,
        artifactDirectory: path.join(root, 'alpha-artifacts'),
        version: 'v6.0.0-alpha.test.1',
        wheelhouseSha256: 'a'.repeat(64),
        environmentSha256: 'b'.repeat(64),
        gitSha: 'c'.repeat(40),
        protectedDirectories: [],
      })
    ).toThrow('missing required file')

    writeRequiredFullStage(stageDirectory)
    expect(() =>
      prepareExperimentalAlphaInstaller({
        stageDirectory,
        artifactDirectory: path.join(stageDirectory, 'alpha-artifacts'),
        version: 'v6.0.0-alpha.test.1',
        wheelhouseSha256: 'a'.repeat(64),
        environmentSha256: 'b'.repeat(64),
        gitSha: 'c'.repeat(40),
        protectedDirectories: [],
      })
    ).toThrow('must not overlap win-unpacked')
  })

  it('rejects unsafe Inno values and version components', () => {
    expect(() => fullInstallerFilename('../escape')).toThrow('safe release filename')
    expect(() =>
      createInstallerScript({
        stageDirectory: 'C:\\unsafe"stage',
        artifactDirectory: 'C:\\out',
        version: 'v6.0.0-alpha.test.1',
      })
    ).toThrow('unsafe quote')
  })
})

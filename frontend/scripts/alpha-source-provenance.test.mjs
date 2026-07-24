import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import {
  ALPHA_SOURCE_INPUTS,
  ALPHA_SOURCE_PROVENANCE_SCHEMA,
  assertSameAlphaPackagingInputs,
  assertSameAlphaSourceInputTree,
  collectAlphaSourceInputManifest,
  createAlphaSourceProvenanceDocument,
} from './capture-alpha-source-provenance.mjs'

const temporaryDirectories = []

const makeTemporaryDirectory = () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-alpha-provenance-'))
  temporaryDirectories.push(directory)
  return directory
}

const writeFile = (root, relativePath, content) => {
  const target = path.join(root, ...relativePath.split('/'))
  fs.mkdirSync(path.dirname(target), { recursive: true })
  fs.writeFileSync(target, content)
}

const createWheelhouse = root => {
  const wheelhouse = path.join(root, 'wheelhouse')
  writeFile(wheelhouse, 'package-1.0-py3-none-any.whl', 'wheel')
  writeFile(wheelhouse, 'manifest.json', '{"schema_version":3}')
  writeFile(wheelhouse, 'runtime-lock.json', '{"schema_version":1}')
  return wheelhouse
}

const sourceInputs = [
  {
    source: 'app',
    exclude: relativePath =>
      relativePath.split('/').includes('__pycache__') || /\.py[oc]$/iu.test(relativePath),
  },
  { source: 'frontend/package.json' },
]

const gitState = {
  head_sha: 'a'.repeat(40),
  worktree_state: 'dirty-captured',
  status_sha256: 'b'.repeat(64),
  tracked_diff_sha256: 'c'.repeat(64),
  status_entry_count: 2,
}

afterEach(() => {
  while (temporaryDirectories.length > 0) {
    fs.rmSync(temporaryDirectories.pop(), { recursive: true, force: true })
  }
})

describe('Alpha source provenance', () => {
  it('hashes only the filtered packaged inputs in stable path order', () => {
    const root = makeTemporaryDirectory()
    writeFile(root, 'app/runtime.py', 'ready')
    writeFile(root, 'app/__pycache__/runtime.pyc', 'ignored')
    writeFile(root, 'frontend/package.json', '{"name":"alpha"}')

    const first = collectAlphaSourceInputManifest(root, sourceInputs)
    const second = collectAlphaSourceInputManifest(root, sourceInputs)

    expect(first).toEqual(second)
    expect(first.files.map(entry => entry.path)).toEqual([
      'app/runtime.py',
      'frontend/package.json',
    ])

    writeFile(root, 'app/runtime.py', 'changed')
    expect(collectAlphaSourceInputManifest(root, sourceInputs).sha256).not.toBe(first.sha256)
  })

  it('records dirty state explicitly and rejects a mismatched expected head', () => {
    const root = makeTemporaryDirectory()
    writeFile(root, 'app/runtime.py', 'ready')
    writeFile(root, 'frontend/package.json', '{}')
    const wheelhouseDirectory = createWheelhouse(root)

    const document = createAlphaSourceProvenanceDocument({
      repositoryRoot: root,
      gitState,
      sourceInputs,
      expectedGitSha: 'a'.repeat(40),
      wheelhouseDirectory,
    })

    expect(document.schema).toBe(ALPHA_SOURCE_PROVENANCE_SCHEMA)
    expect(document.git.worktree_state).toBe('dirty-captured')
    expect(document.source_input_tree.file_count).toBe(2)
    expect(document.source_input_tree.sha256).toMatch(/^[0-9a-f]{64}$/u)
    expect(document.external_wheelhouse.files).toHaveLength(3)
    expect(document.external_wheelhouse.tree_sha256).toMatch(/^[0-9a-f]{64}$/u)
    expect(() =>
      createAlphaSourceProvenanceDocument({
        repositoryRoot: root,
        gitState,
        sourceInputs,
        expectedGitSha: 'd'.repeat(40),
        wheelhouseDirectory,
      })
    ).toThrow('does not match actual HEAD')
  })

  it('fails closed when the captured input tree changes during packaging', () => {
    const before = { source_input_tree: { sha256: 'a'.repeat(64) } }
    const after = { source_input_tree: { sha256: 'b'.repeat(64) } }

    expect(() => assertSameAlphaSourceInputTree(before, after)).toThrow('changed during packaging')
    expect(assertSameAlphaSourceInputTree(before, before)).toBe('a'.repeat(64))
  })

  it('fails closed when the selected wheelhouse changes during packaging', () => {
    const root = makeTemporaryDirectory()
    const wheelhouseDirectory = createWheelhouse(root)
    const before = {
      source_input_tree: { sha256: 'a'.repeat(64) },
      external_wheelhouse: {
        tree_sha256: 'b'.repeat(64),
      },
    }
    const after = structuredClone(before)
    after.external_wheelhouse.tree_sha256 = 'c'.repeat(64)

    expect(() => assertSameAlphaPackagingInputs(before, after)).toThrow(
      'wheelhouse changed during packaging'
    )
    expect(assertSameAlphaPackagingInputs(before, before)).toEqual({
      source_input_tree_sha256: 'a'.repeat(64),
      wheelhouse_tree_sha256: 'b'.repeat(64),
    })

    writeFile(wheelhouseDirectory, 'package-1.0-py3-none-any.whl', 'changed wheel')
    const document = createAlphaSourceProvenanceDocument({
      repositoryRoot: root,
      gitState,
      sourceInputs: [],
      wheelhouseDirectory,
    })
    expect(document.external_wheelhouse.tree_sha256).not.toBe('b'.repeat(64))
  })

  it('tracks the actual Alpha image and safe script payload inputs', () => {
    const sources = ALPHA_SOURCE_INPUTS.map(input => input.source)

    expect(sources).toContain('frontend/public')
    expect(sources).not.toContain('frontend/dict')
    expect(sources).toContain('frontend/src/assets')
    expect(sources).toContain('docs/experimental-alpha')
    expect(sources).toContain('scripts/verify_offline_first_start.ps1')
    expect(sources).toContain('scripts/verify_wheelhouse_snapshot.py')
    expect(sources).toContain('frontend/scripts/build-integration-release.mjs')
    expect(sources).toContain('frontend/scripts/alpha-wheelhouse-provenance.cjs')
    expect(sources).toContain('frontend/scripts/generate-experimental-alpha-installer.mjs')
    expect(sources).toContain('frontend/scripts/experimental-alpha-release-identity.cjs')
    expect(sources).toContain('frontend/scripts/validate-wheelhouse.mjs')
    expect(sources).not.toContain('frontend/scripts')
    expect(sources).not.toContain('plugins/wheels')
  })

  it('changes the payload source tree hash when a bundled Alpha image changes', () => {
    const root = makeTemporaryDirectory()
    const payloadInputs = [{ source: 'frontend/public' }]
    writeFile(root, 'frontend/public/AUTO-MAS.ico', 'first-icon')

    const first = collectAlphaSourceInputManifest(root, payloadInputs)
    writeFile(root, 'frontend/public/AUTO-MAS.ico', 'second-icon')

    expect(collectAlphaSourceInputManifest(root, payloadInputs).sha256).not.toBe(first.sha256)
  })

  it('changes the source tree hash when a tracked packaging script changes', () => {
    const root = makeTemporaryDirectory()
    const packagingInputs = [{ source: 'frontend/scripts/build-integration-release.mjs' }]
    writeFile(root, 'frontend/scripts/build-integration-release.mjs', 'first-plan')

    const first = collectAlphaSourceInputManifest(root, packagingInputs)
    writeFile(root, 'frontend/scripts/build-integration-release.mjs', 'second-plan')

    expect(collectAlphaSourceInputManifest(root, packagingInputs).sha256).not.toBe(first.sha256)
  })
})

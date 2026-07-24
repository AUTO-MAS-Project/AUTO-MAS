import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import {
  assertPinnedPluginBootstrapMatchesRuntimeLock,
  readPinnedPluginBootstrapRequirements,
} from './validate-wheelhouse.mjs'

const temporaryDirectories = []

const writePyproject = maaEndVersion => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-wheelhouse-contract-'))
  temporaryDirectories.push(directory)
  const filePath = path.join(directory, 'pyproject.toml')
  fs.writeFileSync(
    filePath,
    `[tool.auto-mas.plugin-bootstrap]
packages = [
  "automas_plugin_ok_script_adapter",
  { name = "automas_plugin_maaend_adapter", version = "${maaEndVersion}" },
]
`
  )
  return filePath
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    fs.rmSync(directory, { recursive: true, force: true })
  }
})

describe('wheelhouse plugin-bootstrap contract', () => {
  it('accepts a pinned plugin version that matches the runtime lock', () => {
    const pinned = readPinnedPluginBootstrapRequirements(writePyproject('0.0.4'))

    expect(() =>
      assertPinnedPluginBootstrapMatchesRuntimeLock(pinned, [
        { distribution: 'automas-plugin-maaend-adapter', version: '0.0.4' },
      ])
    ).not.toThrow()
  })

  it('rejects the stale host pin that broke Alpha .4 startup', () => {
    const pinned = readPinnedPluginBootstrapRequirements(writePyproject('0.0.3'))

    expect(() =>
      assertPinnedPluginBootstrapMatchesRuntimeLock(pinned, [
        { distribution: 'automas_plugin_maaend_adapter', version: '0.0.4' },
      ])
    ).toThrow('expected 0.0.3, got 0.0.4')
  })
})

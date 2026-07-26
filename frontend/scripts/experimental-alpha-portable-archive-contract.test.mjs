import { createRequire } from 'node:module'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { afterEach, describe, expect, it } from 'vitest'

import { verifyPortableArchiveLayout } from './generate-experimental-alpha-installer.mjs'

const require = createRequire(import.meta.url)
const { experimentalAlphaIdentity } = require('./experimental-alpha-release-identity.cjs')
const AdmZip = require('adm-zip')

const temporaryFiles = []
const executableName = `${experimentalAlphaIdentity.executableName}.exe`

const makeTemporaryArchive = entries => {
  const archivePath = path.join(
    fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-alpha-zip-contract-')),
    'archive.zip'
  )
  temporaryFiles.push(archivePath)
  const archive = new AdmZip()
  // AdmZip.addFile normalizes entry names (strips ./, collapses //, etc.).
  // To inject the exact forbidden shapes the contract must reject, add each
  // entry with a placeholder name and then override entryName directly, the
  // same technique the existing release test uses for its ./ prefix case.
  for (const [index, entry] of entries.entries()) {
    const content = typeof entry === 'string' ? Buffer.from(entry) : entry.content
    archive.addFile(`__placeholder_${index}`, content)
  }
  const added = archive.getEntries()
  for (let i = 0; i < entries.length; i += 1) {
    const entry = entries[i]
    added[i].entryName = typeof entry === 'string' ? entry : entry.name
  }
  archive.writeZip(archivePath)
  return archivePath
}

const validEntries = () => [
  { name: executableName, content: Buffer.from('executable') },
  { name: 'environment/python/python.exe', content: Buffer.from('python') },
  { name: 'environment/git/bin/git.exe', content: Buffer.from('git') },
  { name: 'resources/app.asar', content: Buffer.from('asar') },
  { name: 'resources/integration-snapshot/manifest.json', content: Buffer.from('{}') },
]

afterEach(() => {
  while (temporaryFiles.length > 0) {
    const target = temporaryFiles.pop()
    fs.rmSync(path.dirname(target), { recursive: true, force: true })
  }
})

describe('experimental Alpha portable ZIP central directory contract', () => {
  describe('rejects every forbidden entry shape required by AGENTS.md', () => {
    const forbiddenCases = [
      { label: './ prefix', name: `./${executableName}` },
      { label: '.\\ prefix', name: `.\\${executableName}` },
      { label: 'leading / absolute path', name: `/etc/passwd` },
      { label: 'leading \\ absolute path', name: `\\windows\\system32\\evil.dll` },
      { label: 'C: drive letter prefix', name: `C:\\Users\\evil\\${executableName}` },
      { label: 'backslash anywhere', name: `environment\\python\\python.exe` },
      { label: '.. leading parent segment', name: `../escape.exe` },
      { label: '.. mid path traversal', name: `environment/python/../../escape.exe` },
      { label: '. mid self segment', name: `resources/./app.asar` },
      { label: 'empty segment //', name: `environment//python.exe` },
    ]

    for (const { label, name } of forbiddenCases) {
      it(`rejects ${label}`, () => {
        const archive = makeTemporaryArchive([
          { name, content: Buffer.from('bad') },
          ...validEntries(),
        ])
        expect(() => verifyPortableArchiveLayout(archive)).toThrow()
      })
    }

    it('rejects a wrapper directory prefix (AUTO-MAS/)', () => {
      const archive = makeTemporaryArchive([
        { name: `AUTO-MAS/${executableName}`, content: Buffer.from('wrapped') },
        { name: 'AUTO-MAS/environment/python/python.exe', content: Buffer.from('python') },
        { name: 'AUTO-MAS/resources/app.asar', content: Buffer.from('asar') },
      ])
      expect(() => verifyPortableArchiveLayout(archive)).toThrow('directly at the ZIP root')
    })
  })

  describe('rejects archives missing a required root entry', () => {
    it('rejects an archive without the EXE at the ZIP root', () => {
      const archive = makeTemporaryArchive([
        { name: 'environment/python/python.exe', content: Buffer.from('python') },
        { name: 'resources/app.asar', content: Buffer.from('asar') },
      ])
      expect(() => verifyPortableArchiveLayout(archive)).toThrow(
        `${executableName} directly at the ZIP root`
      )
    })

    it('rejects an archive without environment/ at the ZIP root', () => {
      const archive = makeTemporaryArchive([
        { name: executableName, content: Buffer.from('executable') },
        { name: 'resources/app.asar', content: Buffer.from('asar') },
      ])
      expect(() => verifyPortableArchiveLayout(archive)).toThrow(
        'environment/ directly at the ZIP root'
      )
    })

    it('rejects an archive without resources/ at the ZIP root', () => {
      const archive = makeTemporaryArchive([
        { name: executableName, content: Buffer.from('executable') },
        { name: 'environment/python/python.exe', content: Buffer.from('python') },
      ])
      expect(() => verifyPortableArchiveLayout(archive)).toThrow(
        'resources/ directly at the ZIP root'
      )
    })

    it('rejects an empty archive', () => {
      const archive = makeTemporaryArchive([])
      expect(() => verifyPortableArchiveLayout(archive)).toThrow('must not be empty')
    })
  })

  describe('accepts a compliant flat layout', () => {
    it('returns entry count and sorted top-level names for a valid archive', () => {
      const entries = validEntries()
      const archive = makeTemporaryArchive(entries)
      const result = verifyPortableArchiveLayout(archive)
      expect(result.entryCount).toBe(entries.length)
      expect(result.topLevelNames).toEqual([executableName, 'environment', 'resources'])
    })

    it('accepts directory entries that end with a trailing slash', () => {
      const archive = makeTemporaryArchive([
        { name: executableName, content: Buffer.from('executable') },
        { name: 'environment/', content: Buffer.from('') },
        { name: 'environment/python/python.exe', content: Buffer.from('python') },
        { name: 'resources/', content: Buffer.from('') },
        { name: 'resources/app.asar', content: Buffer.from('asar') },
      ])
      const result = verifyPortableArchiveLayout(archive)
      expect(result.topLevelNames).toContain(executableName)
      expect(result.topLevelNames).toContain('environment')
      expect(result.topLevelNames).toContain('resources')
    })
  })
})

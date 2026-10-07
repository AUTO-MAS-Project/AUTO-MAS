import * as fs from 'fs'
import * as os from 'os'
import * as path from 'path'
import AdmZip = require('adm-zip')
import { afterEach, describe, expect, it } from 'vitest'
import {
  importAppearancePackage,
  isAppearanceGone,
  listAppearances,
  removeAppearance,
  validateAppearanceManifest,
} from './appearanceService'

const PNG_1X1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64'
)
const tempRoots: string[] = []

function pngWithDimensions(width: number, height: number): Buffer {
  const png = Buffer.from(PNG_1X1)
  png.writeUInt32BE(width, 16)
  png.writeUInt32BE(height, 20)
  return png
}

function makeRoot(): string {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-appearance-test-'))
  tempRoots.push(root)
  return root
}

function makeZip(
  root: string,
  id: string,
  name = '示例外观',
  menuIcons: Record<string, string> = {},
  cursors: unknown = {},
  cursorData: Record<string, Buffer> = {}
): string {
  const zip = new AdmZip()
  zip.addFile('assets/', Buffer.alloc(0))
  const cursorEntries =
    cursors !== null && typeof cursors === 'object' && !Array.isArray(cursors)
      ? Object.values(cursors as Record<string, { path?: unknown }>)
      : []
  const cursorPaths = cursorEntries.flatMap(cursor =>
    typeof cursor?.path === 'string' ? [cursor.path] : []
  )
  const manifest = {
    formatVersion: 1,
    id,
    name,
    mode: 'light',
    tokens: { colorPrimary: '#1677ff' },
    background: { path: 'assets/background.png', opacity: 0.2 },
    ...(Object.keys(menuIcons).length > 0 ? { menuIcons } : {}),
    ...(cursors === null ||
    typeof cursors !== 'object' ||
    Array.isArray(cursors) ||
    Object.keys(cursors).length > 0
      ? { cursors }
      : {}),
  }
  zip.addFile('theme.json', Buffer.from(JSON.stringify(manifest)))
  zip.addFile('assets/background.png', PNG_1X1)
  for (const assetPath of new Set([...Object.values(menuIcons), ...cursorPaths])) {
    if (assetPath !== 'assets/background.png') {
      zip.addFile(assetPath, cursorData[assetPath] ?? PNG_1X1)
    }
  }
  const zipPath = path.join(root, `${id}.zip`)
  zip.writeZip(zipPath)
  return zipPath
}

afterEach(() => {
  for (const root of tempRoots.splice(0)) fs.rmSync(root, { recursive: true, force: true })
})

describe('appearanceService', () => {
  it('persists surface opacity through import and installed cache reload', () => {
    const root = makeRoot()
    const zipPath = makeZip(root, 'surfaces')
    const zip = new AdmZip(zipPath)
    const manifest = JSON.parse(zip.readAsText('theme.json'))
    manifest.background.surfaceOpacity = 0.35
    zip.updateFile('theme.json', Buffer.from(JSON.stringify(manifest)))
    zip.writeZip(zipPath)

    const result = importAppearancePackage(root, zipPath)
    expect(result.success).toBe(true)
    expect(result.appearance?.background).toEqual({
      path: 'assets/background.png',
      opacity: 0.2,
      surfaceOpacity: 0.35,
    })
    expect(listAppearances(root)[0].background).toEqual(result.appearance?.background)
  })

  it.each([-0.01, 1.01, NaN, Infinity, '0.5', null])(
    'rejects invalid surface opacity %s',
    surfaceOpacity => {
      expect(() =>
        validateAppearanceManifest({
          formatVersion: 1,
          id: 'surfaces',
          name: 'Surface',
          mode: 'light',
          tokens: { colorPrimary: '#1677ff' },
          background: { path: 'assets/background.png', surfaceOpacity },
        })
      ).toThrow('background.surfaceOpacity')
    }
  )

  it('imports a package with an explicit assets directory and persists safe data', () => {
    const root = makeRoot()
    const zipPath = makeZip(root, 'sunny')

    const result = importAppearancePackage(root, zipPath)
    expect(result.success).toBe(true)
    expect(result.appearance?.id).toBe('sunny')
    expect(result.appearance?.backgroundUrl).toMatch(/^data:image\/png;base64,/)
    expect(listAppearances(root).map(item => item.id)).toEqual(['sunny'])

    expect(removeAppearance(root, 'sunny')).toEqual({ success: true })
    expect(listAppearances(root)).toEqual([])
  })

  it('imports menu icon overrides and reuses one image path for multiple keys', () => {
    const root = makeRoot()
    const zipPath = makeZip(root, 'icons', '图标外观', {
      home: 'assets/background.png',
      settings: 'assets/menu-settings.png',
    })

    const result = importAppearancePackage(root, zipPath)
    expect(result.success).toBe(true)
    expect(result.appearance?.menuIconUrls?.home).toBe(result.appearance?.backgroundUrl)
    expect(result.appearance?.menuIconUrls?.settings).toMatch(/^data:image\/png;base64,/)
    expect(listAppearances(root)[0].menuIconUrls).toEqual(result.appearance?.menuIconUrls)
  })

  it('imports bounded PNG cursors, preserves hotspots, and keeps old packages compatible', () => {
    const root = makeRoot()
    const zipPath = makeZip(
      root,
      'cursor',
      '光标外观',
      {},
      { pointer: { path: 'assets/pointer.png', hotspotX: 2, hotspotY: 3 } },
      { 'assets/pointer.png': pngWithDimensions(64, 64) }
    )

    const result = importAppearancePackage(root, zipPath)
    expect(result.success).toBe(true)
    expect(result.appearance?.cursors?.pointer).toMatchObject({
      path: 'assets/pointer.png',
      hotspotX: 2,
      hotspotY: 3,
    })
    expect(result.appearance?.cursorUrls?.pointer).toMatch(/^data:image\/png;base64,/)

    const oldPackage = importAppearancePackage(root, makeZip(root, 'old-package'))
    expect(oldPackage.success).toBe(true)
    expect(oldPackage.appearance?.cursors).toBeUndefined()
    expect(oldPackage.appearance?.cursorUrls).toBeUndefined()
  })

  it('rejects invalid cursor keys, paths, hotspots, and dimensions', () => {
    const root = makeRoot()
    const unknownKey = makeZip(
      root,
      'cursor-unknown',
      '未知键',
      {},
      {
        busy: { path: 'assets/pointer.png' },
      }
    )
    expect(importAppearancePackage(root, unknownKey)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const nonObject = makeZip(root, 'cursor-nonobject', '非对象', {}, null)
    expect(importAppearancePackage(root, nonObject)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const jpeg = makeZip(
      root,
      'cursor-jpeg',
      'JPEG',
      {},
      {
        pointer: { path: 'assets/pointer.jpg' },
      }
    )
    expect(importAppearancePackage(root, jpeg)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const hotspot = makeZip(
      root,
      'cursor-hotspot',
      '热点越界',
      {},
      {
        pointer: { path: 'assets/pointer.png', hotspotX: 1 },
      }
    )
    expect(importAppearancePackage(root, hotspot)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const oversized = makeZip(
      root,
      'cursor-oversized',
      '尺寸过大',
      {},
      { pointer: { path: 'assets/pointer.png' } },
      { 'assets/pointer.png': pngWithDimensions(65, 64) }
    )
    expect(importAppearancePackage(root, oversized)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const truncated = makeZip(
      root,
      'cursor-truncated',
      '截断 PNG',
      {},
      { pointer: { path: 'assets/pointer.png' } },
      { 'assets/pointer.png': pngWithDimensions(1, 1).subarray(0, 32) }
    )
    expect(importAppearancePackage(root, truncated)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })
  })

  it('rejects unknown menu icon keys and paths outside assets', () => {
    const root = makeRoot()
    const unknownKeyPath = makeZip(root, 'unknown-key', '未知键', {
      unknown: 'assets/background.png',
    })
    expect(importAppearancePackage(root, unknownKeyPath)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })

    const outsidePath = makeZip(root, 'outside-path', '目录外路径', {
      home: 'icons/home.png',
    })
    expect(importAppearancePackage(root, outsidePath)).toMatchObject({
      success: false,
      code: 'INVALID_PACKAGE',
    })
  })

  it('rejects traversal and undeclared executable content before writing', () => {
    const root = makeRoot()
    const traversalZip = new AdmZip()
    traversalZip.addFile('../theme.json', Buffer.from('{}'))
    const traversalPath = path.join(root, 'traversal.zip')
    traversalZip.writeZip(traversalPath)
    expect(importAppearancePackage(root, traversalPath).success).toBe(false)

    const executableZip = new AdmZip()
    executableZip.addFile(
      'theme.json',
      Buffer.from(
        JSON.stringify({
          formatVersion: 1,
          id: 'unsafe',
          name: 'unsafe',
          mode: 'light',
          tokens: { colorPrimary: '#1677ff' },
        })
      )
    )
    executableZip.addFile('run.js', Buffer.from('alert(1)'))
    const executablePath = path.join(root, 'executable.zip')
    executableZip.writeZip(executablePath)
    expect(importAppearancePackage(root, executablePath).success).toBe(false)
    expect(fs.existsSync(path.join(root, 'appearances'))).toBe(false)
  })

  it('requires explicit replacement for duplicate and repairs a damaged old package', () => {
    const root = makeRoot()
    const first = makeZip(root, 'same', 'first')
    const second = makeZip(root, 'same', 'second')
    expect(importAppearancePackage(root, first).success).toBe(true)
    expect(importAppearancePackage(root, second)).toMatchObject({
      success: false,
      code: 'DUPLICATE_ID',
    })
    expect(importAppearancePackage(root, second, true).appearance?.name).toBe('second')

    const brokenDirectory = path.join(root, 'appearances', 'broken')
    fs.mkdirSync(brokenDirectory, { recursive: true })
    fs.writeFileSync(path.join(brokenDirectory, 'theme.json'), '{broken', 'utf8')
    const repair = makeZip(root, 'broken', 'repaired')
    expect(importAppearancePackage(root, repair)).toMatchObject({
      success: false,
      code: 'DUPLICATE_ID',
    })
    expect(importAppearancePackage(root, repair, true).appearance?.name).toBe('repaired')
  })

  it('does not follow a symlinked appearance directory', () => {
    const root = makeRoot()
    const zipPath = makeZip(root, 'linked')
    const outside = path.join(root, 'outside')
    fs.mkdirSync(outside, { recursive: true })
    fs.mkdirSync(path.join(root, 'appearances'), { recursive: true })
    try {
      fs.symlinkSync(outside, path.join(root, 'appearances', 'linked'), 'junction')
    } catch {
      return
    }
    const result = importAppearancePackage(root, zipPath)
    expect(result.success).toBe(false)
    expect(fs.existsSync(path.join(outside, 'theme.json'))).toBe(false)
  })

  it('works when an ancestor of userData is a junction', () => {
    const root = makeRoot()
    const real = path.join(root, 'real')
    fs.mkdirSync(real)
    const linked = path.join(root, 'linked')
    try {
      fs.symlinkSync(real, linked, 'junction')
    } catch {
      return
    }
    const userData = path.join(linked, 'userData')
    fs.mkdirSync(userData)
    const result = importAppearancePackage(userData, makeZip(root, 'via-junction'))
    expect(result.success).toBe(true)
    expect(listAppearances(userData).map(item => item.id)).toEqual(['via-junction'])
    expect(isAppearanceGone(userData, 'via-junction')).toBe(false)
  })

  it('rejects Windows reserved names as id', () => {
    const root = makeRoot()
    const result = importAppearancePackage(root, makeZip(root, 'nul'))
    expect(result).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })
  })

  it('reports corrupt entries as invalid packages', () => {
    const root = makeRoot()
    const zipPath = makeZip(root, 'corrupt')
    const zip = new AdmZip(zipPath)
    const entry = zip.getEntry('assets/background.png')!
    entry.header.crc = (entry.header.crc + 1) >>> 0
    zip.writeZip(zipPath)
    const result = importAppearancePackage(root, zipPath)
    expect(result).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })
  })

  it('explains a package zipped with its outer folder', () => {
    const root = makeRoot()
    const source = new AdmZip(makeZip(root, 'nested'))
    const zip = new AdmZip()
    for (const entry of source.getEntries()) {
      zip.addFile(
        `nested/${entry.entryName}`,
        entry.isDirectory ? Buffer.alloc(0) : entry.getData()
      )
    }
    const zipPath = path.join(root, 'nested-folder.zip')
    zip.writeZip(zipPath)
    const result = importAppearancePackage(root, zipPath)
    expect(result).toMatchObject({ success: false, code: 'INVALID_PACKAGE' })
    expect(result.error).toContain('根目录')
  })

  it('treats missing or invalid packages as gone', () => {
    const root = makeRoot()
    expect(isAppearanceGone(root, 'missing')).toBe(true)
    expect(importAppearancePackage(root, makeZip(root, 'broken')).success).toBe(true)
    fs.rmSync(path.join(root, 'appearances', 'broken', 'assets', 'background.png'))
    expect(isAppearanceGone(root, 'broken')).toBe(true)
  })
})

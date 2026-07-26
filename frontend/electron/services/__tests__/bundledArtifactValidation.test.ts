import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as fs from 'fs'
import * as path from 'path'
import * as os from 'os'

import {
  parseWheelFilenameParts,
  readAndVerifyBundledRuntimeLock,
  readBundledRuntimeLockMetadata,
  verifyBundledWheelDigestsAsync,
  verifyBundledWheelDirectory,
  verifyBundledWheelDirectoryMetadata,
} from '../bundledArtifactValidation'
import { writeCompleteWheelhouse } from './wheelhouseFixture'

interface TempWorkspace {
  wheelsDir: string
  tmpDir: string
}

function createTempWheelsDir(): TempWorkspace {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'mas-bundled-artifact-'))
  const wheelsDir = path.join(tmpDir, 'plugins', 'wheels')
  fs.mkdirSync(wheelsDir, { recursive: true })
  return { wheelsDir, tmpDir }
}

describe('parseWheelFilenameParts', () => {
  it('parses a standard wheel filename', () => {
    const result = parseWheelFilenameParts('automas_script_hsr-0.1.5-py3-none-any.whl')
    expect(result).toEqual({ distribution: 'automas_script_hsr', version: '0.1.5' })
  })

  it('returns null for non-whl files', () => {
    expect(parseWheelFilenameParts('manifest.json')).toBeNull()
    expect(parseWheelFilenameParts('readme.txt')).toBeNull()
  })

  it('returns null when there are not enough dash segments', () => {
    expect(parseWheelFilenameParts('foo-1.0.0.whl')).toBeNull()
    expect(parseWheelFilenameParts('foo-1.0.0-py3.whl')).toBeNull()
  })

  it('returns null for empty input', () => {
    expect(parseWheelFilenameParts('')).toBeNull()
  })

  it('handles uppercase .WHL extension', () => {
    const result = parseWheelFilenameParts('foo-2.0.0-py3-none-any.WHL')
    expect(result).toEqual({ distribution: 'foo', version: '2.0.0' })
  })
})

describe('verifyBundledWheelDirectory — Lane 13: same-distribution multi-version detection', () => {
  let workspace: TempWorkspace

  beforeEach(() => {
    workspace = createTempWheelsDir()
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('passes when wheelhouse contains a single version per distribution', () => {
    writeCompleteWheelhouse(workspace.wheelsDir)
    expect(() => verifyBundledWheelDirectory(workspace.wheelsDir)).not.toThrow()
  })

  it('rejects manifest entries with same distribution but different versions', () => {
    writeCompleteWheelhouse(workspace.wheelsDir)

    // 在 manifest 中追加一条同分发不同版本的 wheel 条目，并写入对应 wheel 文件，
    // 模拟 Alpha.4 中 MaaEnd 0.0.4 与 0.0.5 共存的回归场景。
    const manifestPath = path.join(workspace.wheelsDir, 'manifest.json')
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'))
    const duplicateDistribution = 'automas_script_maa'
    const duplicateVersion = '99.9.9'
    const duplicateFilename = `${duplicateDistribution}-${duplicateVersion}-py3-none-any.whl`
    const duplicateContent = Buffer.from('duplicate-content')
    fs.writeFileSync(path.join(workspace.wheelsDir, duplicateFilename), duplicateContent)
    manifest.wheels.push({
      kind: 'plugin',
      scopes: ['plugin'],
      distribution: duplicateDistribution,
      version: duplicateVersion,
      entry_points: [],
      filename: duplicateFilename,
      size_bytes: duplicateContent.length,
      sha256: require('crypto').createHash('sha256').update(duplicateContent).digest('hex'),
    })
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2))

    let caughtError: Error | null = null
    try {
      verifyBundledWheelDirectory(workspace.wheelsDir)
    } catch (error) {
      caughtError = error as Error
    }
    expect(caughtError).not.toBeNull()
    expect(caughtError!.message).toContain('multiple versions for distribution')
    expect(caughtError!.message).toContain(duplicateDistribution)
    expect(caughtError!.message).toContain(duplicateVersion)
  })

  it('detects same-distribution multi-version via filename parsing when manifest lacks explicit distribution', () => {
    // 构造一个最小 wheelhouse：两个 wheel 文件名同分发不同版本，但 manifest 条目
    // 不显式声明 distribution/version，强制走文件名解析回退路径。
    const wheelsDir = workspace.wheelsDir
    const content1 = Buffer.from('content-1')
    const content2 = Buffer.from('content-2')
    const filename1 = 'shared_pkg-1.0.0-py3-none-any.whl'
    const filename2 = 'shared_pkg-2.0.0-py3-none-any.whl'
    fs.writeFileSync(path.join(wheelsDir, filename1), content1)
    fs.writeFileSync(path.join(wheelsDir, filename2), content2)

    const crypto = require('crypto')
    const manifest = {
      schema_version: 3,
      artifact_scope: 'complete-windows-x64-runtime-wheelhouse',
      expected_plugin_distribution_count: 23,
      expected_plugin_entry_point_count: 21,
      runtime_lock: {
        filename: 'runtime-lock.json',
        size_bytes: 0,
        sha256: '0'.repeat(64),
      },
      wheels: [
        {
          filename: filename1,
          size_bytes: content1.length,
          sha256: crypto.createHash('sha256').update(content1).digest('hex'),
        },
        {
          filename: filename2,
          size_bytes: content2.length,
          sha256: crypto.createHash('sha256').update(content2).digest('hex'),
        },
      ],
    }
    fs.writeFileSync(path.join(wheelsDir, 'manifest.json'), JSON.stringify(manifest, null, 2))

    let caughtError: Error | null = null
    try {
      verifyBundledWheelDirectory(wheelsDir)
    } catch (error) {
      caughtError = error as Error
    }
    expect(caughtError).not.toBeNull()
    expect(caughtError!.message).toContain('multiple versions for distribution')
    expect(caughtError!.message).toContain('shared_pkg')
    expect(caughtError!.message).toContain('1.0.0')
    expect(caughtError!.message).toContain('2.0.0')
  })
})

describe('wheel content digests — streaming vs synchronous verification', () => {
  let workspace: TempWorkspace

  beforeEach(() => {
    workspace = createTempWheelsDir()
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  /** 同长度改写：绕过 size 校验，只有内容摘要能发现。 */
  function tamperKeepingSize(wheelPath: string): void {
    const originalLength = fs.readFileSync(wheelPath).length
    fs.writeFileSync(wheelPath, Buffer.alloc(originalLength, 0x41))
  }

  it('accepts a clean wheelhouse and returns the same wheel list as the sync API', async () => {
    writeCompleteWheelhouse(workspace.wheelsDir)

    await expect(verifyBundledWheelDigestsAsync(workspace.wheelsDir)).resolves.toEqual(
      verifyBundledWheelDirectory(workspace.wheelsDir)
    )
  })

  it('reports the same SHA-256 mismatch as the sync API despite bounded concurrency', async () => {
    const { filenames } = writeCompleteWheelhouse(workspace.wheelsDir)
    tamperKeepingSize(path.join(workspace.wheelsDir, filenames[0]))

    await expect(verifyBundledWheelDigestsAsync(workspace.wheelsDir)).rejects.toThrow(
      `Bundled wheel SHA-256 mismatch: ${filenames[0]}`
    )
    expect(() => verifyBundledWheelDirectory(workspace.wheelsDir)).toThrow(
      `Bundled wheel SHA-256 mismatch: ${filenames[0]}`
    )
  })

  it('metadata-only verification catches size drift but deliberately skips content digests', () => {
    const { filenames } = writeCompleteWheelhouse(workspace.wheelsDir)
    const wheelPath = path.join(workspace.wheelsDir, filenames[0])
    const originalLength = fs.readFileSync(wheelPath).length

    // 安全权衡：同长度改写在快路径上被放行——这些 wheel 本次不会交给 uv，
    // 一旦真的需要安装，installPackages 会先跑 verifyBundledWheelDigestsAsync。
    tamperKeepingSize(wheelPath)
    expect(() => verifyBundledWheelDirectoryMetadata(workspace.wheelsDir)).not.toThrow()

    fs.writeFileSync(wheelPath, Buffer.alloc(originalLength + 1, 0x41))
    expect(() => verifyBundledWheelDirectoryMetadata(workspace.wheelsDir)).toThrow('size mismatch')
  })

  it('metadata-only runtime lock read still authenticates runtime-lock.json itself', () => {
    writeCompleteWheelhouse(workspace.wheelsDir)
    const runtimeLockPath = path.join(workspace.wheelsDir, 'runtime-lock.json')
    expect(() => readBundledRuntimeLockMetadata(workspace.wheelsDir)).not.toThrow()

    // 同长度改写 runtime-lock.json：size 校验放行，摘要校验必须拦下。
    const content = fs.readFileSync(runtimeLockPath, 'utf-8')
    const tampered = content.replace('"python_version": "3.12"', '"python_version": "3.13"')
    expect(tampered.length).toBe(content.length)
    fs.writeFileSync(runtimeLockPath, tampered)

    expect(() => readBundledRuntimeLockMetadata(workspace.wheelsDir)).toThrow(
      'Bundled runtime lock SHA-256 mismatch'
    )
  })

  it('metadata-only runtime lock read enforces the same contract as the full read', () => {
    writeCompleteWheelhouse(workspace.wheelsDir)

    expect(readBundledRuntimeLockMetadata(workspace.wheelsDir)).toEqual(
      readAndVerifyBundledRuntimeLock(workspace.wheelsDir)
    )
  })
})

describe('readAndVerifyBundledRuntimeLock — Lane 13: cross-scope duplicate version diagnostics', () => {
  let workspace: TempWorkspace

  beforeEach(() => {
    workspace = createTempWheelsDir()
  })

  afterEach(() => {
    fs.rmSync(workspace.tmpDir, { recursive: true, force: true })
  })

  it('passes on a clean complete wheelhouse', () => {
    writeCompleteWheelhouse(workspace.wheelsDir)
    expect(() => readAndVerifyBundledRuntimeLock(workspace.wheelsDir)).not.toThrow()
  })

  it('rejects runtime-lock with same distribution appearing twice with different versions', () => {
    writeCompleteWheelhouse(workspace.wheelsDir)

    // 修改 runtime-lock.json，将一个 plugin 条目复制并改 version，模拟 lock 漂移
    const runtimeLockPath = path.join(workspace.wheelsDir, 'runtime-lock.json')
    const runtimeLock = JSON.parse(fs.readFileSync(runtimeLockPath, 'utf-8'))
    const original = runtimeLock.plugins[0]
    runtimeLock.plugins.push({
      ...original,
      version: '99.9.9',
      filename: `${original.distribution}-99.9.9-py3-none-any.whl`,
    })
    // 同步追加 wheel 文件与 manifest 条目以避免 size/sha 校验先行报错
    const duplicateContent = Buffer.from('duplicate')
    fs.writeFileSync(
      path.join(workspace.wheelsDir, `${original.distribution}-99.9.9-py3-none-any.whl`),
      duplicateContent
    )
    const manifestPath = path.join(workspace.wheelsDir, 'manifest.json')
    const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf-8'))
    manifest.wheels.push({
      kind: 'plugin',
      scopes: ['plugin'],
      distribution: original.distribution,
      version: '99.9.9',
      entry_points: [],
      filename: `${original.distribution}-99.9.9-py3-none-any.whl`,
      size_bytes: duplicateContent.length,
      sha256: require('crypto').createHash('sha256').update(duplicateContent).digest('hex'),
    })
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2))
    fs.writeFileSync(runtimeLockPath, JSON.stringify(runtimeLock, null, 2))

    let caughtError: Error | null = null
    try {
      readAndVerifyBundledRuntimeLock(workspace.wheelsDir)
    } catch (error) {
      caughtError = error as Error
    }
    expect(caughtError).not.toBeNull()
    // 应该被同分发多版本检测拦截（manifest 层或 runtime-lock 层均可）
    const message = caughtError!.message
    expect(
      message.includes('multiple versions for distribution') ||
        message.includes('declares multiple versions for distribution')
    ).toBe(true)
    expect(message).toContain(original.distribution)
  })
})

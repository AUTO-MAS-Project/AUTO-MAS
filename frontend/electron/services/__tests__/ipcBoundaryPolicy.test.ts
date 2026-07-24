import * as path from 'path'

import { describe, expect, it } from 'vitest'

import {
  hasRendererReadGrant,
  isLegacyRendererTextPath,
  isPathInsideDirectory,
  isSafeDocumentPath,
  normalizeRendererGrantPath,
  resolveDirectChildPath,
  resolveRendererFilePath,
} from '../fileAccessPolicy'
import { isAllowedMainFrameSender } from '../ipcSenderPolicy'

describe('IPC sender policy', () => {
  it('accepts only an allowed top-level frame', () => {
    const base = {
      senderWebContentsId: 7,
      senderFrameProcessId: 11,
      senderFrameRoutingId: 13,
      mainFrameProcessId: 11,
      mainFrameRoutingId: 13,
    }
    expect(isAllowedMainFrameSender(base, [7])).toBe(true)
    expect(isAllowedMainFrameSender({ ...base, senderWebContentsId: 8 }, [7])).toBe(false)
    expect(isAllowedMainFrameSender({ ...base, senderFrameRoutingId: 99 }, [7])).toBe(false)
  })
})

describe('renderer file access policy', () => {
  it('rejects relative and malformed renderer paths', () => {
    expect(() => resolveRendererFilePath('relative.log')).toThrow('absolute')
    expect(() => resolveRendererFilePath('bad\0path')).toThrow('Invalid')
    expect(() => resolveRendererFilePath('\\\\server\\share\\secret.txt')).toThrow('Network')
    expect(() => resolveRendererFilePath('\\\\?\\C:\\Windows\\win.ini')).toThrow('Network')
    expect(resolveRendererFilePath(path.resolve('safe.log'))).toBe(path.resolve('safe.log'))
  })

  it('grants exact selected files and descendants of selected directories only', () => {
    const selectedFile = normalizeRendererGrantPath(path.resolve('logs', 'selected.custom'))
    const selectedDirectory = normalizeRendererGrantPath(path.resolve('project'))
    const files = new Set([selectedFile])
    const directories = new Set([selectedDirectory])

    expect(hasRendererReadGrant(selectedFile, files, directories)).toBe(true)
    expect(
      hasRendererReadGrant(path.resolve('project', 'logs', 'today.custom'), files, directories)
    ).toBe(true)
    expect(
      hasRendererReadGrant(path.resolve('project-adjacent', 'secret.txt'), files, directories)
    ).toBe(false)
    expect(isPathInsideDirectory(path.resolve('project'), selectedDirectory)).toBe(false)
  })

  it('keeps only established metadata and common log formats as restart-compatible reads', () => {
    expect(isLegacyRendererTextPath('C:\\project\\app.json')).toBe(true)
    expect(isLegacyRendererTextPath('C:\\project\\pyappify.yml')).toBe(true)
    expect(isLegacyRendererTextPath('C:\\project\\run.log')).toBe(true)
    expect(isLegacyRendererTextPath('C:\\Users\\user\\credentials.json')).toBe(false)
    expect(isLegacyRendererTextPath('C:\\Windows\\System32\\config\\SAM')).toBe(false)
  })

  it('keeps log names directly inside the log directory', () => {
    const root = path.resolve('debug')
    expect(resolveDirectChildPath(root, 'frontend.log', 'default.log')).toBe(
      path.join(root, 'frontend.log')
    )
    expect(resolveDirectChildPath(root, '../secret.txt', 'default.log')).toBeNull()
    expect(resolveDirectChildPath(root, path.resolve('secret.txt'), 'default.log')).toBeNull()
  })

  it('blocks executable shell-open targets while allowing ordinary log documents', () => {
    expect(isSafeDocumentPath('run.exe')).toBe(false)
    expect(isSafeDocumentPath('shortcut.lnk')).toBe(false)
    expect(isSafeDocumentPath('frontend.log')).toBe(true)
  })
})

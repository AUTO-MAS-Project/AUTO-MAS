import fs from 'node:fs'
import path from 'node:path'
import { describe, expect, it } from 'vitest'

import { isProcessElevated, type AdminProbeRunner } from '../adminPolicy'

const frontendDirectory = path.resolve(__dirname, '..', '..', '..')

describe('packaged administrator policy', () => {
  it('packages the executable asInvoker and keeps on-demand elevation available', () => {
    const packageJson = JSON.parse(
      fs.readFileSync(path.join(frontendDirectory, 'package.json'), 'utf8')
    )
    const mainSource = fs.readFileSync(path.join(frontendDirectory, 'electron', 'main.ts'), 'utf8')

    expect(packageJson.build.win.requestedExecutionLevel).toBe('asInvoker')
    expect(mainSource).not.toContain('if (app.isPackaged) return true')
    expect(mainSource).toContain("ipcMain.handle('check-admin'")
    expect(mainSource).toContain("ipcMain.handle('restart-as-admin'")
    expect(mainSource).toContain('isProcessElevated()')
  })

  it.each([
    ['true', true],
    [' TRUE\r\n', true],
    ['false', false],
    ['', false],
  ])('interprets the Windows token probe result %j', (stdout, expected) => {
    const runner: AdminProbeRunner = () => ({ status: 0, stdout })
    expect(isProcessElevated('win32', runner)).toBe(expected)
  })

  it('fails closed when the token probe cannot run', () => {
    const nonZeroRunner: AdminProbeRunner = () => ({ status: 1, stdout: 'true' })
    const errorRunner: AdminProbeRunner = () => ({
      status: null,
      stdout: null,
      error: new Error('probe failed'),
    })
    const throwingRunner: AdminProbeRunner = () => {
      throw new Error('probe failed')
    }

    expect(isProcessElevated('win32', nonZeroRunner)).toBe(false)
    expect(isProcessElevated('win32', errorRunner)).toBe(false)
    expect(isProcessElevated('win32', throwingRunner)).toBe(false)
  })

  it('does not require Windows elevation on other platforms', () => {
    const runner: AdminProbeRunner = () => {
      throw new Error('runner must not be called')
    }
    expect(isProcessElevated('linux', runner)).toBe(true)
  })
})

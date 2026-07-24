import { Buffer } from 'node:buffer'

import { describe, expect, it } from 'vitest'

import { buildElevationLaunchSpec, quoteWindowsArgument } from '../elevationService'

describe('buildElevationLaunchSpec', () => {
  it('keeps paths and arguments with spaces or quotes out of PowerShell source', () => {
    const executablePath = 'D:\\AUTO MAS 测试\\AUTO-MAS.exe'
    const argumentsList = ['--profile', 'alpha profile', '--label="quoted value"']
    const spec = buildElevationLaunchSpec(executablePath, argumentsList, { PATH: 'test-path' })
    const encodedCommand = spec.args.at(-1) || ''
    const decodedCommand = Buffer.from(encodedCommand, 'base64').toString('utf16le')

    expect(spec.command).toBe('powershell.exe')
    expect(spec.options).toMatchObject({ shell: false, windowsHide: true, detached: true })
    expect(decodedCommand).not.toContain(executablePath)
    expect(decodedCommand).not.toContain(argumentsList[1])
    expect(spec.options.env).toMatchObject({
      AUTO_MAS_ELEVATE_EXECUTABLE: executablePath,
      AUTO_MAS_ELEVATE_ARGUMENT_LINE: '--profile "alpha profile" "--label=\\"quoted value\\""',
    })
  })

  it('quotes empty values, whitespace, quotes, and trailing backslashes', () => {
    expect(quoteWindowsArgument('plain')).toBe('plain')
    expect(quoteWindowsArgument('')).toBe('""')
    expect(quoteWindowsArgument('two words')).toBe('"two words"')
    expect(quoteWindowsArgument('C:\\path with space\\')).toBe('"C:\\path with space\\\\"')
    expect(quoteWindowsArgument('say "hello"')).toBe('"say \\"hello\\""')
  })

  it('rejects NUL-containing process values', () => {
    expect(() => buildElevationLaunchSpec('AUTO-MAS\0.exe', [])).toThrow('valid executable')
    expect(() => buildElevationLaunchSpec('AUTO-MAS.exe', ['bad\0arg'])).toThrow('valid strings')
  })
})

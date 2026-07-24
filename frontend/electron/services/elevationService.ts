import type { SpawnOptions } from 'child_process'

const ELEVATION_EXECUTABLE_ENV = 'AUTO_MAS_ELEVATE_EXECUTABLE'
const ELEVATION_ARGUMENTS_ENV = 'AUTO_MAS_ELEVATE_ARGUMENT_LINE'

export interface ElevationLaunchSpec {
  command: string
  args: string[]
  options: SpawnOptions
}

/** Quote one argv item according to the Windows CommandLineToArgvW rules. */
export function quoteWindowsArgument(argument: string): string {
  if (argument.length > 0 && !/[\s"]/u.test(argument)) return argument

  let quoted = '"'
  let pendingBackslashes = 0
  for (const character of argument) {
    if (character === '\\') {
      pendingBackslashes += 1
      continue
    }
    if (character === '"') {
      quoted += '\\'.repeat(pendingBackslashes * 2 + 1)
      quoted += '"'
      pendingBackslashes = 0
      continue
    }
    quoted += '\\'.repeat(pendingBackslashes)
    quoted += character
    pendingBackslashes = 0
  }
  quoted += '\\'.repeat(pendingBackslashes * 2)
  return `${quoted}"`
}

/**
 * Build a shell-free Windows elevation request.
 *
 * User-controlled paths and arguments stay out of the PowerShell source. They
 * are transferred through the child environment as a correctly quoted Windows
 * argument line, then removed before Start-Process creates the elevated process.
 */
export function buildElevationLaunchSpec(
  executablePath: string,
  args: string[],
  baseEnvironment: NodeJS.ProcessEnv = process.env
): ElevationLaunchSpec {
  if (!executablePath || executablePath.includes('\0')) {
    throw new Error('Elevation requires a valid executable path')
  }
  if (args.some(argument => typeof argument !== 'string' || argument.includes('\0'))) {
    throw new Error('Elevation arguments must be valid strings')
  }

  const argumentLine = args.map(quoteWindowsArgument).join(' ')
  const script = [
    "$ErrorActionPreference = 'Stop'",
    `$executablePath = [Environment]::GetEnvironmentVariable('${ELEVATION_EXECUTABLE_ENV}', 'Process')`,
    `$argumentLine = [Environment]::GetEnvironmentVariable('${ELEVATION_ARGUMENTS_ENV}', 'Process')`,
    `Remove-Item Env:${ELEVATION_EXECUTABLE_ENV} -ErrorAction SilentlyContinue`,
    `Remove-Item Env:${ELEVATION_ARGUMENTS_ENV} -ErrorAction SilentlyContinue`,
    'if (-not [string]::IsNullOrEmpty($argumentLine)) { Start-Process -FilePath $executablePath -ArgumentList $argumentLine -Verb RunAs } else { Start-Process -FilePath $executablePath -Verb RunAs }',
  ].join('; ')

  return {
    command: 'powershell.exe',
    args: [
      '-NoProfile',
      '-NonInteractive',
      '-EncodedCommand',
      Buffer.from(script, 'utf16le').toString('base64'),
    ],
    options: {
      detached: true,
      env: {
        ...baseEnvironment,
        [ELEVATION_EXECUTABLE_ENV]: executablePath,
        [ELEVATION_ARGUMENTS_ENV]: argumentLine,
      },
      shell: false,
      stdio: 'ignore',
      windowsHide: true,
    },
  }
}

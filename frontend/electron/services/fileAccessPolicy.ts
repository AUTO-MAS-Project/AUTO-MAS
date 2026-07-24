import * as path from 'path'

export const MAX_RENDERER_TEXT_FILE_BYTES = 8 * 1024 * 1024

const UNSAFE_OPEN_EXTENSIONS = new Set([
  '.appref-ms',
  '.bat',
  '.cmd',
  '.com',
  '.cpl',
  '.exe',
  '.hta',
  '.inf',
  '.ins',
  '.isp',
  '.js',
  '.jse',
  '.lnk',
  '.msc',
  '.msi',
  '.msp',
  '.mst',
  '.pif',
  '.ps1',
  '.reg',
  '.scr',
  '.sct',
  '.url',
  '.vbe',
  '.vbs',
  '.ws',
  '.wsc',
  '.wsf',
  '.wsh',
])

const LEGACY_TEXT_FILE_NAMES = new Set(['app.json', 'pyappify.yml', 'pyappify.yaml'])
const LEGACY_LOG_EXTENSIONS = new Set(['.csv', '.log', '.out', '.trace', '.txt'])

function normalizePathForComparison(value: string): string {
  const normalized = path.resolve(value)
  return process.platform === 'win32' ? normalized.toLowerCase() : normalized
}

/** Renderer file APIs require an explicit absolute path; relative paths are ambiguous in packages. */
export function resolveRendererFilePath(value: unknown): string {
  if (typeof value !== 'string' || value.trim() === '' || value.includes('\0')) {
    throw new Error('Invalid file path')
  }
  if (value.startsWith('\\\\')) {
    throw new Error('Network and device paths are not supported')
  }
  if (!path.isAbsolute(value)) {
    throw new Error('File path must be absolute')
  }
  return path.resolve(value)
}

export function normalizeRendererGrantPath(filePath: string): string {
  return normalizePathForComparison(resolveRendererFilePath(filePath))
}

export function isPathInsideDirectory(filePath: string, directoryPath: string): boolean {
  const candidate = normalizePathForComparison(filePath)
  const directory = normalizePathForComparison(directoryPath)
  const relative = path.relative(directory, candidate)
  return relative !== '' && !relative.startsWith('..') && !path.isAbsolute(relative)
}

/** Existing saved projects retain access only to metadata and log formats consumed by the UI. */
export function isLegacyRendererTextPath(filePath: string): boolean {
  const baseName = path.basename(filePath).toLowerCase()
  return LEGACY_TEXT_FILE_NAMES.has(baseName) || LEGACY_LOG_EXTENSIONS.has(path.extname(baseName))
}

export function hasRendererReadGrant(
  filePath: string,
  grantedFiles: ReadonlySet<string>,
  grantedDirectories: ReadonlySet<string>
): boolean {
  const candidate = normalizePathForComparison(filePath)
  if (grantedFiles.has(candidate)) {
    return true
  }
  return [...grantedDirectories].some(directory => isPathInsideDirectory(candidate, directory))
}

/** Resolve one direct child filename without allowing path separators or traversal. */
export function resolveDirectChildPath(
  parentPath: string,
  requestedName: unknown,
  defaultName: string
): string | null {
  const name =
    typeof requestedName === 'string' && requestedName.trim() ? requestedName : defaultName
  if (name !== path.basename(name) || name === '.' || name === '..' || name.includes('\0')) {
    return null
  }

  const parent = path.resolve(parentPath)
  const candidate = path.resolve(parent, name)
  const relative = path.relative(parent, candidate)
  if (!relative || relative.startsWith('..') || path.isAbsolute(relative)) {
    return null
  }
  return candidate
}

/** shell.openPath must not turn renderer-controlled paths into executable launches. */
export function isSafeDocumentPath(filePath: string): boolean {
  return !UNSAFE_OPEN_EXTENSIONS.has(path.extname(filePath).toLowerCase())
}

const { createHash } = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

const WHEELHOUSE_PROVENANCE_SCHEMA = 'auto-mas.experimental-alpha.wheelhouse-provenance/v1'
const SHA256_PATTERN = /^[0-9a-f]{64}$/u
const REQUIRED_METADATA = Object.freeze(['manifest.json', 'runtime-lock.json'])
const OPTIONAL_METADATA = Object.freeze(['pylock.host.toml', 'pylock.combined.toml'])

const sha256Buffer = value => createHash('sha256').update(value).digest('hex')
const sha256File = filePath => sha256Buffer(fs.readFileSync(filePath))

const isPackagedWheelhouseFile = filename =>
  filename.endsWith('.whl') ||
  REQUIRED_METADATA.includes(filename) ||
  OPTIONAL_METADATA.includes(filename)

const canonicalizeExistingDirectory = directory => {
  const resolved = path.resolve(directory)
  const canonical =
    typeof fs.realpathSync.native === 'function'
      ? fs.realpathSync.native(resolved)
      : fs.realpathSync(resolved)
  if (!fs.statSync(canonical).isDirectory()) {
    throw new Error(`Alpha wheelhouse provenance requires a directory: ${canonical}`)
  }
  return canonical
}

const collectWheelhouseProvenance = directory => {
  const canonicalDirectory = canonicalizeExistingDirectory(directory)
  const entries = []
  for (const entry of fs
    .readdirSync(canonicalDirectory, { withFileTypes: true })
    .sort((left, right) => left.name.localeCompare(right.name, 'en'))) {
    if (!isPackagedWheelhouseFile(entry.name)) continue
    const candidate = path.join(canonicalDirectory, entry.name)
    const stats = fs.lstatSync(candidate)
    if (stats.isSymbolicLink() || !stats.isFile()) {
      throw new Error(`Alpha wheelhouse provenance requires a regular file: ${entry.name}`)
    }
    entries.push({
      filename: entry.name,
      size_bytes: stats.size,
      sha256: sha256File(candidate),
    })
  }
  for (const filename of REQUIRED_METADATA) {
    if (!entries.some(entry => entry.filename === filename)) {
      throw new Error(`Alpha wheelhouse provenance is missing: ${filename}`)
    }
  }
  if (!entries.some(entry => entry.filename.endsWith('.whl'))) {
    throw new Error('Alpha wheelhouse provenance requires at least one wheel')
  }

  const canonicalEntries = entries
    .map(entry => `${entry.filename}\0${entry.size_bytes}\0${entry.sha256}\n`)
    .join('')
  const byName = new Map(entries.map(entry => [entry.filename, entry]))
  return {
    schema: WHEELHOUSE_PROVENANCE_SCHEMA,
    canonical_path: canonicalDirectory,
    tree_sha256: sha256Buffer(Buffer.from(canonicalEntries, 'utf8')),
    file_count: entries.length,
    total_bytes: entries.reduce((total, entry) => total + entry.size_bytes, 0),
    manifest_sha256: byName.get('manifest.json').sha256,
    runtime_lock_sha256: byName.get('runtime-lock.json').sha256,
    files: entries,
  }
}

const assertWheelhouseProvenanceMatchesDirectory = (
  expected,
  directory,
  { requirePathMatch = true } = {}
) => {
  if (
    !expected ||
    expected.schema !== WHEELHOUSE_PROVENANCE_SCHEMA ||
    !SHA256_PATTERN.test(expected.tree_sha256 ?? '') ||
    !SHA256_PATTERN.test(expected.manifest_sha256 ?? '') ||
    !SHA256_PATTERN.test(expected.runtime_lock_sha256 ?? '') ||
    !Array.isArray(expected.files)
  ) {
    throw new Error('Alpha wheelhouse provenance has an unexpected schema or identity')
  }
  const actual = collectWheelhouseProvenance(directory)
  if (
    requirePathMatch &&
    path.normalize(expected.canonical_path ?? '').toLowerCase() !==
      path.normalize(actual.canonical_path).toLowerCase()
  ) {
    throw new Error('Alpha wheelhouse provenance was captured from a different directory')
  }
  if (
    expected.tree_sha256 !== actual.tree_sha256 ||
    expected.file_count !== actual.file_count ||
    expected.total_bytes !== actual.total_bytes ||
    expected.manifest_sha256 !== actual.manifest_sha256 ||
    expected.runtime_lock_sha256 !== actual.runtime_lock_sha256 ||
    JSON.stringify(expected.files) !== JSON.stringify(actual.files)
  ) {
    throw new Error('Alpha wheelhouse contents do not match captured provenance')
  }
  return actual
}

module.exports = {
  WHEELHOUSE_PROVENANCE_SCHEMA,
  assertWheelhouseProvenanceMatchesDirectory,
  collectWheelhouseProvenance,
  isPackagedWheelhouseFile,
}

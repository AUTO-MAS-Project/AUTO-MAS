import type { FluxdownRecord } from '@/api'

const knownValue = (value: unknown, allowed: readonly string[]) =>
  typeof value === 'string' && allowed.includes(value) ? value : undefined

const count = (value: unknown) =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0 ? value : undefined

const downloadOrigin = (value?: string | null) => {
  try {
    const { protocol, hostname } = new URL(value ?? '')
    if ((protocol === 'https:' || protocol === 'http:') && hostname) {
      return `${protocol}//${hostname}`
    }
  } catch {
    // 旧记录可能只有本地路径或占位符。
  }
}

const versionMarkers = (value: unknown) => {
  if (!Array.isArray(value)) return undefined
  return value.slice(0, 6).flatMap((marker: unknown) => {
    if (!marker || typeof marker !== 'object' || !('name' in marker) || !('version' in marker)) {
      return []
    }
    const name = knownValue(marker.name, ['version.txt', 'version', 'version.json'])
    const { version } = marker
    return name &&
      typeof version === 'string' &&
      /^v?\d{1,4}(?:\.\d{1,4}){1,4}(?:[-.][A-Za-z0-9.-]{1,240})?$/.test(version)
      ? [{ name, version }]
      : []
  })
}

export const downloadHistoryExport = (item: FluxdownRecord) => {
  const details = item.diagnostic
  return {
    timestamp:
      item.timestamp && /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(item.timestamp)
        ? item.timestamp
        : undefined,
    status: knownValue(item.status, [
      'success',
      'failed',
      'checksum_fail',
      'interrupted',
      'fluxdown_fallback',
    ]),
    url: downloadOrigin(item.url),
    size: count(item.size),
    duration_ms: count(item.duration_ms),
    segments: count(item.segments),
    diagnostic:
      details?.schema === 1
        ? {
            schema: 1,
            phase: knownValue(details.phase, ['download']),
            format: knownValue(details.format, ['opaque', 'zip', 'zip-invalid', '7z']),
            availability: knownValue(details.availability, [
              'missing',
              'inspection_failed',
              'download_failed',
            ]),
            source: knownValue(details.source, [
              'GitHub',
              'MirrorChyan',
              'AutoSite',
              'CNB',
              'unknown',
            ]),
            downloader: knownValue(details.downloader, ['FluxDown', 'httpx']),
            bytes: count(details.bytes),
            entries: count(details.entries),
            expanded_bytes: count(details.expanded_bytes),
            root_count: count(details.root_count),
            known_roots: Array.isArray(details.known_roots)
              ? ['March7thAssistant', 'March7thAssistant_full', 'update'].filter(root =>
                  details.known_roots.includes(root)
                )
              : undefined,
            version_markers: versionMarkers(details.version_markers),
          }
        : undefined,
  }
}

import { describe, expect, it } from 'vite-plus/test'
import { downloadHistoryExport } from './downloadHistoryExport'

describe('download history JSON export', () => {
  const privateFields = {
    url: 'https://user:secret@downloads.example:6789/private/asset.zip?token=secret',
    destination: 'C:\\Users\\private\\asset.zip',
    proxy: 'http://127.0.0.1:7890',
    error: 'Could not write C:\\Users\\private\\asset.zip via http://127.0.0.1:7890',
    checksum: 'unexpected private text',
  }

  it('exports legacy failures without exposing private fields', () => {
    const item = { ...privateFields, status: 'failed', size: 0 }
    expect(JSON.parse(JSON.stringify(downloadHistoryExport(item)))).toEqual({
      status: 'failed',
      url: 'https://downloads.example',
      size: 0,
    })
    expect(item).toMatchObject(privateFields)
  })

  it('preserves safe failure details and an IPv6 origin', () => {
    const item = {
      ...privateFields,
      url: 'https://[2001:db8::1]:8443/private/update.zip?token=secret',
      status: 'failed',
      error: 'HTTPStatusError',
      diagnostic: { schema: 1, availability: 'download_failed', http_status: 403 },
    }
    expect(JSON.parse(JSON.stringify(downloadHistoryExport(item)))).toEqual({
      status: 'failed',
      url: 'https://[2001:db8::1]',
      error_code: 'HTTPStatusError',
      diagnostic: { schema: 1, availability: 'download_failed', http_status: 403 },
    })
  })

  it('exports a successful package summary with only known diagnostic fields', () => {
    const item = {
      ...privateFields,
      timestamp: '2026-11-23 12:00:00',
      status: 'success',
      size: 420,
      diagnostic: {
        schema: 1,
        format: 'zip',
        source: 'https://proxy.example/secret',
        known_roots: ['March7thAssistant', 'C:\\Users\\private'],
        version_markers: [
          { name: 'version.txt', version: 'v1.2.3', path: privateFields.destination },
          { name: 'version.json', version: privateFields.destination },
        ],
        path: privateFields.destination,
      },
    }
    expect(JSON.parse(JSON.stringify(downloadHistoryExport(item)))).toEqual({
      timestamp: '2026-11-23 12:00:00',
      status: 'success',
      url: 'https://downloads.example',
      size: 420,
      diagnostic: {
        schema: 1,
        format: 'zip',
        known_roots: ['March7thAssistant'],
        version_markers: [{ name: 'version.txt', version: 'v1.2.3' }],
      },
    })
  })
})

import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { getRendererDevServerUrl } from '../rendererRuntimePolicy'

describe('renderer runtime policy', () => {
  it('rejects an inherited dev server URL for a packaged application', () => {
    expect(getRendererDevServerUrl(true, 'https://evil.example')).toBeUndefined()
  })

  it('permits an explicitly configured dev server only for an unpackaged application', () => {
    expect(getRendererDevServerUrl(false, 'http://127.0.0.1:5173')).toBe('http://127.0.0.1:5173')
  })

  it('is used by both packaged window entry points instead of reading VITE_DEV_SERVER_URL directly', () => {
    const servicesDirectory = path.dirname(fileURLToPath(import.meta.url))
    const mainSource = fs.readFileSync(
      path.resolve(servicesDirectory, '..', '..', 'main.ts'),
      'utf8'
    )

    expect(mainSource).toContain('getRendererDevServerUrl(app.isPackaged)')
    expect(mainSource).not.toContain('const devServer = process.env.VITE_DEV_SERVER_URL')
  })
})

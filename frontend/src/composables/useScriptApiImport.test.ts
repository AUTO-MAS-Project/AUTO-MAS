import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const composableSource = readFileSync(new URL('./useScriptApi.ts', import.meta.url), 'utf8')
const maaEndUserEditSource = readFileSync(
  new URL('../views/EditView/User/MaaEndUserEdit.vue', import.meta.url),
  'utf8'
)

describe('script config import data flow', () => {
  it('wraps the generated service in useScriptApi', () => {
    expect(composableSource).toContain('importScriptConfigFileApiScriptsConfigImportPost')
    expect(composableSource).toContain('importScriptConfigFile,')
  })

  it('keeps the business request out of the Vue page', () => {
    expect(maaEndUserEditSource).not.toContain('fetch(')
    expect(maaEndUserEditSource).not.toContain('OpenAPI.BASE')
  })
})

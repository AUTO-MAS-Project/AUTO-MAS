import { describe, expect, it } from 'vitest'

import { resolveVendorChunk } from './vite.config'

describe('Vite vendor chunk policy', () => {
  it.each([
    ['/repo/node_modules/monaco-editor/esm/vs/editor/editor.main.js', 'vendor-monaco'],
    ['C:\\repo\\node_modules\\@guolao\\vue-monaco-editor\\dist\\index.js', 'vendor-monaco'],
    ['/repo/node_modules/three/build/three.module.js', 'vendor-three'],
    ['/repo/node_modules/matter-js/build/matter.js', 'vendor-matter'],
    ['/repo/node_modules/markdown-it/index.mjs', 'vendor-markdown'],
    ['/repo/node_modules/ant-design-vue/es/button/index.js', 'vendor-ui'],
    ['/repo/node_modules/@ant-design/icons-vue/es/icons/HomeOutlined.js', 'vendor-ui'],
    ['/repo/node_modules/vue/dist/vue.runtime.esm-bundler.js', 'vendor-ui'],
    ['/repo/node_modules/vue-router/dist/vue-router.mjs', 'vendor-ui'],
  ])('maps %s to %s', (moduleId, expectedChunk) => {
    expect(resolveVendorChunk(moduleId)).toBe(expectedChunk)
  })

  it('leaves application and small unrelated dependencies to Rollup', () => {
    expect(resolveVendorChunk('/repo/src/main.ts')).toBeUndefined()
    expect(resolveVendorChunk('/repo/node_modules/dayjs/dayjs.min.js')).toBeUndefined()
  })
})

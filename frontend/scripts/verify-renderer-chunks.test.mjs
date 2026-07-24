import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { afterEach, describe, expect, it } from 'vitest'

import {
  collectRendererChunkGraph,
  findRendererChunkCycles,
  verifyRendererChunks,
} from './verify-renderer-chunks.mjs'

const temporaryDirectories = []

const createRendererOutput = files => {
  const outputDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-renderer-chunks-'))
  temporaryDirectories.push(outputDirectory)
  const assetsDirectory = path.join(outputDirectory, 'assets')
  fs.mkdirSync(assetsDirectory)
  fs.writeFileSync(path.join(outputDirectory, 'index.html'), '<!doctype html>')
  for (const [filename, source] of Object.entries(files)) {
    fs.writeFileSync(path.join(assetsDirectory, filename), source)
  }
  return outputDirectory
}

afterEach(() => {
  for (const directory of temporaryDirectories.splice(0)) {
    fs.rmSync(directory, { recursive: true, force: true })
  }
})

describe('renderer chunk graph validation', () => {
  it('accepts an acyclic static import graph and ignores dynamic imports', () => {
    const outputDirectory = createRendererOutput({
      'entry.js': 'import{a}from"./vendor-ui.js";import("./lazy.js");console.log(a)',
      'vendor-ui.js': 'export const a = 1',
      'lazy.js': 'import{a}from"./vendor-ui.js";export default a',
    })

    expect(verifyRendererChunks(outputDirectory)).toEqual({
      chunkCount: 3,
      staticEdgeCount: 2,
    })
  })

  it('rejects the vendor-vue and vendor-antd cycle that crashes packaged startup', () => {
    const outputDirectory = createRendererOutput({
      'entry.js': 'import"./vendor-vue.js"',
      'vendor-vue.js': 'import{g}from"./vendor-antd.js";export const v = g()',
      'vendor-antd.js': 'import{v}from"./vendor-vue.js";export const g = () => v',
    })
    const graph = collectRendererChunkGraph(outputDirectory)

    expect(findRendererChunkCycles(graph)).toEqual([
      ['vendor-antd.js', 'vendor-vue.js', 'vendor-antd.js'],
    ])
    expect(() => verifyRendererChunks(outputDirectory)).toThrow(
      'Renderer static chunk cycle detected'
    )
  })

  it('requires a complete renderer output', () => {
    const outputDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'auto-mas-renderer-empty-'))
    temporaryDirectories.push(outputDirectory)

    expect(() => verifyRendererChunks(outputDirectory)).toThrow('missing index.html')
  })
})

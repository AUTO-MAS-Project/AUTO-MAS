import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url))
const frontendDirectory = path.resolve(scriptDirectory, '..')

const STATIC_IMPORT_PATTERN =
  /\b(?:import|export)(?!\s*\()\s*(?:[^"'`;]*?\bfrom\s*)?["'](\.[^"']+)["']/gu

const collectStaticImports = source => {
  const imports = []
  for (const match of source.matchAll(STATIC_IMPORT_PATTERN)) {
    imports.push(match[1])
  }
  return imports
}

export const collectRendererChunkGraph = outputDirectory => {
  const assetsDirectory = path.join(outputDirectory, 'assets')
  if (!fs.existsSync(path.join(outputDirectory, 'index.html'))) {
    throw new Error(`Renderer output is missing index.html: ${outputDirectory}`)
  }
  if (!fs.existsSync(assetsDirectory) || !fs.statSync(assetsDirectory).isDirectory()) {
    throw new Error(`Renderer output is missing assets: ${assetsDirectory}`)
  }

  const javascriptFiles = fs
    .readdirSync(assetsDirectory)
    .filter(name => name.endsWith('.js'))
    .sort()
  if (javascriptFiles.length === 0) {
    throw new Error(`Renderer output contains no JavaScript chunks: ${assetsDirectory}`)
  }

  const graph = new Map()
  for (const filename of javascriptFiles) {
    const source = fs.readFileSync(path.join(assetsDirectory, filename), 'utf8')
    const dependencies = new Set()
    for (const specifier of collectStaticImports(source)) {
      const dependency = path.basename(path.resolve(assetsDirectory, filename, '..', specifier))
      if (javascriptFiles.includes(dependency)) dependencies.add(dependency)
    }
    graph.set(filename, [...dependencies].sort())
  }
  return graph
}

export const findRendererChunkCycles = graph => {
  const state = new Map()
  const stack = []
  const cycles = new Map()

  const visit = chunk => {
    state.set(chunk, 'visiting')
    stack.push(chunk)
    for (const dependency of graph.get(chunk) ?? []) {
      if (state.get(dependency) === 'visiting') {
        const cycleStart = stack.indexOf(dependency)
        const cycle = [...stack.slice(cycleStart), dependency]
        const nodes = cycle.slice(0, -1)
        const rotations = nodes.map((_, index) => [...nodes.slice(index), ...nodes.slice(0, index)])
        const canonical = rotations.map(rotation => rotation.join(' -> ')).sort()[0]
        const canonicalNodes = canonical.split(' -> ')
        cycles.set(canonical, [...canonicalNodes, canonicalNodes[0]])
      } else if (!state.has(dependency)) {
        visit(dependency)
      }
    }
    stack.pop()
    state.set(chunk, 'visited')
  }

  for (const chunk of graph.keys()) {
    if (!state.has(chunk)) visit(chunk)
  }
  return [...cycles.values()]
}

export const verifyRendererChunks = outputDirectory => {
  const graph = collectRendererChunkGraph(outputDirectory)
  const cycles = findRendererChunkCycles(graph)
  if (cycles.length > 0) {
    const details = cycles.map(cycle => cycle.join(' -> ')).join('\n')
    throw new Error(`Renderer static chunk cycle detected:\n${details}`)
  }
  return { chunkCount: graph.size, staticEdgeCount: [...graph.values()].flat().length }
}

const isMainModule =
  process.argv[1] != null && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)

if (isMainModule) {
  try {
    const outputDirectory = path.resolve(process.argv[2] ?? path.join(frontendDirectory, 'dist'))
    const result = verifyRendererChunks(outputDirectory)
    console.log(
      `Renderer chunk graph verified: ${result.chunkCount} chunks, ${result.staticEdgeCount} static edges`
    )
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error))
    process.exitCode = 1
  }
}

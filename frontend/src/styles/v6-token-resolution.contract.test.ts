import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync } from 'node:fs'
import { resolve, join } from 'node:path'

const frontendRoot = resolve(__dirname, '..')
const tokensCssPath = resolve(__dirname, 'v6-tokens.css')
const tokensCss = readFileSync(tokensCssPath, 'utf-8')

/**
 * 收集 v6-tokens.css 中所有以 --v6- 开头的自定义属性名。
 * 仅匹配 `--v6-name:` 形式，避免误把 `var(--v6-x)` 引用当作定义。
 */
const collectDefinedTokens = (css: string): Set<string> => {
  const props = new Set<string>()
  const regex = /(--v6-[\w-]+)\s*(?=:)/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(css)) !== null) {
    props.add(match[1])
  }
  return props
}

/**
 * 收集源文件中所有 var(--v6-...) 引用。
 * 同时捕获 var(--v6-x, fallback) 形式中的 --v6-x。
 */
const collectReferencedTokens = (source: string): Set<string> => {
  const refs = new Set<string>()
  const regex = /var\(\s*(--v6-[\w-]+)/g
  let match: RegExpExecArray | null
  while ((match = regex.exec(source)) !== null) {
    refs.add(match[1])
  }
  return refs
}

const listVueFiles = (dir: string): string[] => {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      out.push(...listVueFiles(full))
    } else if (entry.isFile() && entry.name.endsWith('.vue')) {
      out.push(full)
    }
  }
  return out
}

const LANE16_COMPONENT_DIRS = [
  resolve(frontendRoot, 'components', 'mac'),
  resolve(frontendRoot, 'components', 'v6'),
  resolve(frontendRoot, 'components', 'app-shell'),
]

const LANE16_COMPONENT_FILES = [resolve(frontendRoot, 'components', 'TitleBar.vue')]

describe('v6 token resolution contract for Lane 16 shell/theme components', () => {
  const definedTokens = collectDefinedTokens(tokensCss)

  const componentFiles: string[] = []
  for (const dir of LANE16_COMPONENT_DIRS) {
    componentFiles.push(...listVueFiles(dir))
  }
  for (const f of LANE16_COMPONENT_FILES) {
    componentFiles.push(f)
  }

  it('v6-tokens.css defines the canonical alias set consumed across the shell', () => {
    // 这些别名被多个 Lane 16 组件以及 Lane 07/08 拥有的页面引用，
    // 必须在 v6-tokens.css 中显式定义，否则 var() 解析为空导致样式退化。
    const requiredAliases = [
      '--v6-color-primary',
      '--v6-color-primary-hover',
      '--v6-color-background',
      '--v6-color-fill-tertiary',
      '--v6-focus-ring-inset',
    ]
    for (const token of requiredAliases) {
      expect(definedTokens.has(token), `Missing token definition: ${token}`).toBe(true)
    }
  })

  it('every var(--v6-*) reference in Lane 16 components resolves to a defined token', () => {
    const unresolved: Array<{ file: string; token: string }> = []
    for (const file of componentFiles) {
      const source = readFileSync(file, 'utf-8')
      const refs = collectReferencedTokens(source)
      for (const token of refs) {
        if (!definedTokens.has(token)) {
          unresolved.push({ file, token })
        }
      }
    }

    if (unresolved.length > 0) {
      const report = unresolved
        .map(u => `  ${u.file.replace(frontendRoot + '\\', '')} -> ${u.token}`)
        .join('\n')
      throw new Error(
        `Found ${unresolved.length} unresolved v6 token references in Lane 16 components:\n${report}`
      )
    }
    expect(unresolved).toHaveLength(0)
  })

  it('v6-tokens.css defines both light and dark theme values for the new aliases', () => {
    // 别名必须在 :root 与 :root.dark 中都出现，确保暗色下不会回退到 light 值。
    expect(tokensCss).toMatch(/:root\s*{[\s\S]*?--v6-color-primary:\s*var\(--v6-color-info\)/)
    expect(tokensCss).toMatch(/:root\.dark\s*{[\s\S]*?--v6-color-primary:\s*var\(--v6-color-info\)/)
    expect(tokensCss).toMatch(/--v6-color-background:\s*var\(--v6-color-window\)/)
    expect(tokensCss).toMatch(/--v6-color-fill-tertiary:\s*var\(--v6-color-surface-elevated\)/)
    expect(tokensCss).toMatch(/--v6-focus-ring-inset:\s*inset 0 0 0 2px var\(--v6-color-info\)/)
  })
})

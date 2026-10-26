#!/usr/bin/env node
// i18n 词表审计。零新依赖：词表用 typescript 求值，模板用 vue/compiler-sfc 解析。
//
//   yarn audit:i18n                   人读报告
//   yarn audit:i18n --verbose         列出每一条明细
//   yarn audit:i18n --json            机器可读
//   yarn audit:i18n --check           超过阈值就退出 1（CI 用）
//   yarn audit:i18n --max-missing=0   单项阈值，可覆盖 --check 的默认值
//
// 四类问题：
//   缺译   非源语言缺 key，运行时会静默回退到中文
//   占位符 {name} 之类与源语言不一致，用户会看到字面量 {name}
//   死词条 源码里找不到引用的 key（动态拼接的 key 由前缀/后缀规则兜住）
//   硬编码 模板里写死的中文，切语言后不变
import { existsSync, readFileSync, readdirSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'
import ts from 'typescript'
import { parse as parseSfc } from 'vue/compiler-sfc'

const FRONTEND = dirname(dirname(fileURLToPath(import.meta.url)))
const SRC_DIR = join(FRONTEND, 'src')
const LOCALES_DIR = join(SRC_DIR, 'i18n', 'locales')
const BACKEND_DIR = join(FRONTEND, '..', 'app')
const SOURCE_LOCALE = 'zh-CN'
const TARGET_LOCALES = ['en-US', 'ja-JP']

// 模板里承载用户可见文案的静态属性
const TEXT_ATTRIBUTES = new Set([
  'title',
  'placeholder',
  'label',
  'description',
  'content',
  'alt',
  'aria-label',
  'tooltip',
  'hint',
  'ok-text',
  'okText',
  'cancel-text',
  'cancelText',
  'confirm-text',
  'confirmText',
  'empty-text',
  'emptyText',
])

// 只在开发环境暴露的页面，里面的中文不进用户可见口径
const DEV_ONLY = /(^|\/)(devtools|OCRdev|TestRouter|UpdateDownloadDev|OverlayMaskDev)(\/|\.|$)/i

// 按规则豁免的硬编码中文：游戏内容名称没有官方外文译名，翻错比不翻更糟
const HARDCODED_ALLOWLIST = [
  {
    file: 'src/views/SRCUserEdit/StageConfigSection.vue',
    reason: '遗器/饰品/关卡选项，名称沿用游戏简中原名',
  },
]

// 汉字、假名、谚文；不含全角标点，避免“、。”“「」”单独成条
const CJK = /[\u3005\u3007\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/

const args = process.argv.slice(2)
const hasFlag = name => args.includes('--' + name)
const numberArg = (name, fallback) => {
  const hit = args.find(arg => arg.startsWith('--' + name + '='))
  return hit ? Number(hit.slice(name.length + 3)) : fallback
}

const loadLocale = async locale => {
  const source = readFileSync(join(LOCALES_DIR, locale + '.ts'), 'utf8')
  const js = ts.transpileModule(source, {
    compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 },
  }).outputText
  // 词表文件必须能单独求值；一旦引入 import，这里会先炸而不是给出错的结果
  if (/^\s*import\s/m.test(js)) throw new Error(locale + '.ts 引入了其它模块，审计脚本无法直接求值')
  const url = 'data:text/javascript;base64,' + Buffer.from(js).toString('base64')
  return (await import(url)).default
}

const flatten = (node, prefix = '', out = new Map()) => {
  if (typeof node === 'string') {
    out.set(prefix, node)
    return out
  }
  for (const [key, value] of Object.entries(node)) {
    flatten(value, prefix ? prefix + '.' + key : key, out)
  }
  return out
}

const placeholdersOf = value =>
  [...value.matchAll(/(?<!\\)\{(\w+)\}/g)].map(match => match[1]).sort()

// 测试文件也算引用方：断言里点名的 key 是有意保留的
const walkSourceFiles = dir =>
  readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) return entry.name === 'api' ? [] : walkSourceFiles(full)
    if (entry.name.endsWith('.d.ts')) return []
    return /\.(vue|ts)$/.test(entry.name) ? [full] : []
  })

// 后端的 labelKey、消息键也是词表消费者：前端 t(item.labelKey) 静态看不出来
const walkBackendFiles = dir =>
  existsSync(dir)
    ? readdirSync(dir, { withFileTypes: true }).flatMap(entry => {
        const full = join(dir, entry.name)
        if (entry.isDirectory()) return entry.name === '__pycache__' ? [] : walkBackendFiles(full)
        return entry.name.endsWith('.py') ? [full] : []
      })
    : []

// key 可能被拼出来：`home.module.${key}`、'misc.' + x、`${prefix}Empty`
// 这类动态片段整段跳过，宁可不判死也不误删
const collectFragments = (source, prefixes, suffixes) => {
  for (const match of source.matchAll(/`([^`]*)`/g)) {
    const segments = match[1].split(/\$\{[^}]*\}/)
    const head = segments[0].trim()
    if (head.length >= 4) prefixes.add(head)
    for (const segment of segments) {
      const trimmed = segment.trim()
      if (trimmed.length >= 4 && trimmed.endsWith('.')) prefixes.add(trimmed)
    }
    const tail = segments.length > 1 ? segments[segments.length - 1].trim() : ''
    if (tail.length >= 4 && !head) suffixes.add(tail)
  }
  for (const match of source.matchAll(/'([A-Za-z][\w]*(?:\.[\w]+)*\.)'/g)) {
    prefixes.add(match[1])
  }
}

const audit = async () => {
  const sourceCatalog = await loadLocale(SOURCE_LOCALE)
  const locales = { [SOURCE_LOCALE]: flatten(sourceCatalog) }
  for (const locale of TARGET_LOCALES) locales[locale] = flatten(await loadLocale(locale))
  const sourceKeys = new Set(locales[SOURCE_LOCALE].keys())

  // ---- 源码引用 ----
  const files = walkSourceFiles(SRC_DIR)
  const referenceFiles = [...files, ...walkBackendFiles(BACKEND_DIR)]
  const literalKeys = new Set()
  const calledKeys = new Set()
  const prefixes = new Set()
  const suffixes = new Set()
  let opaqueCalls = 0
  for (const file of referenceFiles) {
    const source = readFileSync(file, 'utf8')
    // 任何形如 xxx.yyy 的字符串都算引用：labelKey、常量表、任务映射都走这条路
    for (const match of source.matchAll(/['"]([A-Za-z][\w]*(?:\.[\w]+)+)['"]/g)) {
      literalKeys.add(match[1])
    }
    for (const match of source.matchAll(/(?<![\w$])\$?t\(\s*'([\w.]+)'/g)) {
      calledKeys.add(match[1])
    }
    // 参数不是字面量的调用（t(key)），这类 key 静态看不出来
    opaqueCalls += [...source.matchAll(/(?<![\w$])\$?t\(\s*[A-Za-z_$]/g)].length
    collectFragments(source, prefixes, suffixes)
  }

  const prefixList = [...prefixes].filter(Boolean)
  const suffixList = [...suffixes].filter(Boolean)
  const covered = key =>
    prefixList.some(prefix => key.startsWith(prefix)) ||
    suffixList.some(suffix => key.endsWith(suffix))

  const missing = {}
  const placeholders = {}
  for (const locale of TARGET_LOCALES) {
    const target = locales[locale]
    missing[locale] = [...sourceKeys]
      .filter(key => !target.has(key))
      .map(key => ({ key, inUse: literalKeys.has(key) || covered(key) }))
    const mismatched = []
    for (const [key, value] of locales[SOURCE_LOCALE]) {
      const translated = target.get(key)
      if (translated === undefined) continue
      const expected = placeholdersOf(value)
      const actual = placeholdersOf(translated)
      if (expected.join(',') === actual.join(',')) continue
      mismatched.push({ key, expected, actual })
    }
    placeholders[locale] = mismatched
  }

  // 和 locales.test.ts 同口径：带命名空间前缀的字面量 t('ns.key') 必须在源语言里
  const namespaces = new Set(Object.keys(sourceCatalog))
  const unknownSourceKeys = [...calledKeys].filter(
    key => namespaces.has(key.split('.')[0]) && !sourceKeys.has(key)
  )

  const unused = [...sourceKeys].filter(key => !literalKeys.has(key) && !covered(key))
  const looseUnused = [...sourceKeys].filter(
    key => literalKeys.has(key) && !calledKeys.has(key) && !covered(key)
  )

  // ---- 模板里的硬编码中文 ----
  const hardcoded = []
  for (const file of files) {
    if (!file.endsWith('.vue') || file.endsWith('.test.ts')) continue
    const source = readFileSync(file, 'utf8')
    const parsed = parseSfc(source, { filename: file })
    const root = parsed.descriptor.template && parsed.descriptor.template.ast
    if (!root) continue
    const shown = 'src/' + relative(SRC_DIR, file).split('\\').join('/')
    const exempt = HARDCODED_ALLOWLIST.find(entry => entry.file === shown)
    const report = (node, text, kind) => {
      hardcoded.push({
        file: shown,
        line: node.loc.start.line,
        kind,
        text: text.trim().replace(/\s+/g, ' ').slice(0, 80),
        devOnly: DEV_ONLY.test('/' + shown),
        exemptReason: exempt ? exempt.reason : undefined,
      })
    }
    const visit = node => {
      if (!node || typeof node.type !== 'number') return
      if (node.type === 2 && CJK.test(node.content)) report(node, node.content, 'text')
      if (node.type === 5) {
        const expression = node.content && node.content.content
        if (expression && CJK.test(expression)) {
          for (const literal of expression.match(/'[^']*'|"[^"]*"/g) || []) {
            if (CJK.test(literal)) report(node, literal, 'expression')
          }
        }
      }
      if (node.type === 1) {
        for (const prop of node.props || []) {
          if (prop.type !== 6 || !TEXT_ATTRIBUTES.has(prop.name)) continue
          const value = prop.value && prop.value.content
          if (value && CJK.test(value)) report(prop, value, 'attribute:' + prop.name)
        }
      }
      for (const child of node.children || []) visit(child)
    }
    visit(root)
  }

  const reportable = hardcoded.filter(item => !item.devOnly && !item.exemptReason)
  return {
    localeKeyCounts: Object.fromEntries(
      Object.entries(locales).map(([locale, map]) => [locale, map.size])
    ),
    scannedFiles: files.length,
    sourceKeys: sourceKeys.size,
    calledKeys: calledKeys.size,
    opaqueCalls,
    dynamicFragments: { prefixes: prefixList.length, suffixes: suffixList.length },
    prefixList,
    suffixList,
    missing,
    placeholders,
    unknownSourceKeys,
    unused,
    looseUnused,
    hardcoded: reportable,
    hardcodedDevOnly: hardcoded.filter(item => item.devOnly).length,
    hardcodedExempt: hardcoded.filter(item => item.exemptReason).length,
  }
}

const countBy = (items, pick) => {
  const groups = new Map()
  for (const item of items) {
    const group = pick(item)
    groups.set(group, (groups.get(group) || 0) + 1)
  }
  return [...groups].sort((a, b) => b[1] - a[1])
}

const pad = (label, width) => label + ' '.repeat(Math.max(0, width - label.length))

const report = result => {
  const verbose = hasFlag('verbose')
  const lines = []
  lines.push(
    'i18n 审计：源语言 ' +
      SOURCE_LOCALE +
      ' ' +
      result.sourceKeys +
      ' 条，扫描 ' +
      result.scannedFiles +
      ' 个前端文件'
  )

  lines.push('')
  lines.push('缺译（运行时会回退到 ' + SOURCE_LOCALE + '）')
  for (const locale of TARGET_LOCALES) {
    const entries = result.missing[locale]
    lines.push(
      '  ' +
        pad(locale, 8) +
        entries.length +
        ' 条，其中源码在用 ' +
        entries.filter(entry => entry.inUse).length +
        ' 条'
    )
    if (verbose) {
      for (const entry of entries) lines.push('    ' + entry.key)
    } else if (entries.length > 0) {
      const groups = countBy(entries, entry => entry.key.split('.')[0])
      lines.push(
        '    按命名空间：' +
          groups
            .slice(0, 8)
            .map(g => g[0] + ' ' + g[1])
            .join('、')
      )
    }
  }

  const mismatch = Object.entries(result.placeholders).flatMap(([locale, entries]) =>
    entries.map(entry => ({ locale, ...entry }))
  )
  lines.push('')
  lines.push('源码在用但 ' + SOURCE_LOCALE + ' 里没有 ' + result.unknownSourceKeys.length + ' 条')
  for (const key of result.unknownSourceKeys.slice(0, verbose ? Infinity : 10)) {
    lines.push('  ' + key)
  }

  lines.push('')
  lines.push('占位符与源语言不一致 ' + mismatch.length + ' 条')
  for (const entry of mismatch.slice(0, verbose ? Infinity : 10)) {
    lines.push(
      '  ' +
        pad(entry.locale, 8) +
        pad(entry.key, 46) +
        '源语言 {' +
        entry.expected.join('}{') +
        '}，译文 {' +
        entry.actual.join('}{') +
        '}'
    )
  }

  lines.push('')
  lines.push('死词条 ' + result.unused.length + ' 条（源码里没有任何引用）')
  if (result.unused.length > 0) {
    const groups = countBy(result.unused, key => key.split('.').slice(0, 2).join('.'))
    lines.push(
      '  按命名空间：' +
        groups
          .slice(0, 10)
          .map(g => g[0] + ' ' + g[1])
          .join('、')
    )
  }
  if (verbose) for (const key of result.unused) lines.push('    ' + key)
  lines.push(
    '  疑似死词条 ' +
      result.looseUnused.length +
      ' 条（只出现在字符串里，没有 t() 调用，可能是 labelKey 一类动态 key，默认保留）'
  )

  const hardcoded = result.hardcoded
  const files = new Set(hardcoded.map(item => item.file))
  lines.push('')
  lines.push(
    '模板里的硬编码中文 ' +
      hardcoded.length +
      ' 处 / ' +
      files.size +
      ' 个文件（开发页面 ' +
      result.hardcodedDevOnly +
      ' 处、按规则豁免 ' +
      result.hardcodedExempt +
      ' 处不计）'
  )
  for (const [file, count] of countBy(hardcoded, item => item.file).slice(
    0,
    verbose ? Infinity : 12
  )) {
    lines.push('  ' + pad(file, 70) + count)
  }
  if (verbose) {
    for (const item of hardcoded) {
      lines.push('  ' + item.file + ':' + item.line + ' [' + item.kind + '] ' + item.text)
    }
  }

  lines.push('')
  lines.push(
    '动态拼接片段 ' +
      result.prefixList.length +
      ' 个前缀 / ' +
      result.suffixList.length +
      ' 个后缀' +
      (verbose ? '' : '（--verbose 查看）') +
      '；参数不是字面量的 t() 调用 ' +
      result.opaqueCalls +
      ' 处，静态审计看不到'
  )
  if (verbose) {
    for (const prefix of result.prefixList) lines.push('  ' + prefix + '*')
    for (const suffix of result.suffixList) lines.push('  *' + suffix)
  }
  return lines.join('\n')
}

const main = async () => {
  const result = await audit()
  if (hasFlag('json')) process.stdout.write(JSON.stringify(result, null, 2) + '\n')
  else process.stdout.write(report(result) + '\n')

  if (!hasFlag('check')) return
  const limits = [
    {
      name: '缺译',
      actual: TARGET_LOCALES.reduce((sum, locale) => sum + result.missing[locale].length, 0),
      max: numberArg('max-missing', 0),
    },
    {
      name: '源码缺 key',
      actual: result.unknownSourceKeys.length,
      max: numberArg('max-unknown', 0),
    },
    {
      name: '占位符不一致',
      actual: Object.values(result.placeholders).reduce((sum, entries) => sum + entries.length, 0),
      max: numberArg('max-placeholder', 0),
    },
    { name: '死词条', actual: result.unused.length, max: numberArg('max-unused', 0) },
    { name: '硬编码中文', actual: result.hardcoded.length, max: numberArg('max-hardcoded', 0) },
  ]
  const exceeded = limits.filter(limit => limit.actual > limit.max)
  if (exceeded.length === 0) {
    process.stdout.write(
      '\n审计通过：' + limits.map(l => l.name + ' ' + l.actual).join('、') + '\n'
    )
    return
  }
  process.stdout.write(
    '\n审计失败：' +
      exceeded.map(l => l.name + ' ' + l.actual + ' > ' + l.max).join('、') +
      '\n' +
      '补词表或清理引用后重跑 yarn audit:i18n；确实保留下来的条目用脚本里的白名单加注理由。\n'
  )
  process.exitCode = 1
}

await main()

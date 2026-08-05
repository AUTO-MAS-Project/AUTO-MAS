import type {
  MaaFWManagedCheckout,
  MaaFWManagedGlobalInventory,
  MaaFWManagedProjectVersion,
  MaaFWManagedRuntime,
} from '@/composables/useMaaFWManagedApi'

export type GraphNodeKind = 'script' | 'version' | 'dependency' | 'runtime' | 'directory'

export interface GraphDetail {
  label: string
  value: string
  copyable?: boolean
}

export interface GraphNode {
  id: string
  kind: GraphNodeKind
  title: string
  subtitle: string
  badges: string[]
  details: GraphDetail[]
}

export interface GraphColumn {
  key: string
  label: string
  nodes: GraphNode[]
}

interface GraphVersion extends MaaFWManagedProjectVersion {
  synthetic?: boolean
  checkouts: MaaFWManagedCheckout[]
}

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}

const asString = (value: unknown) => (typeof value === 'string' ? value.trim() : '')

const uniqueStrings = (values: unknown[]) => {
  const result: string[] = []
  for (const value of values) {
    const text = asString(value)
    if (text && !result.includes(text)) result.push(text)
  }
  return result
}

const formatList = (values: unknown[], empty = '未记录') => {
  const items = uniqueStrings(values)
  return items.length ? items.join('、') : empty
}

const formatBytes = (value: unknown) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '未记录'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(2)} GB`
}

const versionKey = (projectId: string, version: string) => `${projectId}@${version}`
const versionNodeId = (projectId: string, version: string) =>
  `version:${versionKey(projectId, version)}`

const parseScriptReference = (reference: string) => {
  const value = reference.trim()
  const match = value.match(/^(?:maafw-)?script:/i)
  return match ? value.slice(match[0].length).trim() : value
}

const buildGraphVersions = (inventory: MaaFWManagedGlobalInventory) => {
  const checkoutMap = new Map<string, MaaFWManagedCheckout[]>()
  for (const checkout of inventory.checkouts || []) {
    const key = versionKey(checkout.projectId, checkout.version)
    checkoutMap.set(key, [...(checkoutMap.get(key) || []), checkout])
  }
  const records: GraphVersion[] = inventory.versions.map(version => ({
    ...version,
    checkouts: checkoutMap.get(versionKey(version.projectId, version.version)) || [],
  }))
  const existing = new Set(records.map(version => versionKey(version.projectId, version.version)))
  for (const checkout of inventory.checkouts || []) {
    const key = versionKey(checkout.projectId, checkout.version)
    if (existing.has(key)) continue
    records.push({
      projectId: checkout.projectId,
      version: checkout.version,
      references: [checkout.scriptId],
      activeLeaseIds: checkout.activeLeaseIds || [],
      dataPath: '',
      runtimeConstraint: null,
      synthetic: true,
      checkouts: [checkout],
    })
    existing.add(key)
  }
  return records
}

const versionRuntimeBinding = (version: GraphVersion) => {
  const runtime = asRecord(asRecord(version.manifest).runtime)
  const binding = asRecord(runtime.binding)
  const runtimeId = asString(binding.runtimeId) || asString(runtime.runtimeId)
  const runtimeConstraint =
    asString(version.runtimeConstraint) ||
    asString(runtime.constraint) ||
    asString(runtime.requirement) ||
    asString(runtime.maafwRequirement)
  const maafwVersion = asString(runtime.maafwVersion) || asString(runtime.version)
  const requirements = [
    ...(Array.isArray(runtime.selectorRequirements) ? runtime.selectorRequirements : []),
    ...(Array.isArray(runtime.requirements) ? runtime.requirements : []),
  ]
  return { runtimeId, runtimeConstraint, maafwVersion, requirements: uniqueStrings(requirements) }
}

const matchingRuntimes = (inventory: MaaFWManagedGlobalInventory, version: GraphVersion) => {
  const binding = versionRuntimeBinding(version)
  const identity = versionKey(version.projectId, version.version)
  return inventory.runtimes.filter(
    runtime =>
      Boolean(binding.runtimeId && runtime.runtimeId === binding.runtimeId) ||
      (runtime.references || []).some(reference => reference.includes(identity))
  )
}

const makeScriptNode = (scriptId: string, versions: GraphVersion[]): GraphNode => ({
  id: `script:${scriptId}`,
  kind: 'script',
  title: scriptId === 'unbound' ? '未绑定脚本' : scriptId,
  subtitle: scriptId === 'unbound' ? '无脚本引用的托管资源' : '脚本引用',
  badges: [`${versions.length} 个版本`],
  details: [
    {
      label: '脚本 ID',
      value: scriptId === 'unbound' ? '未绑定' : scriptId,
      copyable: scriptId !== 'unbound',
    },
    {
      label: '关联项目版本',
      value: versions.map(version => versionKey(version.projectId, version.version)).join('、'),
    },
    {
      label: '脱壳目录',
      value: formatList(
        versions.flatMap(version => version.checkouts.map(checkout => checkout.dataPath)),
        '无'
      ),
    },
  ],
})

const makeVersionNode = (version: GraphVersion): GraphNode => {
  const references = uniqueStrings(version.references || [])
  const runtime = versionRuntimeBinding(version)
  return {
    id: versionNodeId(version.projectId, version.version),
    kind: 'version',
    title: versionKey(version.projectId, version.version),
    subtitle: version.synthetic ? '脱壳目录仍存在，Store 版本未返回' : 'Project Store 版本',
    badges: [
      ...(version.current ? ['当前'] : []),
      ...(version.pinned ? ['已固定'] : []),
      ...(references.length ? [`${references.length} 个引用`] : ['无引用']),
    ],
    details: [
      { label: 'Project ID', value: version.projectId, copyable: true },
      { label: '版本', value: version.version },
      {
        label: '状态',
        value: version.synthetic
          ? '仅发现脱壳目录'
          : version.current
            ? 'Store 当前版本'
            : '已安装版本',
      },
      { label: '运行时约束', value: runtime.runtimeConstraint || '未声明' },
      { label: '脚本引用', value: formatList(version.references || [], '无') },
      { label: '活跃租约', value: formatList(version.activeLeaseIds || [], '无') },
      {
        label: '项目数据目录',
        value: version.dataPath || '未返回',
        copyable: Boolean(version.dataPath),
      },
      {
        label: 'ProjectInterface',
        value: version.projectInterfacePath || '未返回',
        copyable: Boolean(version.projectInterfacePath),
      },
      {
        label: 'Manifest',
        value: version.manifestPath || '未返回',
        copyable: Boolean(version.manifestPath),
      },
      { label: '最近使用', value: version.lastUsedAt || '未记录' },
    ],
  }
}

const makeDependencyNode = (version: GraphVersion): GraphNode => {
  const binding = versionRuntimeBinding(version)
  return {
    id: `dependency:${versionKey(version.projectId, version.version)}`,
    kind: 'dependency',
    title: binding.maafwVersion
      ? `MaaFW ${binding.maafwVersion}`
      : binding.runtimeConstraint || 'MaaFW 依赖未声明',
    subtitle: '版本 / 依赖约束',
    badges: binding.requirements.length ? [`${binding.requirements.length} 项依赖`] : [],
    details: [
      { label: '关联项目版本', value: versionKey(version.projectId, version.version) },
      { label: 'MaaFW 版本', value: binding.maafwVersion || '未解析' },
      { label: '运行时约束', value: binding.runtimeConstraint || '未声明' },
      { label: '选择器依赖', value: formatList(binding.requirements, '未记录') },
      {
        label: 'Project Store 目录',
        value: version.dataPath || '未返回',
        copyable: Boolean(version.dataPath),
      },
    ],
  }
}

const makeRuntimeNode = (runtime: MaaFWManagedRuntime): GraphNode => ({
  id: `runtime:${runtime.runtimeId}`,
  kind: 'runtime',
  title: runtime.runtimeId,
  subtitle: `MaaFW ${runtime.maafwVersion || runtime.maafwRequirement || '版本未记录'}`,
  badges: [
    ...(runtime.pinned ? ['已固定'] : []),
    ...(runtime.references?.length ? [`${runtime.references.length} 个引用`] : ['无引用']),
  ],
  details: [
    { label: 'Runtime ID', value: runtime.runtimeId, copyable: true },
    { label: 'MaaFW 版本', value: runtime.maafwVersion || '未记录' },
    { label: 'MaaFW 约束', value: runtime.maafwRequirement || '未记录' },
    { label: '选择器依赖', value: formatList(runtime.selectorRequirements || [], '未记录') },
    {
      label: '解析依赖',
      value: formatList(runtime.resolvedRequirements || runtime.packages || [], '未记录'),
    },
    {
      label: '环境目录',
      value: runtime.environmentPath || runtime.path || '未返回',
      copyable: Boolean(runtime.environmentPath || runtime.path),
    },
    { label: '活跃租约', value: formatList(runtime.activeLeaseIds || [], '无') },
    { label: '占用', value: formatBytes(runtime.sizeBytes) },
    { label: '最近使用', value: runtime.lastUsedAt || '未记录' },
  ],
})

const makeDirectoryNode = (
  path: string,
  kind: string,
  owner: string,
  details: GraphDetail[] = []
): GraphNode => ({
  id: `directory:${kind}:${path}`,
  kind: 'directory',
  title: kind,
  subtitle: path,
  badges: [],
  details: [
    { label: '目录类型', value: kind },
    { label: '归属', value: owner },
    { label: '路径', value: path, copyable: true },
    ...details,
  ],
})

export const buildResourceGraphColumns = (
  inventory: MaaFWManagedGlobalInventory
): GraphColumn[] => {
  const graphVersions = buildGraphVersions(inventory)
  const scriptVersions = new Map<string, GraphVersion[]>()
  const seen = new Set<string>()
  const columns: Record<'script' | 'version' | 'dependency' | 'directory', GraphNode[]> = {
    script: [],
    version: [],
    dependency: [],
    directory: [],
  }
  const addNode = (column: keyof typeof columns, node: GraphNode) => {
    if (seen.has(node.id)) return
    seen.add(node.id)
    columns[column].push(node)
  }

  for (const version of graphVersions) {
    const references = uniqueStrings([
      ...(version.references || []),
      ...version.checkouts.map(checkout => checkout.scriptId),
    ])
    const scriptIds = references.map(parseScriptReference).filter(Boolean)
    if (!scriptIds.length) scriptIds.push('unbound')
    for (const scriptId of scriptIds) {
      const records = scriptVersions.get(scriptId) || []
      if (
        !records.some(
          item =>
            versionKey(item.projectId, item.version) ===
            versionKey(version.projectId, version.version)
        )
      ) {
        records.push(version)
      }
      scriptVersions.set(scriptId, records)
    }
    addNode('version', makeVersionNode(version))
    const runtimes = matchingRuntimes(inventory, version)
    if (runtimes.length) {
      for (const runtime of runtimes) addNode('dependency', makeRuntimeNode(runtime))
    } else {
      addNode('dependency', makeDependencyNode(version))
    }
    if (version.dataPath) {
      addNode(
        'directory',
        makeDirectoryNode(
          version.dataPath,
          'Project Store',
          versionKey(version.projectId, version.version)
        )
      )
    }
    for (const checkout of version.checkouts) {
      if (!checkout.dataPath) continue
      addNode(
        'directory',
        makeDirectoryNode(checkout.dataPath, '脱壳 checkout', checkout.scriptId, [
          { label: 'Checkout ID', value: checkout.checkoutId, copyable: true },
          {
            label: '状态',
            value: checkout.orphanReason || (checkout.bindingCurrent ? '当前脚本绑定' : '未标记'),
          },
          { label: '源哈希', value: checkout.sourceHash || '未记录' },
        ])
      )
    }
  }

  for (const runtime of inventory.runtimes || []) {
    if (!seen.has(`runtime:${runtime.runtimeId}`)) addNode('dependency', makeRuntimeNode(runtime))
    const runtimePath = runtime.environmentPath || runtime.path
    if (runtimePath) {
      addNode(
        'directory',
        makeDirectoryNode(runtimePath, 'Runtime Pool', runtime.runtimeId, [
          { label: 'Pool ID', value: runtime.poolId || '未记录' },
        ])
      )
    }
  }

  for (const [scriptId, versions] of scriptVersions)
    addNode('script', makeScriptNode(scriptId, versions))

  return [
    { key: 'script', label: '脚本', nodes: columns.script },
    { key: 'version', label: '项目版本', nodes: columns.version },
    { key: 'dependency', label: 'MaaFW 版本 / 依赖', nodes: columns.dependency },
    { key: 'directory', label: '资源目录', nodes: columns.directory },
  ]
}

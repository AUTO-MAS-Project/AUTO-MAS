/**
 * 插件列表布局持久化 composable。
 * 管理分组、实例排序和 localstorage 持久化。
 */

import { ref } from 'vue'
import type { PluginInstance, PluginListLayoutState } from '../types'

const PLUGIN_LIST_LAYOUT_STORAGE_KEY = 'plugin-manager-list-layout-v1'

const logger = window.electronAPI.getLogger('插件布局')

function createEmptyLayout(): PluginListLayoutState {
  return {
    version: 1,
    groupOrder: [],
    instanceOrder: [],
    instanceGroups: {},
  }
}

function cloneLayout(layout: PluginListLayoutState): PluginListLayoutState {
  return {
    version: 1,
    groupOrder: [...layout.groupOrder],
    instanceOrder: [...layout.instanceOrder],
    instanceGroups: { ...layout.instanceGroups },
  }
}

function normalizeNamedGroup(value: unknown): string {
  return String(value ?? '').trim()
}

function normalizeLayout(
  layout: Partial<PluginListLayoutState> | null | undefined,
  availableInstanceIds?: string[]
): PluginListLayoutState {
  const normalized = createEmptyLayout()
  const availableSet = new Set(availableInstanceIds || [])
  const limitToAvailable = Array.isArray(availableInstanceIds)
  const seenGroups = new Set<string>()
  const seenInstanceIds = new Set<string>()

  for (const rawGroup of Array.isArray(layout?.groupOrder) ? layout.groupOrder : []) {
    const group = normalizeNamedGroup(rawGroup)
    if (!group || seenGroups.has(group)) continue
    seenGroups.add(group)
    normalized.groupOrder.push(group)
  }

  for (const rawId of Array.isArray(layout?.instanceOrder) ? layout.instanceOrder : []) {
    const id = String(rawId ?? '').trim()
    if (!id || seenInstanceIds.has(id)) continue
    if (limitToAvailable && !availableSet.has(id)) continue
    seenInstanceIds.add(id)
    normalized.instanceOrder.push(id)
  }

  const rawGroups =
    layout?.instanceGroups && typeof layout.instanceGroups === 'object' ? layout.instanceGroups : {}

  for (const [id, rawGroup] of Object.entries(rawGroups)) {
    if (limitToAvailable && !availableSet.has(id)) continue
    const group = normalizeNamedGroup(rawGroup)
    if (!group) continue
    normalized.instanceGroups[id] = group
    if (!seenGroups.has(group)) {
      seenGroups.add(group)
      normalized.groupOrder.push(group)
    }
  }

  for (const id of availableInstanceIds || []) {
    if (!seenInstanceIds.has(id)) {
      normalized.instanceOrder.push(id)
    }
  }

  return normalized
}

export function usePluginLayout() {
  const layout = ref<PluginListLayoutState>(loadLayout())

  function loadLayout(): PluginListLayoutState {
    try {
      const raw = window.localStorage.getItem(PLUGIN_LIST_LAYOUT_STORAGE_KEY)
      if (!raw) return createEmptyLayout()
      return normalizeLayout(JSON.parse(raw))
    } catch (error) {
      logger.warn(`读取插件列表布局失败，将回退到默认布局: ${String(error)}`)
      return createEmptyLayout()
    }
  }

  function persistLayout(nextLayout: PluginListLayoutState, availableInstanceIds?: string[]) {
    const normalized = normalizeLayout(nextLayout, availableInstanceIds ?? [])
    layout.value = normalized
    try {
      window.localStorage.setItem(PLUGIN_LIST_LAYOUT_STORAGE_KEY, JSON.stringify(normalized))
    } catch (error) {
      logger.warn(`保存插件列表布局失败: ${String(error)}`)
    }
  }

  function updateLayout(
    updater: (draft: PluginListLayoutState) => void,
    availableInstanceIds?: string[]
  ) {
    const draft = cloneLayout(layout.value)
    updater(draft)
    persistLayout(draft, availableInstanceIds)
  }

  function syncWithInstances(nextInstances: PluginInstance[]) {
    persistLayout(
      layout.value,
      nextInstances.map(item => item.id)
    )
  }

  function getInstanceGroupKey(instanceId: string): string {
    return layout.value.instanceGroups[instanceId] || ''
  }

  return {
    layout,
    loadLayout,
    persistLayout,
    updateLayout,
    syncWithInstances,
    getInstanceGroupKey,
  }
}

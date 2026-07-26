<template>
  <div class="left-panel">
    <section class="list-card" aria-label="插件实例">
      <header class="list-card-header">
        <div class="list-card-title">
          <span>插件实例</span>
          <a-tag>v{{ version }}</a-tag>
        </div>
        <a-button size="small" type="text" @click="$emit('createGroup')">新建分组</a-button>
      </header>

      <div class="list-card-content">
        <a-input
          v-model:value="localKeyword"
          placeholder="搜索实例 ID、名称或插件"
          allow-clear
          class="search-box"
        />

        <div class="instance-list">
          <div v-if="groupedInstances.length === 0" class="compact-empty">
            <span class="compact-empty-title">暂无插件实例</span>
            <span class="compact-empty-hint">新增实例后即可在此管理配置与运行状态</span>
          </div>
          <div
            v-for="group in groupedInstances"
            :key="group.key"
            class="instance-group"
            :data-group="group.key"
          >
            <div class="group-header">
              <span class="group-name">{{ group.label }}</span>
              <a-dropdown v-if="group.key !== ''" :trigger="['click']">
                <a-button size="small" type="text" class="group-menu-btn" aria-label="分组菜单"
                  >...</a-button
                >
                <template #overlay>
                  <a-menu @click="handleGroupMenuClick($event, group.key)">
                    <a-menu-item key="rename">重命名分组</a-menu-item>
                    <a-menu-item key="delete" danger>删除分组</a-menu-item>
                  </a-menu>
                </template>
              </a-dropdown>
            </div>

            <draggable
              :model-value="group.items"
              item-key="id"
              :animation="200"
              :disabled="isSearchActive"
              ghost-class="instance-ghost"
              chosen-class="instance-chosen"
              drag-class="instance-drag"
              handle=".drag-handle"
              group="plugins"
              @end="(evt: any) => $emit('dragEnd', evt, group.key)"
            >
              <template #item="{ element }">
                <a-dropdown
                  :trigger="['contextmenu']"
                  placement="bottomRight"
                  :overlay-class-name="'plugin-row-ctx-menu'"
                >
                  <div
                    class="instance-item"
                    :class="{
                      active: selectedInstanceId === element.id,
                      disabled: !getInstanceSwitchChecked(element),
                    }"
                    :data-id="element.id"
                    role="button"
                    tabindex="0"
                    @click="$emit('select', element.id)"
                    @keydown.enter.prevent="$emit('select', element.id)"
                    @keydown.space.prevent="$emit('select', element.id)"
                  >
                    <span class="drag-handle" title="拖拽排序" @click.stop>
                      <span class="drag-dots" />
                    </span>

                    <span
                      class="plugin-icon-wrap"
                      :class="getIconClass(element)"
                      :style="getIconStyle(element)"
                    >
                      <span class="plugin-icon-text">{{ getIconText(element) }}</span>
                    </span>

                    <div class="plugin-info">
                      <!-- 第一行：实例名为主标题，必须可见；截断时以 title 提供完整名称 -->
                      <div class="plugin-name-row">
                        <span class="plugin-name" :title="element.name || element.id">
                          {{ element.name || element.id }}
                        </span>
                        <span
                          v-if="getRuntimeStatus(element) === 'error'"
                          class="state-badge state-error"
                        >
                          <ExclamationCircleOutlined />
                          异常
                        </span>
                        <span
                          v-else-if="getRuntimeStatus(element) === 'active'"
                          class="state-badge state-active"
                        >
                          运行中
                        </span>
                      </div>
                      <!-- 第二行：版本号 / 类型徽章 / 提供者描述统一降级到次行 -->
                      <div class="plugin-meta-row">
                        <span v-if="getPluginVersion(element)" class="plugin-version">
                          v{{ getPluginVersion(element) }}
                        </span>
                        <span v-if="element.system" class="plugin-type-badge badge-system">
                          系统
                        </span>
                        <span v-else class="plugin-type-badge badge-user">用户</span>
                        <span class="plugin-desc" :title="getPluginDescription(element)">
                          {{ getPluginDescription(element) }}
                        </span>
                      </div>
                    </div>

                    <span class="plugin-toggle-wrap" @click.stop>
                      <a-switch
                        size="small"
                        :checked="getInstanceSwitchChecked(element)"
                        :loading="togglingInstanceId === element.id"
                        :disabled="element.locked || togglingInstanceId === element.id"
                        @update:checked="(val: boolean) => $emit('toggleEnabled', element, val)"
                      />
                    </span>

                    <div class="plugin-actions" @click.stop>
                      <button
                        type="button"
                        class="icon-btn"
                        title="配置"
                        aria-label="配置"
                        @click="$emit('select', element.id)"
                      >
                        <SettingOutlined />
                      </button>
                      <a-dropdown
                        :trigger="['click']"
                        placement="bottomRight"
                        :overlay-class-name="'plugin-row-ctx-menu'"
                      >
                        <button
                          type="button"
                          class="icon-btn"
                          title="更多"
                          aria-label="更多"
                          @click.stop
                        >
                          <MoreOutlined />
                        </button>
                        <template #overlay>
                          <a-menu @click="handleRowMenuClick($event, element)">
                            <a-menu-item key="configure">
                              <template #icon><SettingOutlined /></template>
                              配置插件
                            </a-menu-item>
                            <a-menu-item key="openDir">
                              <template #icon><FolderOpenOutlined /></template>
                              打开插件目录
                            </a-menu-item>
                            <a-menu-item key="checkUpdate">
                              <template #icon><SyncOutlined /></template>
                              检查更新
                            </a-menu-item>
                            <a-menu-divider />
                            <a-menu-item key="toggleEnabled">
                              <template #icon><PoweroffOutlined /></template>
                              {{ getInstanceSwitchChecked(element) ? '禁用' : '启用' }}
                            </a-menu-item>
                            <a-menu-item key="uninstall" danger>
                              <template #icon><DeleteOutlined /></template>
                              卸载
                            </a-menu-item>
                          </a-menu>
                        </template>
                      </a-dropdown>
                    </div>
                  </div>
                </a-dropdown>
              </template>
            </draggable>
          </div>
        </div>

        <div class="drop-zone">
          <div class="drop-zone-inner">
            <div class="drop-icon-wrap">
              <CloudUploadOutlined />
            </div>
            <div class="drop-text">
              <span class="drop-title">从插件市场获取插件</span>
              <span class="drop-hint">
                安装完成后可在这里新建和管理插件实例
                <button type="button" class="drop-link" @click="$emit('openPluginMarket')">
                  打开插件市场
                </button>
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import draggable from 'vuedraggable'
import {
  CloudUploadOutlined,
  DeleteOutlined,
  ExclamationCircleOutlined,
  FolderOpenOutlined,
  MoreOutlined,
  PoweroffOutlined,
  SettingOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'
import type {
  PluginInstance,
  PluginRuntimeState,
  PluginListLayoutState,
  PluginPackageInfo,
  PluginServiceInfo,
  PluginRouteInfo,
} from '../types'

const props = defineProps<{
  instances: PluginInstance[]
  orderedInstances: PluginInstance[]
  filteredInstances: PluginInstance[]
  runtimeStates: Record<string, PluginRuntimeState>
  layout: PluginListLayoutState
  selectedInstanceId: string
  togglingInstanceId: string
  keyword: string
  version: number
  pluginPackages: Record<string, PluginPackageInfo>
  pluginServices: Record<string, PluginServiceInfo>
  pluginRoutes: Record<string, PluginRouteInfo[]>
  schemaErrors: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'update:keyword', value: string): void
  (e: 'select', instanceId: string): void
  (e: 'toggleEnabled', instance: PluginInstance, enabled: boolean): void
  (e: 'dragEnd', evt: any, groupKey: string): void
  (e: 'createGroup'): void
  (e: 'groupAction', action: string, groupKey: string): void
  (e: 'openAddModal'): void
  (e: 'openPluginMarket'): void
  (e: 'openPluginDir', instance: PluginInstance): void
  (e: 'checkUpdate', instance: PluginInstance): void
  (e: 'uninstallPlugin', instance: PluginInstance): void
}>()

const localKeyword = computed({
  get: () => props.keyword,
  set: value => emit('update:keyword', value),
})

const isSearchActive = computed(() => props.keyword.trim().length > 0)

// ---- 实例元信息 ----

function getRuntimeState(instanceId: string): PluginRuntimeState | undefined {
  return props.runtimeStates[instanceId]
}

function getRuntimeStatus(instance: PluginInstance): string | undefined {
  return getRuntimeState(instance.id)?.status
}

function getInstanceSwitchChecked(instance: PluginInstance): boolean {
  if (!instance.enabled) return false
  const runtime = getRuntimeState(instance.id)
  if (!runtime) return true
  return !['error', 'disposed', 'unloaded'].includes(runtime.status)
}

function getPluginVersion(instance: PluginInstance): string {
  const pkg = props.pluginPackages[instance.plugin]
  return pkg?.version || ''
}

function getPluginDescription(instance: PluginInstance): string {
  const pluginName = instance.plugin
  const service = props.pluginServices[pluginName]
  const routes = props.pluginRoutes[pluginName] || []
  const schemaError = props.schemaErrors[pluginName]

  if (schemaError) return schemaError
  if (service) {
    const parts: string[] = []
    if (service.provides.length > 0) parts.push(`提供 ${service.provides.join('、')}`)
    if (service.needs.length > 0) parts.push(`必须 ${service.needs.join('、')}`)
    if (service.wants.length > 0) parts.push(`可选 ${service.wants.join('、')}`)
    if (parts.length > 0) return parts.join(' · ')
  }
  if (routes.length > 0) {
    return routes
      .slice(0, 2)
      .map(route => `${route.kind.toUpperCase()} ${route.path}`)
      .join(' · ')
  }
  return `插件实例 ${instance.id}`
}

// ---- 图标 ----
const PLUGIN_ICON_PALETTE: Record<string, { gradient: string; text: string }> = {
  m9a: { gradient: 'linear-gradient(135deg, #ff7a45, #e55a2b)', text: 'M9' },
  maafw: { gradient: 'linear-gradient(135deg, #13c2c2, #09a8a8)', text: 'FW' },
  hsr: { gradient: 'linear-gradient(135deg, #7c6bf7, #5a4fd6)', text: 'HS' },
  ocr: { gradient: 'linear-gradient(135deg, #af52de, #8f3fd1)', text: 'OCR' },
  webhook: { gradient: 'linear-gradient(135deg, #ff9f0a, #e88e00)', text: 'WH' },
  signin: { gradient: 'linear-gradient(135deg, #34c759, #28a745)', text: 'SI' },
  debug: { gradient: 'linear-gradient(135deg, #8e8e93, #636366)', text: 'DB' },
}

function getIconClass(instance: PluginInstance): string {
  return instance.system ? 'plugin-icon-system' : 'plugin-icon-user'
}

function getIconStyle(instance: PluginInstance): Record<string, string> {
  const palette = PLUGIN_ICON_PALETTE[instance.plugin.toLowerCase()]
  if (palette) return { background: palette.gradient }
  // 系统插件用蓝色渐变，用户插件用紫色渐变
  return instance.system
    ? { background: 'linear-gradient(135deg, var(--v6-color-info), #0064d6)' }
    : { background: 'linear-gradient(135deg, #7c6bf7, #5a4fd6)' }
}

function getIconText(instance: PluginInstance): string {
  const palette = PLUGIN_ICON_PALETTE[instance.plugin.toLowerCase()]
  if (palette) return palette.text
  // 取插件名前 2-3 个字符
  const name = instance.plugin.replace(/[^a-zA-Z0-9]/g, '')
  return name.slice(0, 2).toUpperCase() || instance.plugin.slice(0, 2)
}

// ---- 分组 ----

function getInstanceGroupKey(instanceId: string): string {
  return props.layout.instanceGroups[instanceId] || ''
}

interface InstanceGroup {
  key: string
  label: string
  items: PluginInstance[]
}

const groupedInstances = computed<InstanceGroup[]>(() => {
  const groupMap = new Map<string, PluginInstance[]>([['', []]])
  const groupOrder: string[] = ['']

  for (const group of props.layout.groupOrder) {
    if (groupMap.has(group)) continue
    groupMap.set(group, [])
    groupOrder.push(group)
  }

  for (const item of props.filteredInstances) {
    const groupKey = getInstanceGroupKey(item.id)
    if (!groupMap.has(groupKey)) {
      groupMap.set(groupKey, [])
      groupOrder.push(groupKey)
    }
    groupMap.get(groupKey)!.push(item)
  }

  return groupOrder
    .filter(key => !isSearchActive.value || (groupMap.get(key)?.length ?? 0) > 0)
    .map(key => ({
      key,
      label: key === '' ? '默认分组' : key,
      items: groupMap.get(key) || [],
    }))
})

function handleGroupMenuClick(event: { key: string | number }, groupKey: string) {
  emit('groupAction', String(event.key), groupKey)
}

function handleRowMenuClick(event: { key: string | number }, instance: PluginInstance) {
  const key = String(event.key)
  if (key === 'configure') {
    emit('select', instance.id)
  } else if (key === 'openDir') {
    emit('openPluginDir', instance)
  } else if (key === 'checkUpdate') {
    emit('checkUpdate', instance)
  } else if (key === 'toggleEnabled') {
    emit('toggleEnabled', instance, !getInstanceSwitchChecked(instance))
  } else if (key === 'uninstall') {
    emit('uninstallPlugin', instance)
  }
}
</script>

<style scoped>
.left-panel {
  position: sticky;
  top: 0;
  height: 100%;
}

.list-card {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.list-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-2);
  min-height: 52px;
  padding: 0 var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border);
}

.list-card-content {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
  padding: var(--v6-space-3);
  gap: 10px;
}

.search-box {
  flex-shrink: 0;
}

.list-card-title {
  display: flex;
  align-items: center;
  gap: 8px;
}

.instance-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 2px;
  padding-bottom: 4px;
  scrollbar-width: thin;
  -ms-overflow-style: none;
}

.compact-empty {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-1);
  margin: var(--v6-space-2);
  padding: var(--v6-space-4);
  border: 1px dashed var(--v6-color-border);
  border-radius: var(--v6-radius-control);
  background: color-mix(in srgb, var(--v6-color-surface) 58%, transparent);
}

.compact-empty-title {
  color: var(--v6-color-text);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-semibold);
}

.compact-empty-hint {
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-xs);
  line-height: var(--v6-line-height-normal);
}

.instance-list::-webkit-scrollbar {
  width: 6px;
  height: 0;
}

.instance-group {
  margin-bottom: 12px;
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 2px;
  margin-bottom: 4px;
}

.group-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--v6-color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.group-menu-btn {
  font-size: 14px;
  line-height: 1;
  padding: 0 4px;
  color: var(--v6-color-text-tertiary);
}

/* ── Plugin Row (compact NSTableView style) ── */
.instance-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  height: 56px;
  border-bottom: 0.5px solid var(--v6-color-border-subtle);
  transition: background var(--v6-motion-fast) var(--v6-ease-out);
  position: relative;
  cursor: default;
  background: transparent;
  outline: none;
}

.instance-item:last-child {
  border-bottom: none;
}

.instance-item:hover {
  background: var(--v6-vibrancy-hover);
}

.instance-item.active {
  background: var(--v6-vibrancy-selected);
}

.instance-item.disabled {
  opacity: 0.7;
}

.instance-item.disabled .plugin-icon-wrap {
  filter: saturate(0.6);
}

.instance-item:focus-visible {
  box-shadow: inset 0 0 0 2px color-mix(in srgb, var(--v6-color-info) 40%, transparent);
}

.drag-handle {
  flex: 0 0 14px;
  width: 14px;
  height: 18px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--v6-color-text-quaternary);
  cursor: move;
  user-select: none;
  opacity: 0.4;
  transition: opacity var(--v6-motion-fast) var(--v6-ease-out);
}

.instance-item:hover .drag-handle {
  opacity: 0.85;
}

.drag-dots {
  width: 8px;
  height: 14px;
  display: block;
  background-image: radial-gradient(currentColor 1px, transparent 1px);
  background-size: 4px 4px;
  background-position: 0 0;
}

/* ── Plugin Icon (32px rounded square with gradient) ── */
.plugin-icon-wrap {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #fff;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: -0.02em;
  box-shadow: 0 1px 3px rgb(0 0 0 / 12%);
  user-select: none;
}

.plugin-icon-text {
  line-height: 1;
}

.plugin-icon-system {
  /* 颜色由 inline style 控制 */
}

.plugin-icon-user {
  /* 颜色由 inline style 控制 */
}

/* ── Plugin Info ── */
.plugin-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.plugin-name-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

/* 实例名是主标题：占据剩余宽度、允许收缩但始终可见，溢出截断（title 提供全名） */
.plugin-name {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 次行：版本 / 类型徽章 / 提供者描述 */
.plugin-meta-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.plugin-version {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  flex-shrink: 0;
}

.state-badge {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: var(--v6-font-size-xs);
  font-weight: 600;
  padding: 1px 7px;
  border-radius: var(--v6-radius-full);
  white-space: nowrap;
  flex-shrink: 0;
}

.state-active {
  color: var(--v6-color-success);
  background: var(--v6-color-success-bg);
}

.state-error {
  color: var(--v6-color-error);
  background: var(--v6-color-error-bg);
}

.plugin-desc {
  flex: 1 1 auto;
  min-width: 0;
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Plugin type badge (system/user，随次行收纳) ── */
.plugin-type-badge {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-medium);
  padding: 1px 7px;
  border-radius: var(--v6-radius-full);
  white-space: nowrap;
}

.badge-system {
  background: var(--v6-vibrancy-hover);
  color: var(--v6-color-text-secondary);
}

.badge-user {
  background: var(--v6-color-info-bg);
  color: var(--v6-color-info);
}

/* ── Toggle Switch (macOS NSToggle style override) ── */
.plugin-toggle-wrap {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  align-self: center;
  min-width: 36px;
  padding: 0 2px;
  line-height: 1;
}

.plugin-toggle-wrap :deep(.ant-switch) {
  flex: 0 0 32px;
  width: 32px;
  height: 18px;
  min-width: 32px;
  padding: 0;
  line-height: 18px;
  background: rgb(120 120 128 / 32%);
}

.plugin-toggle-wrap :deep(.ant-switch.ant-switch-checked) {
  background: var(--v6-color-info);
}

.plugin-toggle-wrap :deep(.ant-switch-handle) {
  width: 14px;
  height: 14px;
  top: 2px;
  inset-inline-start: 2px;
}

.plugin-toggle-wrap :deep(.ant-switch-checked .ant-switch-handle) {
  inset-inline-start: calc(100% - 16px);
}

.plugin-toggle-wrap :deep(.ant-switch-handle::before) {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: #fff;
  box-shadow:
    0 1px 3px rgb(0 0 0 / 15%),
    0 0 0 0.5px rgb(0 0 0 / 6%);
}

.plugin-toggle-wrap :deep(.ant-switch-inner) {
  display: none;
}

/* ── Plugin Action Buttons (hidden by default, shown on hover) ── */
.plugin-actions {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity var(--v6-motion-fast) var(--v6-ease-out);
}

.instance-item:hover .plugin-actions,
.instance-item.active .plugin-actions {
  opacity: 1;
}

.icon-btn {
  width: 26px;
  height: 26px;
  border-radius: var(--v6-radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--v6-color-text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition:
    background var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
  font-size: 14px;
}

.icon-btn:hover {
  background: rgb(0 0 0 / 8%);
  color: var(--v6-color-text);
}

:root.dark .icon-btn:hover {
  background: rgb(255 255 255 / 10%);
}

.instance-ghost {
  opacity: 0.4;
}

.instance-chosen {
  cursor: move !important;
}

.instance-drag {
  transform: rotate(1deg);
  box-shadow: 0 8px 24px rgb(0 0 0 / 15%);
  z-index: 1000;
}

.instance-drag .drag-handle {
  cursor: grabbing !important;
}

.instance-drag .drag-dots {
  opacity: 1;
}

/* ── Plugin market CTA ── */
.drop-zone {
  flex-shrink: 0;
  border-radius: var(--v6-radius-card);
  border: 1.5px dashed color-mix(in srgb, var(--v6-color-info) 30%, transparent);
  background: color-mix(in srgb, var(--v6-color-info) 4%, transparent);
  transition:
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    background var(--v6-motion-fast) var(--v6-ease-out);
  margin-top: 4px;
}

.drop-zone:hover {
  border-color: var(--v6-color-info);
  background: color-mix(in srgb, var(--v6-color-info) 8%, transparent);
}

.drop-zone-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 22px 28px;
}

.drop-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: var(--v6-vibrancy-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: var(--v6-color-info);
  font-size: 20px;
}

.drop-text {
  display: flex;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.drop-title {
  font-size: var(--v6-font-size-base);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text);
}

.drop-hint {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
}

.drop-link {
  color: var(--v6-color-info);
  font-weight: var(--v6-font-weight-medium);
  font-size: inherit;
  padding: 0;
  border: none;
  background: transparent;
  text-decoration: none;
  cursor: pointer;
  transition: opacity var(--v6-motion-fast) var(--v6-ease-out);
}

.drop-link:hover {
  opacity: 0.75;
}
</style>

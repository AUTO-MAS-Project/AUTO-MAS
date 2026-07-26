<template>
  <aside class="history-sidebar" aria-label="筛选器">
    <div class="sidebar-scroll">
      <!-- 日期分组 -->
      <div class="filter-section">
        <div class="filter-section-header">
          <CalendarOutlined class="filter-section-icon" />
          <span class="filter-section-title">日期</span>
        </div>
        <div class="filter-list">
          <button
            v-for="preset in timePresets"
            :key="preset.key"
            type="button"
            class="filter-item"
            :class="{ 'filter-selected': currentPreset === preset.key }"
            @click="$emit('quick-select', preset)"
          >
            <span class="filter-check">
              <CheckOutlined v-if="currentPreset === preset.key" class="check-icon" />
            </span>
            <span class="filter-label">{{ preset.label }}</span>
            <span v-if="getDateCount(preset.key)" class="filter-count">{{
              getDateCount(preset.key)
            }}</span>
          </button>
        </div>
      </div>

      <div class="sidebar-sep" />

      <!-- 脚本分组 -->
      <div class="filter-section">
        <div class="filter-section-header">
          <FileTextOutlined class="filter-section-icon" />
          <span class="filter-section-title">脚本</span>
        </div>
        <div class="filter-list">
          <button
            v-for="opt in scriptOptions"
            :key="opt.name"
            type="button"
            class="filter-item"
            :class="{ 'filter-selected': selectedScripts.has(opt.name) }"
            @click="$emit('toggle-script', opt.name)"
          >
            <span class="filter-check">
              <CheckOutlined v-if="selectedScripts.has(opt.name)" class="check-icon" />
            </span>
            <span class="script-dot" :style="{ background: getScriptColor(opt.name) }" />
            <span class="filter-label">{{ opt.name }}</span>
            <span class="filter-count">{{ opt.count }}</span>
          </button>
          <div v-if="scriptOptions.length === 0" class="filter-empty">暂无脚本</div>
        </div>
      </div>

      <div class="sidebar-sep" />

      <!-- 级别分组 -->
      <div class="filter-section">
        <div class="filter-section-header">
          <ExclamationCircleOutlined class="filter-section-icon" />
          <span class="filter-section-title">级别</span>
        </div>
        <div class="filter-list">
          <button
            v-for="opt in levelOptions"
            :key="opt.key"
            type="button"
            class="filter-item"
            :class="{ 'filter-selected': levelFilter === opt.key }"
            @click="$emit('select-level', opt.key)"
          >
            <span class="filter-check">
              <CheckOutlined v-if="levelFilter === opt.key" class="check-icon" />
            </span>
            <span class="level-dot" :class="`dot-${opt.key}`" />
            <span class="filter-label">{{ opt.label }}</span>
            <span class="filter-count">{{ opt.count }}</span>
          </button>
        </div>
      </div>

      <div class="sidebar-sep" />

      <!-- 用户分组 -->
      <div class="filter-section">
        <div class="filter-section-header">
          <UserOutlined class="filter-section-icon" />
          <span class="filter-section-title">用户</span>
        </div>
        <div class="filter-list">
          <button
            type="button"
            class="filter-item"
            :class="{ 'filter-selected': !selectedUserFilter }"
            @click="$emit('toggle-user', '')"
          >
            <span class="filter-check">
              <CheckOutlined v-if="!selectedUserFilter" class="check-icon" />
            </span>
            <span class="filter-label">全部用户</span>
            <span class="filter-count">{{ totalUserCount }}</span>
          </button>
          <button
            v-for="opt in userOptions"
            :key="opt.name"
            type="button"
            class="filter-item"
            :class="{ 'filter-selected': selectedUserFilter === opt.name }"
            @click="$emit('toggle-user', opt.name)"
          >
            <span class="filter-check">
              <CheckOutlined v-if="selectedUserFilter === opt.name" class="check-icon" />
            </span>
            <span class="user-avatar-sm" :class="{ 'user-avatar-alt': isAltAvatar(opt.name) }">
              {{ getAvatarInitial(opt.name) }}
            </span>
            <span class="filter-label">{{ opt.name }}</span>
            <span class="filter-count">{{ opt.count }}</span>
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {
  CalendarOutlined,
  CheckOutlined,
  ExclamationCircleOutlined,
  FileTextOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import type { LevelFilter } from '../useHistoryLogic.ts'
import { timePresets } from '../useHistoryLogic.ts'

interface ScriptOption {
  name: string
  count: number
}

interface LevelOption {
  key: LevelFilter
  label: string
  count: number
}

interface UserOption {
  name: string
  count: number
}

interface DateOption {
  date: string
  count: number
}

interface Props {
  currentPreset: string
  dateOptions: DateOption[]
  scriptOptions: ScriptOption[]
  levelOptions: LevelOption[]
  userOptions: UserOption[]
  levelFilter: LevelFilter
  selectedScripts: Set<string>
  selectedUserFilter: string
}

const props = defineProps<Props>()

defineEmits<{
  (e: 'quick-select', preset: (typeof timePresets)[0]): void
  (e: 'toggle-script', name: string): void
  (e: 'select-level', level: LevelFilter): void
  (e: 'toggle-user', name: string): void
}>()

const totalUserCount = computed(() => props.userOptions.reduce((sum, o) => sum + o.count, 0))

// 取首个日期分组的计数作为日期预设的近似展示
const getDateCount = (presetKey: string): number => {
  if (props.dateOptions.length === 0) return 0
  // 长时间范围预设展示全部日期分组的总和
  if (presetKey === 'halfYear' || presetKey === 'threeMonths' || presetKey === 'twoMonths') {
    return props.dateOptions.reduce((sum, d) => sum + d.count, 0)
  }
  // 其余预设展示最近一个日期分组的计数
  return props.dateOptions[0]?.count ?? 0
}

// 脚本颜色：按名称哈希到固定调色板
const SCRIPT_COLORS = ['#007aff', '#af52de', '#34c759', '#ff9f0a', '#ff375f', '#5ac8fa']
const getScriptColor = (name: string): string => {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return SCRIPT_COLORS[hash % SCRIPT_COLORS.length]
}

// 用户头像首字母
const getAvatarInitial = (name: string): string => {
  if (!name) return '?'
  return name.charAt(0).toUpperCase()
}

// 隔位用户头像配色
const isAltAvatar = (name: string): boolean => {
  let hash = 0
  for (let i = 0; i < name.length; i++) {
    hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  }
  return hash % 2 === 1
}
</script>

<style scoped>
.history-sidebar {
  width: var(--history-sidebar-width, 220px);
  min-width: var(--history-sidebar-width, 220px);
  background: var(--v6-vibrancy-sidebar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-right: 1px solid var(--v6-color-border);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--v6-space-3) 0;
}

.sidebar-scroll::-webkit-scrollbar {
  width: 8px;
}

.sidebar-scroll::-webkit-scrollbar-track {
  background: transparent;
}

.sidebar-scroll::-webkit-scrollbar-thumb {
  background: var(--v6-color-border);
  border-radius: var(--v6-radius-full);
}

.sidebar-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--v6-color-border-strong);
}

.filter-section {
  padding: 0 var(--v6-space-2);
  margin-bottom: var(--v6-space-1);
}

.filter-section-header {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  padding: var(--v6-space-1) var(--v6-space-2) var(--v6-space-2);
  font-size: var(--v6-font-size-xs);
  font-weight: var(--v6-font-weight-semibold);
  color: var(--v6-color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  user-select: none;
}

.filter-section-icon {
  font-size: 11px;
  color: var(--v6-color-text-tertiary);
}

.filter-section-title {
  font-size: var(--v6-font-size-xs);
}

.filter-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  height: 28px;
  padding: 0 var(--v6-space-2);
  border-radius: var(--v6-radius-control);
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text);
  cursor: pointer;
  transition: background-color var(--v6-motion-fast) var(--v6-ease-out);
  user-select: none;
  background: transparent;
  border: none;
  text-align: left;
  width: 100%;
}

.filter-item:hover {
  background: var(--v6-vibrancy-hover);
}

.filter-selected {
  background: var(--v6-vibrancy-selected);
  color: var(--v6-color-info);
}

.filter-selected:hover {
  background: var(--v6-vibrancy-selected);
}

.filter-check {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.check-icon {
  font-size: 12px;
  color: var(--v6-color-info);
}

.filter-label {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.filter-count {
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.filter-selected .filter-count {
  color: var(--v6-color-info);
}

/* 级别圆点 */
.level-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--v6-radius-full);
  flex-shrink: 0;
}

.dot-error {
  background: var(--v6-color-error);
}

.dot-info {
  background: var(--v6-color-info);
}

/* 脚本圆点 */
.script-dot {
  width: 8px;
  height: 8px;
  border-radius: var(--v6-radius-full);
  flex-shrink: 0;
}

/* 用户头像 */
.user-avatar-sm {
  width: 20px;
  height: 20px;
  border-radius: var(--v6-radius-full);
  background: linear-gradient(135deg, var(--v6-color-info) 0%, #5ac8fa 100%);
  color: var(--v6-color-text-inverse);
  font-size: 10px;
  font-weight: var(--v6-font-weight-semibold);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.user-avatar-alt {
  background: linear-gradient(135deg, var(--v6-color-warning) 0%, var(--v6-color-error) 100%);
}

.sidebar-sep {
  height: 1px;
  background: var(--v6-color-border-subtle);
  margin: var(--v6-space-2) var(--v6-space-4);
}

.filter-empty {
  padding: var(--v6-space-2) var(--v6-space-3);
  font-size: var(--v6-font-size-xs);
  color: var(--v6-color-text-tertiary);
}

:root[data-perf-mode='low'] .history-sidebar {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v6-color-sidebar);
}

@media (prefers-reduced-motion: reduce) {
  .filter-item {
    transition: none;
  }
}
</style>

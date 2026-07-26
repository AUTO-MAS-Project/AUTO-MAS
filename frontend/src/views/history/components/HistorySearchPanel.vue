<template>
  <div class="history-toolbar" role="toolbar" aria-label="历史记录工具栏">
    <!-- 左侧：分段级别筛选 -->
    <div class="toolbar-leading">
      <div class="segmented-control" role="tablist" aria-label="日志级别过滤">
        <button
          v-for="opt in levelSegments"
          :key="opt.key"
          class="seg-item"
          :class="{ 'seg-active': levelFilter === opt.key }"
          role="tab"
          :aria-selected="levelFilter === opt.key"
          type="button"
          @click="$emit('update:level-filter', opt.key)"
        >
          {{ opt.label }}
        </button>
      </div>
      <!-- 极窄容器下分段控件折叠为下拉（显隐由容器查询控制） -->
      <select
        class="level-select"
        :value="levelFilter"
        aria-label="日志级别过滤"
        @change="handleLevelSelectChange"
      >
        <option v-for="opt in levelSegments" :key="opt.key" :value="opt.key">
          {{ opt.label }}
        </option>
      </select>
    </div>

    <!-- 中间：搜索框 -->
    <div class="toolbar-center">
      <div class="search-field" :class="{ 'search-field--focused': searchFocused }">
        <SearchOutlined class="search-icon" />
        <input
          :value="keyword"
          type="text"
          class="search-input"
          placeholder="搜索用户名、脚本、状态或错误信息..."
          @input="handleKeywordInput"
          @keyup.enter="$emit('search')"
          @focus="searchFocused = true"
          @blur="searchFocused = false"
        />
        <button
          v-if="keyword"
          class="search-clear"
          type="button"
          aria-label="清空关键词"
          @click="handleClearKeyword"
        >
          <CloseCircleFilled />
        </button>
      </div>
    </div>

    <!-- 右侧：操作按钮 -->
    <div class="toolbar-trailing">
      <!-- 自定义日期范围 popover -->
      <a-popover
        v-model:open="datePopoverOpen"
        trigger="click"
        placement="bottomRight"
        overlay-class-name="history-date-popover"
      >
        <template #content>
          <div class="date-popover">
            <div class="popover-row">
              <span class="popover-label">合并模式</span>
              <a-select
                :value="mode"
                size="small"
                style="width: 120px"
                @change="(v: HistorySearchIn.mode) => $emit('update:mode', v)"
              >
                <a-select-option value="DAILY">按日合并</a-select-option>
                <a-select-option value="WEEKLY">按周合并</a-select-option>
                <a-select-option value="MONTHLY">按月合并</a-select-option>
              </a-select>
            </div>
            <div class="popover-row">
              <span class="popover-label">开始日期</span>
              <a-date-picker
                :value="startDate"
                size="small"
                style="width: 140px"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                @change="(v: string) => handleStartDateChange(v)"
              />
            </div>
            <div class="popover-row">
              <span class="popover-label">结束日期</span>
              <a-date-picker
                :value="endDate"
                size="small"
                style="width: 140px"
                format="YYYY-MM-DD"
                value-format="YYYY-MM-DD"
                @change="(v: string) => handleEndDateChange(v)"
              />
            </div>
            <div class="popover-actions">
              <a-button size="small" type="primary" :loading="loading" @click="handlePopoverSearch">
                搜索
              </a-button>
              <a-button size="small" @click="datePopoverOpen = false">取消</a-button>
            </div>
          </div>
        </template>
        <button
          class="toolbar-icon-btn"
          type="button"
          aria-label="自定义日期范围"
          title="自定义日期范围"
        >
          <CalendarOutlined />
        </button>
      </a-popover>

      <button
        class="toolbar-icon-btn"
        type="button"
        aria-label="刷新"
        title="刷新"
        :disabled="loading"
        @click="$emit('search')"
      >
        <ReloadOutlined :spin="loading" />
      </button>

      <button
        class="toolbar-icon-btn toolbar-icon-btn--danger"
        type="button"
        aria-label="清空筛选"
        title="清空筛选"
        @click="$emit('clear-filters')"
      >
        <DeleteOutlined />
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  CalendarOutlined,
  CloseCircleFilled,
  DeleteOutlined,
  ReloadOutlined,
  SearchOutlined,
} from '@ant-design/icons-vue'
import { ref } from 'vue'
import type { HistorySearchIn } from '@/api'
import type { LevelFilter } from '../useHistoryLogic.ts'

interface Props {
  mode: HistorySearchIn.mode
  startDate: string
  endDate: string
  keyword: string
  currentPreset: string
  loading: boolean
  levelFilter: LevelFilter
}

defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:mode', value: HistorySearchIn.mode): void
  (e: 'update:startDate', value: string): void
  (e: 'update:endDate', value: string): void
  (e: 'update:keyword', value: string): void
  (e: 'update:level-filter', value: LevelFilter): void
  (e: 'search'): void
  (e: 'reset'): void
  (e: 'clear-filters'): void
  (e: 'date-change'): void
}>()

const searchFocused = ref(false)
const datePopoverOpen = ref(false)

// 与后端历史两态对应：错误=ERROR，信息=DONE（窄屏下拉与分段控件共用本选项源）
const levelSegments: Array<{ key: LevelFilter; label: string }> = [
  { key: 'all', label: '全部' },
  { key: 'error', label: '错误' },
  { key: 'info', label: '信息' },
]

const handleKeywordInput = (e: Event) => {
  emit('update:keyword', (e.target as HTMLInputElement).value)
}

const handleLevelSelectChange = (e: Event) => {
  emit('update:level-filter', (e.target as HTMLSelectElement).value as LevelFilter)
}

const handleClearKeyword = () => {
  emit('update:keyword', '')
  emit('search')
}

const handleStartDateChange = (v: string) => {
  emit('update:startDate', v)
  emit('date-change')
}

const handleEndDateChange = (v: string) => {
  emit('update:endDate', v)
  emit('date-change')
}

const handlePopoverSearch = () => {
  datePopoverOpen.value = false
  emit('search')
}
</script>

<style scoped>
.history-toolbar {
  display: flex;
  align-items: center;
  gap: var(--v6-space-3);
  padding: var(--v6-space-2) var(--v6-space-4);
  background: var(--v6-vibrancy-toolbar);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
  border-bottom: 1px solid var(--v6-color-border);
  min-height: 44px;
}

.toolbar-leading {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  flex-shrink: 0;
}

.toolbar-center {
  flex: 1;
  display: flex;
  justify-content: center;
  min-width: 0;
}

.toolbar-trailing {
  display: flex;
  align-items: center;
  gap: var(--v6-space-1);
  flex-shrink: 0;
}

/* ── Segmented Control ─────────────────────────────────── */
.segmented-control {
  display: inline-flex;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-control);
  padding: 2px;
}

.seg-item {
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-medium);
  color: var(--v6-color-text-secondary);
  padding: 3px var(--v6-space-3);
  border-radius: var(--v6-radius-sm);
  transition:
    color var(--v6-motion-fast) var(--v6-ease-out),
    background-color var(--v6-motion-fast) var(--v6-ease-out);
  white-space: nowrap;
  line-height: 1.5;
  border: none;
  background: transparent;
  cursor: pointer;
}

.seg-item:hover {
  color: var(--v6-color-text);
  background: var(--v6-vibrancy-hover);
}

.seg-active {
  background: var(--v6-color-info);
  color: var(--v6-color-text-inverse);
  box-shadow: 0 1px 3px color-mix(in srgb, var(--v6-color-info) 30%, transparent);
}

.seg-active:hover {
  background: var(--v6-color-primary-hover);
  color: var(--v6-color-text-inverse);
}

/* ── 窄容器降级（容器 history-page 声明于 index.vue） ──── */
/* 级别下拉：默认隐藏，仅极窄容器下替代分段控件 */
.level-select {
  display: none;
  height: 28px;
  padding: 0 var(--v6-space-2);
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-medium);
  color: var(--v6-color-text);
  background: var(--v6-color-border-subtle);
  border: none;
  border-radius: var(--v6-radius-control);
  outline: none;
  cursor: pointer;
  max-width: 100%;
}

/* 中等窄度：压缩分段控件与间距，为搜索框保留可用宽度 */
@container history-page (max-width: 720px) {
  .history-toolbar {
    gap: var(--v6-space-2);
  }

  .seg-item {
    padding: 3px var(--v6-space-2);
    font-size: var(--v6-font-size-xs);
  }
}

/* 极窄：分段控件折叠为下拉，搜索框换行独占一行，避免横向溢出 */
@container history-page (max-width: 560px) {
  .history-toolbar {
    flex-wrap: wrap;
    row-gap: var(--v6-space-2);
  }

  .segmented-control {
    display: none;
  }

  .level-select {
    display: block;
  }

  .toolbar-leading {
    min-width: 0;
  }

  .toolbar-center {
    order: 3;
    flex-basis: 100%;
  }

  .search-field {
    max-width: none;
  }
}

/* ── Search Field ──────────────────────────────────────── */
.search-field {
  display: flex;
  align-items: center;
  background: var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-full);
  padding: 0 var(--v6-space-2) 0 var(--v6-space-2);
  height: 28px;
  gap: var(--v6-space-1);
  width: 100%;
  max-width: 360px;
  transition:
    background-color var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out);
}

.search-field--focused {
  background: var(--v6-color-surface);
  box-shadow: var(--v6-shadow-focus-ring);
}

.search-icon {
  font-size: 14px;
  color: var(--v6-color-text-tertiary);
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  min-width: 0;
  font-size: var(--v6-font-size-base);
  color: var(--v6-color-text);
  background: transparent;
  border: none;
  outline: none;
}

.search-input::placeholder {
  color: var(--v6-color-text-tertiary);
}

.search-clear {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: transparent;
  color: var(--v6-color-text-tertiary);
  cursor: pointer;
  border-radius: var(--v6-radius-full);
  transition: color var(--v6-motion-fast) var(--v6-ease-out);
  font-size: 12px;
}

.search-clear:hover {
  color: var(--v6-color-text);
}

/* ── Toolbar Icon Buttons ──────────────────────────────── */
.toolbar-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--v6-radius-control);
  border: none;
  background: transparent;
  color: var(--v6-color-info);
  cursor: pointer;
  transition:
    background-color var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
  flex-shrink: 0;
  font-size: 14px;
}

.toolbar-icon-btn:hover:not(:disabled) {
  background: var(--v6-vibrancy-hover);
}

.toolbar-icon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.toolbar-icon-btn--danger {
  color: var(--v6-color-error);
}

.toolbar-icon-btn--danger:hover {
  background: var(--v6-color-error-bg);
}

/* ── Date Popover ──────────────────────────────────────── */
.date-popover {
  display: flex;
  flex-direction: column;
  gap: var(--v6-space-2);
  width: 240px;
  padding: var(--v6-space-1);
}

.popover-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-2);
}

.popover-label {
  font-size: var(--v6-font-size-sm);
  color: var(--v6-color-text-secondary);
  font-weight: var(--v6-font-weight-medium);
}

.popover-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--v6-space-2);
  margin-top: var(--v6-space-1);
}

:root[data-perf-mode='low'] .history-toolbar {
  backdrop-filter: none;
  -webkit-backdrop-filter: none;
  background: var(--v6-color-surface);
}

@media (prefers-reduced-motion: reduce) {
  .seg-item,
  .search-field,
  .toolbar-icon-btn,
  .search-clear {
    transition: none;
  }
}
</style>

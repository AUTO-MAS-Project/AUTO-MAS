<template>
  <div v-if="narrow" class="narrow-switcher-bar">
    <a-select
      :value="activeKey"
      class="narrow-target-select"
      :aria-label="t('core.games.selectTarget')"
      @change="handleSelectChange"
    >
      <a-select-option v-for="row in rows" :key="row.uid" :value="row.uid">
        {{ targetName(row) }} ({{ countOnlineDevices(row) }}/{{ countActiveDevices(row) }})
      </a-select-option>
    </a-select>

    <button
      v-if="otherOperatingTarget"
      type="button"
      class="narrow-other-op-pill"
      @click="emit('select', otherOperatingTarget.uid)"
    >
      <LoadingOutlined />
      <span>
        {{ t('core.games.otherTargetOperating', { name: targetName(otherOperatingTarget) }) }}
      </span>
      <SwapOutlined class="swap-icon" />
    </button>
  </div>

  <aside v-else class="target-rail">
    <div v-if="showSearch" class="rail-search-wrap">
      <a-input
        v-model:value="keyword"
        allow-clear
        :placeholder="t('core.games.searchPlaceholder')"
        :aria-label="t('core.games.searchPlaceholder')"
      >
        <template #prefix><SearchOutlined class="search-prefix-icon" /></template>
      </a-input>
    </div>

    <div class="rail-list" role="tablist" :aria-label="t('core.games.target')">
      <button
        v-for="row in filteredRows"
        :key="row.uid"
        type="button"
        role="tab"
        :aria-selected="row.uid === activeKey"
        class="rail-item"
        :class="{ 'rail-item--active': row.uid === activeKey }"
        @click="emit('select', row.uid)"
      >
        <div class="rail-item-top">
          <span class="rail-item-icon" aria-hidden="true">
            <MobileOutlined v-if="row.type.kind === 'emulator'" />
            <DesktopOutlined v-else />
          </span>
          <span class="rail-item-name" :title="targetName(row)">{{ targetName(row) }}</span>
          <span
            class="rail-online-count"
            :class="{ 'rail-online-count--active': countOnlineDevices(row) > 0 }"
          >
            <span class="online-dot" aria-hidden="true" />
            {{ countOnlineDevices(row) }}/{{ countActiveDevices(row) }}
          </span>
        </div>

        <div class="rail-item-meta">
          <span class="rail-adapter">{{ row.type.name }}</span>
          <span
            v-if="badgeFor(row)"
            class="rail-single-badge"
            :class="`rail-single-badge--${badgeFor(row)!.tone}`"
          >
            <LoadingOutlined v-if="badgeFor(row)!.spinning" />
            {{ t(badgeFor(row)!.labelKey) }}
          </span>
        </div>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  DesktopOutlined,
  LoadingOutlined,
  MobileOutlined,
  SearchOutlined,
  SwapOutlined,
} from '@ant-design/icons-vue'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { ActiveTriggerField } from '@/api'
import type { GameRow } from '@/types/games'
import {
  countActiveDevices,
  countOnlineDevices,
  getTargetPriorityBadge,
  type TargetPriorityBadge,
} from '../gamePresentation'

const RAIL_SEARCH_THRESHOLD = 5

const props = defineProps<{
  rows: readonly GameRow[]
  activeKey?: string
  operationsByTarget: ReadonlyMap<string, ActiveTriggerField[]>
  narrow: boolean
}>()

const emit = defineEmits<{ select: [uid: string] }>()

const { t } = useI18n()
const keyword = ref('')

const showSearch = computed(() => props.rows.length > RAIL_SEARCH_THRESHOLD)

const filteredRows = computed(() => {
  const query = keyword.value.trim().toLowerCase()
  if (!query) return props.rows
  return props.rows.filter(row => {
    const name = (row.document.info?.name ?? '').toLowerCase()
    const path = (row.document.info?.path ?? '').toLowerCase()
    const adapter = row.type.name.toLowerCase()
    return name.includes(query) || path.includes(query) || adapter.includes(query)
  })
})

const otherOperatingTarget = computed(() =>
  props.rows.find(
    row => row.uid !== props.activeKey && (props.operationsByTarget.get(row.uid)?.length ?? 0) > 0
  )
)

function handleSelectChange(value: SelectValue): void {
  if (typeof value === 'string') emit('select', value)
}

function targetName(row: GameRow): string {
  return row.document.info?.name || t('core.emulator.unnamed')
}

function badgeFor(row: GameRow): TargetPriorityBadge | null {
  return getTargetPriorityBadge(row, props.operationsByTarget.get(row.uid))
}
</script>

<style scoped>
.narrow-switcher-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-fill-quaternary);
}

.narrow-target-select {
  width: 248px;
  max-width: 100%;
}

.narrow-other-op-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid var(--ant-color-primary-border);
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-size: 12px;
  line-height: 20px;
  cursor: pointer;
}

.swap-icon {
  font-size: 11px;
  opacity: 0.75;
}

.target-rail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-right: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-fill-quaternary);
}

.rail-search-wrap {
  padding: 10px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.search-prefix-icon {
  color: var(--ant-color-text-tertiary);
}

.rail-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.rail-item {
  width: 100%;
  text-align: left;
  border: 1px solid transparent;
  background: transparent;
  border-radius: var(--ant-border-radius-lg);
  padding: 9px 10px;
  cursor: pointer;
  color: var(--ant-color-text);
  transition:
    background-color 0.15s ease,
    border-color 0.15s ease;
}

.rail-item:hover {
  background: var(--ant-color-fill-tertiary);
}

.rail-item--active {
  background: var(--ant-color-bg-container);
  border-color: var(--ant-color-primary-border);
}

html.appearance-background-custom .rail-item--active {
  background: var(--ant-color-primary-bg);
}

.rail-item-top {
  display: flex;
  align-items: center;
  gap: 8px;
}

.rail-item-icon {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  flex-shrink: 0;
}

.rail-item--active .rail-item-icon {
  color: var(--ant-color-primary);
}

.rail-item-name {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-online-count {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  color: var(--ant-color-text-tertiary);
  flex-shrink: 0;
}

.online-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-text-quaternary);
}

.rail-online-count--active {
  color: var(--ant-color-success);
  font-weight: 500;
}

.rail-online-count--active .online-dot {
  background: var(--ant-color-success);
}

.rail-item-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin-top: 5px;
  padding-left: 22px;
}

.rail-adapter {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-single-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  font-size: 11px;
  line-height: 16px;
  padding: 0 6px;
  border-radius: var(--ant-border-radius-sm);
}

.rail-single-badge--processing {
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
}

.rail-single-badge--error {
  background: var(--ant-color-error-bg);
  color: var(--ant-color-error);
}

.rail-single-badge--warning {
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-warning-text);
}

.rail-single-badge--success {
  background: var(--ant-color-success-bg);
  color: var(--ant-color-success);
}
</style>

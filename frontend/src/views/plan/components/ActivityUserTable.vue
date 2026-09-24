<template>
  <div class="activity-user-table">
    <!-- 工具栏：筛选（未指派/注意是批量作业的两个入口） -->
    <div class="toolbar">
      <a-radio-group
        :value="filter"
        size="small"
        button-style="solid"
        @update:value="(value: ActivityFilter) => emit('update:filter', value)"
      >
        <a-radio-button value="all">{{ t('plan.activity.filterAll') }}</a-radio-button>
        <a-radio-button value="no-intent">
          {{ t('plan.activity.filterNoIntent', { n: noIntentCount }) }}
        </a-radio-button>
        <a-radio-button value="attention">
          {{ t('plan.activity.filterAttention', { n: summary.attention }) }}
        </a-radio-button>
      </a-radio-group>
      <span v-if="selectedCount" class="picked">
        {{ t('plan.activity.selected', { n: selectedCount }) }}
      </span>
    </div>

    <a-table
      class="user-table"
      :columns="columns"
      :data-source="rows"
      :pagination="false"
      row-key="key"
      size="small"
      :scroll="{ y: 320 }"
    >
      <template #headerCell="{ column }">
        <a-checkbox
          v-if="column.key === 'sel'"
          :checked="allSelected"
          :indeterminate="someSelected"
          :disabled="saving || !rows.length"
          @change="onSelectAll"
        />
      </template>

      <template #bodyCell="{ column, record }">
        <a-checkbox
          v-if="column.key === 'sel'"
          :checked="selectedKeys.has(record.key)"
          :disabled="saving"
          @change="() => emit('select', record.key, !selectedKeys.has(record.key))"
        />

        <div v-else-if="column.key === 'user'" class="user-cell">
          <span class="user-name">{{ record.row.userName }}</span>
          <span class="user-server">{{ serverName(record.row.server) }}</span>
        </div>

        <a-switch
          v-else-if="column.key === 'switch'"
          size="small"
          :checked="record.row.ifActivityFirst"
          :disabled="saving"
          :aria-label="t('plan.activity.colSwitch')"
          @change="(checked: boolean) => emit('toggle', record, checked)"
        />

        <a-select
          v-else-if="column.key === 'stage'"
          :value="record.row.intent"
          :options="record.options"
          :disabled="saving"
          size="small"
          class="intent-select"
          show-search
          option-filter-prop="label"
          @update:value="(value: string) => emit('intent', record, value)"
        />

        <span
          v-else-if="column.key === 'status'"
          class="state"
          :class="`state-${record.state}`"
          :title="record.skipDetail"
        >
          <span class="dot"></span>{{ record.stateText }}
        </span>
      </template>
    </a-table>

    <!-- 批量条：两个控件默认「不修改」，只写动过的那个 -->
    <div class="bulk">
      <a-select
        v-model:value="bulkSwitch"
        class="bulk-op"
        size="small"
        :disabled="saving || !selectedCount"
        :options="switchOptions"
      />
      <a-select
        v-model:value="bulkIntent"
        class="bulk-intent"
        size="small"
        :disabled="saving || !selectedCount"
        :options="intentBulkOptions"
        show-search
        option-filter-prop="label"
      />
      <a-button
        type="primary"
        size="small"
        :loading="saving"
        :disabled="!selectedCount || !bulkDirty"
        @click="onApply"
      >
        {{ t('plan.activity.bulkApply') }}
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
// 活动关指派表：行 = 用户，每人各自一个选关意图；多选后可用批量条一次性改开关
// 或选关。组件只渲染与回传事件，取数、状态判定与写回都在
// useActivityStageAssignment / activityUserRows。
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ActivityUserRowView, ActivityFilter, IntentOptionView } from './activityUserRows'
import { getServerDisplayName } from '@/utils/serverLabel'

const props = defineProps<{
  rows: ActivityUserRowView[]
  /** 当前筛选下的行数（筛选条上的「未指派」计数用全量） */
  noIntentCount: number
  summary: { followed: number; willInject: number; attention: number }
  filter: ActivityFilter
  selectedKeys: Set<string>
  selectedCount: number
  allSelected: boolean
  someSelected: boolean
  bulkStageOptions: IntentOptionView[]
  saving: boolean
}>()

const emit = defineEmits<{
  (e: 'select', key: string, checked: boolean): void
  (e: 'selectAll', checked: boolean): void
  (e: 'toggle', view: ActivityUserRowView, checked: boolean): void
  (e: 'intent', view: ActivityUserRowView, intent: string): void
  (e: 'bulk', toggle: boolean | null, intent: string | null): void
  (e: 'update:filter', filter: ActivityFilter): void
}>()

const { t } = useI18n()

const columns = computed(() => [
  { key: 'sel', width: 40, align: 'center' as const },
  { title: t('plan.activity.colUser'), key: 'user', width: 160, align: 'left' as const },
  { title: t('plan.activity.colSwitch'), key: 'switch', width: 70, align: 'center' as const },
  { title: t('plan.activity.colStage'), key: 'stage', width: 260, align: 'left' as const },
  { title: t('plan.activity.colStatus'), key: 'status', align: 'left' as const },
])

const serverName = (server: string) => getServerDisplayName(server)

/** 表头全选框：antd 的事件类型在脚本里标注，模板里直接引用避免表达式解析问题 */
const onSelectAll = (e: { target: { checked: boolean } }) => emit('selectAll', e.target.checked)

/** 批量条：null = 不修改 */
const bulkSwitch = ref<boolean | null>(null)
const bulkIntent = ref<string | null>(null)
const bulkDirty = computed(() => bulkSwitch.value !== null || bulkIntent.value !== null)

const switchOptions = computed(() => [
  { value: null, label: t('plan.activity.bulkKeep') },
  { value: true, label: t('plan.activity.bulkOn') },
  { value: false, label: t('plan.activity.bulkOff') },
])

const intentBulkOptions = computed(() => [
  { value: null, label: t('plan.activity.bulkKeep') },
  ...props.bulkStageOptions,
])

const onApply = () => {
  emit('bulk', bulkSwitch.value, bulkIntent.value)
  bulkSwitch.value = null
  bulkIntent.value = null
}
</script>

<style scoped>
.activity-user-table {
  margin-bottom: 8px;
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}

.picked {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.user-cell {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
}

.user-name {
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-server {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.intent-select {
  width: 100%;
}

.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.state .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentcolor;
  opacity: 0.6;
}

.state-inject {
  color: var(--ant-color-success);
}

.state-no-match,
.state-skipped,
.state-no-quick-config,
.state-disabled {
  color: var(--ant-color-warning);
}

.bulk {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 0 4px;
}

.bulk-op {
  width: 96px;
}

.bulk-intent {
  width: 260px;
}
</style>

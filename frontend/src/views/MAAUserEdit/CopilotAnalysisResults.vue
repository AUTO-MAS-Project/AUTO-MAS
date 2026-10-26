<template>
  <div class="analysis-results">
    <a-row :gutter="[16, 16]" class="coverage-summary">
      <a-col :xs="12" :md="6"
        ><a-statistic
          :title="t('maaCopilot.ready')"
          :value="result.ready"
          :suffix="`/ ${result.analyzable}`"
      /></a-col>
      <a-col :xs="12" :md="6"
        ><a-statistic
          :title="t('maaCopilot.projected')"
          :value="result.projectedReady"
          :suffix="`/ ${result.analyzable}`"
      /></a-col>
      <a-col :xs="12" :md="6"
        ><a-statistic :title="t('maaCopilot.missingJobs')" :value="result.missing"
      /></a-col>
      <a-col :xs="12" :md="6"
        ><a-statistic :title="t('maaCopilot.unknown')" :value="result.unknown"
      /></a-col>
    </a-row>
    <p class="source-summary">
      {{
        t('maaCopilot.summary', {
          total: result.total,
          stages: result.stageCount,
          time: capturedTime,
        })
      }}
    </p>
    <div class="analysis-note">
      <InfoCircleOutlined aria-hidden="true" />
      <span>{{ t('maaCopilot.limitSummary') }}</span>
      <a-popover :title="t('maaCopilot.analysisNotes')" trigger="click" placement="bottomLeft">
        <template #content
          ><p class="source-detail">{{ t('maaCopilot.limitHint') }}</p></template
        >
        <a-button type="link" size="small">{{ t('maaCopilot.sourceDetails') }}</a-button>
      </a-popover>
    </div>
    <div
      v-if="
        (result.ready ?? 0) + (result.trainable ?? 0) <
        Math.ceil(((result.analyzable ?? 0) * coverage) / 100)
      "
      class="analysis-note"
    >
      <InfoCircleOutlined aria-hidden="true" />
      {{
        t('maaCopilot.ceiling', {
          count: (result.ready ?? 0) + (result.trainable ?? 0),
          total: result.analyzable,
        })
      }}
    </div>
    <a-tabs v-model:active-key="resultTab">
      <a-tab-pane key="operators" :tab="t('maaCopilot.operators')">
        <div class="result-actions">
          <a-input
            v-model:value="operatorFilter"
            :placeholder="t('maaCopilot.searchOperator')"
            allow-clear
            ><template #prefix><SearchOutlined aria-hidden="true" /></template
          ></a-input>
          <a-button
            type="primary"
            :loading="importing"
            :disabled="disabled || !selectedPlans.length"
            @click="emit('import', selectedPlans)"
          >
            {{ t('maaCopilot.import', { count: selectedPlans.length }) }}
          </a-button>
        </div>
        <a-table
          :columns="operatorColumns"
          :data-source="filteredOperators"
          row-key="operatorId"
          :pagination="{ pageSize: 15, showSizeChanger: false }"
          :row-selection="rowSelection"
          :scroll="{ x: 760 }"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'status'">
              <a-tag :color="record.owned ? 'blue' : 'orange'">{{
                t(
                  record.owned
                    ? 'maaCopilot.training'
                    : record.optional
                      ? 'maaCopilot.optionalOperator'
                      : 'maaCopilot.missingOperator'
                )
              }}</a-tag>
            </template>
            <template v-else-if="column.key === 'progress'">
              <span v-if="record.owned"
                >{{
                  t('maaCopilot.level', {
                    elite: record.currentElite,
                    level: record.currentLevel,
                  })
                }}
                →
                {{
                  t('maaCopilot.level', { elite: record.targetElite, level: record.targetLevel })
                }}</span
              >
              <span v-else>—</span>
            </template>
            <template v-else-if="column.key === 'goals'">
              <div class="goal-lines">
                <div v-for="(line, index) in goalLines(record)" :key="index">{{ line }}</div>
              </div>
            </template>
          </template>
        </a-table>
      </a-tab-pane>
      <a-tab-pane key="jobs" :tab="t('maaCopilot.jobs')">
        <div class="result-actions">
          <a-input v-model:value="jobFilter" :placeholder="t('maaCopilot.searchJob')" allow-clear />
          <a-select v-model:value="jobState" :options="jobStateOptions" class="status-select" />
        </div>
        <a-table
          :columns="jobColumns"
          :data-source="filteredJobs"
          row-key="id"
          :pagination="{ pageSize: 15, showSizeChanger: false }"
          :scroll="{ x: 760 }"
          size="small"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'title'">
              <a
                :href="`https://prts.plus/operation/${record.id}`"
                target="_blank"
                rel="noreferrer"
                @click="handleExternalLink"
                >{{ record.title }}</a
              >
            </template>
            <template v-else-if="column.key === 'state'">{{
              t(`maaCopilot.state.${record.state}`)
            }}</template>
            <template v-else-if="column.key === 'gaps'">{{
              [
                ...record.missingOperators,
                ...(record.missingAlternatives ?? []).map((names: string[]) =>
                  t('maaCopilot.oneOf', { names: names.join(' / ') })
                ),
                ...record.gaps,
              ].join('、') || '—'
            }}</template>
          </template>
        </a-table>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import dayjs from 'dayjs'
import { InfoCircleOutlined, SearchOutlined } from '@ant-design/icons-vue'
import type { Key } from 'ant-design-vue/es/_util/type'
import type { MaaCopilotAnalyzeOut, MaaCopilotOperator } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import type { CultivateOperatorCatalogEntry } from './cultivateTargets'

const props = defineProps<{
  result: MaaCopilotAnalyzeOut
  catalog: CultivateOperatorCatalogEntry[]
  coverage: number
  disabled: boolean
  importing: boolean
}>()
const emit = defineEmits<{ import: [plans: MaaCopilotOperator[]] }>()
const { t } = useI18n()
const resultTab = ref('operators')
const operatorFilter = ref('')
const jobFilter = ref('')
const jobState = ref('all')
const selected = ref<Key[]>([])

const formatTime = (value?: number) =>
  value ? dayjs.unix(value).format('YYYY-MM-DD HH:mm:ss') : '—'
const capturedTime = computed(() => formatTime(props.result?.capturedAt))
// 只有手动补等级提示、没有具体培养目标的干员不能导入。
const canImportOperator = (operator: MaaCopilotOperator) =>
  operator.owned && Boolean(operator.goals?.length)
const selectedPlans = computed(() =>
  (props.result?.operators ?? []).filter(
    op => canImportOperator(op) && selected.value.includes(op.operatorId)
  )
)
const filteredOperators = computed(() =>
  (props.result?.operators ?? []).filter(op =>
    op.name.toLowerCase().includes(operatorFilter.value.trim().toLowerCase())
  )
)
const filteredJobs = computed(() =>
  (props.result?.assignments ?? []).filter(
    job =>
      (jobState.value === 'all' || job.state === jobState.value) &&
      `${job.title} ${job.stage} ${job.author} ${job.id}`
        .toLowerCase()
        .includes(jobFilter.value.trim().toLowerCase())
  )
)
const operatorColumns = computed(() => [
  { title: t('maaCopilot.name'), dataIndex: 'name', width: 140 },
  { title: t('maaCopilot.status'), key: 'status', width: 110 },
  { title: t('maaCopilot.progress'), key: 'progress', width: 220 },
  { title: t('maaCopilot.goals'), key: 'goals' },
  { title: t('maaCopilot.demand'), dataIndex: 'demand', width: 100 },
])
const jobColumns = computed(() => [
  { title: t('maaCopilot.copilot'), key: 'title', width: 300 },
  { title: t('maaCopilot.author'), dataIndex: 'author', width: 120 },
  { title: t('maaCopilot.status'), key: 'state', width: 130 },
  { title: t('maaCopilot.gaps'), key: 'gaps' },
])
const jobStateOptions = computed(() =>
  ['all', 'ready', 'training', 'missing', 'unknown'].map(value => ({
    value,
    label: t(`maaCopilot.state.${value}`),
  }))
)
const rowSelection = computed(() => ({
  selectedRowKeys: selected.value,
  onChange: (keys: Key[]) => {
    selected.value = keys
  },
  getCheckboxProps: (record: MaaCopilotOperator) => ({
    disabled: !canImportOperator(record) || props.disabled || props.importing,
  }),
}))
const goalLines = (operator: MaaCopilotOperator) => {
  const lines = [
    ...(operator.goals ?? []).map(goal => {
      const entry = props.catalog.find(item => item.value === operator.operatorId)
      const options =
        goal.kind === 'mastery' ? entry?.skills : goal.kind === 'module' ? entry?.modules : []
      const target = options?.find(item => item.value === goal.target_id)
      const skillIndex = target?.skillIndex
      const skillLabel =
        goal.kind === 'mastery' && (skillIndex === 1 || skillIndex === 2 || skillIndex === 3)
          ? t(`edit.maaCultivateSkill${skillIndex}`)
          : null
      const name =
        target && skillLabel
          ? t('edit.maaCultivateSkillName', { name: target.label, skill: skillLabel })
          : target?.label
      return `${name ? `${name} · ` : ''}${t(`maaCopilot.kinds.${goal.kind}`)} ${goal.to_level}`
    }),
    ...(operator.manualLevel ? [t('maaCopilot.manualLevel')] : []),
  ]
  return lines.length ? lines : ['—']
}

watch(
  () => props.result,
  () => {
    selected.value = []
  }
)
</script>

<style scoped>
.analysis-results {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.result-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
}
.result-actions .ant-input-affix-wrapper {
  max-width: 280px;
}
.goal-lines {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.status-select {
  min-width: 150px;
}
.coverage-summary {
  padding: 4px 0;
}
.coverage-summary :deep(.ant-statistic-content) {
  font-size: 24px;
  font-variant-numeric: tabular-nums;
}
.coverage-summary :deep(.ant-statistic-content-suffix) {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}
.source-summary {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.analysis-note {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.analysis-note .ant-btn {
  font-size: 12px;
}
.source-detail {
  max-width: 360px;
  margin: 0;
  line-height: 1.7;
}
</style>

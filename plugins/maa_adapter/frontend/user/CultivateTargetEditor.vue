<template>
  <div class="cultivate-editor">
    <a-alert
      v-if="operatorOptionsError"
      :message="operatorOptionsError"
      type="warning"
      show-icon
      class="cultivate-alert"
    />
    <!-- 识别口径一行摘要，完整说明收进行尾 ?（对齐 PipelineRow 的 row-help） -->
    <div class="cultivate-hint cultivate-hint-inline">
      {{ t('core.maaCopilot.recognitionHintShort') }}
      <a-tooltip
        :title="t('plugins.maa_adapter.edit.maaCultivateRecognitionHint')"
        :trigger="['hover', 'focus']"
      >
        <button
          type="button"
          class="hint-help"
          :aria-label="t('plugins.maa_adapter.edit.maaCultivateRecognitionHint')"
        >
          <QuestionCircleOutlined aria-hidden="true" />
        </button>
      </a-tooltip>
    </div>
    <div v-if="!sklandBound" class="cultivate-hint cultivate-hint-inline">
      {{ t('plugins.maa_adapter.edit.maaCultivateSklandUnboundHint') }}
    </div>

    <!-- 添加干员：目录选择器、全部托管与剪贴板导入 -->
    <div class="cultivate-toolbar">
      <CultivateOperatorPicker
        :operator-catalog="operatorCatalog"
        :selected-operator-ids="rows.map(row => row.operatorId)"
        :disabled="editorLoading"
        :loading="operatorOptionsLoading"
        @add="handleAddOperator"
      />
      <CultivateManageButton :disabled="editorLoading" :skland-bound="sklandBound" />
      <CultivateClipboardImport
        :disabled="editorLoading"
        :import-targets="importCultivateTargets"
        @busy="onImportBusy"
        @imported="reveal"
      />
    </div>

    <!-- 已添加干员的批量操作 -->
    <div class="cultivate-list-bar">
      <a-input
        v-model:value="operatorFilter"
        class="cultivate-search"
        :placeholder="t('plugins.maa_adapter.edit.maaCultivateSearchOperators')"
        :aria-label="t('plugins.maa_adapter.edit.maaCultivateSearchOperators')"
        allow-clear
      >
        <template #prefix><SearchOutlined aria-hidden="true" /></template>
      </a-input>
      <a-checkbox
        :checked="allOperatorsSelected"
        :indeterminate="selectedVisibleCount > 0 && !allOperatorsSelected"
        :disabled="editorLoading || !filteredViews.length"
        @change="selectAllOperators($event.target.checked)"
      >
        {{
          t(
            operatorFilter.trim()
              ? 'plugins.maa_adapter.edit.maaCultivateSelectMatches'
              : 'plugins.maa_adapter.edit.maaCultivateSelectAll'
          )
        }}
      </a-checkbox>
      <a-button
        danger
        :disabled="editorLoading || !operatorSelection.size"
        @click="removeSelectedOperators"
      >
        {{
          t('plugins.maa_adapter.edit.maaCultivateDeleteSelected', {
            count: operatorSelection.size,
          })
        }}
      </a-button>
      <a-space class="cultivate-module-toggle">
        <a-switch
          v-model:checked="showModules"
          :disabled="editorLoading"
          :aria-label="t('plugins.maa_adapter.edit.maaCultivateShowModules')"
        />
        <span>{{ t('plugins.maa_adapter.edit.maaCultivateShowModules') }}</span>
      </a-space>
    </div>

    <!-- 双栏：左为目标卡片列表，右为材料需求预览（sticky 跟随滚动） -->
    <div class="cultivate-body">
      <CultivateOperatorList
        v-model:page="operatorPage"
        :views="filteredViews"
        :page-size="OPERATOR_PAGE_SIZE"
        :loading="operatorOptionsLoading && !operatorCatalog.length"
        :busy="editorLoading"
        :selected="operatorSelection"
        :collapsed="collapsedGroups"
        :skland-bound="sklandBound"
        :skland-degraded="sklandDegraded"
        :filter-active="!!operatorFilter.trim()"
        @toggle-selection="toggleOperatorSelection"
        @toggle-collapse="toggleGroup"
        @remove="handleRemoveOperator"
        @goal-change="handleGoalChange"
      />
      <aside class="cultivate-side">
        <CultivatePreviewPanel
          v-if="rows.length"
          :preview="cultivatePreview"
          :loading="cultivatePreviewLoading"
          :error="cultivatePreviewError"
          :item-options="itemOptions"
        />
      </aside>
    </div>
    <a-typography-link
      class="data-source-note"
      href="https://ark.yituliu.cn"
      target="_blank"
      rel="noreferrer"
      @click="handleExternalLink"
    >
      {{ t('plugins.maa_adapter.edit.maaDataSourceYituliu') }}
    </a-typography-link>
  </div>
</template>
<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { Modal } from 'ant-design-vue'
import type { CultivatePreviewOut } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import { computed, onMounted, ref, shallowRef, watch } from 'vue'
import CultivateOperatorList from './CultivateOperatorList.vue'
import CultivatePreviewPanel from './CultivatePreviewPanel.vue'
import CultivateClipboardImport from './CultivateClipboardImport.vue'
import CultivateOperatorPicker from './CultivateOperatorPicker.vue'
import CultivateManageButton from './CultivateManageButton.vue'
import {
  buildCultivateOperatorViews,
  hasUnknownDimensionGoals,
  type CultivateOperatorView,
} from './cultivateGoalLines'
import {
  appendOperator,
  parseCultivateTargets,
  removeGoal,
  removeOperator,
  serializeCultivateTargets,
  setEliteLevel,
  setMasteryLevel,
  upsertGoal,
  type CultivateGoalKind,
  type CultivateOperatorCatalogEntry as OperatorCatalogEntry,
  type CultivateTargetRow,
  type CultivateImportResult,
} from './cultivateTargets'

const { t } = useI18n()

type SelectOption = { label: string; value: string }

const props = defineProps<{
  formData: any
  loading: boolean
  /** 干员目录（一图流全量表，含技能/模组名称目录；[] 表示已加载但为空） */
  operatorCatalog: OperatorCatalogEntry[]
  operatorOptionsLoading: boolean
  operatorOptionsError: string
  /** 未绑定森空岛时技能/专精/模组目标只读 */
  sklandBound: boolean
  /** 物品目录（MAA item_index，供预览材料名显示） */
  itemOptions: SelectOption[]
  /** 养成需求预览（后端纯计算结果） */
  cultivatePreview: CultivatePreviewOut | null
  cultivatePreviewLoading: boolean
  cultivatePreviewError: string
  /** 目标行变化时触发（父级负责请求与竞态守卫） */
  loadCultivatePreview: (targetsJson: string) => Promise<void>
  importCultivateTargets: (
    content: string,
    format?: 'clipboard' | 'targets'
  ) => Promise<CultivateImportResult>
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  busy: [value: boolean]
}>()

const showModules = ref(false)
const operatorFilter = ref('')
// 目标编辑统一替换数组；不为全量目标创建深层代理，避免保存/预览序列化遍历代理。
const rows = shallowRef<CultivateTargetRow[]>([])
const operatorSelection = ref(new Set<string>())
// 分页只限制渲染，保存与需求预览始终使用全量目标。
const OPERATOR_PAGE_SIZE = 4
const operatorPage = ref(1)
const importing = ref(false)
const editorLoading = computed(() => props.loading || importing.value)
// 本组件刚序列化写回的 JSON：watch 回声时跳过重建，避免下拉与行列表闪变
let lastEmitted: string | null = null

watch(
  () => props.formData?.Task?.CultivateTargets,
  json => {
    if (json === lastEmitted) return
    rows.value = parseCultivateTargets(json)
    lastEmitted = null
  },
  { immediate: true }
)

watch(rows, nextRows => {
  const remainingIds = new Set(nextRows.map(row => row.operatorId))
  operatorSelection.value = new Set([...operatorSelection.value].filter(id => remainingIds.has(id)))
})

const persist = (next: CultivateTargetRow[]) => {
  rows.value = next
  lastEmitted = serializeCultivateTargets(next)
  emit('save', 'Task.CultivateTargets', lastEmitted)
}

// ── 干员卡片视图（目录 + 练度快照合成，纯展示） ──
const translate = (key: string, params?: Record<string, unknown>) => t(key, params ?? {})
const operatorViews = computed<CultivateOperatorView[]>(() =>
  buildCultivateOperatorViews({
    rows: rows.value,
    catalog: props.operatorCatalog,
    progressions: props.cultivatePreview?.progressions,
    showModules: showModules.value,
    t: translate,
  })
)

const filteredViews = computed(() => {
  const query = operatorFilter.value.trim().toLowerCase()
  return query
    ? operatorViews.value.filter(
        view =>
          view.name.toLowerCase().includes(query) || view.operatorId.toLowerCase().includes(query)
      )
    : operatorViews.value
})

const selectedVisibleCount = computed(
  () => filteredViews.value.filter(view => operatorSelection.value.has(view.operatorId)).length
)
const allOperatorsSelected = computed(
  () => filteredViews.value.length > 0 && selectedVisibleCount.value === filteredViews.value.length
)

const handleAddOperator = (operatorId: string) => {
  if (!operatorId) return
  operatorFilter.value = ''
  const catalogEntry = props.operatorCatalog.find(entry => entry.value === operatorId)
  persist(appendOperator(rows.value, operatorId, [], catalogEntry?.maxElite ?? 2))
  operatorPage.value = Math.ceil(rows.value.length / OPERATOR_PAGE_SIZE)
}

const handleRemoveOperator = (operatorId: string) => {
  persist(removeOperator(rows.value, operatorId))
}

const toggleOperatorSelection = (operatorId: string, checked: boolean) => {
  const next = new Set(operatorSelection.value)
  if (checked) next.add(operatorId)
  else next.delete(operatorId)
  operatorSelection.value = next
}

const selectAllOperators = (checked: boolean) => {
  const next = new Set(operatorSelection.value)
  for (const view of filteredViews.value) {
    if (checked) next.add(view.operatorId)
    else next.delete(view.operatorId)
  }
  operatorSelection.value = next
}

const removeSelectedOperators = () => {
  const selected = new Set(operatorSelection.value)
  Modal.confirm({
    title: t('plugins.maa_adapter.edit.maaCultivateDeleteSelected', { count: selected.size }),
    content: t('plugins.maa_adapter.edit.maaCultivateDeleteSelectedConfirm', {
      count: selected.size,
    }),
    okText: t('core.common.confirm'),
    cancelText: t('core.common.cancel'),
    okType: 'danger',
    onOk: () => persist(rows.value.filter(row => !selected.has(row.operatorId))),
  })
}

// ── 折叠与定位（导入后展开并翻到对应页） ──
const collapsedGroups = ref(new Set<string>())
const toggleGroup = (operatorId: string) => {
  const next = new Set(collapsedGroups.value)
  if (next.has(operatorId)) {
    next.delete(operatorId)
  } else {
    next.add(operatorId)
  }
  collapsedGroups.value = next
}
const reveal = (operatorIds: string[]) => {
  operatorFilter.value = ''
  const next = new Set(collapsedGroups.value)
  for (const id of operatorIds) next.delete(id)
  collapsedGroups.value = next
  const importedIds = new Set(operatorIds)
  const firstImported = rows.value.findIndex(row => importedIds.has(row.operatorId))
  if (firstImported >= 0) {
    operatorPage.value = Math.floor(firstImported / OPERATOR_PAGE_SIZE) + 1
  }
}
defineExpose({ reveal })

watch(
  operatorFilter,
  () => {
    operatorPage.value = 1
  },
  { flush: 'sync' }
)
watch(
  () => filteredViews.value.length,
  length => {
    operatorPage.value = Math.min(
      operatorPage.value,
      Math.max(1, Math.ceil(length / OPERATOR_PAGE_SIZE))
    )
  }
)

// ── 目标改写：选档=写入/更新，清空=移除（elite 复用 setEliteLevel 的 0=null 口径） ──
const mutateRow = (operatorId: string, mutate: (rawGoals: unknown[]) => unknown[]) => {
  persist(
    rows.value.map(row =>
      row.operatorId === operatorId ? { ...row, rawGoals: mutate(row.rawGoals) } : row
    )
  )
}

const handleGoalChange = (
  operatorId: string,
  kind: CultivateGoalKind,
  targetId: string,
  event: unknown
) => {
  const level = Number(event)
  mutateRow(operatorId, raw => {
    if (kind === 'elite') return setEliteLevel(raw, level || null)
    if (kind === 'mastery') return setMasteryLevel(raw, targetId, level || null)
    return level
      ? upsertGoal(raw, { kind, targetId, toLevel: level })
      : removeGoal(raw, kind, targetId)
  })
}

// 已绑定但本次快照未携带专精/模组观测（森空岛拉取失败降级本地档案）：
// 目标保留、暂停刷取，须明确提示用户，而不是让「当前 ？」默默出现
const sklandDegraded = computed(
  () =>
    props.sklandBound && hasUnknownDimensionGoals(rows.value, props.cultivatePreview?.progressions)
)

const onImportBusy = (value: boolean) => {
  importing.value = value
  emit('busy', value)
}

// 目标行变化 → 防抖后请求需求预览（竞态守卫在父级加载器里）。
watch(rows, (nextRows, _previousRows, onCleanup) => {
  const loadPreview = () => void props.loadCultivatePreview(serializeCultivateTargets(nextRows))
  if (!nextRows.length) return loadPreview()
  const previewTimer = window.setTimeout(loadPreview, 600)
  onCleanup(() => window.clearTimeout(previewTimer))
})

onMounted(() => {
  void props.loadCultivatePreview(serializeCultivateTargets(rows.value))
})
</script>

<style scoped>
.cultivate-alert {
  margin-bottom: 12px;
}

.cultivate-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.cultivate-hint-inline {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: 0 0 6px;
}

/* 行尾 ? 说明按钮（可聚焦，对齐 PipelineRow 的 row-help 口径） */
.hint-help {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  padding: 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  cursor: help;
}

.hint-help:hover {
  color: var(--ant-color-primary);
}

.hint-help:focus-visible {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 1px;
}

/* 添加干员工具条 */
.cultivate-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.cultivate-toolbar .operator-picker {
  flex: 1 1 280px;
  min-width: 200px;
  max-width: 480px;
}

/* 批量操作条：搜索占余量，其余靠右 */
.cultivate-list-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 16px;
  margin-bottom: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.cultivate-search {
  flex: 1 1 200px;
  min-width: 160px;
  max-width: 320px;
}

.cultivate-module-toggle {
  margin-left: auto;
}

/* 双栏：左为目标卡片，右为材料预览 */
.cultivate-body {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-start;
}

.cultivate-side {
  flex: 1 1 340px;
  min-width: 0;
}

/* 预览面板跟随滚动（页面级滚动容器在 AppLayout） */
@media (min-width: 900px) {
  .cultivate-side {
    position: sticky;
    top: 16px;
  }
}

/* 一图流数据署名（CC BY-NC 4.0 授权条件，方案 §5.4/决策 3）；链接走系统浏览器 */
.data-source-note {
  margin-top: 12px;
  font-size: 12px;
}

/* 427 条长列表：全量渲染防 rc-virtual-list 混渲染，contain 防滚动链式带动整页
   （与 DepotMaintainPlanEditor 同款，PR1 下拉污染三根因的②③） */
.cultivate-editor :deep(.rc-virtual-list-holder) {
  overscroll-behavior: contain;
}
</style>

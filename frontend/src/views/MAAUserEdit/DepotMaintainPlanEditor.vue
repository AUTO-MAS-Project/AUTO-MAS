<template>
  <div class="depot-plan-editor">
    <a-alert v-if="itemOptionsError" :message="itemOptionsError" type="warning" show-icon />
    <div v-if="eventMode && activityLoading" class="activity-loading">
      <a-spin size="small" />
      <span>{{ t('eventDepotPreview.loading') }}</span>
    </div>
    <a-alert
      v-if="eventMode && activityError"
      :message="activityError"
      type="warning"
      show-icon
      class="takeover-alert"
    >
      <template #action>
        <a-button
          size="small"
          :loading="activityLoading"
          :disabled="loading"
          @click="emit('retryActivity')"
        >
          {{ t('eventDepotPreview.retry') }}
        </a-button>
      </template>
    </a-alert>
    <!-- 活动模式：当期可刷关卡逐行常驻，勾选即「本轮刷取」，无需增删条目 -->
    <template v-if="eventMode">
      <div v-if="eventRows.length" class="plan-scroll">
        <div class="plan-grid-header is-event">
          <span />
          <span>{{ t('eventDepotPreview.stageColumn') }}</span>
          <span>{{ t('edit.item') }}</span>
          <span>{{ t('edit.targetStock') }}</span>
          <span>
            <a-tooltip :title="stockColumnTitle">
              <span>{{ t('edit.stock') }}</span>
            </a-tooltip>
          </span>
        </div>
        <div class="plan-rows">
          <div
            v-for="row in eventRows"
            :key="row.identity"
            class="plan-row is-event"
            :class="{ 'is-skipped': !row.farmed }"
          >
            <span class="col-check">
              <a-checkbox
                :checked="row.farmed"
                :disabled="loading"
                :aria-label="t('eventDepotPreview.farmStage')"
                @change="toggleFarm(row, $event.target.checked)"
              />
            </span>
            <span class="event-stage-text" :title="stageTextOf(row)">
              <span class="stage-name">{{ row.stage.Display }}</span>
              <span class="stage-kind">{{ stageKindOf(row) }}</span>
            </span>
            <span class="event-item-text" :title="itemTextOf(row)">{{ itemTextOf(row) }}</span>
            <a-input-number
              :value="row.target"
              :disabled="loading"
              :min="1"
              :precision="0"
              :aria-label="t('edit.targetStock')"
              @change="setStageTarget(row, $event)"
            />
            <span class="stock-value">{{ eventStockOf(row) }}</span>
          </div>
        </div>
      </div>
      <a-empty
        v-else
        :description="
          eligibleStages.length ? t('edit.noStockKeepingPlans') : t('eventDepotPreview.noActivity')
        "
        :image-style="{ height: '48px' }"
      />
    </template>
    <template v-else>
      <div class="plan-actions">
        <a-space wrap>
          <a-dropdown :disabled="loading" :trigger="['click']">
            <a-button type="dashed" size="small" :disabled="loading">
              <template #icon><AppstoreAddOutlined /></template>
              {{ t('edit.addPreset') }}
              <DownOutlined />
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="all" @click="importPreset('all')">{{
                  t('edit.allPresets')
                }}</a-menu-item>
                <a-menu-divider />
                <a-menu-item
                  v-for="preset in DEPOT_MAINTAIN_PRESETS"
                  :key="preset.key"
                  @click="importPreset(preset.key)"
                >
                  {{ preset.label }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-button type="dashed" size="small" :disabled="loading" @click="addPlan">
            <template #icon><PlusOutlined /></template>
            {{ t('edit.addItem') }}
          </a-button>
          <a-popconfirm
            :title="t('edit.depotDeleteSelectedConfirm', { n: selectedRowKeys.length })"
            :ok-text="t('edit.ok')"
            :cancel-text="t('edit.cancel')"
            @confirm="removeSelectedPlans"
          >
            <a-button danger size="small" :disabled="loading || selectedRowKeys.length === 0">
              <template #icon><DeleteOutlined /></template>
              {{ t('edit.deleteSelected') }}
            </a-button>
          </a-popconfirm>
        </a-space>
      </div>
      <!-- 行顺序即 MAA 执行顺序：vuedraggable 拖拽排序（QueueItemManager 先例：
           a-table 不支持行拖拽，用可拖拽列表承载表格外观）。列对齐由 header 与
           行共用的 grid 模板保证，窄屏整块横向滚动等价原 :scroll="{ x: 780 }" -->
      <div v-if="plans.length" class="plan-scroll">
        <div class="plan-grid-header">
          <span />
          <span class="col-check">
            <a-checkbox
              :checked="allSelected"
              :indeterminate="someSelected"
              :disabled="loading"
              :aria-label="t('edit.selectPlanRows')"
              @change="toggleAll($event.target.checked)"
            />
          </span>
          <span>{{ t('edit.stage') }}</span>
          <span>{{ t('edit.item') }}</span>
          <span>{{ t('edit.targetStock') }}</span>
          <span>
            <a-tooltip :title="stockColumnTitle">
              <span>{{ t('edit.stock') }}</span>
            </a-tooltip>
          </span>
          <span />
        </div>
        <draggable
          v-model="plans"
          item-key="key"
          handle=".depot-drag-handle"
          :animation="200"
          ghost-class="depot-row-ghost"
          :disabled="loading"
          class="plan-rows"
          @end="savePlans"
        >
          <template #item="{ element: record, index }">
            <div class="plan-row" :class="{ 'row-selected': selectedKeys.has(record.key) }">
              <span
                class="depot-drag-handle"
                :title="t('edit.maaDepotDragSortHint')"
                :aria-label="t('edit.maaDepotDragSortHint')"
              >
                <span class="drag-dots" aria-hidden="true"></span>
              </span>
              <span class="col-check">
                <a-checkbox
                  :checked="selectedKeys.has(record.key)"
                  :disabled="loading"
                  :aria-label="t('edit.selectPlanRow')"
                  @change="toggleRow(record.key, $event.target.checked)"
                />
              </span>
              <a-select
                v-model:value="record.Stage"
                :options="stageOptionsFor(record)"
                :loading="isStageLoading(record)"
                :disabled="loading"
                allow-clear
                show-search
                option-filter-prop="label"
                :virtual="false"
                :get-popup-container="getPopupContainer"
                :list-height="popupListHeight"
                :popup-match-select-width="false"
                :placeholder="t('edit.pickStage')"
                @change="onStageChange(record)"
                @dropdown-visible-change="
                  (open: boolean) => open && record.DropId && loadStageCandidates(record.DropId)
                "
              />
              <a-select
                v-model:value="record.DropId"
                :options="itemOptions"
                :disabled="loading || itemOptionsLoading"
                :loading="itemOptionsLoading"
                allow-clear
                show-search
                option-filter-prop="label"
                :virtual="false"
                :get-popup-container="getPopupContainer"
                :list-height="popupListHeight"
                :placeholder="t('edit.pickItem')"
                @change="onItemChange(record)"
              />
              <a-input-number
                v-model:value="record.DropCount"
                :disabled="loading"
                :min="1"
                :precision="0"
                :aria-label="t('edit.targetStock')"
                @change="queueSave"
              />
              <span class="stock-value">{{ stockOf(record) }}</span>
              <span class="col-action">
                <!-- 键盘排序走上移/下移按钮（MFW 任务队列先例），拖拽手柄供鼠标 -->
                <a-button
                  type="text"
                  size="small"
                  :aria-label="t('edit.maaDepotMoveUp')"
                  :disabled="loading || index === 0"
                  @click="moveRow(index, -1)"
                >
                  <ArrowUpOutlined />
                </a-button>
                <a-button
                  type="text"
                  size="small"
                  :aria-label="t('edit.maaDepotMoveDown')"
                  :disabled="loading || index === plans.length - 1"
                  @click="moveRow(index, 1)"
                >
                  <ArrowDownOutlined />
                </a-button>
                <a-button
                  type="text"
                  danger
                  :aria-label="t('edit.deleteStockKeepingPlan')"
                  :disabled="loading"
                  @click="removePlan(record.key)"
                >
                  <DeleteOutlined />
                </a-button>
              </span>
            </div>
          </template>
        </draggable>
      </div>
      <a-empty
        v-else
        :description="t('edit.noStockKeepingPlans')"
        :image-style="{ height: '48px' }"
      />
    </template>
    <a-alert
      v-if="eventMode && !activityUnavailable && eligibleStages.length === 0 && plans.length"
      :message="t('eventDepotPreview.expiredHint')"
      type="warning"
      show-icon
    />
    <a-typography-link
      v-if="!eventMode"
      class="data-source-note"
      href="https://ark.yituliu.cn"
      target="_blank"
      rel="noreferrer"
      @click="handleExternalLink"
    >
      {{ t('edit.maaDataSourceYituliu') }}
    </a-typography-link>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { handleExternalLink } from '@/utils/openExternal'
import { computed, onMounted, watch } from 'vue'
import draggable from 'vuedraggable'
import {
  AppstoreAddOutlined,
  ArrowDownOutlined,
  ArrowUpOutlined,
  DeleteOutlined,
  DownOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import { DEPOT_MAINTAIN_PRESETS } from './depotMaintainPresets'
import {
  eventDepotItemId,
  eventDepotPlanIdentity,
  eventStageIdentity,
  getEventDepotStages,
  getEventOrundumStages,
  isOrundumStage,
} from './eventDepotMaintainPresets'
import { usePlanSelectPopup } from './usePlanSelectPopup'
import type { ActivityItem } from '@/types/home'
import type {
  DepotMaintainPlanEditorState,
  DepotMaintainPlanRow as DepotMaintainPlan,
} from './useDepotMaintainPlanEditor'

const { t } = useI18n()

const props = defineProps<{
  formData: any
  editor: DepotMaintainPlanEditorState
  loading: boolean
  stageOptions: SelectOption[]
  itemOptions: SelectOption[]
  itemOptionsLoading: boolean
  itemOptionsError: string
  /** 按物品缓存的关卡候选（含每理智效率，来自一图流数据层；[] 表示已加载但无候选） */
  stageCandidates: Record<string, SelectOption[]>
  /** 正在加载候选的物品 ID 列表 */
  stageCandidatesLoading: string[]
  /** 仓库库存映射（itemId → 数量，当前用户识别档案） */
  inventory: Record<string, number>
  /** 库存档案的最近识别时间（本地格式；空串=未识别） */
  depotInventoryTime: string
  /** 提供活动列表时，按当期可刷关卡逐行展示。 */
  activityStages?: ActivityItem[]
  activityLoading?: boolean
  activityError?: string
}>()

const emit = defineEmits<{ retryActivity: [] }>()

type SelectOption = { label: string; value: string; disabled?: boolean }

/** 活动模式的一行：当期关卡 + 该关已保存的勾选与目标 */
type EventRow = {
  identity: string
  type: 'material' | 'orundum'
  index: number
  stage: ActivityItem
  rock: boolean
  plan?: DepotMaintainPlan
  farmed: boolean
  target: number
}

const stockColumnTitle = computed(() =>
  props.depotInventoryTime
    ? t('edit.stockRecognizedAt', { time: props.depotInventoryTime })
    : t('edit.stock')
)

const eventMode = computed(() => props.activityStages !== undefined)
const eligibleStages = computed(() => [
  ...getEventDepotStages(props.activityStages ?? []),
  ...getEventOrundumStages(props.activityStages ?? []),
])
const activityUnavailable = computed(() => !!props.activityLoading || !!props.activityError)

const {
  plans,
  selectedRowKeys,
  savePlans,
  queueSave,
  loadStageCandidates,
  onItemChange,
  onStageChange,
  importPreset,
  ensureEventPlan,
  moveRow,
  addPlan,
  removePlan,
  removeSelectedPlans,
} = props.editor

onMounted(() => {
  if (eventMode.value) return
  // 面板重开时补查失败项；缓存与在途请求由页面统一复用。
  for (const itemId of new Set(plans.value.map(plan => plan.DropId).filter(Boolean))) {
    void loadStageCandidates(itemId)
  }
})

/** 当期关卡逐行常驻：未保存的行按预设默认值展示（默认全开）。 */
const eventRows = computed<EventRow[]>(() => {
  const saved = new Map(
    plans.value
      .filter(plan => plan.StageType !== 'all')
      .map(plan => [eventDepotPlanIdentity(plan), plan] as const)
  )
  const allRow = plans.value.find(plan => plan.StageType === 'all')
  const rows: EventRow[] = []
  const push = (type: EventRow['type'], stage: ActivityItem, index: number) => {
    const plan = saved.get(eventStageIdentity(type, index))
    const rock = isOrundumStage(stage)
    const preset = rock ? (allRow?.OrundumDropCount ?? 9999) : (allRow?.DropCount ?? 999)
    rows.push({
      identity: eventStageIdentity(type, index),
      type,
      index,
      stage,
      rock,
      plan,
      farmed: !plan?.Skip,
      target: plan ? (rock ? (plan.OrundumDropCount ?? plan.DropCount) : plan.DropCount) : preset,
    })
  }
  getEventDepotStages(props.activityStages ?? []).forEach((stage, i) =>
    push('material', stage, i + 1)
  )
  getEventOrundumStages(props.activityStages ?? []).forEach((stage, i) =>
    push('orundum', stage, i + 1)
  )
  return rows
})

// 没有 all 预设的旧配置：补齐当期每个可刷关卡的条目，否则它们不会进入 MAA 计划。
watch(
  () => [props.activityStages, props.activityLoading, props.activityError] as const,
  () => {
    if (!eventMode.value || props.loading || activityUnavailable.value) return
    if (!eligibleStages.value.length) return
    if (plans.value.some(plan => plan.StageType === 'all')) return
    let added = false
    for (const row of eventRows.value) {
      if (row.plan) continue
      ensureEventPlan({ StageType: row.type, StageIndex: row.index, DropCount: row.target })
      added = true
    }
    if (added) savePlans()
  },
  { immediate: true }
)

/** 关卡类别：搓玉关只有一处，不带序号；材料关按序号区分。 */
const stageKindOf = (row: EventRow) =>
  row.type === 'orundum'
    ? t('eventDepotPreview.orundumStage')
    : t('eventDepotPreview.stageIndex', { n: row.index })

const stageTextOf = (row: EventRow) => [row.stage.Display, stageKindOf(row)].join(' · ')

const itemTextOf = (row: EventRow) =>
  props.itemOptions.find(option => option.value === eventDepotItemId(row.stage))?.label ??
  row.stage.DropName

const eventStockOf = (row: EventRow) => props.inventory?.[eventDepotItemId(row.stage)] ?? '—'

/** 勾选状态即 Skip 标记：取消勾选不清空已保存的目标。 */
const toggleFarm = (row: EventRow, farmed: boolean) => {
  const plan = ensureEventPlan({
    StageType: row.type,
    StageIndex: row.index,
    DropCount: row.target,
  })
  if (farmed) delete plan.Skip
  else plan.Skip = true
  savePlans()
}

const setStageTarget = (row: EventRow, value: number | string | null) => {
  const next = Math.max(1, Math.trunc(Number(value) || 1))
  const plan = ensureEventPlan({ StageType: row.type, StageIndex: row.index, DropCount: next })
  // 搓玉关沿用 MAA 侧的固源岩目标字段，其余关卡写通用目标。
  if (row.rock && plan.OrundumDropCount !== undefined) plan.OrundumDropCount = next
  else plan.DropCount = next
  queueSave()
}

const selectedKeys = computed(() => new Set(selectedRowKeys.value))
const allSelected = computed(
  () => plans.value.length > 0 && selectedRowKeys.value.length === plans.value.length
)
const someSelected = computed(
  () => selectedRowKeys.value.length > 0 && selectedRowKeys.value.length < plans.value.length
)
const toggleRow = (key: number, checked: boolean) => {
  selectedRowKeys.value = checked
    ? [...selectedRowKeys.value, key]
    : selectedRowKeys.value.filter(selectedKey => selectedKey !== key)
}
const toggleAll = (checked: boolean) => {
  selectedRowKeys.value = checked ? plans.value.map(plan => plan.key) : []
}

// 行内关卡选项四态：
// - 未选物品 → 全量表（允许先选关卡）
// - 候选已加载且非空 → 只显示掉落该物品的关（按单件理智升序，后端截断 top-10）
// - 候选加载中（缓存无 key）→ 只保留当前值，绝不回退全量表——否则滚轮
//   浏览期间候选完成、列表从全量集突变为候选集，滚动位置与新内容错位
//   （表现为"被全量表里的关卡污染"）
// - 候选已加载但为空（请求失败/数据源确实无此物品）→ 保留当前值即可，
//   不回退全量表：让用户误选一个不掉该物品的关比空列表更糟
const stageOptionsFor = (record: DepotMaintainPlan): SelectOption[] => {
  if (!record.DropId) return props.stageOptions
  const candidates = props.stageCandidates?.[record.DropId]
  if (candidates === undefined) {
    const current = props.stageOptions.find(option => option.value === record.Stage)
    return current ? [current] : []
  }
  if (candidates.length === 0) {
    const current = props.stageOptions.find(option => option.value === record.Stage)
    return current ? [current] : []
  }
  // 已保存的关被截断在候选外：追加显示（全量表有则带名称，否则裸关码），
  // 绝不静默丢失已保存选择
  if (record.Stage && !candidates.some(option => option.value === record.Stage)) {
    const saved = props.stageOptions.find(option => option.value === record.Stage)
    return [...candidates, saved ?? { label: record.Stage, value: record.Stage }]
  }
  return candidates
}

const isStageLoading = (record: DepotMaintainPlan): boolean =>
  !!record.DropId && (props.stageCandidatesLoading ?? []).includes(record.DropId)

const stockOf = (record: DepotMaintainPlan): number | string =>
  record.DropId ? (props.inventory?.[record.DropId] ?? '—') : '—'

const { getPopupContainer, listHeight: popupListHeight } = usePlanSelectPopup()
</script>

<style scoped>
/* 浮层挂载基准：下拉浮层 absolute 定位相对本容器 */
.depot-plan-editor {
  position: relative;
}

/* 浮层滚轮隔离：候选列表滚到底（或不足一屏不可滚）时，滚轮事件会
   链式传播到主页面，页面整体滚走、下拉随容器移出视野——用户视角即
   "在下拉里滚滚轮被其他内容污染"。holder 恒为 overflow:auto 滚动容器，
   contain 切断向页面主滚动的传播链 */
.depot-plan-editor :deep(.rc-virtual-list-holder) {
  overscroll-behavior: contain;
}

.takeover-alert {
  margin-bottom: 12px;
}

.activity-loading {
  min-height: 64px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
}

.plan-actions {
  margin-bottom: 12px;
}

/* 表格式拖拽列表：表头与数据行共用一份 grid 列模板保证列对齐；
   窄屏整块横向滚动（min-width 等价原表格 :scroll="{ x: 780 }"） */
.plan-scroll {
  overflow-x: auto;
}

.plan-grid-header,
.plan-row {
  display: grid;
  grid-template-columns: 24px 32px minmax(0, 1fr) minmax(0, 1.3fr) 116px 88px 104px;
  gap: 8px;
  align-items: center;
  min-width: 816px;
}

/* 活动模式只有「勾选 / 关卡 / 材料 / 目标 / 库存」五列，关卡与材料为只读文本 */
.plan-grid-header.is-event,
.plan-row.is-event {
  grid-template-columns: 32px minmax(0, 1fr) minmax(0, 1.2fr) 116px 88px;
  min-width: 560px;
}

.plan-grid-header {
  padding: 4px 0 8px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.plan-rows {
  display: flex;
  flex-direction: column;
}

.plan-row {
  padding: 4px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.row-selected {
  background: var(--ant-color-fill-tertiary);
}

/* 材料是计划的只读信息；过长省略时靠 title 提示完整值 */
.event-item-text {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

/* 关卡列两级信息：关卡代号在前保证各行列头对齐，类别（第 n 个材料关 / 搓玉关）小字次要色随后 */
.event-stage-text {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.stage-kind {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.stage-name {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-weight: 500;
}

/* 未勾选的关卡降一级文字色，与勾选框一起表达「本轮不刷」 */
.plan-row.is-skipped .stage-name,
.plan-row.is-skipped .event-item-text {
  color: var(--ant-color-text-secondary);
  font-weight: 400;
}

.col-action {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 0;
}

/* 拖拽手柄：可见把手 + grab 光标，热区仅限手柄（行内控件不受影响） */
.depot-drag-handle {
  cursor: grab;
  padding: 6px 2px;
  color: var(--ant-color-text-quaternary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.depot-drag-handle:hover {
  color: var(--ant-color-text-secondary);
}

/* 拖拽进行中：光标转 grabbing（拖拽全程按住左键，active 即拖拽态） */
.depot-drag-handle:active {
  cursor: grabbing;
}

.drag-dots {
  display: inline-block;
  width: 8px;
  height: 14px;
  background-image: radial-gradient(circle, currentColor 1px, transparent 1.2px);
  background-size: 4px 4px;
}

/* 拖拽反馈只用一种：拖动中的行半透明（ghost），不叠底色高亮 */
.depot-row-ghost {
  opacity: 0.4;
}

/* 一图流数据署名（CC BY-NC 4.0 授权条件，方案 §5.4/决策 3）；链接走系统浏览器 */
.data-source-note {
  margin-top: 4px;
  font-size: 12px;
}

.stock-value {
  color: var(--ant-color-text-secondary, #888);
}

:deep(.ant-select),
:deep(.ant-input-number) {
  width: 100%;
}
</style>

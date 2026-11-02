<template>
  <div class="depot-plan-editor">
    <a-alert v-if="itemOptionsError" :message="itemOptionsError" type="warning" show-icon />
    <div class="plan-actions">
      <a-space wrap>
        <a-dropdown :disabled="loading" :trigger="['click']">
          <a-button type="dashed" size="small" :disabled="loading">
            <template #icon><AppstoreAddOutlined /></template>
            {{ t('core.edit.addPreset') }}
            <DownOutlined />
          </a-button>
          <template #overlay>
            <a-menu>
              <a-menu-item key="all" @click="importPreset('all')">{{
                t('core.edit.allPresets')
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
          {{ t('core.edit.addItem') }}
        </a-button>
        <a-popconfirm
          :title="t('core.edit.depotDeleteSelectedConfirm', { n: selectedRowKeys.length })"
          :ok-text="t('core.edit.ok')"
          :cancel-text="t('core.edit.cancel')"
          @confirm="removeSelectedPlans"
        >
          <a-button danger size="small" :disabled="loading || selectedRowKeys.length === 0">
            <template #icon><DeleteOutlined /></template>
            {{ t('core.edit.deleteSelected') }}
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
            :aria-label="t('core.edit.selectPlanRows')"
            @change="toggleAll($event.target.checked)"
          />
        </span>
        <span>{{ t('core.edit.stage') }}</span>
        <span>{{ t('core.edit.item') }}</span>
        <span>{{ t('core.edit.targetStock') }}</span>
        <span>
          <a-tooltip :title="stockColumnTitle">
            <span>{{ t('core.edit.stock') }}</span>
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
              :title="t('core.edit.maaDepotDragSortHint')"
              :aria-label="t('core.edit.maaDepotDragSortHint')"
            >
              <span class="drag-dots" aria-hidden="true"></span>
            </span>
            <span class="col-check">
              <a-checkbox
                :checked="selectedKeys.has(record.key)"
                :disabled="loading"
                :aria-label="t('core.edit.selectPlanRow')"
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
              :placeholder="t('core.edit.pickStage')"
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
              :placeholder="t('core.edit.pickItem')"
              @change="onItemChange(record)"
            />
            <a-input-number
              v-model:value="record.DropCount"
              :disabled="loading"
              :min="1"
              :precision="0"
              :aria-label="t('core.edit.targetStock')"
              @change="queueSave"
            />
            <span class="stock-value">{{ stockOf(record) }}</span>
            <span class="col-action">
              <!-- 键盘排序走上移/下移按钮（MFW 任务队列先例），拖拽手柄供鼠标 -->
              <a-button
                type="text"
                size="small"
                :aria-label="t('core.edit.maaDepotMoveUp')"
                :disabled="loading || index === 0"
                @click="moveRow(index, -1)"
              >
                <ArrowUpOutlined />
              </a-button>
              <a-button
                type="text"
                size="small"
                :aria-label="t('core.edit.maaDepotMoveDown')"
                :disabled="loading || index === plans.length - 1"
                @click="moveRow(index, 1)"
              >
                <ArrowDownOutlined />
              </a-button>
              <a-button
                type="text"
                danger
                :aria-label="t('core.edit.deleteStockKeepingPlan')"
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
    <NoData
      v-else
      :description="t('core.edit.noStockKeepingPlans')"
      :image-style="{ height: '48px' }"
    />
    <a-typography-link
      class="data-source-note"
      href="https://ark.yituliu.cn"
      target="_blank"
      rel="noreferrer"
      @click="handleExternalLink"
    >
      {{ t('core.edit.maaDataSourceYituliu') }}
    </a-typography-link>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { handleExternalLink } from '@/utils/openExternal'
import { computed, onMounted } from 'vue'
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
import { usePlanSelectPopup } from './usePlanSelectPopup'
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
}>()

type SelectOption = { label: string; value: string; disabled?: boolean }

const stockColumnTitle = computed(() =>
  props.depotInventoryTime
    ? t('core.edit.stockRecognizedAt', { time: props.depotInventoryTime })
    : t('core.edit.stock')
)

const {
  plans,
  selectedRowKeys,
  savePlans,
  queueSave,
  loadStageCandidates,
  onItemChange,
  onStageChange,
  importPreset,
  moveRow,
  addPlan,
  removePlan,
  removeSelectedPlans,
} = props.editor

onMounted(() => {
  // 面板重开时补查失败项；缓存与在途请求由页面统一复用。
  for (const itemId of new Set(plans.value.map(plan => plan.DropId).filter(Boolean))) {
    void loadStageCandidates(itemId)
  }
})

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

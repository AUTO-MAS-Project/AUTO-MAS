<template>
  <div class="depot-plan-editor">
    <!-- 养成接管提示：接管发生时本任务整条不注入（方案决策 20/28），与养成编辑器共用后端写入的提示字段 -->
    <a-alert
      v-if="formData.Data?.CultivateNotice"
      :message="formData.Data.CultivateNotice"
      type="warning"
      show-icon
      class="takeover-alert"
    />
    <a-alert v-if="itemOptionsError" :message="itemOptionsError" type="warning" show-icon />
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
          :title="`确定删除选中的 ${selectedRowKeys.length} 项库存保持计划吗？`"
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
    <a-table
      :columns="columns"
      :data-source="plans"
      :pagination="false"
      :row-selection="rowSelection"
      :scroll="{ x: 780 }"
      size="small"
    >
      <template #emptyText>{{ t('edit.noStockKeepingPlans') }}</template>
      <template #bodyCell="{ column, record }">
        <a-select
          v-if="column.key === 'stage'"
          :key="`${record.key}-stage`"
          v-model:value="record.Stage"
          :options="stageOptionsFor(record)"
          :loading="isStageLoading(record)"
          :disabled="loading"
          allow-clear
          show-search
          option-filter-prop="label"
          :virtual="false"
          :get-popup-container="getPopupContainer"
          :popup-match-select-width="false"
          :placeholder="t('edit.pickStage')"
          @change="savePlans"
        />
        <a-select
          v-else-if="column.key === 'item'"
          :key="`${record.key}-item`"
          v-model:value="record.DropId"
          :options="itemOptions"
          :disabled="loading || itemOptionsLoading"
          :loading="itemOptionsLoading"
          allow-clear
          show-search
          option-filter-prop="label"
          :virtual="false"
          :get-popup-container="getPopupContainer"
          :placeholder="t('edit.pickItem')"
          @change="onItemChange(record)"
        />
        <a-input-number
          v-else-if="column.key === 'count'"
          v-model:value="record.DropCount"
          :disabled="loading"
          :min="1"
          :precision="0"
          @change="savePlans"
        />
        <span v-else-if="column.key === 'stock'" class="stock-value">{{
          stockOf(record)
        }}</span>
        <a-button
          v-else-if="column.key === 'action'"
          type="text"
          danger
          :aria-label="t('edit.deleteStockKeepingPlan')"
          :disabled="loading"
          @click="removePlan(record.key)"
        >
          <DeleteOutlined />
        </a-button>
      </template>
    </a-table>
    <a-typography-link
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
import { computed, ref, watch } from 'vue'
import {
  AppstoreAddOutlined,
  DeleteOutlined,
  DownOutlined,
  PlusOutlined,
} from '@ant-design/icons-vue'
import type { TableColumnsType } from 'ant-design-vue'
import {
  DEPOT_MAINTAIN_PRESETS,
  getDepotMaintainPreset,
  type DepotMaintainPlan as SavedDepotMaintainPlan,
  type DepotMaintainPresetKey,
} from './depotMaintainPresets'

const { t } = useI18n()

type SelectOption = { label: string; value: string }
type DepotMaintainPlan = SavedDepotMaintainPlan & { key: number }

const props = defineProps<{
  formData: any
  loading: boolean
  stageOptions: SelectOption[]
  itemOptions: SelectOption[]
  itemOptionsLoading: boolean
  itemOptionsError: string
  /** 按物品缓存的关卡候选（含每理智效率，来自一图流数据层；[] 表示已加载但无候选） */
  stageCandidates: Record<string, SelectOption[]>
  /** 正在加载候选的物品 ID 列表 */
  stageCandidatesLoading: string[]
  /** 仓库库存映射（itemId → 数量，安装级） */
  inventory: Record<string, number>
  /** 按需加载某物品的关卡候选（父级负责请求与缓存） */
  loadStageCandidates: (itemId: string) => Promise<void>
}>()

const emit = defineEmits<{ save: [key: string, value: any] }>()

const columns: TableColumnsType = [
  { title: t('edit.stage'), key: 'stage', width: '26%' },
  { title: t('edit.item'), key: 'item', width: '34%' },
  { title: t('edit.targetStock'), key: 'count', width: 120 },
  { title: t('edit.stock'), key: 'stock', width: 90 },
  { title: '', key: 'action', width: 56, align: 'center' },
]

const plans = ref<DepotMaintainPlan[]>([])
const selectedRowKeys = ref<number[]>([])
let nextKey = 0
const rowSelection = computed(() => ({
  selectedRowKeys: selectedRowKeys.value,
  getCheckboxProps: () => ({ disabled: props.loading }),
  onChange: (keys: (string | number)[]) => {
    selectedRowKeys.value = keys.filter((key): key is number => typeof key === 'number')
  },
}))

watch(
  () => props.formData.Task.DepotMaintainPlans,
  value => {
    // 自身 savePlans 的回声：formData 原样写回后会再触发本 watch。若此时
    // 重建 plans，所有行 key 递增导致整表重挂载，打开中的下拉浮层被拆毁
    // 重建（表现为下拉内容闪变/污染），因此与当前内容一致时直接跳过
    const normalized = JSON.stringify(
      plans.value.map(({ Stage, DropId, DropCount }) => ({ Stage, DropId, DropCount }))
    )
    if (value === normalized) return
    selectedRowKeys.value = []
    try {
      const parsed = JSON.parse(value || '[]')
      plans.value = Array.isArray(parsed)
        ? parsed
            .filter(
              plan =>
                typeof plan?.Stage === 'string' &&
                typeof plan?.DropId === 'string' &&
                typeof plan?.DropCount === 'number'
            )
            .map(plan => ({ key: nextKey++, ...plan }))
        : []
    } catch {
      plans.value = []
    }
    // 已配置条目的关卡候选预加载，保证过滤与动态预设可用
    for (const itemId of new Set(plans.value.map(plan => plan.DropId).filter(Boolean))) {
      props.loadStageCandidates(itemId)
    }
  },
  { immediate: true }
)

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
  props.inventory?.[record.DropId] ?? '—'

// 下拉浮层挂到编辑器根容器：既不被表格滚动容器裁剪（挂 td 会被 overflow
// 裁掉显示不全），又随页面滚动移动（挂 body 会驻留原地）
const getPopupContainer = (trigger: HTMLElement): HTMLElement =>
  trigger.closest<HTMLElement>('.depot-plan-editor') ?? document.body

const onItemChange = async (record: DepotMaintainPlan) => {
  const itemId = record.DropId
  // 换物品后旧关卡大概率不再掉该材料，清空待重选（防提交无效组合）；
  // 清空物品同样清掉残留关卡，避免显示物品为空的脏组合
  record.Stage = ''
  if (!itemId) {
    savePlans()
    return
  }
  await props.loadStageCandidates(itemId)
  // await 期间物品可能又被换了：只为仍是当前物品的请求自动填最优关
  if (record.DropId === itemId && !record.Stage) {
    const best = props.stageCandidates?.[itemId]?.[0]
    if (best) record.Stage = best.value
  }
  savePlans()
}

const savePlans = () => {
  emit(
    'save',
    'Task.DepotMaintainPlans',
    JSON.stringify(
      plans.value.map(({ Stage, DropId, DropCount }) => ({ Stage, DropId, DropCount }))
    )
  )
}

const addPlan = () => {
  plans.value.push({ key: nextKey++, Stage: '', DropId: '', DropCount: 1 })
  savePlans()
}

const importPreset = async (preset: DepotMaintainPresetKey) => {
  selectedRowKeys.value = []
  const imported = getDepotMaintainPreset(preset).map(plan => ({
    key: nextKey++,
    ...plan,
  }))
  // 动态预设：先确保候选加载完成，再用当前最优关替代预设里的硬编码关卡
  await Promise.all(
    [...new Set(imported.map(plan => plan.DropId).filter(Boolean))].map(itemId =>
      props.loadStageCandidates(itemId)
    )
  )
  for (const plan of imported) {
    const best = props.stageCandidates?.[plan.DropId]?.[0]
    if (best) plan.Stage = best.value
  }
  plans.value.push(...imported)
  savePlans()
}

const removePlan = (key: number) => {
  selectedRowKeys.value = selectedRowKeys.value.filter(selectedKey => selectedKey !== key)
  plans.value = plans.value.filter(plan => plan.key !== key)
  savePlans()
}

const removeSelectedPlans = () => {
  plans.value = plans.value.filter(plan => !selectedRowKeys.value.includes(plan.key))
  selectedRowKeys.value = []
  savePlans()
}
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

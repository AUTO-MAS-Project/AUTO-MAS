<template>
  <div class="cultivate-editor">
    <!-- 接管提示：后端注入时写入，非空表示养成接管中、库存保持暂停 -->
    <a-alert
      v-if="formData.Data?.CultivateNotice"
      :message="formData.Data.CultivateNotice"
      type="warning"
      show-icon
      class="cultivate-alert"
    />
    <a-alert
      :message="t('edit.maaCultivateRecognitionHint')"
      type="info"
      show-icon
      class="cultivate-alert"
    />
    <a-alert
      v-if="operatorOptionsError"
      :message="operatorOptionsError"
      type="warning"
      show-icon
      class="cultivate-alert"
    />

    <a-form-item class="cultivate-picker">
      <template #label>
        <LabelWithHint
          :text="t('edit.maaCultivatePickOperators')"
          :hint="t('edit.maaCultivatePickOperatorsHint')"
        />
      </template>
      <a-select
        :value="null"
        :options="pickerOptions"
        :loading="operatorOptionsLoading"
        :disabled="loading || operatorOptionsLoading || availableOperatorOptions.length === 0"
        :placeholder="operatorPlaceholder"
        show-search
        :filter-option="false"
        :virtual="false"
        :get-popup-container="getPopupContainer"
        @search="handleOperatorSearch"
        @change="handleAddOperator"
      />
    </a-form-item>

    <div v-if="rows.length" class="cultivate-rows">
      <div v-for="row in rows" :key="row.operatorId" class="cultivate-row">
        <span class="cultivate-name" :title="operatorName(row.operatorId)">{{ operatorName(row.operatorId) }}</span>
        <a-select
          :value="row.toLevel"
          :options="eliteLevelOptions"
          :disabled="loading"
          class="cultivate-level"
          @change="handleLevelChange(row.operatorId, $event)"
        />
        <a-button
          size="small"
          danger
          :disabled="loading"
          @click="handleRemoveOperator(row.operatorId)"
        >
          {{ t('edit.maaCultivateRemove') }}
        </a-button>
      </div>
    </div>
    <a-empty
      v-else
      :description="t('edit.maaCultivateEmpty')"
      :image-style="{ height: '48px' }"
    />
    <div class="cultivate-skips">
      <a-checkbox
        :checked="formData.Task?.CultivateSkipDuringActivity"
        :disabled="loading"
        @change="emit('save', 'Task.CultivateSkipDuringActivity', $event.target.checked)"
      >
        {{ t('edit.maaCultivateSkipActivity') }}
      </a-checkbox>
      <a-checkbox
        :checked="formData.Task?.CultivateSkipDuringResourceCollection"
        :disabled="loading"
        @change="emit('save', 'Task.CultivateSkipDuringResourceCollection', $event.target.checked)"
      >
        {{ t('edit.maaCultivateSkipResource') }}
      </a-checkbox>
    </div>
    <div v-if="rows.length" class="cultivate-preview">
      <div class="preview-header">
        <span class="preview-title">{{ t('edit.maaCultivatePreviewTitle') }}</span>
        <a-tag v-if="cultivatePreviewLoading" color="processing">
          {{ t('edit.maaCultivatePreviewComputing') }}
        </a-tag>
      </div>
      <a-alert
        v-if="cultivatePreviewError"
        :message="cultivatePreviewError"
        type="error"
        show-icon
        class="cultivate-alert"
      />
      <a-alert
        v-if="cultivatePreview && (!cultivatePreview.hasProgression || !cultivatePreview.hasInventory)"
        :message="availabilityNotice"
        type="info"
        show-icon
        class="cultivate-alert"
      />
      <template v-if="cultivatePreview">
        <div v-if="unobtainableText" class="preview-unobtainable">
          {{ t('edit.maaCultivatePreviewUnobtainable') }}：{{ unobtainableText }}
        </div>
        <div class="preview-heading">{{ t('edit.maaCultivatePreviewStageHeading') }}</div>
        <div
          v-for="entry in cultivatePreview.stages"
          :key="`s-${entry.itemId}-${entry.stage}`"
          class="preview-line"
        >
          <span class="preview-stage">{{ entry.stage }}</span>
          <span class="preview-item">{{ entry.name || itemName(entry.itemId) }}</span>
          <span class="preview-count">× {{ entry.count }}</span>
          <span v-if="entry.expectedSanity != null" class="preview-sanity">
            ≈ {{ entry.expectedSanity }} {{ t('edit.maaCultivateSanityUnit') }}
          </span>
        </div>
        <div v-if="!cultivatePreview.stages.length" class="preview-empty">
          {{ t('edit.maaCultivatePreviewNone') }}
        </div>
        <div
          v-if="cultivatePreview.totalExpectedSanity != null"
          class="preview-line preview-total"
        >
          <span class="preview-item">
            {{ t('edit.maaCultivatePreviewSanityTotal') }}
          </span>
          <span class="preview-sanity">
            ≈ {{ cultivatePreview.totalExpectedSanity }}
            {{ t('edit.maaCultivateSanityUnit') }}
          </span>
        </div>
        <div class="preview-heading">{{ t('edit.maaCultivatePreviewDemandHeading') }}</div>
        <div
          v-for="item in cultivatePreview.demands"
          :key="`d-${item.itemId}`"
          class="preview-line"
        >
          <span class="preview-item">{{ item.name || itemName(item.itemId) }}</span>
          <span class="preview-count">× {{ item.count }}</span>
        </div>
      </template>
    </div>
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
import type { CultivatePreviewOut } from '@/api'
import { handleExternalLink } from '@/utils/openExternal'
import { computed, onMounted, ref, watch } from 'vue'
import LabelWithHint from './LabelWithHint.vue'
import {
  appendOperator,
  parseCultivateTargets,
  removeOperator,
  serializeCultivateTargets,
  updateLevel,
  type CultivateTargetRow,
} from './cultivateTargets'

const { t } = useI18n()

type SelectOption = { label: string; value: string }

const props = defineProps<{
  formData: any
  loading: boolean
  /** 干员目录（一图流全量表；[] 表示已加载但为空） */
  operatorOptions: SelectOption[]
  operatorOptionsLoading: boolean
  operatorOptionsError: string
  /** 物品目录（MAA item_index，供预览材料名显示） */
  itemOptions: SelectOption[]
  /** 养成需求预览（后端纯计算结果） */
  cultivatePreview: CultivatePreviewOut | null
  cultivatePreviewLoading: boolean
  cultivatePreviewError: string
  /** 目标行变化时触发（父级负责请求与竞态守卫） */
  loadCultivatePreview: (targetsJson: string) => Promise<void>
}>()

const emit = defineEmits<{ save: [key: string, value: any] }>()

const rows = ref<CultivateTargetRow[]>([])
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

const persist = (next: CultivateTargetRow[]) => {
  rows.value = next
  lastEmitted = serializeCultivateTargets(next)
  emit('save', 'Task.CultivateTargets', lastEmitted)
}

const handleAddOperator = (operatorId: string) => {
  if (!operatorId) return
  operatorSearch.value = ''
  persist(appendOperator(rows.value, operatorId))
}

// 搜索驱动 + 截断：427 条全量目录参与搜索，列表只显示前 10 条（对齐关卡候选的
// top-10 口径）；内置过滤关闭（filter-option false），过滤由 pickerOptions 完成
const operatorSearch = ref('')
const handleOperatorSearch = (value: string) => {
  operatorSearch.value = value
}
const pickerOptions = computed(() => {
  const text = operatorSearch.value.trim().toLowerCase()
  const matched = text
    ? availableOperatorOptions.value.filter(
        option =>
          option.label.toLowerCase().includes(text) ||
          option.value.toLowerCase().includes(text)
      )
    : availableOperatorOptions.value
  return matched.slice(0, 10)
})

const handleRemoveOperator = (operatorId: string) => {
  persist(removeOperator(rows.value, operatorId))
}

const handleLevelChange = (operatorId: string, toLevel: unknown) => {
  persist(updateLevel(rows.value, operatorId, Number(toLevel)))
}

// 已添加的干员不再出现在选择器里（Set 查找，目录 427 条 × 目标行）
const selectedOperatorIds = computed(
  () => new Set(rows.value.map(row => row.operatorId))
)
const availableOperatorOptions = computed(() =>
  props.operatorOptions.filter(option => !selectedOperatorIds.value.has(option.value))
)

const operatorPlaceholder = computed(() =>
  availableOperatorOptions.value.length
    ? t('edit.maaCultivatePickOperators')
    : t('edit.maaCultivateNoOperators')
)

const operatorLabelById = computed(
  () => new Map(props.operatorOptions.map(option => [option.value, option.label]))
)
const operatorName = (operatorId: string) =>
  operatorLabelById.value.get(operatorId) ?? operatorId

const eliteLevelOptions = computed(() => [
  { label: t('edit.maaCultivateElite1'), value: 1 },
  { label: t('edit.maaCultivateElite2'), value: 2 },
])

// 目标行变化 → 防抖后请求需求预览（竞态守卫在父级加载器里）。
// 组件随 PipelineRow 展开销毁重建：重进页面/重新展开时 rows 不再变化，
// 不会触发 watch，须在挂载时对已保存的目标主动拉一次预览
let previewTimer: number | undefined
watch(rows, nextRows => {
  if (previewTimer) window.clearTimeout(previewTimer)
  previewTimer = window.setTimeout(() => {
    if (!nextRows.length) return
    props.loadCultivatePreview(serializeCultivateTargets(nextRows))
  }, 600)
})

onMounted(() => {
  if (rows.value.length) {
    props.loadCultivatePreview(serializeCultivateTargets(rows.value))
  }
})

const unobtainableText = computed(() =>
  (props.cultivatePreview?.unobtainable ?? [])
    .map((item: { itemId: string; name?: string }) => item.name || itemName(item.itemId))
    .join('、')
)

const itemLabelById = computed(
  () => new Map(props.itemOptions.map(option => [option.value, option.label]))
)
const itemName = (itemId: string) => itemLabelById.value.get(itemId) ?? itemId

// 干员/仓库识别档案缺失时预览按精0+空库存估算：明示估算口径，避免把偏大
// 的需求数字当成精确值（方案 §4.3 预览须注明"以识别后为准"）
const availabilityNotice = computed(() => {
  if (!props.cultivatePreview) return ''
  const missing: string[] = []
  if (!props.cultivatePreview.hasProgression)
    missing.push(t('edit.maaCultivateMissingProgression'))
  if (!props.cultivatePreview.hasInventory)
    missing.push(t('edit.maaCultivateMissingInventory'))
  if (!missing.length) return ''
  return `${t('edit.maaCultivateEstimatePrefix')}${missing.join(
    t('edit.maaCultivateEstimateJoin')
  )}${t('edit.maaCultivateEstimateSuffix')}`
})

// 下拉浮层挂编辑器根容器：挂 body 时页面滚动浮层驻留原地不跟随（与
// DepotMaintainPlanEditor 同款，PR1 下拉污染三根因的①）
const getPopupContainer = (trigger: HTMLElement): HTMLElement =>
  trigger.closest<HTMLElement>('.cultivate-editor') ?? document.body
</script>

<style scoped>
.cultivate-alert {
  margin-bottom: 12px;
}

.cultivate-picker {
  margin-bottom: 12px;
}

.cultivate-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cultivate-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cultivate-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--ant-color-text);
}

.cultivate-level {
  width: 120px;
  flex-shrink: 0;
}

/* 父组件 TaskPipelineSection 有 :deep(.ant-select){width:100%}，会穿透把档位
   下拉顶成通栏、把干员名挤成 0 宽（特异性同为 0-2-0、胜负看加载顺序）——
   这里加一层选择器提高特异性压回来，行内布局才是 名字|档位|移除 三段 */
.cultivate-row .cultivate-level {
  width: 120px;
  flex-shrink: 0;
}

/* 一图流数据署名（CC BY-NC 4.0 授权条件，方案 §5.4/决策 3）；链接走系统浏览器 */
.data-source-note {
  margin-top: 8px;
  font-size: 12px;
}

/* 427 条长列表：全量渲染防 rc-virtual-list 混渲染，contain 防滚动链式带动整页
   （与 DepotMaintainPlanEditor 同款，PR1 下拉污染三根因的②③） */
.cultivate-editor :deep(.rc-virtual-list-holder) {
  overscroll-behavior: contain;
}

.cultivate-skips {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}

.cultivate-preview {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.preview-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.preview-title {
  font-weight: 600;
  color: var(--ant-color-text);
}

.preview-heading {
  margin: 8px 0 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.preview-line {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 2px 0;
  font-size: 13px;
  color: var(--ant-color-text);
}

.preview-stage {
  min-width: 88px;
  color: var(--ant-color-text-secondary);
}

.preview-item {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.preview-count {
  color: var(--ant-color-text-secondary);
}

.preview-sanity {
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.preview-total {
  margin-top: 4px;
  font-weight: 600;
}

.preview-unobtainable {
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--ant-color-warning);
}

.preview-empty {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>

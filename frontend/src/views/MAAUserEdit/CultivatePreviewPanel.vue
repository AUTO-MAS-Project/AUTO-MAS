<template>
  <div class="cultivate-preview" :aria-busy="loading">
    <a-tabs default-active-key="stages" size="small">
      <template #rightExtra>
        <span
          class="preview-loading"
          role="status"
          :aria-label="loading ? t('edit.maaCultivatePreviewComputing') : undefined"
        >
          <a-spin v-if="loading" size="small" />
        </span>
      </template>
      <a-tab-pane
        v-for="tab in ['stages', 'demands']"
        :key="tab"
        :tab="
          t(
            tab === 'stages'
              ? 'edit.maaCultivatePreviewTitle'
              : 'edit.maaCultivatePreviewDemandHeading'
          )
        "
      >
        <a-alert v-if="error" :message="error" type="error" show-icon class="cultivate-alert" />
        <a-alert
          v-if="preview && (!preview.hasProgression || !preview.hasInventory)"
          :message="availabilityNotice"
          type="info"
          show-icon
          class="cultivate-alert"
        />
        <div v-if="unobtainableText" class="preview-unobtainable">
          {{ t('edit.maaCultivatePreviewUnobtainable') }}：{{ unobtainableText }}
        </div>
        <template v-if="preview && tab === 'stages'">
          <div class="preview-heading">{{ t('edit.maaCultivatePreviewStageHeading') }}</div>
          <!-- 刷取计划四列：材料名称 → 关卡 → 数量 → 理智（固定列宽对齐） -->
          <div
            v-for="entry in preview.stages"
            :key="`s-${entry.itemId}-${entry.stage}`"
            class="preview-line"
          >
            <span class="preview-stage">{{ entry.stage }}</span>
            <span class="preview-item" :title="entry.name || itemName(entry.itemId)">
              {{ entry.name || itemName(entry.itemId) }}
            </span>
            <span class="preview-count">× {{ entry.count }}</span>
            <template v-if="entry.expectedSanity != null">
              <span class="preview-sanity-sym">≈</span>
              <span class="preview-sanity">
                {{ entry.expectedSanity }} {{ t('edit.maaCultivateSanityUnit') }}
              </span>
            </template>
            <template v-else>
              <span class="preview-sanity-sym" />
              <span class="preview-sanity" />
            </template>
          </div>
          <div v-if="!preview.stages.length" class="preview-empty">
            {{ t('edit.maaCultivatePreviewNone') }}
          </div>
          <div v-if="preview.totalExpectedSanity != null" class="preview-line preview-total">
            <span class="preview-item">
              {{ t('edit.maaCultivatePreviewSanityTotal') }}
            </span>
            <span class="preview-sanity">
              ≈ {{ preview.totalExpectedSanity }}
              {{ t('edit.maaCultivateSanityUnit') }}
            </span>
          </div>
        </template>
        <template v-else-if="preview">
          <div v-for="item in preview.demands" :key="`d-${item.itemId}`" class="preview-line">
            <span class="preview-item" :title="item.name || itemName(item.itemId)">
              {{ item.name || itemName(item.itemId) }}
            </span>
            <span class="preview-count">× {{ item.count }}</span>
          </div>
          <div v-if="!preview.demands.length" class="preview-empty">
            {{ t('edit.maaCultivatePreviewDemandNone') }}
          </div>
        </template>
      </a-tab-pane>
    </a-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { CultivatePreviewOut } from '@/api'

const props = defineProps<{
  preview: CultivatePreviewOut | null
  loading: boolean
  error: string
  itemOptions: Array<{ label: string; value: string }>
}>()
const { t } = useI18n()

const unobtainableText = computed(() =>
  (props.preview?.unobtainable ?? [])
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
  if (!props.preview) return ''
  const missing: string[] = []
  if (!props.preview.hasProgression) missing.push(t('edit.maaCultivateMissingProgression'))
  if (!props.preview.hasInventory) missing.push(t('edit.maaCultivateMissingInventory'))
  if (!missing.length) return ''
  return `${t('edit.maaCultivateEstimatePrefix')}${missing.join(
    t('edit.maaCultivateEstimateJoin')
  )}${t('edit.maaCultivateEstimateSuffix')}`
})
</script>

<style scoped>
.cultivate-alert {
  margin-bottom: 12px;
}

.cultivate-preview {
  padding: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.preview-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
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

/* 刷取计划四列固定宽：名称占余量，关卡/数量/理智成列（含空理智占位保持对齐） */
.preview-stage {
  width: 64px;
  flex-shrink: 0;
  color: var(--ant-color-text-secondary);
}

.preview-line .preview-count {
  width: 64px;
  flex-shrink: 0;
  text-align: left;
}

/* ≈ 符号与理智值各自成列（空值行留空占位保持对齐） */
.preview-sanity-sym {
  width: 20px;
  flex-shrink: 0;
  text-align: left;
  color: var(--ant-color-text-secondary);
}

.preview-line .preview-sanity {
  width: 96px;
  flex-shrink: 0;
  text-align: right;
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

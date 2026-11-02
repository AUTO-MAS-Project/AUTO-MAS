<template>
  <div class="cultivate-preview" :aria-busy="loading">
    <!-- 理智合计与材料时间统一展示在页面总览。 -->
    <div class="preview-head">
      <span class="preview-title">{{ t('core.edit.maaCultivatePreviewTitle') }}</span>
      <a-spin
        v-if="loading"
        size="small"
        :aria-label="t('core.edit.maaCultivatePreviewComputing')"
      />
    </div>
    <a-tabs default-active-key="stages" size="small">
      <a-tab-pane
        v-for="tab in ['stages', 'demands']"
        :key="tab"
        :tab="
          t(
            tab === 'stages'
              ? 'core.edit.maaCultivatePreviewStageHeading'
              : 'core.edit.maaCultivatePreviewDemandHeading'
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
          {{ t('core.edit.maaCultivatePreviewUnobtainable') }}：{{ unobtainableText }}
        </div>
        <template v-if="preview && tab === 'stages'">
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
                {{ entry.expectedSanity }} {{ t('core.edit.maaCultivateSanityUnit') }}
              </span>
            </template>
            <template v-else>
              <span class="preview-sanity-sym" />
              <span class="preview-sanity" />
            </template>
          </div>
          <NoData
            v-if="!preview.stages.length"
            class="preview-empty"
            :description="t('core.edit.maaCultivatePreviewNone')"
          />
        </template>
        <template v-else-if="preview">
          <div v-for="item in preview.demands" :key="`d-${item.itemId}`" class="preview-line">
            <span class="preview-item" :title="item.name || itemName(item.itemId)">
              {{ item.name || itemName(item.itemId) }}
            </span>
            <span class="preview-count">× {{ item.count }}</span>
          </div>
          <NoData
            v-if="!preview.demands.length"
            class="preview-empty"
            :description="t('core.edit.maaCultivatePreviewDemandNone')"
          />
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
  if (!props.preview.hasProgression) missing.push(t('core.edit.maaCultivateMissingProgression'))
  if (!props.preview.hasInventory) missing.push(t('core.edit.maaCultivateMissingInventory'))
  if (!missing.length) return ''
  return `${t('core.edit.maaCultivateEstimatePrefix')}${missing.join(
    t('core.edit.maaCultivateEstimateJoin')
  )}${t('core.edit.maaCultivateEstimateSuffix')}`
})
</script>

<style scoped>
.cultivate-alert {
  margin-bottom: 12px;
}

.cultivate-preview {
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.preview-head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-bottom: 4px;
}

.preview-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.preview-head .ant-spin {
  align-self: center;
  margin-left: auto;
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

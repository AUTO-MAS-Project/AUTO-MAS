<template>
  <div class="form-section">
    <a-row :gutter="24" align="middle">
      <a-col :xs="24" :sm="10">
        <a-form-item name="IfAutoCollect">
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.maaEndAutoCollectEnabled')"
              :hint="t('edit.maaEndAutoCollectEnabledHint')"
              variant="form"
            />
          </template>
          <a-switch :checked="enabled" :disabled="loading" @change="handleEnabledChange" />
        </a-form-item>
      </a-col>
      <a-col v-if="enabled" :xs="24" :sm="14">
        <a-form-item name="AutoCollectMode">
          <template #label>
            <FieldLabelWithHint
              :text="t('edit.maaEndAutoCollectMode')"
              :hint="modeHint"
              variant="form"
            />
          </template>
          <a-select
            :value="mode"
            :options="modeOptions"
            :disabled="loading"
            @change="handleModeChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item v-if="enabled">
      <a-alert type="info" show-icon :message="t('edit.maaEndCollectInventoryHint')" />
    </a-form-item>

    <a-spin v-if="enabled" :spinning="optionsLoading" class="collect-options">
      <a-alert
        v-if="!optionsLoading && !groups.length"
        type="warning"
        show-icon
        :message="t('edit.maaEndAutoCollectOptionsUnavailable')"
      />
      <div class="route-panel-list">
        <div v-for="panel in groups" :key="panel.value" class="route-panel">
          <div class="route-panel-header">
            <span class="route-panel-name">{{
              [panel.regionLabel, panel.label].filter(Boolean).join(' · ')
            }}</span>
            <span class="route-panel-count">{{
              t('edit.maaEndRouteSelectedCount', {
                n: panelValues(panel).length,
                m: panel.options.length,
              })
            }}</span>
            <span class="route-panel-actions">
              <a-button
                type="link"
                size="small"
                :disabled="controlsDisabled"
                @click="
                  applyValues(
                    panel,
                    panel.options.map(option => String(option.value))
                  )
                "
                >{{ t('edit.maaEndRouteSelectAll') }}</a-button
              >
              <a-button
                type="link"
                size="small"
                :disabled="controlsDisabled"
                @click="applyValues(panel, [])"
                >{{ t('edit.maaEndRouteClear') }}</a-button
              >
            </span>
          </div>
          <div class="route-card-grid">
            <a-checkbox
              v-for="option in panel.options"
              :key="String(option.value)"
              class="route-card"
              :checked="selectedValues(panel).includes(String(option.value))"
              :disabled="controlsDisabled"
              @change="toggleRoute(panel, String(option.value))"
            >
              <span class="route-card-label">{{ option.label }}</span>
            </a-checkbox>
          </div>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaEndAutoCollectGroup } from '@/api'
import type { MaaEndTaskConfig } from '@/types/script'
import {
  MAAEND_AUTO_COLLECT_MODE_OPTIONS,
  type MaaEndAutoCollectMode,
} from '@/utils/maaEndProtocolSpace'

const props = defineProps<{
  formData: {
    Task?: Partial<
      Pick<MaaEndTaskConfig, 'IfAutoCollect' | 'AutoCollectRoutes' | 'AutoCollectCommonRoutes'>
    > & { AutoCollectMode?: string }
  }
  loading: boolean
  optionsLoading: boolean
  groups: MaaEndAutoCollectGroup[]
}>()
const emit = defineEmits<{ save: [key: string, value: boolean | string | string[]] }>()
const { t } = useI18n()
const enabled = computed(() => Boolean(props.formData.Task?.IfAutoCollect))
const mode = computed(() => props.formData.Task?.AutoCollectMode ?? 'Distributed')
const controlsDisabled = computed(() => props.loading || props.optionsLoading)
const modeOptions = computed(() =>
  MAAEND_AUTO_COLLECT_MODE_OPTIONS.map(option => ({
    value: option.value,
    label: t(option.labelKey),
  }))
)
const modeHint = computed(() =>
  mode.value === 'Concentrated'
    ? t('edit.maaEndAutoCollectModeConcentratedHint')
    : t('edit.maaEndAutoCollectModeDistributedHint')
)

const selectedValues = (panel: MaaEndAutoCollectGroup): string[] =>
  props.formData.Task?.[panel.configKey] ??
  props.groups
    .filter(group => group.configKey === panel.configKey)
    .flatMap(group => group.defaultCases)
const panelValues = (panel: MaaEndAutoCollectGroup) =>
  panel.options
    .map(option => String(option.value))
    .filter(value => selectedValues(panel).includes(value))

const applyValues = (panel: MaaEndAutoCollectGroup, values: string[]) => {
  if (controlsDisabled.value) return
  // 只替换当前分类的选择；保留其他地区及暂时不可见的旧选项。
  const panelSet = new Set(panel.options.map(option => String(option.value)))
  const next = [
    ...new Set([...selectedValues(panel).filter(value => !panelSet.has(value)), ...values]),
  ]
  emit('save', `Task.${panel.configKey}`, next)
}
const toggleRoute = (panel: MaaEndAutoCollectGroup, value: string) => {
  const values = panelValues(panel)
  applyValues(
    panel,
    values.includes(value) ? values.filter(item => item !== value) : [...values, value]
  )
}
const handleEnabledChange = (value: boolean) => emit('save', 'Task.IfAutoCollect', value)
const handleModeChange = (value: MaaEndAutoCollectMode) =>
  emit('save', 'Task.AutoCollectMode', value)
</script>

<style scoped>
.route-panel-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
  width: 100%;
}

.route-panel {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 12px 16px 16px;
}

.collect-options {
  display: block;
  min-height: 160px;
}

.route-panel-header {
  flex-wrap: wrap;
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.route-panel-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.route-panel-count {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.route-panel-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
}

.route-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 180px), 1fr));
  gap: 8px;
  width: 100%;
}

.route-card {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 44px;
  padding: 6px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  transition: background-color 0.2s ease;
}

.route-card:hover:not(.ant-checkbox-wrapper-disabled) {
  background: var(--ant-color-fill-quaternary);
}

.route-card:focus-within {
  outline: 2px solid var(--ant-color-primary);
  outline-offset: -2px;
}

.route-card.ant-checkbox-wrapper-disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.route-card-label {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>

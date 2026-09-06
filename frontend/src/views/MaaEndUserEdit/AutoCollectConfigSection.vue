<template>
  <div class="form-section">
    <a-row :gutter="24" align="middle">
      <a-col :span="6">
        <a-form-item name="IfAutoCollect">
          <template #label>
            <span class="form-label">
              {{ t('edit.maaEndAutoCollectEnabled') }}
              <a-tooltip :title="t('edit.maaEndAutoCollectEnabledHint')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-switch v-model:checked="enabled" :disabled="loading" @change="handleEnabledChange" />
        </a-form-item>
      </a-col>
      <a-col v-if="enabled" :span="8">
        <a-form-item name="AutoCollectMode">
          <template #label>
            <span class="form-label">
              {{ t('edit.maaEndAutoCollectMode') }}
              <a-tooltip :title="modeHint">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-select
            v-model:value="mode"
            :options="modeOptions"
            :disabled="loading"
            size="large"
            @change="handleModeChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <template v-if="enabled">
      <a-form-item :label="t('edit.maaEndAutoCollectRoutes')">
        <div class="route-panel-list">
          <div v-for="panel in regionPanels" :key="panel.key" class="route-panel">
            <div class="route-panel-header">
              <span class="route-panel-name">{{ panel.label }}</span>
              <span class="route-panel-count">
                {{
                  t('edit.maaEndRouteSelectedCount', {
                    n: panelSelectedCount(panel),
                    m: panel.options.length,
                  })
                }}
              </span>
              <span class="route-panel-actions">
                <a-button
                  type="link"
                  size="small"
                  :disabled="loading"
                  @click="handleSelectAll(panel)"
                >
                  {{ t('edit.maaEndRouteSelectAll') }}
                </a-button>
                <a-button
                  type="link"
                  size="small"
                  :disabled="loading"
                  @click="handleClear(panel)"
                >
                  {{ t('edit.maaEndRouteClear') }}
                </a-button>
              </span>
            </div>
            <div class="route-card-grid">
              <button
                v-for="option in panel.options"
                :key="option.value"
                type="button"
                class="route-card"
                :class="{ selected: isRouteSelected(option.value) }"
                :disabled="loading"
                :aria-pressed="isRouteSelected(option.value)"
                @click="toggleRoute(panel, option.value)"
              >
                <span class="route-card-label">{{ option.label }}</span>
                <CheckCircleFilled v-if="isRouteSelected(option.value)" class="route-card-check" />
              </button>
            </div>
          </div>
        </div>
      </a-form-item>

      <a-form-item>
        <div class="route-panel-list">
          <div class="route-panel">
            <div class="route-panel-header">
              <span class="route-panel-name">{{ t('edit.maaEndAutoCollectCommonRoutes') }}</span>
              <span class="route-panel-count">
                {{
                  t('edit.maaEndRouteSelectedCount', {
                    n: commonSelectedCount,
                    m: commonRouteOptions.length,
                  })
                }}
              </span>
              <span class="route-panel-actions">
                <a-button
                  type="link"
                  size="small"
                  :disabled="loading"
                  @click="handleCommonSelectAll"
                >
                  {{ t('edit.maaEndRouteSelectAll') }}
                </a-button>
                <a-button
                  type="link"
                  size="small"
                  :disabled="loading"
                  @click="handleCommonClear"
                >
                  {{ t('edit.maaEndRouteClear') }}
                </a-button>
              </span>
            </div>
            <div class="route-card-grid">
              <button
                v-for="option in commonRouteOptions"
                :key="option.value"
                type="button"
                class="route-card"
                :class="{ selected: isCommonRouteSelected(option.value) }"
                :disabled="loading"
                :aria-pressed="isCommonRouteSelected(option.value)"
                @click="toggleCommonRoute(option.value)"
              >
                <span class="route-card-label">{{ option.label }}</span>
                <CheckCircleFilled
                  v-if="isCommonRouteSelected(option.value)"
                  class="route-card-check"
                />
              </button>
            </div>
          </div>
        </div>
      </a-form-item>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleFilled, QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS,
  MAAEND_AUTO_COLLECT_MODE_OPTIONS,
  MAAEND_AUTO_COLLECT_ROUTE_OPTIONS,
  MAAEND_AUTO_COLLECT_ROUTE_REGIONS,
  type MaaEndAutoCollectCommonRoute,
  type MaaEndAutoCollectMode,
  type MaaEndAutoCollectRegionKey,
  type MaaEndAutoCollectRoute,
} from '@/utils/maaEndProtocolSpace'

const { t } = useI18n()

const props = defineProps<{
  formData: any
  loading: boolean
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
}>()

const normalizeRoutes = <T extends string>(
  value: unknown,
  options: readonly { value: T }[]
): T[] => {
  if (!Array.isArray(value)) return options.map(option => option.value)
  const allowed = new Set(options.map(option => option.value))
  return value.filter((item): item is T => typeof item === 'string' && allowed.has(item as T))
}

const enabled = ref(Boolean(props.formData.Task?.IfAutoCollect))
const mode = ref<MaaEndAutoCollectMode>(
  props.formData.Task?.AutoCollectMode === 'Concentrated' ? 'Concentrated' : 'Distributed'
)
const routes = ref<MaaEndAutoCollectRoute[]>(
  normalizeRoutes(props.formData.Task?.AutoCollectRoutes, MAAEND_AUTO_COLLECT_ROUTE_OPTIONS)
)
const commonRoutes = ref<MaaEndAutoCollectCommonRoute[]>(
  normalizeRoutes(
    props.formData.Task?.AutoCollectCommonRoutes,
    MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS
  )
)

const modeOptions = computed(() =>
  MAAEND_AUTO_COLLECT_MODE_OPTIONS.map(option => ({
    value: option.value,
    label: t(option.labelKey),
  }))
)
const routeOptions = computed(() =>
  MAAEND_AUTO_COLLECT_ROUTE_OPTIONS.map(option => ({
    value: option.value,
    label: t(option.labelKey),
    regionKey: option.regionKey,
  }))
)
const commonRouteOptions = computed(() =>
  MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS.map(option => ({
    value: option.value,
    label: t(option.labelKey),
  }))
)
const modeHint = computed(() =>
  mode.value === 'Concentrated'
    ? t('edit.maaEndAutoCollectModeConcentratedHint')
    : t('edit.maaEndAutoCollectModeDistributedHint')
)

interface RegionPanel {
  key: MaaEndAutoCollectRegionKey
  label: string
  options: Array<{ value: MaaEndAutoCollectRoute; label: string }>
}

const regionPanels = computed<RegionPanel[]>(() =>
  MAAEND_AUTO_COLLECT_ROUTE_REGIONS.map(regionKey => ({
    key: regionKey,
    label: t(regionKey),
    options: routeOptions.value.filter(option => option.regionKey === regionKey),
  }))
)

const panelValues = (panel: RegionPanel) =>
  panel.options.filter(option => routes.value.includes(option.value)).map(option => option.value)

const panelSelectedCount = (panel: RegionPanel) => panelValues(panel).length

const commonSelectedCount = computed(
  () =>
    commonRouteOptions.value.filter(option => commonRoutes.value.includes(option.value)).length
)

// 区域勾选结果与其余区域已选合并后按选项源顺序重组，保证保存的始终是完整有序数组
const applyRegionValues = (panel: RegionPanel, values: Array<string | number>) => {
  const regionValueSet = new Set<string>(panel.options.map(option => option.value))
  const nextSet = new Set<string>([
    ...routes.value.filter(value => !regionValueSet.has(value)),
    ...values.map(String),
  ])
  routes.value = MAAEND_AUTO_COLLECT_ROUTE_OPTIONS.map(option => option.value).filter(value =>
    nextSet.has(value)
  )
  emit('save', 'Task.AutoCollectRoutes', routes.value)
}

const isRouteSelected = (value: MaaEndAutoCollectRoute) => routes.value.includes(value)

const isCommonRouteSelected = (value: MaaEndAutoCollectCommonRoute) =>
  commonRoutes.value.includes(value)

const toggleRoute = (panel: RegionPanel, value: MaaEndAutoCollectRoute) => {
  const current = panelValues(panel)
  const next = current.includes(value)
    ? current.filter(item => item !== value)
    : [...current, value]
  applyRegionValues(panel, next)
}

const toggleCommonRoute = (value: MaaEndAutoCollectCommonRoute) => {
  const next = commonRoutes.value.includes(value)
    ? commonRoutes.value.filter(item => item !== value)
    : [...commonRoutes.value, value]
  applyCommonRoutes(next)
}

const handleSelectAll = (panel: RegionPanel) => {
  applyRegionValues(
    panel,
    panel.options.map(option => option.value)
  )
}

const handleClear = (panel: RegionPanel) => {
  applyRegionValues(panel, [])
}

const applyCommonRoutes = (values: MaaEndAutoCollectCommonRoute[]) => {
  const nextSet = new Set<string>(values)
  commonRoutes.value = MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS.map(option =>
    option.value
  ).filter(value => nextSet.has(value))
  emit('save', 'Task.AutoCollectCommonRoutes', commonRoutes.value)
}

const handleCommonSelectAll = () => {
  applyCommonRoutes(commonRouteOptions.value.map(option => option.value))
}

const handleCommonClear = () => {
  applyCommonRoutes([])
}

watch(
  () => props.formData.Task?.IfAutoCollect,
  value => {
    enabled.value = Boolean(value)
  }
)

watch(
  () => props.formData.Task?.AutoCollectMode,
  value => {
    mode.value = value === 'Concentrated' ? 'Concentrated' : 'Distributed'
  }
)

watch(
  () => props.formData.Task?.AutoCollectRoutes,
  value => {
    routes.value = normalizeRoutes(value, MAAEND_AUTO_COLLECT_ROUTE_OPTIONS)
  },
  { deep: true }
)

watch(
  () => props.formData.Task?.AutoCollectCommonRoutes,
  value => {
    commonRoutes.value = normalizeRoutes(value, MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS)
  },
  { deep: true }
)

const handleEnabledChange = (value: boolean) => {
  enabled.value = value
  emit('save', 'Task.IfAutoCollect', value)
}

const handleModeChange = (value: MaaEndAutoCollectMode) => {
  mode.value = value
  emit('save', 'Task.AutoCollectMode', value)
}
</script>

<style scoped>
.form-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

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

.route-panel-header {
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
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 8px;
  width: 100%;
}

.route-card {
  position: relative;
  display: flex;
  align-items: center;
  min-height: 40px;
  padding: 8px 34px 8px 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
  font-size: 13px;
  line-height: 1.4;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}

.route-card:hover:not(:disabled) {
  border-color: var(--ant-color-primary-hover);
}

.route-card.selected {
  border-color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.route-card:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.route-card-label {
  min-width: 0;
}

.route-card-check {
  position: absolute;
  right: 10px;
  color: var(--ant-color-primary);
  font-size: 15px;
}
</style>

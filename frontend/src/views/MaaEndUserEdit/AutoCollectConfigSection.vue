<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.maaEndAutoCollectConfig') }}</h3>
    </div>

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
          <a-switch
            v-model:checked="enabled"
            :disabled="loading"
            @change="handleEnabledChange"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <template v-if="enabled">
      <a-row :gutter="24">
        <a-col :span="8">
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
              @change="handleModeChange"
            />
          </a-form-item>
        </a-col>
      </a-row>

      <a-row :gutter="24">
        <a-col :span="12">
          <a-form-item :label="t('edit.maaEndAutoCollectRoutes')">
            <a-checkbox-group
              v-model:value="routes"
              class="route-checkbox-group"
              :disabled="loading"
              @change="handleRoutesChange"
            >
              <a-checkbox
                v-for="option in routeOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-checkbox>
            </a-checkbox-group>
          </a-form-item>
        </a-col>

        <a-col :span="12">
          <a-form-item :label="t('edit.maaEndAutoCollectCommonRoutes')">
            <a-checkbox-group
              v-model:value="commonRoutes"
              class="route-checkbox-group"
              :disabled="loading"
              @change="handleCommonRoutesChange"
            >
              <a-checkbox
                v-for="option in commonRouteOptions"
                :key="option.value"
                :value="option.value"
              >
                {{ option.label }}
              </a-checkbox>
            </a-checkbox-group>
          </a-form-item>
        </a-col>
      </a-row>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS,
  MAAEND_AUTO_COLLECT_MODE_OPTIONS,
  MAAEND_AUTO_COLLECT_ROUTE_OPTIONS,
  type MaaEndAutoCollectCommonRoute,
  type MaaEndAutoCollectMode,
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

const handleRoutesChange = (value: Array<string | number>) => {
  routes.value = normalizeRoutes(value, MAAEND_AUTO_COLLECT_ROUTE_OPTIONS)
  emit('save', 'Task.AutoCollectRoutes', routes.value)
}

const handleCommonRoutesChange = (value: Array<string | number>) => {
  commonRoutes.value = normalizeRoutes(value, MAAEND_AUTO_COLLECT_COMMON_ROUTE_OPTIONS)
  emit('save', 'Task.AutoCollectCommonRoutes', commonRoutes.value)
}
</script>

<style scoped>
.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

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

.route-checkbox-group {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px 16px;
  width: 100%;
}
</style>

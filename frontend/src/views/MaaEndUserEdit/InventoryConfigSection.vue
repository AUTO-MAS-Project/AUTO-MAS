<template>
  <a-space direction="vertical" size="middle" class="inventory-section">
    <div v-if="optionsLoading" class="inventory-loading"><a-spin /></div>
    <a-alert
      v-else-if="!inventory"
      type="warning"
      show-icon
      :message="t('edit.maaEndImsUnavailable')"
    >
      <template #action
        ><a-button @click="emit('reload')">{{ t('edit.maaEndImsReload') }}</a-button></template
      >
    </a-alert>
    <template v-else>
      <a-alert
        v-if="targets === null || unknownTargets.length"
        type="error"
        show-icon
        :message="t('edit.maaEndImsInvalidTargets')"
      >
        <template #action>
          <a-button danger :disabled="disabled" @click="repairTargets">
            {{ t(targets === null ? 'edit.maaEndImsResetInvalid' : 'edit.maaEndImsRemoveUnknown') }}
          </a-button>
        </template>
      </a-alert>
      <div class="inventory-toolbar">
        <a-input
          v-model:value="search"
          :placeholder="t('edit.maaEndImsSearch')"
          :aria-label="t('edit.maaEndImsSearch')"
          allow-clear
          class="material-search"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
        <a-checkbox v-model:checked="plannedOnly">
          {{ t('edit.maaEndImsPlannedOnly') }}
        </a-checkbox>
      </div>
      <div class="inventory-summary">
        <span>{{ t('edit.maaEndImsPlannedCount', { n: planned.length }) }}</span>
        <span>{{ t('edit.maaEndImsTargetHint') }}</span>
      </div>
      <a-tabs v-model:active-key="activeCategory" class="inventory-tabs">
        <a-tab-pane v-for="category in categories" :key="category.key">
          <template #tab>
            {{ t(category.label) }}
            <span class="category-count">{{ category.rows.length }}</span>
          </template>
          <a-table
            :data-source="filterRows(category.rows)"
            :columns="columns"
            row-key="value"
            :pagination="false"
            size="middle"
          >
            <template #bodyCell="{ column, record }">
              <template v-if="column.key === 'target'">
                <a-input-number
                  class="inventory-target"
                  :value="targets?.[record.value] ?? '0'"
                  string-mode
                  :min="'0'"
                  :max="'9007199254740991'"
                  :precision="0"
                  :disabled="disabled || targets === null"
                  :aria-label="`${record.label} ${t('edit.maaEndImsTarget')}`"
                  @change="setTarget(record.value, $event)"
                />
              </template>
              <template v-else-if="column.key === 'participation'">
                <a-badge
                  :color="
                    isInventoryTargetActive(targets?.[record.value])
                      ? 'var(--ant-color-primary)'
                      : 'var(--ant-color-text-quaternary)'
                  "
                  :text="
                    t(
                      isInventoryTargetActive(targets?.[record.value])
                        ? 'edit.maaEndImsIncluded'
                        : 'edit.maaEndImsExcluded'
                    )
                  "
                />
              </template>
            </template>
            <template #emptyText
              ><a-empty
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                :description="t('edit.maaEndImsNoMatches')"
            /></template>
          </a-table>
        </a-tab-pane>
      </a-tabs>
      <div class="inventory-preferences">
        <a-row :gutter="[24, 16]">
          <a-col :xs="24" :sm="12">
            <a-form-item :label="t('edit.maaEndImsClaimMode')">
              <a-select
                :value="formData.Task.ProtocolSpaceObtainModeClaim"
                :options="inventory.claimModes"
                :disabled="disabled"
                @change="saveClaimMode"
              />
            </a-form-item>
          </a-col>
          <a-col :xs="24" :sm="12">
            <a-form-item :label="t('edit.maaEndImsMedication')">
              <a-select
                :value="formData.Task.IfAutoUseSpMedication ? 'use' : 'skip'"
                :options="medicationOptions"
                :aria-label="t('edit.maaEndImsMedication')"
                :disabled="disabled"
                @change="saveMedication"
              />
            </a-form-item>
          </a-col>
        </a-row>
      </div>
    </template>
  </a-space>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { SearchOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { Empty, Modal } from 'ant-design-vue'
import type { MaaEndInventoryOptions } from '@/api'
import { readInventoryTargets, isInventoryTargetActive } from '@/views/MaaEndUserEdit/inventoryPlan'
import { INVENTORY_CATEGORIES, inventoryCategoryFor } from './inventoryCategories'
import { MAAEND_INVENTORY_TARGET_DEFAULTS } from './userDefaults'

const props = defineProps<{
  formData: {
    Info: { IfQuickConfig: boolean; SanityStrategy: string }
    Task: {
      SupplyPlanLimits: string
      ProtocolSpaceObtainModeClaim: string
      IfSanity: boolean
      IfAutoUseSpMedication: boolean
    }
  }
  inventory: MaaEndInventoryOptions | null
  loading: boolean
  optionsLoading: boolean
}>()
const emit = defineEmits<{
  save: [key: string, value: string | boolean]
  reload: []
}>()
const { t } = useI18n()
const disabled = computed(() => props.loading || !props.formData.Info.IfQuickConfig)
const overrides = computed(() => readInventoryTargets(props.formData.Task.SupplyPlanLimits))
const targets = computed(() =>
  overrides.value === null ? null : { ...MAAEND_INVENTORY_TARGET_DEFAULTS, ...overrides.value }
)
const rows = computed(() =>
  (props.inventory?.inputs ?? []).map(item => ({ value: item.value ?? '', label: item.label }))
)
const planned = computed(() =>
  rows.value.filter(item => isInventoryTargetActive(targets.value?.[item.value]))
)
const unknownTargets = computed(() =>
  Object.keys(overrides.value ?? {}).filter(key => !rows.value.some(item => item.value === key))
)
const search = ref('')
const plannedOnly = ref(false)
const categories = computed(() =>
  INVENTORY_CATEGORIES.map(category => ({
    ...category,
    rows: rows.value.filter(item => inventoryCategoryFor(item.value) === category.key),
  })).filter(category => category.rows.length)
)
const activeCategory = ref('experience')
watch(
  categories,
  groups => {
    if (!groups.some(group => group.key === activeCategory.value)) {
      activeCategory.value = groups[0]?.key ?? 'experience'
    }
  },
  { immediate: true }
)
const filterRows = (items: typeof rows.value) => {
  const query = search.value.trim().toLocaleLowerCase()
  return items.filter(
    item =>
      item.label.toLocaleLowerCase().includes(query) &&
      (!plannedOnly.value || isInventoryTargetActive(targets.value?.[item.value]))
  )
}
const columns = computed(() => [
  { title: t('edit.maaEndImsMaterial'), dataIndex: 'label', key: 'label' },
  { title: t('edit.maaEndImsTarget'), key: 'target', width: 160 },
  { title: t('edit.maaEndImsParticipation'), key: 'participation', width: 120 },
])
const medicationOptions = computed(() => [
  { label: t('edit.maaEndImsMedicationUse'), value: 'use' },
  { label: t('edit.maaEndImsMedicationSkip'), value: 'skip' },
])

function setTarget(key: string, quantity: string | number | null) {
  if (disabled.value || targets.value === null) return
  const value = String(quantity ?? '0')
  if (!/^\d+$/.test(value)) return
  props.formData.Task.SupplyPlanLimits = JSON.stringify({ ...overrides.value, [key]: value })
  emit('save', 'Task.SupplyPlanLimits', props.formData.Task.SupplyPlanLimits)
}

function saveClaimMode(value: string) {
  props.formData.Task.ProtocolSpaceObtainModeClaim = value
  emit('save', 'Task.ProtocolSpaceObtainModeClaim', value)
}

function saveMedication(value: string) {
  if (disabled.value) return
  const enabled = value === 'use'
  props.formData.Task.IfAutoUseSpMedication = enabled
  emit('save', 'Task.IfAutoUseSpMedication', enabled)
}

function repairTargets() {
  const save = () => {
    const known = Object.fromEntries(
      Object.entries(overrides.value ?? {}).filter(([key]) =>
        rows.value.some(item => item.value === key)
      )
    )
    props.formData.Task.SupplyPlanLimits = JSON.stringify(known)
    emit('save', 'Task.SupplyPlanLimits', props.formData.Task.SupplyPlanLimits)
  }
  if (targets.value !== null) {
    save()
    return
  }
  Modal.confirm({
    title: t('edit.maaEndImsResetInvalid'),
    content: t('edit.maaEndImsResetHint'),
    okType: 'danger',
    okText: t('edit.maaEndImsResetInvalid'),
    cancelText: t('edit.cancel'),
    onOk: save,
  })
}
</script>

<style scoped>
.inventory-section {
  width: 100%;
}
.inventory-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  justify-content: space-between;
  flex-wrap: wrap;
}
.category-count {
  margin-inline-start: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.material-search {
  width: 240px;
  max-width: 100%;
}
.inventory-summary {
  display: flex;
  gap: 8px 24px;
  flex-wrap: wrap;
  justify-content: space-between;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
.inventory-preferences :deep(.ant-form-item) {
  margin-bottom: 0;
}
.inventory-target {
  width: 100%;
}
.inventory-loading {
  min-height: 160px;
  display: grid;
  place-items: center;
}
</style>

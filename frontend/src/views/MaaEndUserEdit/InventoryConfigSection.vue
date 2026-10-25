<template>
  <a-space direction="vertical" size="middle" class="inventory-section">
    <a-alert
      :type="active ? 'info' : 'warning'"
      show-icon
      :message="t(active ? 'edit.maaEndImsActiveHint' : 'edit.maaEndImsInactiveHint')"
    />
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
      <a-typography-paragraph>{{ inventory.description }}</a-typography-paragraph>
      <a-flex align="center" justify="space-between" wrap="wrap" gap="small">
        <span>{{ t('edit.maaEndImsPlannedCount', { n: planned.length }) }}</span>
        <a-button
          :disabled="disabled || !planned.length || targets === null || unknownTargets.length > 0"
          @click="usePlan"
        >
          {{ t('edit.maaEndImsUsePlan') }}
        </a-button>
      </a-flex>
      <a-descriptions v-if="planned.length" size="small" :column="2" bordered>
        <a-descriptions-item v-for="item in planned" :key="item.value" :label="item.label">
          {{ targets?.[item.value] }}
        </a-descriptions-item>
      </a-descriptions>
      <a-empty
        v-else
        :description="t('edit.maaEndImsEmpty')"
        :image="Empty.PRESENTED_IMAGE_SIMPLE"
      />
      <a-row :gutter="24">
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
            <a-switch
              v-model:checked="formData.Task.IfAutoUseSpMedication"
              :disabled="disabled"
              @change="
                emit('save', 'Task.IfAutoUseSpMedication', formData.Task.IfAutoUseSpMedication)
              "
            />
          </a-form-item>
        </a-col>
      </a-row>
      <a-table
        :data-source="rows"
        :columns="columns"
        row-key="value"
        :pagination="false"
        size="small"
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
            {{
              t(
                isInventoryTargetActive(targets?.[record.value])
                  ? 'edit.maaEndImsIncluded'
                  : 'edit.maaEndImsExcluded'
              )
            }}
          </template>
        </template>
      </a-table>
    </template>
  </a-space>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Empty, Modal } from 'ant-design-vue'
import type { MaaEndInventoryOptions } from '@/api'
import { readInventoryTargets, isInventoryTargetActive } from '@/views/MaaEndUserEdit/inventoryPlan'

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
  saveBatch: [changes: Array<{ key: string; value: string | boolean }>]
  reload: []
}>()
const { t } = useI18n()
const disabled = computed(() => props.loading || !props.formData.Info.IfQuickConfig)
const active = computed(
  () => props.formData.Info.SanityStrategy === 'Inventory' && props.formData.Task.IfSanity
)
const targets = computed(() => readInventoryTargets(props.formData.Task.SupplyPlanLimits))
const rows = computed(() =>
  (props.inventory?.inputs ?? []).map(item => ({ value: item.value ?? '', label: item.label }))
)
const planned = computed(() =>
  rows.value.filter(item => isInventoryTargetActive(targets.value?.[item.value]))
)
const unknownTargets = computed(() =>
  Object.keys(targets.value ?? {}).filter(key => !rows.value.some(item => item.value === key))
)
const columns = computed(() => [
  { title: t('edit.maaEndImsMaterial'), dataIndex: 'label', key: 'label' },
  { title: t('edit.maaEndImsTarget'), key: 'target', width: 180 },
  { title: t('edit.maaEndImsParticipation'), key: 'participation', width: 120 },
])

function setTarget(key: string, quantity: string | number | null) {
  if (disabled.value || targets.value === null) return
  const value = String(quantity ?? '0')
  if (!/^\d+$/.test(value)) return
  props.formData.Task.SupplyPlanLimits = JSON.stringify({ ...targets.value, [key]: value })
  emit('save', 'Task.SupplyPlanLimits', props.formData.Task.SupplyPlanLimits)
}

function saveClaimMode(value: string) {
  props.formData.Task.ProtocolSpaceObtainModeClaim = value
  emit('save', 'Task.ProtocolSpaceObtainModeClaim', value)
}

function usePlan() {
  props.formData.Info.SanityStrategy = 'Inventory'
  props.formData.Task.IfSanity = true
  emit('saveBatch', [
    { key: 'Info.SanityStrategy', value: 'Inventory' },
    { key: 'Task.IfSanity', value: true },
  ])
}

function repairTargets() {
  const save = () => {
    const known = Object.fromEntries(
      Object.entries(targets.value ?? {}).filter(([key]) =>
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
.inventory-target {
  width: 100%;
}
.inventory-loading {
  min-height: 160px;
  display: grid;
  place-items: center;
}
</style>

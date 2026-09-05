<template>
  <div>
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
      :scroll="{ x: 680 }"
      size="small"
    >
      <template #emptyText>{{ t('edit.noStockKeepingPlans') }}</template>
      <template #bodyCell="{ column, record }">
        <a-select
          v-if="column.key === 'stage'"
          v-model:value="record.Stage"
          :options="stageOptions"
          :disabled="loading"
          allow-clear
          show-search
          option-filter-prop="label"
          :placeholder="t('edit.pickStage')"
          @change="savePlans"
        />
        <a-select
          v-else-if="column.key === 'item'"
          v-model:value="record.DropId"
          :options="itemOptions"
          :disabled="loading || itemOptionsLoading"
          :loading="itemOptionsLoading"
          allow-clear
          show-search
          option-filter-prop="label"
          :placeholder="t('edit.pickItem')"
          @change="savePlans"
        />
        <a-input-number
          v-else-if="column.key === 'count'"
          v-model:value="record.DropCount"
          :disabled="loading"
          :min="1"
          :precision="0"
          @change="savePlans"
        />
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
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
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
}>()

const emit = defineEmits<{ save: [key: string, value: any] }>()

const columns: TableColumnsType = [
  { title: t('edit.stage'), key: 'stage', width: '28%' },
  { title: t('edit.item'), key: 'item', width: '38%' },
  { title: t('edit.targetStock'), key: 'count', width: 140 },
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
  },
  { immediate: true }
)

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

const importPreset = (preset: DepotMaintainPresetKey) => {
  selectedRowKeys.value = []
  plans.value.push(...getDepotMaintainPreset(preset).map(plan => ({ key: nextKey++, ...plan })))
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
.plan-actions {
  margin-bottom: 12px;
}

:deep(.ant-select),
:deep(.ant-input-number) {
  width: 100%;
}
</style>

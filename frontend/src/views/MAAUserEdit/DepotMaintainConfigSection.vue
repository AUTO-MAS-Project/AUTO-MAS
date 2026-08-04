<template>
  <div class="form-section">
    <div class="section-header">
      <h3>库存保持</h3>
      <a-space>
        <span>启用</span>
        <a-switch
          :checked="formData.Task.IfDepotMaintain"
          :disabled="loading"
          @change="handleEnabledChange"
        />
      </a-space>
    </div>

    <template v-if="formData.Task.IfDepotMaintain">
      <a-alert v-if="itemOptionsError" :message="itemOptionsError" type="warning" show-icon />
      <div class="plan-actions">
        <a-space wrap>
          <a-dropdown :disabled="loading" :trigger="['click']">
            <a-button type="dashed" :disabled="loading">
              <template #icon><AppstoreAddOutlined /></template>
              添加预设
              <DownOutlined />
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="all" @click="importPreset('all')">全部预设</a-menu-item>
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
          <a-button type="dashed" :disabled="loading" @click="addPlan">
            <template #icon><PlusOutlined /></template>
            添加物品
          </a-button>
          <a-popconfirm
            :title="`确定删除选中的 ${selectedRowKeys.length} 项库存保持计划吗？`"
            ok-text="确定"
            cancel-text="取消"
            @confirm="removeSelectedPlans"
          >
            <a-button danger :disabled="loading || selectedRowKeys.length === 0">
              <template #icon><DeleteOutlined /></template>
              删除选中
            </a-button>
          </a-popconfirm>
        </a-space>
      </div>
      <a-table
        :columns="columns"
        :data-source="plans"
        :pagination="false"
        :row-key="rowKey"
        :row-selection="rowSelection"
        :scroll="{ x: 680 }"
        size="small"
      >
        <template #emptyText>暂无库存保持计划</template>
        <template #bodyCell="{ column, record }">
          <a-select
            v-if="column.key === 'stage'"
            v-model:value="record.Stage"
            :options="stageOptions"
            :disabled="loading"
            allow-clear
            show-search
            option-filter-prop="label"
            placeholder="选择关卡"
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
            placeholder="选择物品"
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
            aria-label="删除库存保持计划"
            :disabled="loading"
            @click="removePlan(record.key)"
          >
            <DeleteOutlined />
          </a-button>
        </template>
      </a-table>
    </template>
  </div>
</template>

<script setup lang="ts">
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
  importDepotMaintainPreset,
  type DepotMaintainPlan as SavedDepotMaintainPlan,
  type DepotMaintainPresetKey,
} from './depotMaintainPresets'

type SelectOption = {
  label: string
  value: string
}

type DepotMaintainPlan = SavedDepotMaintainPlan & {
  key: number
}

const props = defineProps<{
  formData: any
  loading: boolean
  stageOptions: SelectOption[]
  itemOptions: SelectOption[]
  itemOptionsLoading: boolean
  itemOptionsError: string
}>()

const emit = defineEmits<{
  save: [key: string, value: any]
  'update-enabled': [value: boolean]
}>()

const columns: TableColumnsType = [
  { title: '关卡', key: 'stage', width: '28%' },
  { title: '物品', key: 'item', width: '38%' },
  { title: '目标库存', key: 'count', width: 140 },
  { title: '', key: 'action', width: 56, align: 'center' },
]

const plans = ref<DepotMaintainPlan[]>([])
const selectedRowKeys = ref<number[]>([])
let nextKey = 0
const rowKey = (record: DepotMaintainPlan) => record.key
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

const emitSave = (key: string, value: any) => emit('save', key, value)
const handleEnabledChange = (value: boolean) => {
  emit('update-enabled', value)
}

const savePlans = () => {
  emitSave(
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
  plans.value = importDepotMaintainPreset(
    plans.value.map(({ Stage, DropId, DropCount }) => ({ Stage, DropId, DropCount })),
    preset
  ).map(plan => ({ key: nextKey++, ...plan }))
  savePlans()
}

const removePlan = (key: number) => {
  selectedRowKeys.value = selectedRowKeys.value.filter(selectedKey => selectedKey !== key)
  plans.value = plans.value.filter(plan => plan.key !== key)
  savePlans()
}

const removeSelectedPlans = () => {
  const keys = new Set(selectedRowKeys.value)
  plans.value = plans.value.filter(plan => !keys.has(plan.key))
  selectedRowKeys.value = []
  savePlans()
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
  display: flex;
  justify-content: space-between;
  align-items: center;
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

.plan-actions {
  margin-bottom: 12px;
}

:deep(.ant-select),
:deep(.ant-input-number) {
  width: 100%;
}
</style>

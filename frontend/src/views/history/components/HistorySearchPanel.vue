<template>
  <div class="search-panel">
    <!-- 快捷时间选择 -->
    <div class="quick-time-section">
      <span class="section-label">快捷选择</span>
      <div class="time-buttons">
        <a-button
          v-for="preset in timePresets"
          :key="preset.key"
          :type="currentPreset === preset.key ? 'primary' : 'default'"
          size="middle"
          @click="$emit('quick-select', preset)"
        >
          {{ preset.label }}
        </a-button>
      </div>
    </div>

    <!-- 详细筛选条件 -->
    <div class="filter-section">
      <div class="filter-item">
        <span class="filter-label">合并模式</span>
        <a-select v-model:value="localMode" style="width: 120px" @change="handleModeChange">
          <a-select-option value="DAILY">按日合并</a-select-option>
          <a-select-option value="WEEKLY">按周合并</a-select-option>
          <a-select-option value="MONTHLY">按月合并</a-select-option>
        </a-select>
      </div>

      <div class="filter-item">
        <span class="filter-label">开始日期</span>
        <a-date-picker
          v-model:value="localStartDate"
          style="width: 140px"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          @change="handleStartDateChange"
        />
      </div>

      <div class="filter-item">
        <span class="filter-label">结束日期</span>
        <a-date-picker
          v-model:value="localEndDate"
          style="width: 140px"
          format="YYYY-MM-DD"
          value-format="YYYY-MM-DD"
          @change="handleEndDateChange"
        />
      </div>

      <div class="filter-actions">
        <a-button type="primary" :loading="loading" @click="$emit('search')">
          <template #icon>
            <SearchOutlined />
          </template>
          搜索
        </a-button>
        <a-button @click="$emit('reset')">
          <template #icon>
            <ClearOutlined />
          </template>
          重置
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ClearOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { ref, watch } from 'vue'
import { timePresets } from '../useHistoryLogic.ts'

interface Props {
  mode: string
  startDate: string
  endDate: string
  currentPreset: string
  loading: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:mode', value: string): void
  (e: 'update:startDate', value: string): void
  (e: 'update:endDate', value: string): void
  (e: 'quick-select', preset: (typeof timePresets)[0]): void
  (e: 'search'): void
  (e: 'reset'): void
  (e: 'date-change'): void
}>()

const localMode = ref(props.mode)
const localStartDate = ref(props.startDate)
const localEndDate = ref(props.endDate)

watch(
  () => props.mode,
  val => {
    localMode.value = val
  }
)
watch(
  () => props.startDate,
  val => {
    localStartDate.value = val
  }
)
watch(
  () => props.endDate,
  val => {
    localEndDate.value = val
  }
)

const handleModeChange = (val: string) => {
  emit('update:mode', val)
}

const handleStartDateChange = (val: string) => {
  emit('update:startDate', val)
  emit('date-change')
}

const handleEndDateChange = (val: string) => {
  emit('update:endDate', val)
  emit('date-change')
}
</script>

<style scoped>
.search-panel {
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 20px;
  border: 1px solid var(--ant-color-border-secondary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.quick-time-section {
  margin-bottom: 16px;
}

.section-label {
  display: block;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  margin-bottom: 10px;
  font-weight: 500;
}

.time-buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.filter-section {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  gap: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filter-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  font-weight: 500;
}

.filter-actions {
  display: flex;
  gap: 8px;
  margin-left: auto;
}

@media (max-width: 768px) {
  .filter-section {
    flex-direction: column;
    align-items: stretch;
  }

  .filter-actions {
    margin-left: 0;
    margin-top: 8px;
  }
}
</style>

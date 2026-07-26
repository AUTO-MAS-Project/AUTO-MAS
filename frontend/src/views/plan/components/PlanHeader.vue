<template>
  <div class="plans-header">
    <!-- 统一 MacPageHeader 规范（compact + transparent，动作在右侧） -->
    <MacPageHeader
      class="plan-page-header"
      title="计划管理"
      subtitle="维护 MAA 计划表，按日或按周切换任务配置"
      compact
      transparent
    >
      <a-space size="middle">
        <a-dropdown-button type="primary" @click="openCreateDialog">
          <PlusOutlined />
          新建计划
          <template #overlay>
            <a-menu @click="handlePlanTypeMenuClick">
              <a-menu-item key="MaaPlanConfig">
                <PlusOutlined />
                新建 MAA 计划
              </a-menu-item>
            </a-menu>
          </template>
        </a-dropdown-button>

        <!-- Lane 8：复制当前计划 -->
        <a-tooltip title="基于当前计划创建副本">
          <a-button
            :disabled="!activePlanId || planList.length === 0"
            :loading="copyLoading"
            @click="$emit('copy-plan', activePlanId)"
          >
            <template #icon>
              <CopyOutlined />
            </template>
            复制当前计划
          </a-button>
        </a-tooltip>

        <a-popconfirm
          v-if="planList.length > 0"
          title="确定要删除这个计划吗？"
          ok-text="确定"
          cancel-text="取消"
          ok-type="danger"
          @confirm="$emit('remove-plan', activePlanId)"
        >
          <a-button danger :disabled="!activePlanId">
            <template #icon>
              <DeleteOutlined />
            </template>
            删除当前计划
          </a-button>
        </a-popconfirm>
      </a-space>
    </MacPageHeader>

    <a-modal
      v-model:open="createDialogOpen"
      title="选择计划类型"
      ok-text="创建计划"
      cancel-text="取消"
      @ok="confirmCreate"
    >
      <a-radio-group v-model:value="selectedPlanType" class="plan-type-options">
        <a-radio-button value="MaaPlanConfig" class="plan-type-option">
          <span class="plan-type-title">MAA 计划</span>
          <span class="plan-type-description">按日或按周配置 MAA 任务。</span>
        </a-radio-button>
      </a-radio-group>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { CopyOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { computed, ref } from 'vue'
import MacPageHeader from '@/components/mac/PageHeader.vue'

interface Plan {
  id: string
  name: string
  type: string
}

interface Props {
  planList: Plan[]
  activePlanId: string
  copyLoading?: boolean
}

interface Emits {
  (e: 'add-plan', planType: string): void

  (e: 'remove-plan', planId: string): void

  (e: 'copy-plan', planId: string): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 默认计划类型
const selectedPlanType = ref('MaaPlanConfig')
const createDialogOpen = ref(false)

const openCreateDialog = () => {
  createDialogOpen.value = true
}

const handlePlanTypeMenuClick = ({ key }: { key: string }) => {
  selectedPlanType.value = key
  openCreateDialog()
}

const confirmCreate = () => {
  emit('add-plan', selectedPlanType.value)
  createDialogOpen.value = false
}

// copyLoading from props
const copyLoading = computed(() => props.copyLoading ?? false)
</script>

<style scoped>
.plans-header {
  container: plans-header / inline-size;
  margin-bottom: var(--v6-space-4);
}

/* 页面容器自带内边距，抵消 PageHeader 的全宽内边距保持对齐 */
.plan-page-header :deep(.mac-page-header) {
  padding-inline: 4px;
}

.plan-type-options {
  display: grid;
  grid-template-columns: 1fr;
  width: 100%;
}

.plan-type-option {
  height: auto;
  padding: var(--v6-space-4);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-lg);
  background: var(--v6-color-surface-transparent);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  line-height: 1.5;
}

.plan-type-option::before {
  display: none;
}

.plan-type-option :deep(.ant-radio-button) {
  display: none;
}

.plan-type-title,
.plan-type-description {
  display: block;
}

.plan-type-title {
  font-weight: 600;
  color: var(--v6-color-text);
}

.plan-type-description {
  margin-top: var(--v6-space-1);
  color: var(--v6-color-text-secondary);
  font-size: 13px;
}

.plan-type-option.ant-radio-button-wrapper-checked {
  border-color: var(--v6-color-primary);
  box-shadow: 0 0 0 1px var(--v6-color-primary);
}

/* 页头窄屏换行由 MacPageHeader 内置容器查询处理 */
@container plans-header (max-width: 768px) {
  .plan-page-header :deep(.ant-space) {
    flex-wrap: wrap;
  }
}
</style>

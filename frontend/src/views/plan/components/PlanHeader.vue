<template>
  <div class="plans-header">
    <div class="header-left">
      <h1 class="page-title">计划管理</h1>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <!-- 新建计划下拉菜单 -->
        <a-dropdown>
          <template #overlay>
            <a-menu @click="handleMenuClick">
              <a-menu-item key="MaaPlan">
                <PlusOutlined />
                新建 MAA 计划
              </a-menu-item>
              <!-- 预留其他计划类型 -->
              <!-- <a-menu-item key="GeneralPlan">
                <PlusOutlined />
                新建通用计划
              </a-menu-item>
              <a-menu-item key="CustomPlan">
                <PlusOutlined />
                新建自定义计划
              </a-menu-item> -->
            </a-menu>
          </template>
          <a-button type="primary" size="large">
            <template #icon>
              <PlusOutlined />
            </template>
            新建计划
            <DownOutlined />
          </a-button>
        </a-dropdown>

        <a-popconfirm
          v-if="planList.length > 0"
          title="确定要删除这个计划吗？"
          ok-text="确定"
          cancel-text="取消"
          @confirm="$emit('remove-plan', activePlanId)"
        >
          <a-button danger size="large" :disabled="!activePlanId">
            <template #icon>
              <DeleteOutlined />
            </template>
            删除当前计划
          </a-button>
        </a-popconfirm>
      </a-space>
    </div>
  </div>
</template>

<script setup lang="ts">
import { DeleteOutlined, DownOutlined, PlusOutlined } from '@ant-design/icons-vue'

interface Plan {
  id: string
  name: string
  type: string
}

interface Props {
  planList: Plan[]
  activePlanId: string
}

interface Emits {
  (e: 'add-plan', planType: string): void

  (e: 'remove-plan', planId: string): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const handleMenuClick = ({ key }: { key: string }) => {
  emit('add-plan', key)
}
</script>

<style scoped>
.plans-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}

.header-left {
  flex: 1;
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.header-actions {
  flex-shrink: 0;
}

@media (max-width: 1200px) {
  .plans-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .page-title {
    font-size: 28px;
  }
}

@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }

  .header-actions {
    width: 100%;
    display: flex;
    justify-content: center;
  }
}
</style>

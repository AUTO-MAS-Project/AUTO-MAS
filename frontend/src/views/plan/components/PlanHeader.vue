<template>
  <div class="plans-header">
    <div class="header-left">
      <h1 class="page-title">计划管理</h1>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <a-dropdown :trigger="['click']">
          <template #overlay>
            <a-menu @click="handleAddPlanFromMenu">
              <a-menu-item key="MaaPlanConfig"> 新建 MAA 计划 </a-menu-item>
              <a-menu-item key="MaaEndPlanConfig"> 新建 MaaEnd 计划 </a-menu-item>
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
import { DeleteOutlined, DownOutlined } from '@ant-design/icons-vue'

interface Plan {
  id: string
  name: string
  type: string
}

interface Props {
  planList: Plan[]
  activePlanId: string
}

defineProps<Props>()
const emit = defineEmits<{
  'add-plan': [planType: string]
  'remove-plan': [planId: string]
}>()

const handleAddPlanFromMenu = ({ key }: { key: string }) => {
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
  min-width: 0; /* 防止文字溢出 */
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
  white-space: nowrap; /* 防止标题换行 */
  overflow: hidden;
  text-overflow: ellipsis; /* 长标题时显示省略号 */
}

.header-actions {
  flex-shrink: 0;
  margin-left: 16px; /* 添加间距防止太紧密 */
}

@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }

  .plans-header {
    padding: 0 2px; /* 减少边距给内容更多空间 */
  }

  .header-actions {
    margin-left: 8px; /* 小屏幕时减少间距 */
  }
}
</style>

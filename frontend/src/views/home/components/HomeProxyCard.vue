<template>
  <a-card class="home-proxy-card" :bordered="false" title="代理状态">
    <LoadingSkeleton v-if="loading" variant="card" :rows="3" />
    <div v-else-if="Object.keys(proxyData).length > 0" class="proxy-list">
      <div v-for="(proxy, username) in proxyData" :key="username" class="proxy-item">
        <div class="proxy-header">
          <div class="proxy-username">
            <UserOutlined class="user-icon" />
            <span class="username">{{ username }}</span>
          </div>
          <StatusBadge
            :status="proxy.ErrorTimes > 0 ? 'error' : 'success'"
            :label="proxy.ErrorTimes > 0 ? '异常' : '正常'"
            size="small"
          />
        </div>
        <div class="proxy-stats">
          <div class="proxy-stat full-width">
            <span class="proxy-stat-label">最后代理时间</span>
            <span class="proxy-stat-value">{{ formatProxyDisplay(proxy.LastProxyDate) }}</span>
          </div>
          <div class="proxy-stat">
            <span class="proxy-stat-label">代理次数</span>
            <span class="proxy-stat-value">{{ proxy.ProxyTimes }}</span>
          </div>
          <div class="proxy-stat">
            <span class="proxy-stat-label">错误次数</span>
            <span class="proxy-stat-value" :class="{ 'proxy-error': proxy.ErrorTimes > 0 }">
              {{ proxy.ErrorTimes }}
            </span>
          </div>
        </div>
      </div>
    </div>
    <div v-else class="proxy-empty">
      <EmptyState title="暂无代理数据" description="当前没有代理活动记录" compact />
    </div>
  </a-card>
</template>

<script setup lang="ts">
import { UserOutlined } from '@ant-design/icons-vue'
import EmptyState from '@/components/v6/EmptyState.vue'
import LoadingSkeleton from '@/components/v6/LoadingSkeleton.vue'
import StatusBadge from '@/components/v6/StatusBadge.vue'
import type { ProxyInfo } from '../useHomeLogic'

interface Props {
  proxyData: Record<string, ProxyInfo>
  loading: boolean
  formatProxyDisplay: (value: string) => string
}

defineProps<Props>()
</script>

<style scoped>
.home-proxy-card {
  border-radius: var(--v6-radius-card);
  background: var(--v6-color-surface);
  border: 1px solid var(--v6-color-border-subtle);
}

.home-proxy-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.home-proxy-card :deep(.ant-card-head-title) {
  font-size: 15px;
  font-weight: 600;
}

.proxy-empty {
  padding: var(--v6-space-4) 0;
}

/* 代理项网格:按 Home.vue 的 home-layout 容器宽度响应(替代视口栅格 a-col),
   宽容器 3 列 / 中容器 2 列 / 窄容器 1 列 */
.proxy-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

@container home-layout (max-width: 1200px) {
  .proxy-list {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@container home-layout (max-width: 992px) {
  .proxy-list {
    grid-template-columns: 1fr;
  }
}

.proxy-item {
  padding: var(--v6-space-4);
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-md);
  background: var(--v6-color-fill-quaternary);
}

.proxy-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--v6-space-3);
  gap: var(--v6-space-2);
}

.proxy-username {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
}

.user-icon {
  color: var(--v6-color-text-secondary);
  flex-shrink: 0;
}

.username {
  min-width: 0;
  font-weight: 600;
  color: var(--v6-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.proxy-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--v6-space-3);
}

.proxy-stat {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.proxy-stat.full-width {
  grid-column: 1 / -1;
}

.proxy-stat-label {
  font-size: 12px;
  color: var(--v6-color-text-secondary);
}

.proxy-stat-value {
  font-size: 14px;
  font-weight: 600;
  color: var(--v6-color-text);
}

.proxy-error {
  color: var(--v6-color-error);
}

/* 窄容器兜底:统计项改单列,避免标签/数值挤压换行 */
@container home-layout (max-width: 480px) {
  .proxy-stats {
    grid-template-columns: 1fr;
  }
}
</style>

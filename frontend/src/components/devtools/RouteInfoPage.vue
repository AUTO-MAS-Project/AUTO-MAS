<template>
  <div class="route-info-page">
    <!-- 当前路由信息 -->
    <div class="debug-section">
      <h4>🛣️ 当前路由信息</h4>
      <div class="info-item">
        <span class="label">路径:</span>
        <span class="value">{{ currentRoute.path }}</span>
      </div>
      <div class="info-item">
        <span class="label">名称:</span>
        <span class="value">{{ currentRoute.name || '未命名' }}</span>
      </div>
      <div class="info-item">
        <span class="label">标题:</span>
        <span class="value">{{ currentRoute.meta?.title || '无标题' }}</span>
      </div>
      <div v-if="Object.keys(currentRoute.params).length > 0" class="info-item">
        <span class="label">参数:</span>
        <pre class="value">{{ JSON.stringify(currentRoute.params, null, 2) }}</pre>
      </div>
      <div v-if="Object.keys(currentRoute.query).length > 0" class="info-item">
        <span class="label">查询:</span>
        <pre class="value">{{ JSON.stringify(currentRoute.query, null, 2) }}</pre>
      </div>
    </div>

    <!-- 路由历史 -->
    <div class="debug-section">
      <h4>📚 路由历史 (最近10条)</h4>
      <div class="route-history">
        <div
          v-for="(route, index) in routeHistory"
          :key="index"
          class="history-item"
          :class="{ current: index === 0 }"
        >
          <span class="time">{{ route.time }}</span>
          <span class="path">{{ route.path }}</span>
          <span class="name">{{ route.name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

interface RouteHistoryItem {
  path: string
  name: string | null | undefined
  time: string
}

const route = useRoute()

// 当前路由信息
const currentRoute = computed(() => ({
  path: route.path,
  name: route.name,
  params: route.params,
  query: route.query,
  meta: route.meta,
}))

// 路由历史记录
const routeHistory = ref<RouteHistoryItem[]>([])

// 添加路由记录
const addRouteHistory = (newRoute: typeof route) => {
  const historyItem: RouteHistoryItem = {
    path: newRoute.path,
    name: typeof newRoute.name === 'string' ? newRoute.name : String(newRoute.name || ''),
    time: new Date().toLocaleTimeString(),
  }

  routeHistory.value.unshift(historyItem)
  // 只保留最近10条记录
  if (routeHistory.value.length > 10) {
    routeHistory.value = routeHistory.value.slice(0, 10)
  }
}

// 监听路由变化
watch(
  route,
  newRoute => {
    addRouteHistory(newRoute)
  },
  { immediate: true }
)
</script>

<style scoped>
.route-info-page {
  color: #fff;
}

.debug-section {
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #333;
}

.debug-section:last-child {
  margin-bottom: 0;
  border-bottom: none;
}

.debug-section h4 {
  margin: 0 0 8px 0;
  color: #4caf50;
  font-size: 11px;
  font-weight: bold;
}

.info-item {
  display: flex;
  margin-bottom: 4px;
  align-items: flex-start;
}

.label {
  min-width: 50px;
  color: #999;
  font-weight: bold;
}

.value {
  flex: 1;
  color: #fff;
  word-break: break-word;
}

.value pre {
  margin: 0;
  font-size: 10px;
  background: rgba(255, 255, 255, 0.1);
  padding: 4px;
  border-radius: 4px;
  white-space: pre-wrap;
}

.route-history {
  max-height: 120px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 10px;
}

.history-item.current {
  background: rgba(76, 175, 80, 0.2);
  border-radius: 4px;
  padding: 4px;
}

.history-item .time {
  color: #999;
  min-width: 60px;
}

.history-item .path {
  color: #2196f3;
  flex: 1;
}

.history-item .name {
  color: #4caf50;
  min-width: 60px;
}

.route-history::-webkit-scrollbar {
  width: 4px;
}

.route-history::-webkit-scrollbar-track {
  background: rgba(255, 255, 255, 0.1);
}

.route-history::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.3);
  border-radius: 2px;
}
</style>

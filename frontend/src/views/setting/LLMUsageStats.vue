<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import {
  ReloadOutlined,
  ThunderboltOutlined,
  CloudOutlined,
  FieldTimeOutlined,
} from '@ant-design/icons-vue'
import { LLMService } from '@/api/services/LLMService'
import type { LLMUsageStatisticsOut } from '@/api/models/LLMUsageStatisticsOut'
import { getLogger } from '@/utils/logger'

const logger = getLogger('LLM使用统计')

// 状态
const loading = ref(false)
const statistics = ref<LLMUsageStatisticsOut | null>(null)

// 计算属性：当天统计
const dailyStats = computed(() => {
  return (
    statistics.value?.daily || {
      total_tokens: 0,
      total_requests: 0,
      average_tokens_per_request: 0,
      input_tokens: 0,
      output_tokens: 0,
    }
  )
})

// 计算属性：本周统计
const weeklyStats = computed(() => {
  return (
    statistics.value?.weekly || {
      total_tokens: 0,
      total_requests: 0,
      average_tokens_per_request: 0,
      input_tokens: 0,
      output_tokens: 0,
    }
  )
})

// 计算属性：本月统计
const monthlyStats = computed(() => {
  return (
    statistics.value?.monthly || {
      total_tokens: 0,
      total_requests: 0,
      average_tokens_per_request: 0,
      input_tokens: 0,
      output_tokens: 0,
    }
  )
})

// 格式化数字
const formatNumber = (num: number | undefined | null): string => {
  if (num === undefined || num === null) return '0'
  if (num >= 1000000) {
    return (num / 1000000).toFixed(2) + 'M'
  }
  if (num >= 1000) {
    return (num / 1000).toFixed(2) + 'K'
  }
  return num.toLocaleString()
}

// 格式化平均值
const formatAverage = (num: number | undefined | null): string => {
  if (num === undefined || num === null) return '0'
  return num.toFixed(1)
}

// 加载统计数据
const loadStatistics = async () => {
  loading.value = true
  try {
    const res = await LLMService.getLLMUsageStatisticsApiLlmUsageStatisticsPost({})
    if (res) {
      statistics.value = res
    }
  } catch (e) {
    logger.error('加载 Token 使用统计失败', e)
    message.error('加载统计数据失败')
  } finally {
    loading.value = false
  }
}

// 刷新数据
const refresh = () => {
  loadStatistics()
}

onMounted(() => {
  loadStatistics()
})

// 暴露刷新方法供父组件调用
defineExpose({
  refresh,
})
</script>

<template>
  <div class="usage-stats-container">
    <div class="stats-header">
      <h4>
        <ThunderboltOutlined />
        Token 使用统计
      </h4>
      <a-button type="text" size="small" :loading="loading" @click="refresh">
        <template #icon>
          <ReloadOutlined />
        </template>
        刷新
      </a-button>
    </div>

    <a-spin :spinning="loading">
      <div class="stats-grid">
        <!-- 当天统计 -->
        <div class="stats-card">
          <div class="stats-card-header">
            <FieldTimeOutlined class="stats-icon today" />
            <span class="stats-period">今日</span>
          </div>
          <div class="stats-card-body">
            <div class="stat-item main">
              <span class="stat-value">{{ formatNumber(dailyStats.total_tokens) }}</span>
              <span class="stat-label">总 Token</span>
            </div>
            <div class="stat-row">
              <div class="stat-item">
                <span class="stat-value small">{{ dailyStats.total_requests || 0 }}</span>
                <span class="stat-label">请求数</span>
              </div>
              <div class="stat-item">
                <span class="stat-value small">{{
                  formatAverage(dailyStats.average_tokens_per_request)
                }}</span>
                <span class="stat-label">平均/次</span>
              </div>
            </div>
            <div class="stat-row tokens">
              <div class="stat-item">
                <span class="stat-value tiny input">{{
                  formatNumber(dailyStats.input_tokens)
                }}</span>
                <span class="stat-label">输入</span>
              </div>
              <div class="stat-item">
                <span class="stat-value tiny output">{{
                  formatNumber(dailyStats.output_tokens)
                }}</span>
                <span class="stat-label">输出</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 本周统计 -->
        <div class="stats-card">
          <div class="stats-card-header">
            <CloudOutlined class="stats-icon week" />
            <span class="stats-period">本周</span>
          </div>
          <div class="stats-card-body">
            <div class="stat-item main">
              <span class="stat-value">{{ formatNumber(weeklyStats.total_tokens) }}</span>
              <span class="stat-label">总 Token</span>
            </div>
            <div class="stat-row">
              <div class="stat-item">
                <span class="stat-value small">{{ weeklyStats.total_requests || 0 }}</span>
                <span class="stat-label">请求数</span>
              </div>
              <div class="stat-item">
                <span class="stat-value small">{{
                  formatAverage(weeklyStats.average_tokens_per_request)
                }}</span>
                <span class="stat-label">平均/次</span>
              </div>
            </div>
            <div class="stat-row tokens">
              <div class="stat-item">
                <span class="stat-value tiny input">{{
                  formatNumber(weeklyStats.input_tokens)
                }}</span>
                <span class="stat-label">输入</span>
              </div>
              <div class="stat-item">
                <span class="stat-value tiny output">{{
                  formatNumber(weeklyStats.output_tokens)
                }}</span>
                <span class="stat-label">输出</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 本月统计 -->
        <div class="stats-card">
          <div class="stats-card-header">
            <ThunderboltOutlined class="stats-icon month" />
            <span class="stats-period">本月</span>
          </div>
          <div class="stats-card-body">
            <div class="stat-item main">
              <span class="stat-value">{{ formatNumber(monthlyStats.total_tokens) }}</span>
              <span class="stat-label">总 Token</span>
            </div>
            <div class="stat-row">
              <div class="stat-item">
                <span class="stat-value small">{{ monthlyStats.total_requests || 0 }}</span>
                <span class="stat-label">请求数</span>
              </div>
              <div class="stat-item">
                <span class="stat-value small">{{
                  formatAverage(monthlyStats.average_tokens_per_request)
                }}</span>
                <span class="stat-label">平均/次</span>
              </div>
            </div>
            <div class="stat-row tokens">
              <div class="stat-item">
                <span class="stat-value tiny input">{{
                  formatNumber(monthlyStats.input_tokens)
                }}</span>
                <span class="stat-label">输入</span>
              </div>
              <div class="stat-item">
                <span class="stat-value tiny output">{{
                  formatNumber(monthlyStats.output_tokens)
                }}</span>
                <span class="stat-label">输出</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </a-spin>
  </div>
</template>

<style scoped>
.usage-stats-container {
  margin-top: 24px;
}

.stats-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.stats-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: 1fr;
  }
}

.stats-card {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 12px;
  padding: 16px;
  transition: all 0.2s ease;
}

.stats-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

.stats-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.stats-icon {
  font-size: 20px;
}

.stats-icon.today {
  color: #52c41a;
}

.stats-icon.week {
  color: #1890ff;
}

.stats-icon.month {
  color: #722ed1;
}

.stats-period {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.stats-card-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.stat-item.main {
  padding: 8px 0;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--ant-color-text);
  font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Fira Mono', 'Droid Sans Mono', monospace;
}

.stat-value.small {
  font-size: 18px;
  font-weight: 600;
}

.stat-value.tiny {
  font-size: 14px;
  font-weight: 600;
}

.stat-value.input {
  color: #1890ff;
}

.stat-value.output {
  color: #52c41a;
}

.stat-label {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.stat-row {
  display: flex;
  justify-content: space-around;
  padding: 8px 0;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.stat-row.tokens {
  background: var(--ant-color-fill-quaternary);
  border-radius: 8px;
  margin: 0 -8px;
  padding: 8px;
  border-top: none;
}
</style>

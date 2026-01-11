<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue'
import { message } from 'ant-design-vue'
import { ReloadOutlined, HistoryOutlined, SearchOutlined } from '@ant-design/icons-vue'
import { LLMService } from '@/api/services/LLMService'
import type { LLMUsageHistoryOut } from '@/api/models/LLMUsageHistoryOut'
import { getLogger } from '@/utils/logger'
import dayjs from 'dayjs'

const logger = getLogger('LLM使用历史')

// 状态
const loading = ref(false)
const historyData = ref<LLMUsageHistoryOut | null>(null)
const records = computed(() => historyData.value?.records || [])
const totalCount = computed(() => historyData.value?.total_count || 0)

// 日期范围筛选
const dateRange = ref<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)

// 分页
const pagination = reactive({
  current: 1,
  pageSize: 10,
  total: 0,
})

// 表格列定义
const columns = [
  {
    title: '时间',
    dataIndex: 'timestamp',
    key: 'timestamp',
    width: 180,
    customRender: ({ text }: { text: string }) => {
      return dayjs(text).format('YYYY-MM-DD HH:mm:ss')
    },
  },
  {
    title: '提供商',
    dataIndex: 'provider_name',
    key: 'provider_name',
    width: 120,
  },
  {
    title: '模型',
    dataIndex: 'model_name',
    key: 'model_name',
    width: 180,
    ellipsis: true,
  },
  {
    title: '输入 Token',
    dataIndex: 'input_tokens',
    key: 'input_tokens',
    width: 100,
    align: 'right' as const,
    customRender: ({ text }: { text: number }) => {
      return text.toLocaleString()
    },
  },
  {
    title: '输出 Token',
    dataIndex: 'output_tokens',
    key: 'output_tokens',
    width: 100,
    align: 'right' as const,
    customRender: ({ text }: { text: number }) => {
      return text.toLocaleString()
    },
  },
  {
    title: '总 Token',
    dataIndex: 'total_tokens',
    key: 'total_tokens',
    width: 100,
    align: 'right' as const,
    customRender: ({ text }: { text: number }) => {
      return text.toLocaleString()
    },
  },
  {
    title: '任务 ID',
    dataIndex: 'task_id',
    key: 'task_id',
    width: 120,
    ellipsis: true,
    customRender: ({ text }: { text: string | undefined }) => {
      return text || '-'
    },
  },
]

// 加载历史数据
const loadHistory = async () => {
  loading.value = true
  try {
    const params: { start_date?: string; end_date?: string } = {}

    if (dateRange.value && dateRange.value.length === 2) {
      params.start_date = dateRange.value[0].format('YYYY-MM-DD')
      params.end_date = dateRange.value[1].format('YYYY-MM-DD')
    }

    const res = await LLMService.getLLMUsageHistoryApiLlmUsageHistoryPost(params)
    if (res) {
      historyData.value = res
      pagination.total = res.total_count || res.records?.length || 0
    }
  } catch (e) {
    logger.error('加载 Token 使用历史失败', e)
    message.error('加载历史数据失败')
  } finally {
    loading.value = false
  }
}

// 处理日期范围变化
const handleDateRangeChange = (dates: [dayjs.Dayjs, dayjs.Dayjs] | null) => {
  dateRange.value = dates
  pagination.current = 1
  loadHistory()
}

// 处理表格分页变化
const handleTableChange = (pag: { current?: number; pageSize?: number }) => {
  pagination.current = pag.current || 1
  pagination.pageSize = pag.pageSize || 10
}

// 刷新数据
const refresh = () => {
  loadHistory()
}

// 清除筛选
const clearFilter = () => {
  dateRange.value = null
  pagination.current = 1
  loadHistory()
}

// 快捷日期范围
const setQuickRange = (days: number) => {
  const end = dayjs()
  const start = dayjs().subtract(days - 1, 'day')
  dateRange.value = [start, end]
  pagination.current = 1
  loadHistory()
}

onMounted(() => {
  loadHistory()
})

// 暴露刷新方法供父组件调用
defineExpose({
  refresh,
})
</script>

<template>
  <div class="usage-history-container">
    <div class="history-header">
      <h4>
        <HistoryOutlined />
        使用历史记录
      </h4>
      <div class="header-actions">
        <a-button type="text" size="small" :loading="loading" @click="refresh">
          <template #icon>
            <ReloadOutlined />
          </template>
          刷新
        </a-button>
      </div>
    </div>

    <!-- 筛选区域 -->
    <div class="filter-section">
      <div class="filter-row">
        <div class="filter-item">
          <span class="filter-label">日期范围:</span>
          <a-range-picker
            :value="dateRange"
            :allow-clear="true"
            format="YYYY-MM-DD"
            :placeholder="['开始日期', '结束日期']"
            style="width: 260px"
            @change="handleDateRangeChange"
          />
        </div>
        <div class="quick-filters">
          <a-button size="small" @click="setQuickRange(7)">近7天</a-button>
          <a-button size="small" @click="setQuickRange(30)">近30天</a-button>
          <a-button size="small" @click="setQuickRange(90)">近90天</a-button>
          <a-button size="small" type="link" @click="clearFilter">清除筛选</a-button>
        </div>
      </div>
      <div class="filter-summary">
        <span class="summary-text">
          共 <strong>{{ totalCount }}</strong> 条记录
        </span>
      </div>
    </div>

    <!-- 数据表格 -->
    <a-table
      :columns="columns"
      :data-source="records"
      :loading="loading"
      :pagination="{
        current: pagination.current,
        pageSize: pagination.pageSize,
        total: pagination.total,
        showSizeChanger: true,
        showQuickJumper: true,
        showTotal: (total: number) => `共 ${total} 条`,
        pageSizeOptions: ['10', '20', '50', '100'],
      }"
      :scroll="{ x: 900 }"
      row-key="id"
      size="middle"
      class="history-table"
      @change="handleTableChange"
    >
      <template #emptyText>
        <div class="empty-state">
          <SearchOutlined
            style="font-size: 48px; color: var(--ant-color-text-quaternary); margin-bottom: 16px"
          />
          <p>暂无使用记录</p>
          <p class="empty-hint">启用 LLM 判定功能后，使用记录将显示在这里</p>
        </div>
      </template>
    </a-table>
  </div>
</template>

<style scoped>
.usage-history-container {
  margin-top: 32px;
}

.history-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.history-header h4 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.filter-section {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.filter-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-label {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.quick-filters {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.filter-summary {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--ant-color-border-secondary);
}

.summary-text {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.summary-text strong {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.history-table {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
}

.history-table :deep(.ant-table) {
  border-radius: 8px;
}

.history-table :deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-fill-quaternary);
  font-weight: 600;
}

.empty-state {
  padding: 48px 24px;
  text-align: center;
}

.empty-state p {
  margin: 0;
  color: var(--ant-color-text-secondary);
}

.empty-hint {
  font-size: 12px;
  margin-top: 8px !important;
  color: var(--ant-color-text-quaternary) !important;
}

@media (max-width: 768px) {
  .filter-row {
    flex-direction: column;
    align-items: flex-start;
  }

  .quick-filters {
    width: 100%;
    justify-content: flex-start;
  }
}
</style>

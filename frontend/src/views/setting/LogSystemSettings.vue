<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, h } from 'vue'
import { message } from 'ant-design-vue'
import { 
  SettingOutlined, 
  ReloadOutlined, 
  ClearOutlined, 
  SaveOutlined,
  DashboardOutlined,
  FilterOutlined,
  ClockCircleOutlined,
  DatabaseOutlined
} from '@ant-design/icons-vue'
import type { 
  LogPipelineConfig, 
  LogBatchConfig, 
  LogCacheConfig,
  LogLevel,
  LogProcessingStats,
  LogParserInfo
} from '@/types/log'
import { getLogger } from '@/utils/logger'

const logger = getLogger('日志系统设置')

// 响应式数据
const loading = ref(false)
const saving = ref(false)
const stats = ref<LogProcessingStats | null>(null)
const refreshingStats = ref(false)

// 管道配置
const pipelineConfig = reactive<LogPipelineConfig>({
  enableCache: true,
  enableBatching: true,
  enableCompression: false,
  enableFiltering: false,
  cacheConfig: {
    maxSize: 1000,
    ttl: 300000, // 5分钟
    enableLRU: true,
    enableStats: true
  },
  batchConfig: {
    batchSize: 100,
    batchTimeout: 1000, // 1秒
    maxBatchSize: 200,
    priorityLevels: ['CRITICAL', 'ERROR', 'WARN', 'INFO', 'DEBUG', 'TRACE'] as any,
    immediateLevels: ['CRITICAL', 'ERROR'] as any
  },
  transmitOptions: {
    enableCompression: false,
    enableBatching: true,
    enablePriority: true,
    retryCount: 3,
    retryDelay: 1000
  }
})

// 解析器配置
const parsers = ref<LogParserInfo[]>([])

// 预设配置
const presetConfigs = [
  {
    name: '默认配置',
    description: '平衡性能和资源使用的标准配置',
    config: 'default'
  },
  {
    name: '高性能配置',
    description: '优化处理速度，适合高负载环境',
    config: 'high-performance'
  },
  {
    name: '低延迟配置',
    description: '减少处理延迟，适合实时日志查看',
    config: 'low-latency'
  },
  {
    name: '资源节约配置',
    description: '减少内存和CPU使用',
    config: 'resource-saving'
  }
]

// 日志级别选项
const logLevelOptions = [
  { label: 'TRACE', value: 'TRACE' },
  { label: 'DEBUG', value: 'DEBUG' },
  { label: 'INFO', value: 'INFO' },
  { label: 'WARN', value: 'WARN' },
  { label: 'ERROR', value: 'ERROR' },
  { label: 'CRITICAL', value: 'CRITICAL' }
]

// 计算属性
const cacheHitRate = computed(() => {
  if (!stats.value?.cacheStats) return '0%'
  const rate = stats.value.cacheStats.hitRate * 100
  return `${rate.toFixed(1)}%`
})

const batchEfficiency = computed(() => {
  if (!stats.value?.batchStats) return '0%'
  const efficiency = (stats.value.batchStats.totalProcessed / (stats.value.batchStats.totalBatches || 1)) * 100
  return `${efficiency.toFixed(1)}%`
})

const averageProcessingTime = computed(() => {
  if (!stats.value) return '0ms'
  return `${stats.value.averageProcessingTime.toFixed(2)}ms`
})

// 方法
const loadConfig = async () => {
  loading.value = true
  try {
    // 从后端加载配置
    if (window.electronAPI?.logManagement?.getConfig) {
      const result = await window.electronAPI.logManagement.getConfig()
      if (result.success && result.data) {
        Object.assign(pipelineConfig, result.data)
      }
    } else {
      // 降级到默认配置
      logger.warn('无法从后端加载日志配置，使用默认配置')
    }
  } catch (error) {
    logger.error('加载日志配置失败:', error)
    message.error('加载日志配置失败')
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  saving.value = true
  try {
    // 保存配置到后端
    if (window.electronAPI?.logManagement?.updateConfig) {
      const result = await window.electronAPI.logManagement.updateConfig(pipelineConfig)
      if (result.success) {
        message.success('日志配置已保存')
      } else {
        throw new Error(result.error || '保存配置失败')
      }
    } else {
      logger.warn('无法保存日志配置到后端')
      message.warning('配置已更新但未能保存到后端')
    }
  } catch (error) {
    logger.error('保存日志配置失败:', error)
    message.error('保存日志配置失败')
  } finally {
    saving.value = false
  }
}

const loadStats = async () => {
  refreshingStats.value = true
  try {
    if (window.electronAPI?.logManagement?.getStats) {
      const result = await window.electronAPI.logManagement.getStats()
      if (result.success && result.data) {
        stats.value = result.data
        
        // 更新解析器信息
        if (result.data.parserStats) {
          parsers.value = result.data.parserStats
        }
      }
    }
  } catch (error) {
    logger.error('加载日志统计失败:', error)
    message.error('加载日志统计失败')
  } finally {
    refreshingStats.value = false
  }
}

const applyPresetConfig = (presetType: string) => {
  try {
    switch (presetType) {
      case 'high-performance':
        pipelineConfig.enableCache = true
        pipelineConfig.enableBatching = true
        pipelineConfig.enableCompression = true
        if (pipelineConfig.cacheConfig) {
          pipelineConfig.cacheConfig.maxSize = 2000
          pipelineConfig.cacheConfig.ttl = 600000 // 10分钟
        }
        if (pipelineConfig.batchConfig) {
          pipelineConfig.batchConfig.batchSize = 200
          pipelineConfig.batchConfig.batchTimeout = 500
          pipelineConfig.batchConfig.maxBatchSize = 500
        }
        break
        
      case 'low-latency':
        pipelineConfig.enableCache = true
        pipelineConfig.enableBatching = true
        pipelineConfig.enableCompression = false
        if (pipelineConfig.cacheConfig) {
          pipelineConfig.cacheConfig.maxSize = 500
          pipelineConfig.cacheConfig.ttl = 120000 // 2分钟
        }
        if (pipelineConfig.batchConfig) {
          pipelineConfig.batchConfig.batchSize = 50
          pipelineConfig.batchConfig.batchTimeout = 200
          pipelineConfig.batchConfig.maxBatchSize = 100
          pipelineConfig.batchConfig.immediateLevels = ['CRITICAL', 'ERROR', 'WARN', 'INFO'] as any
        }
        break
        
      case 'resource-saving':
        pipelineConfig.enableCache = false
        pipelineConfig.enableBatching = true
        pipelineConfig.enableCompression = false
        if (pipelineConfig.batchConfig) {
          pipelineConfig.batchConfig.batchSize = 50
          pipelineConfig.batchConfig.batchTimeout = 2000
          pipelineConfig.batchConfig.maxBatchSize = 100
        }
        break
        
      case 'default':
      default:
        pipelineConfig.enableCache = true
        pipelineConfig.enableBatching = true
        pipelineConfig.enableCompression = false
        if (pipelineConfig.cacheConfig) {
          pipelineConfig.cacheConfig.maxSize = 1000
          pipelineConfig.cacheConfig.ttl = 300000 // 5分钟
        }
        if (pipelineConfig.batchConfig) {
          pipelineConfig.batchConfig.batchSize = 100
          pipelineConfig.batchConfig.batchTimeout = 1000
          pipelineConfig.batchConfig.maxBatchSize = 200
          pipelineConfig.batchConfig.immediateLevels = ['CRITICAL', 'ERROR'] as any
        }
        break
    }
    
    message.success(`已应用${presetConfigs.find(p => p.config === presetType)?.name}`)
  } catch (error) {
    logger.error('应用预设配置失败:', error)
    message.error('应用预设配置失败')
  }
}

const toggleParser = (parserName: string, enabled: boolean) => {
  if (window.electronAPI?.logManagement?.toggleParser) {
    window.electronAPI.logManagement.toggleParser(parserName, enabled)
      .then(result => {
        if (result.success) {
          message.success(`解析器 ${parserName} 已${enabled ? '启用' : '禁用'}`)
        } else {
          throw new Error(result.error || '操作失败')
        }
      })
      .catch(error => {
        logger.error('切换解析器状态失败:', error)
        message.error('切换解析器状态失败')
      })
  }
}

const clearCache = () => {
  if (window.electronAPI?.logManagement?.clearCache) {
    window.electronAPI.logManagement.clearCache()
      .then(result => {
        if (result.success) {
          message.success('日志缓存已清空')
          loadStats() // 刷新统计信息
        } else {
          throw new Error(result.error || '清空缓存失败')
        }
      })
      .catch(error => {
        logger.error('清空日志缓存失败:', error)
        message.error('清空日志缓存失败')
      })
  }
}

const resetStats = () => {
  if (window.electronAPI?.logManagement?.resetStats) {
    window.electronAPI.logManagement.resetStats()
      .then(result => {
        if (result.success) {
          message.success('日志统计信息已重置')
          loadStats() // 刷新统计信息
        } else {
          throw new Error(result.error || '重置统计失败')
        }
      })
      .catch(error => {
        logger.error('重置日志统计失败:', error)
        message.error('重置日志统计失败')
      })
  }
}

const formatTTL = (ttl: number) => {
  const minutes = Math.floor(ttl / 60000)
  const seconds = Math.floor((ttl % 60000) / 1000)
  return `${minutes}分${seconds}秒`
}

// 解析器表格列配置
const parserColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '格式', dataIndex: 'format', key: 'format' },
  { title: '优先级', dataIndex: 'priority', key: 'priority' },
  { title: '解析次数', dataIndex: ['stats', 'parseCount'], key: 'parseCount' },
  { title: '成功率', dataIndex: ['stats', 'successCount'], key: 'successCount' },
  { title: '平均时间', dataIndex: ['stats', 'averageTime'], key: 'averageTime' },
  {
    title: '状态',
    key: 'enabled',
    customRender: ({ record }: { record: LogParserInfo }) => {
      return h('a-switch', {
        checked: record.enabled,
        onChange: (checked: boolean) => toggleParser(record.name, checked)
      })
    }
  }
]

// 监听配置变化
watch(pipelineConfig, () => {
  // 配置变化时可以添加自动保存逻辑
}, { deep: true })

// 生命周期
onMounted(() => {
  loadConfig()
  loadStats()
  
  // 定期刷新统计信息
  const statsInterval = setInterval(loadStats, 5000) // 每5秒刷新一次
  
  // 组件卸载时清理定时器
  onUnmounted(() => {
    clearInterval(statsInterval)
  })
})
</script>

<template>
  <div class="tab-content">
    <!-- 预设配置 -->
    <div class="form-section">
      <div class="section-header">
        <h3><SettingOutlined /> 预设配置</h3>
        <a-button type="primary" :loading="saving" @click="saveConfig">
          <template #icon><SaveOutlined /></template>
          保存配置
        </a-button>
      </div>
      <div class="preset-configs">
        <a-row :gutter="[16, 16]">
          <a-col 
            v-for="preset in presetConfigs" 
            :key="preset.config"
            :xs="24" 
            :sm="12" 
            :md="6"
          >
            <a-card 
              size="small" 
              hoverable 
              @click="applyPresetConfig(preset.config)"
              class="preset-card"
            >
              <template #title>
                <span>{{ preset.name }}</span>
              </template>
              <p class="preset-description">{{ preset.description }}</p>
            </a-card>
          </a-col>
        </a-row>
      </div>
    </div>

    <!-- 管道配置 -->
    <div class="form-section">
      <div class="section-header">
        <h3><DatabaseOutlined /> 管道配置</h3>
        <a-button @click="loadConfig" :loading="loading">
          <template #icon><ReloadOutlined /></template>
          重新加载
        </a-button>
      </div>
      
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用缓存</span>
            </div>
            <a-switch v-model:checked="pipelineConfig.enableCache" />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用批处理</span>
            </div>
            <a-switch v-model:checked="pipelineConfig.enableBatching" />
          </div>
        </a-col>
      </a-row>

      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用压缩</span>
            </div>
            <a-switch v-model:checked="pipelineConfig.enableCompression" />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用过滤</span>
            </div>
            <a-switch v-model:checked="pipelineConfig.enableFiltering" />
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 缓存配置 -->
    <div class="form-section" v-if="pipelineConfig.enableCache">
      <div class="section-header">
        <h3><DatabaseOutlined /> 缓存配置</h3>
      </div>
      
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">最大缓存条目</span>
            </div>
            <a-input-number 
              v-model:value="pipelineConfig.cacheConfig!.maxSize" 
              :min="100" 
              :max="10000"
              style="width: 100%"
            />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">生存时间</span>
            </div>
            <a-input-number 
              v-model:value="pipelineConfig.cacheConfig!.ttl" 
              :min="60000" 
              :max="3600000"
              :step="60000"
              :formatter="formatTTL"
              style="width: 100%"
            />
          </div>
        </a-col>
      </a-row>

      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用LRU淘汰</span>
            </div>
            <a-switch v-model:checked="pipelineConfig.cacheConfig!.enableLRU" />
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">启用统计</span>
            </div>
            <a-switch v-model:checked="pipelineConfig.cacheConfig!.enableStats" />
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 批处理配置 -->
    <div class="form-section" v-if="pipelineConfig.enableBatching">
      <div class="section-header">
        <h3><ClockCircleOutlined /> 批处理配置</h3>
      </div>
      
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">批次大小</span>
            </div>
            <a-input-number 
              v-model:value="pipelineConfig.batchConfig!.batchSize" 
              :min="10" 
              :max="1000"
              style="width: 100%"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">批次超时 (毫秒)</span>
            </div>
            <a-input-number 
              v-model:value="pipelineConfig.batchConfig!.batchTimeout" 
              :min="100" 
              :max="10000"
              :step="100"
              style="width: 100%"
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">最大批次大小</span>
            </div>
            <a-input-number 
              v-model:value="pipelineConfig.batchConfig!.maxBatchSize" 
              :min="50" 
              :max="2000"
              style="width: 100%"
            />
          </div>
        </a-col>
      </a-row>

      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">立即处理级别</span>
            </div>
            <a-select
              v-model:value="pipelineConfig.batchConfig!.immediateLevels"
              mode="multiple"
              style="width: 100%"
              placeholder="选择立即处理的日志级别"
            >
              <a-select-option 
                v-for="level in logLevelOptions" 
                :key="level.value" 
                :value="level.value"
              >
                {{ level.label }}
              </a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">优先级顺序</span>
            </div>
            <a-select
              v-model:value="pipelineConfig.batchConfig!.priorityLevels"
              mode="multiple"
              style="width: 100%"
              placeholder="选择优先级顺序"
            >
              <a-select-option 
                v-for="level in logLevelOptions" 
                :key="level.value" 
                :value="level.value"
              >
                {{ level.label }}
              </a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <!-- 解析器管理 -->
    <div class="form-section">
      <div class="section-header">
        <h3><FilterOutlined /> 解析器管理</h3>
        <a-button @click="loadStats" :loading="refreshingStats">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </div>
      
      <a-table 
        :dataSource="parsers" 
        :columns="parserColumns"
        :pagination="false"
        size="small"
      />
    </div>

    <!-- 性能统计 -->
    <div class="form-section">
      <div class="section-header">
        <h3><DashboardOutlined /> 性能统计</h3>
        <a-space>
          <a-button @click="clearCache">
            <template #icon><ClearOutlined /></template>
            清空缓存
          </a-button>
          <a-button @click="resetStats">
            <template #icon><ReloadOutlined /></template>
            重置统计
          </a-button>
        </a-space>
      </div>
      
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic title="总日志数" :value="stats?.totalLogs || 0" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="已处理日志" :value="stats?.processedLogs || 0" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="错误日志" :value="stats?.errorLogs || 0" />
        </a-col>
        <a-col :span="6">
          <a-statistic title="平均处理时间" :value="averageProcessingTime" />
        </a-col>
      </a-row>

      <a-row :gutter="16" style="margin-top: 16px;">
        <a-col :span="8">
          <a-statistic title="缓存命中率" :value="cacheHitRate" />
        </a-col>
        <a-col :span="8">
          <a-statistic title="批处理效率" :value="batchEfficiency" />
        </a-col>
        <a-col :span="8">
          <a-statistic 
            title="缓存大小" 
            :value="stats?.cacheStats?.size || 0" 
            suffix="/"
            :value-style="{ fontSize: '16px' }"
          >
            <template #suffix>{{ stats?.cacheStats?.maxSize || 0 }}</template>
          </a-statistic>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<style scoped>
.preset-configs {
  margin-bottom: 16px;
}

.preset-card {
  cursor: pointer;
  transition: all 0.3s ease;
}

.preset-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.preset-description {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.form-item-vertical {
  margin-bottom: 16px;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}

.form-label {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

/* 响应式调整 */
@media (max-width: 768px) {
  .preset-configs .ant-col {
    margin-bottom: 16px;
  }
}
</style>
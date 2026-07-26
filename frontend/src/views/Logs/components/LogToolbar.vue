<template>
  <div class="log-toolbar">
    <div class="toolbar-filters">
      <a-segmented
        :value="localSource"
        :options="sourceOptions"
        aria-label="日志源"
        @change="handleSourceChange"
      />

      <a-select
        v-model:value="localLevel"
        class="level-filter"
        placeholder="全部级别"
        allow-clear
        :options="levelOptions"
        size="middle"
      />

      <a-input-search
        v-model:value="localKeyword"
        class="keyword-filter"
        placeholder="搜索日志"
        allow-clear
        size="middle"
      />
    </div>

    <div class="toolbar-actions">
      <a-space :size="6" wrap>
        <a-tooltip title="立即重新读取当前日志文件">
          <a-button
            size="middle"
            :loading="refreshing"
            aria-label="刷新日志"
            @click="$emit('refresh')"
          >
            <template #icon>
              <ReloadOutlined />
            </template>
            刷新
          </a-button>
        </a-tooltip>

        <a-button
          :type="isRealtime ? 'primary' : 'default'"
          size="middle"
          :aria-label="isRealtime ? '停止实时刷新' : '启用实时刷新'"
          @click="$emit('toggle-realtime')"
        >
          <template #icon>
            <SyncOutlined :spin="isRealtime && !isPaused" />
          </template>
          {{ isRealtime ? '实时刷新' : '已暂停' }}
        </a-button>

        <a-button
          v-if="isRealtime"
          size="middle"
          :aria-label="isPaused ? '继续滚动' : '暂停滚动'"
          @click="$emit('toggle-pause')"
        >
          <template #icon>
            <PauseCircleOutlined v-if="!isPaused" />
            <PlayCircleOutlined v-else />
          </template>
          {{ isPaused ? '继续' : '暂停' }}
        </a-button>

        <a-button size="middle" :disabled="!canCopy" @click="$emit('copy')">
          <template #icon>
            <CopyOutlined />
          </template>
          复制
        </a-button>

        <a-tooltip title="只清空当前视图，不删除磁盘日志">
          <a-button size="middle" :disabled="!canClear" @click="$emit('clear')">
            <template #icon>
              <DeleteOutlined />
            </template>
            清空视图
          </a-button>
        </a-tooltip>

        <a-button :loading="exporting" size="middle" @click="$emit('export')">
          <template #icon>
            <DownloadOutlined />
          </template>
          导出
        </a-button>
      </a-space>
    </div>
  </div>
</template>

<script setup lang="ts">
import {
  CopyOutlined,
  DeleteOutlined,
  DownloadOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  SyncOutlined,
} from '@ant-design/icons-vue'
import { computed } from 'vue'
import type { LogLevel, LogSource } from '../useLogViewer'

interface Props {
  source: LogSource
  level: LogLevel | ''
  keyword: string
  isRealtime: boolean
  isPaused: boolean
  exporting: boolean
  refreshing: boolean
  canCopy: boolean
  canClear: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'update:source', value: LogSource): void
  (e: 'update:level', value: LogLevel | ''): void
  (e: 'update:keyword', value: string): void
  (e: 'toggle-realtime'): void
  (e: 'toggle-pause'): void
  (e: 'refresh'): void
  (e: 'copy'): void
  (e: 'clear'): void
  (e: 'export'): void
}>()

const localSource = computed<LogSource>({
  get: () => props.source,
  set: value => emit('update:source', value),
})

const localLevel = computed<LogLevel | ''>({
  get: () => props.level,
  set: value => emit('update:level', value),
})

const localKeyword = computed({
  get: () => props.keyword,
  set: value => emit('update:keyword', value),
})

const sourceOptions: Array<{ label: string; value: LogSource }> = [
  { label: '后端', value: 'app' },
  { label: '前端', value: 'frontend' },
]

const handleSourceChange = (value: string | number) => {
  if (value === 'app' || value === 'frontend') {
    localSource.value = value
  }
}

const levelOptions: { label: string; value: LogLevel }[] = [
  { label: '错误', value: 'error' },
  { label: '警告', value: 'warning' },
  { label: '信息', value: 'info' },
  { label: '调试', value: 'debug' },
  { label: '跟踪', value: 'trace' },
]
</script>

<style scoped>
.log-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--v6-space-3);
  flex-wrap: wrap;
}

.toolbar-filters,
.toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--v6-space-2);
}

.level-filter {
  width: 118px;
}

.keyword-filter {
  width: min(240px, 32vw);
}

@media (max-width: 900px) {
  .log-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-actions {
    justify-content: flex-start;
  }

  .keyword-filter {
    width: min(100%, 320px);
  }
}
</style>

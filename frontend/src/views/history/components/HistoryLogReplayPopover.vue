<template>
  <a-popover placement="bottomLeft" trigger="click">
    <template #content>
      <div class="replay-popover">
        <div v-for="replay in replays" :key="replay.replayId" class="replay-entry">
          <div class="replay-entry-info">
            <strong>{{ replay.scriptName }}</strong>
            <span>{{ formatBackendDateTime(replay.failedAt) }}</span>
          </div>
          <a-space size="small">
            <a-button size="small" type="link" @click="handleOpenReplay(replay)">
              {{ t('history.replays.play') }}
            </a-button>
            <a-button size="small" type="link" @click="handleLocateReplay(replay)">
              {{ t('history.replays.locate') }}
            </a-button>
          </a-space>
        </div>
      </div>
    </template>
    <a-button size="small" class="replay-trigger">
      <PlayCircleOutlined />
      {{ t('history.replays.associated', { count: replays.length }) }}
    </a-button>
  </a-popover>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { PlayCircleOutlined } from '@ant-design/icons-vue'
import type { ReplayRecord } from '@/types/replay'
import { formatBackendDateTime } from '@/utils/dateDisplay'

defineProps<{ replays: ReplayRecord[] }>()

const { t } = useI18n()

const handleOpenReplay = async (replay: ReplayRecord) => {
  if (!replay.filePath) {
    message.error(t('history.replays.openFileFailed'))
    return
  }
  if (!window.electronAPI?.openFile) {
    message.error(t('history.replays.openFileUnsupported'))
    return
  }
  try {
    const result = await window.electronAPI.openFile(replay.filePath)
    if (result.success) {
      message.success(t('history.replays.played'))
    } else {
      message.error(result.error || t('history.replays.openFileFailed'))
    }
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('history.replays.openFileFailed'))
  }
}

const handleLocateReplay = async (replay: ReplayRecord) => {
  if (!replay.filePath) {
    message.error(t('history.replays.openDirectoryFailed'))
    return
  }
  if (!window.electronAPI?.showItemInFolder) {
    message.error(t('history.replays.openDirectoryUnsupported'))
    return
  }
  try {
    await window.electronAPI.showItemInFolder(replay.filePath)
    message.success(t('history.replays.directoryOpened'))
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('history.replays.openDirectoryFailed'))
  }
}
</script>

<style scoped>
/* 与 HistoryLogModal 头部统计按钮（.drop-btn）同款外观 */
.replay-trigger {
  font-size: 12px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  border: 1px solid var(--ant-color-primary);
  border-radius: 4px;
  padding: 2px 8px;
  height: auto;
}

.replay-trigger:hover {
  background: var(--ant-color-primary);
  color: #fff;
}

.replay-popover {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 280px;
  max-width: 420px;
}

.replay-entry {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.replay-entry:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.replay-entry-info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  gap: 2px;
}

.replay-entry-info strong,
.replay-entry-info span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.replay-entry-info span {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}
</style>

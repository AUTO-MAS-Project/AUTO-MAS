<template>
  <a-modal
    :open="open"
    :title="t('history.replays.title')"
    :footer="null"
    width="900px"
    :body-style="{ maxHeight: '70vh', overflowY: 'auto' }"
    @cancel="$emit('close')"
  >
    <div class="replay-modal-content">
      <div class="replay-toolbar">
        <span class="replay-hint">{{ t('history.replays.hint') }}</span>
        <a-button size="small" :disabled="!directory" @click="openDirectory">
          <template #icon><FolderOpenOutlined /></template>
          {{ t('history.replays.openDirectory') }}
        </a-button>
      </div>

      <a-alert v-if="error" type="error" show-icon :message="error" class="replay-error">
        <template #description>
          <a-button size="small" @click="loadReplays">{{ t('history.replays.retry') }}</a-button>
        </template>
      </a-alert>

      <div v-if="loading" class="replay-loading">
        <a-spin />
      </div>
      <a-empty v-else-if="replays.length === 0" :description="t('history.replays.empty')" />
      <div v-else class="replay-list">
        <div v-for="replay in replays" :key="replay.replayId" class="replay-item">
          <div class="replay-item-main">
            <div class="replay-item-title">
              <span class="replay-script">{{ replay.scriptName }}</span>
              <a-tag v-if="replay.taskId" color="error">{{ t('history.failed') }}</a-tag>
              <a-tag v-else color="blue">{{ t('setting.replay.saveTest') }}</a-tag>
            </div>
            <div class="replay-item-meta">
              <span v-if="replay.userName">
                {{ t('history.replays.account') }}: {{ replay.userName }}
              </span>
              <span>{{ formatBackendDateTime(replay.failedAt) }}</span>
            </div>
            <div class="replay-reason">{{ replay.reason }}</div>
            <div class="replay-file" :title="replay.filePath">{{ replay.filePath }}</div>
          </div>
          <div class="replay-item-actions">
            <a-button
              type="primary"
              size="small"
              :disabled="!replay.filePath"
              @click="playReplay(replay)"
            >
              {{ t('history.replays.play') }}
            </a-button>
            <a-button size="small" :disabled="!replay.filePath" @click="locateReplay(replay)">
              <template #icon><FolderOpenOutlined /></template>
              {{ t('history.replays.locate') }}
            </a-button>
          </div>
        </div>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FolderOpenOutlined } from '@ant-design/icons-vue'
import { useObsReplayApi } from '@/composables/useObsReplayApi'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import type { ReplayRecord } from '@/types/replay'

const props = defineProps<{ open: boolean }>()
defineEmits<{ close: [] }>()
const { t } = useI18n()
const replays = ref<ReplayRecord[]>([])
const directory = ref('')
const { loading, error, listObsReplays } = useObsReplayApi()

const loadReplays = async () => {
  try {
    const response = await listObsReplays()
    replays.value = response.replays ?? []
    directory.value = response.directory ?? ''
  } catch {
    replays.value = []
  }
}

const openFile = async (filePath: string) => {
  if (!window.electronAPI?.openFile) {
    message.error(t('history.replays.openFileUnsupported'))
    return
  }
  const result = await window.electronAPI.openFile(filePath)
  if (!result.success) {
    message.error(result.error || t('history.replays.openFileFailed'))
  }
}

const playReplay = async (replay: ReplayRecord) => {
  if (!replay.filePath) {
    message.error(t('history.replays.openFileFailed'))
    return
  }
  try {
    await openFile(replay.filePath)
  } catch (caught) {
    message.error(caught instanceof Error ? caught.message : t('history.replays.openFileFailed'))
  }
}

const locatePath = async (path: string) => {
  if (!window.electronAPI?.showItemInFolder) {
    message.error(t('history.replays.openDirectoryUnsupported'))
    return
  }
  await window.electronAPI.showItemInFolder(path)
  message.success(t('history.replays.directoryOpened'))
}

const locateReplay = async (replay: ReplayRecord) => {
  if (!replay.filePath) {
    message.error(t('history.replays.openDirectoryFailed'))
    return
  }
  try {
    await locatePath(replay.filePath)
  } catch (caught) {
    message.error(
      caught instanceof Error ? caught.message : t('history.replays.openDirectoryFailed')
    )
  }
}

const openDirectory = async () => {
  if (!directory.value) return
  try {
    await openFile(directory.value)
  } catch (caught) {
    message.error(
      caught instanceof Error ? caught.message : t('history.replays.openDirectoryFailed')
    )
  }
}

watch(
  () => props.open,
  isOpen => {
    if (isOpen) void loadReplays()
  },
  { immediate: true }
)
</script>

<style scoped>
.replay-modal-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.replay-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.replay-hint {
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.replay-error {
  margin-bottom: 4px;
}

.replay-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
}

.replay-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.replay-item {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.replay-item-main {
  min-width: 0;
  flex: 1;
}

.replay-item-title,
.replay-item-meta,
.replay-item-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.replay-item-title {
  margin-bottom: 4px;
}

.replay-script {
  font-weight: 600;
  color: var(--ant-color-text);
}

.replay-item-meta {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  flex-wrap: wrap;
}

.replay-reason {
  margin-top: 6px;
  color: var(--ant-color-error);
  overflow-wrap: anywhere;
}

.replay-file {
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .replay-item {
    flex-direction: column;
  }

  .replay-item-actions {
    width: 100%;
  }
}
</style>

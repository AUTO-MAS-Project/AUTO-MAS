<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { HistoryAttachment } from '@/api'
import { OpenAPI } from '@/api'
import { beginAnalyticsOperation } from '@/utils/analytics'

defineProps<{ attachments: HistoryAttachment[] }>()
const { t } = useI18n()
const failed = ref(new Set<string>())
const playback = new WeakMap<
  EventTarget,
  ReturnType<typeof beginAnalyticsOperation<'replay_tool_finished'>>
>()
// 播放意图与实际开始分开；元数据加载、缓冲恢复不重复计为新回放。
const startReplay = (event: Event) => {
  if (event.currentTarget) {
    playback.set(event.currentTarget, beginAnalyticsOperation('replay_tool_finished'))
  }
}
const finishReplay = (event: Event, outcome: 'success' | 'failure') => {
  if (!event.currentTarget) return
  playback.get(event.currentTarget)?.finish({ action: 'play', outcome })
  playback.delete(event.currentTarget)
}
// 媒体元素直接访问 ID 资源以支持 Range；路径解析与访问边界由后端负责。
const attachmentUrl = (id: string) => `${OpenAPI.BASE}/api/history/attachments/${id}`
const unavailableReason = (reason?: string | null) => {
  const keys: Record<string, string> = {
    missing: 'core.history.attachments.missing',
    quota: 'core.history.attachments.quota',
    directory_unavailable: 'core.history.attachments.directoryUnavailable',
    archive_failed: 'core.history.attachments.archiveFailed',
  }
  return t(keys[reason ?? ''] ?? 'core.history.attachments.unavailable')
}
const markFailed = (id: string, event?: Event) => {
  if (event) finishReplay(event, 'failure')
  failed.value = new Set([...failed.value, id])
}
</script>

<template>
  <a-collapse v-if="attachments.length" class="history-attachments">
    <a-collapse-panel
      key="attachments"
      :header="t('core.history.attachments.title', { count: attachments.length })"
    >
      <div v-for="attachment in attachments" :key="attachment.id" class="history-attachment">
        <div class="attachment-heading">
          <span>{{ attachment.display_name }}</span>
          <a
            v-if="attachment.available"
            :href="`${attachmentUrl(attachment.id)}?download=true`"
            target="_blank"
            rel="noopener noreferrer"
            :download="attachment.display_name"
          >
            {{ t('core.history.attachments.download') }}
          </a>
        </div>
        <a-alert
          v-if="!attachment.available || failed.has(attachment.id)"
          type="warning"
          show-icon
          :message="unavailableReason(attachment.unavailable_reason)"
        />
        <video
          v-else-if="attachment.kind === 'video'"
          :src="attachmentUrl(attachment.id)"
          controls
          preload="metadata"
          @play="startReplay"
          @playing="finishReplay($event, 'success')"
          @error="markFailed(attachment.id, $event)"
        />
        <a-image
          v-else-if="attachment.kind === 'image'"
          :src="attachmentUrl(attachment.id)"
          :alt="attachment.display_name"
          :width="160"
          @error="markFailed(attachment.id)"
        />
      </div>
    </a-collapse-panel>
  </a-collapse>
</template>

<style scoped>
.history-attachments {
  margin: 0 16px 8px;
  max-height: 40vh;
  overflow: auto;
  flex-shrink: 0;
}
.history-attachment + .history-attachment {
  margin-top: 12px;
}
.attachment-heading {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 8px;
  overflow-wrap: anywhere;
}
video {
  display: block;
  max-width: 100%;
  max-height: 260px;
}
</style>

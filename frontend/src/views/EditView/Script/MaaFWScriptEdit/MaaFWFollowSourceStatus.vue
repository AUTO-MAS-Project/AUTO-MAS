<template>
  <div class="follow-source-status">
    <a-tag v-if="sourceForm" color="processing" class="follow-source-tag">
      {{ t('core.edit.maafwSourceFormTag') }}
    </a-tag>
    <span>{{ statusText }}</span>
    <span v-if="!embeddedStatus.sourceExists" class="follow-source-missing">
      {{ t('core.edit.maafwFollowSourceMissing') }}
    </span>
    <a-button
      size="small"
      class="follow-source-sync"
      :loading="syncing"
      :disabled="disabled"
      @click="emit('sync')"
    >
      {{ t('core.edit.maafwFollowSourceSyncNow') }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { MaaFWEmbeddedStatus } from '@/composables/useMaaFWEmbeddedApi'

/**
 * 跟随来源目录时的状态行：跟随哪个目录、上次什么时候从它同步过（运行前自动同步，「立即同步」
 * 手动强制重导）。源码形态的项目必然跟随，这一行放在目录字段下面，前面带「源码形态」标签；
 * 普通项目开了开关时跟着开关放在基本信息末尾。
 */
const props = defineProps<{
  embeddedStatus: MaaFWEmbeddedStatus
  /** 后端没给来源目录时退回脚本配置里的路径 */
  fallbackPath: string | null
  sourceForm: boolean
  syncing: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  sync: []
}>()

const { t } = useI18n()

const statusText = computed(() => {
  const path = props.embeddedStatus.sourcePath || props.fallbackPath || ''
  const syncedAt = props.embeddedStatus.followSourceSyncedAt
  if (!syncedAt) return t('core.edit.maafwFollowSourceNotSynced', { path })
  return t('core.edit.maafwFollowSourceStatus', {
    path,
    time: syncedAt.slice(0, 16).replace('T', ' '),
  })
})
</script>

<style scoped>
.follow-source-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px 8px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--ant-color-primary);
  overflow-wrap: anywhere;
}

.follow-source-tag {
  margin-inline-end: 0;
}

.follow-source-sync {
  font-size: 12px;
}

.follow-source-missing {
  color: var(--ant-color-warning);
}
</style>

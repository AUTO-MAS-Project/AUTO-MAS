<template>
  <!-- ══ 备份文件内容（只读；等宽原文 + 复制）══ -->
  <AppModal
    :open="true"
    @update:open="emit('close')"
    footer="none"
    width="720px"
    :body-style="{ maxHeight: '65vh', overflowY: 'auto' }"
  >
    <template #header>
      <div class="file-modal-title">
        <span class="file-modal-path">{{ item.path }}</span>
        <a-button type="text" size="small" @click="copyFileContent">
          {{ t('core.edit.configRestoreCopy') }}
        </a-button>
      </div>
    </template>
    <a-spin :spinning="fileLoading">
      <p v-if="fileError" class="restore-desc">{{ fileError }}</p>
      <pre v-else class="backup-file-content">{{ fileContent }}</pre>
    </a-spin>
  </AppModal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { AppModal } from '@/components/ui'
import type { BackupFileItem, ConfigRestoreProps } from './configRestore'

const props = defineProps<{
  item: BackupFileItem
  target: string
  time: string
  readFile?: ConfigRestoreProps['api']['readFile']
}>()
const { t } = useI18n()
const emit = defineEmits<{ close: [] }>()
const fileLoading = ref(false)
const fileError = ref('')
const fileContent = ref('')

watch(
  [() => props.item.path, () => props.target, () => props.time],
  async ([path, target, time], _, onCleanup) => {
    let current = true
    onCleanup(() => {
      current = false
    })
    fileLoading.value = true
    fileError.value = ''
    fileContent.value = ''
    try {
      if (!props.readFile) throw new Error(t('core.edit.configRestoreFileUnsupported'))
      const resp = await props.readFile(target, time, path)
      if (!current) return
      if (resp.code !== 200) throw new Error(resp.message || t('core.edit.configRestoreFileFailed'))
      fileContent.value = resp.content ?? ''
    } catch (error) {
      if (current)
        fileError.value =
          error instanceof Error ? error.message : t('core.edit.configRestoreFileFailed')
    } finally {
      if (current) fileLoading.value = false
    }
  },
  { immediate: true }
)
const copyFileContent = async () => {
  if (!fileContent.value) return
  try {
    await navigator.clipboard.writeText(fileContent.value)
    message.success(t('core.edit.configRestoreCopied'))
  } catch {
    message.error(t('core.edit.configRestoreFileFailed'))
  }
}
</script>

<style scoped>
.restore-desc {
  margin: 0 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 文件内容弹窗：标题路径 + 复制按钮；正文等宽原文 */
.file-modal-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-right: 24px;
}

.file-modal-path {
  font-size: 14px;
  word-break: break-all;
}

.backup-file-content {
  margin: 0;
  padding: 12px;
  border-radius: 6px;
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text);
  font-family: var(--font-monospace, 'Consolas', 'Monaco', monospace);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>

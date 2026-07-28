<template>
  <!-- 应用内弹窗组件：展示后端 dialog.request 请求并回传用户选择 -->
  <Modal
    v-model:open="isModalOpen"
    :title="currentDialog?.title || '操作提示'"
    :closable="false"
    :mask-closable="false"
    :keyboard="true"
    centered
    @ok="handleChoice(true)"
    @cancel="handleChoice(false)"
  >
    <p class="modal-message">{{ currentDialog?.message || '' }}</p>
    <!-- 显示队列中还有多少待处理的弹窗 -->
    <p v-if="pendingCount > 0" class="modal-queue-hint">还有 {{ pendingCount }} 条消息待处理</p>
    <template #footer>
      <Button
        v-for="(option, index) in currentDialog?.options || ['确定', '取消']"
        :key="index"
        :type="index === 0 ? 'primary' : 'default'"
        @click="handleChoice(index === 0)"
      >
        {{ option }}
      </Button>
    </template>
  </Modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Modal, Button } from 'ant-design-vue'
import { useAppLifecycle } from '@/composables/useAppLifecycle'
import type { WSDialogRequestData } from '@/services/websocket/types'

const logger = window.electronAPI.getLogger('WebSocket消息')

const { dialogRequests, respondDialog } = useAppLifecycle()

const isModalOpen = ref(false)
const currentDialog = computed<WSDialogRequestData | null>(() => dialogRequests.value[0] ?? null)
const pendingCount = computed(() => Math.max(0, dialogRequests.value.length - 1))

// 激活窗口到前台
const focusWindow = async () => {
  try {
    if (window.electronAPI?.windowFocus) {
      await window.electronAPI.windowFocus()
      logger.info('窗口已激活到前台')
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.warn(`激活窗口失败: ${errorMsg}`)
  }
}

// 有新弹窗请求时打开弹窗并拉起窗口
watch(
  currentDialog,
  dialog => {
    if (dialog) {
      logger.info(`显示弹窗请求: ${dialog.requestId}`)
      isModalOpen.value = true
      void focusWindow()
    } else {
      isModalOpen.value = false
    }
  },
  { immediate: true }
)

// 处理用户选择（第一个选项为 true）
const handleChoice = (choice: boolean) => {
  const dialog = currentDialog.value
  if (!dialog) return
  logger.info(`弹窗已处理: ${dialog.requestId}, choice=${choice}`)
  respondDialog(dialog.requestId, choice)
}
</script>

<style scoped>
.modal-message {
  font-size: 14px;
  line-height: 1.6;
  color: var(--text-secondary, #595959);
  margin: 0;
  word-wrap: break-word;
  white-space: pre-wrap;
}

.modal-queue-hint {
  font-size: 12px;
  color: var(--text-tertiary, #8c8c8c);
  margin-top: 12px;
  margin-bottom: 0;
  padding-top: 8px;
  border-top: 1px solid var(--border-secondary, #f0f0f0);
}
</style>

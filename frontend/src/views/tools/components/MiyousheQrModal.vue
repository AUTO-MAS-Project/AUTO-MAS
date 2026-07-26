<script setup lang="ts">
/**
 * Lane 8：米游社扫码登录弹窗。
 *
 * 从 TabGameSign.vue 拆分。UI 由本组件渲染，状态与逻辑由 useMiyousheQrLogin 管理。
 */
import type { QrStatus } from '../composables/useMiyousheQrLogin'

defineProps<{
  visible: boolean
  status: QrStatus
  statusText: string
  qrUrl: string
}>()

const emit = defineEmits<{
  cancel: []
}>()
</script>

<template>
  <a-modal
    :open="visible"
    title="米游社扫码登录"
    :footer="null"
    :width="360"
    @cancel="emit('cancel')"
  >
    <div class="qr-login-container">
      <!-- 二维码 -->
      <div v-if="qrUrl && status !== 'error'" class="qr-code-wrapper">
        <a-qrcode :value="qrUrl" :size="240" error-level="M" class="qr-code-img" />
      </div>

      <!-- 加载中 -->
      <div v-if="status === 'loading'" class="qr-status">
        <a-spin />
        <span style="margin-left: 8px">{{ statusText }}</span>
      </div>

      <!-- 状态提示 -->
      <div v-if="status !== 'loading'" class="qr-status">
        <span v-if="status === 'waiting'" class="qr-status-primary"> ⏳ {{ statusText }} </span>
        <span v-else-if="status === 'scanned'" class="qr-status-warning">
          📱 {{ statusText }}
        </span>
        <span v-else-if="status === 'exchanging'" class="qr-status-primary">
          ⚙️ {{ statusText }}
        </span>
        <span v-else-if="status === 'done'" class="qr-status-success"> ✅ {{ statusText }} </span>
        <span v-else-if="status === 'error'" class="qr-status-error"> ❌ {{ statusText }} </span>
      </div>

      <div class="qr-hint">打开米游社 APP → 左上角扫码 → 扫描上方二维码</div>
    </div>
  </a-modal>
</template>

<style scoped>
.qr-login-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 16px 0;
}
.qr-code-wrapper {
  margin-bottom: 16px;
}
.qr-code-img {
  width: 240px;
  height: 240px;
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}
.qr-status {
  margin: 12px 0;
  font-size: 14px;
  text-align: center;
}
.qr-status-primary {
  color: var(--ant-color-primary);
}
.qr-status-warning {
  color: var(--ant-color-warning);
}
.qr-status-success {
  color: var(--ant-color-success);
}
.qr-status-error {
  color: var(--ant-color-error);
}
.qr-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-top: 8px;
  text-align: center;
}
</style>

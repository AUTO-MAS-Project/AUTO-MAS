<template>
  <a-modal :open="open" title="米游社扫码登录" :footer="null" :width="360" @cancel="emit('cancel')">
    <div class="qr-login-container">
      <!-- 二维码 -->
      <div
        v-if="qrCodeDataUrl && status !== 'error' && status !== 'expired'"
        class="qr-code-wrapper"
      >
        <img :src="qrCodeDataUrl" alt="扫码登录" class="qr-code-img" />
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
        <span v-else-if="status === 'expired'" class="qr-status-error"> ⚠️ {{ statusText }} </span>
        <span v-else-if="status === 'error'" class="qr-status-error"> ❌ {{ statusText }} </span>
      </div>

      <div v-if="status === 'waiting' || status === 'scanned'" class="qr-hint">
        打开米游社 APP → 左上角扫码 → 扫描上方二维码
      </div>

      <div v-if="status === 'expired' || status === 'error'" class="qr-actions">
        <a-button type="primary" size="small" :loading="loading" @click="emit('retry')">
          <template #icon><ReloadOutlined /></template>
          重新生成二维码
        </a-button>
      </div>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { ReloadOutlined } from '@ant-design/icons-vue'
import type { QrLoginStatus } from './useQrLogin'

/**
 * 米游社扫码登录弹窗：纯展示 + 把用户操作转发出去。
 *
 * 会话状态全部由 useQrLogin 持有，这里刻意不做 v-model:open——
 * 关闭必须走 cancel 事件，让 composable 有机会清定时器、abort 在途请求。
 */
defineProps<{
  open: boolean
  status: QrLoginStatus
  statusText: string
  qrCodeDataUrl: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'cancel'): void

  (e: 'retry'): void
}>()
</script>

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
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.qr-status {
  text-align: center;
  font-size: 14px;
  margin-bottom: 12px;
  min-height: 24px;
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
  text-align: center;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.qr-actions {
  margin-top: 4px;
}
</style>

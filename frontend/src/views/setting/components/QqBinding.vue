<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CheckCircleOutlined, QrcodeOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useQqBinding } from '../useQqBinding'

const props = defineProps<{
  enabled: boolean
  onChange: (enabled: boolean) => Promise<void>
}>()
const { t } = useI18n()
const {
  status,
  statusLoading,
  statusError,
  unbinding,
  open,
  loading,
  checking,
  qrDataUrl,
  state,
  hint,
  loadStatus,
  close,
  start,
  unbind,
} = useQqBinding(props.onChange)
const saving = ref(false)
const setEnabled = async (value: boolean | string | number) => {
  saving.value = true
  try {
    await props.onChange(Boolean(value))
  } finally {
    saving.value = false
  }
}
const failed = computed(() => ['expired', 'error'].includes(state.value))
</script>

<template>
  <a-space direction="vertical" :size="16" class="qq-binding">
    <a-typography-paragraph type="secondary" class="binding-hint">
      {{ t('setting.notify.openclawQqSetupHint') }}
    </a-typography-paragraph>
    <a-alert v-if="statusError" type="error" show-icon :message="statusError">
      <template #action>
        <a-button
          size="small"
          :loading="statusLoading"
          :aria-label="t('setting.notify.openclawQqStatusRetry')"
          @click="loadStatus"
        >
          <ReloadOutlined />
        </a-button>
      </template>
    </a-alert>
    <div class="binding-row">
      <a-space :size="8">
        <a-spin v-if="statusLoading" size="small" />
        <a-tag v-else-if="status" :color="status.connected ? 'success' : 'default'">
          {{
            t(`setting.notify.${status.connected ? 'openclawQqBound' : 'openclawQqUnbound'}`)
          }}
        </a-tag>
        <span>{{ t('setting.notify.openclawQqEnable') }}</span>
        <a-switch
          :checked="props.enabled && !!status?.connected"
          :loading="saving"
          :aria-label="t('setting.notify.openclawQqEnable')"
          :disabled="!status?.connected || statusLoading || unbinding"
          @change="setEnabled"
        />
      </a-space>
      <a-space wrap>
        <a-button
          :type="status?.connected ? 'default' : 'primary'"
          :disabled="statusLoading || unbinding"
          @click="start"
        >
          <template #icon><QrcodeOutlined /></template>
          {{ t(`setting.notify.${status?.connected ? 'openclawQqRebind' : 'openclawQqBind'}`) }}
        </a-button>
        <a-popconfirm
          v-if="status?.connected"
          :title="t('setting.notify.openclawQqUnbindConfirm')"
          @confirm="unbind"
        >
          <a-button danger :loading="unbinding">{{
            t('setting.notify.openclawQqUnbind')
          }}</a-button>
        </a-popconfirm>
      </a-space>
    </div>
  </a-space>
  <a-modal
    :open="open"
    :title="t('setting.notify.openclawQqLoginTitle')"
    :width="400"
    :z-index="900"
    :footer="null"
    :body-style="{ maxHeight: 'calc(100vh - 160px)', overflowY: 'auto' }"
    centered
    @cancel="close"
  >
    <div class="qr-content">
      <div class="qr-stage">
        <a-spin v-if="loading" />
        <CheckCircleOutlined v-else-if="state === 'connected'" class="qr-success" />
        <a-button v-else-if="failed" type="primary" @click="start">
          <template #icon><ReloadOutlined /></template>
          {{ t('setting.notify.openclawQqQrRetry') }}
        </a-button>
        <img
          v-else-if="qrDataUrl"
          :src="qrDataUrl"
          :alt="t('setting.notify.openclawQqQrAlt')"
          width="240"
          height="240"
        />
      </div>
      <a-alert
        :type="failed ? 'error' : state === 'connected' ? 'success' : 'info'"
        :message="hint"
        show-icon
        role="status"
        class="qr-hint"
      />
      <a-button v-if="state === 'connected'" type="primary" block @click="close">{{
        t('common.confirm')
      }}</a-button>
    </div>
  </a-modal>
</template>

<style scoped>
.qq-binding,
.qr-hint {
  width: 100%;
}
.binding-hint {
  margin: 0;
}
.binding-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
.qr-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.qr-stage {
  width: 240px;
  height: 240px;
  display: grid;
  place-items: center;
}
.qr-success {
  font-size: 48px;
  color: var(--ant-color-success);
}
</style>

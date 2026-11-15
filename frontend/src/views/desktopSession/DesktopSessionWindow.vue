<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { EyeOutlined, EyeInvisibleOutlined } from '@ant-design/icons-vue'
import type {
  DesktopSessionRequest,
  DesktopSessionSnapshot,
  DesktopQueueResult,
} from '../../../electron/services/desktopSessionProtocol'

const { t, te } = useI18n()
const preview = ref<HTMLElement | null>(null)
const snapshot = shallowRef<DesktopSessionSnapshot | null>(null)
const pending = shallowRef<DesktopSessionRequest | null>(null)
const readingPending = ref(false)
const results = shallowRef<DesktopQueueResult[]>([])
const mode = ref<DesktopSessionRequest['mode']>('proxy')
const resolution = ref<DesktopSessionRequest['resolution']>('1080p')
const password = ref('')
const passwordDialog = ref(false)
const starting = ref(false)
const checking = ref(true)
const volume = ref(0)
const disposers: (() => void)[] = []
const api = window.electronAPI

const statusText = computed(() => {
  if (snapshot.value?.closing) return t('bootstrap.desktopSession.closing')
  if (checking.value) return t('bootstrap.desktopSession.checking')
  if (snapshot.value?.state === 'blocked') return t('bootstrap.desktopSession.blocked')
  if (starting.value || snapshot.value?.state === 'connecting')
    return t('bootstrap.desktopSession.starting')
  return snapshot.value?.state === 'connected'
    ? t('bootstrap.desktopSession.connected')
    : snapshot.value?.state === 'disconnected'
      ? t('bootstrap.desktopSession.disconnected')
      : t('bootstrap.desktopSession.idle')
})
const running = computed(() => snapshot.value?.state === 'connected')
const blocked = computed(
  () =>
    snapshot.value?.state === 'blocked' ||
    !snapshot.value?.checks.length ||
    snapshot.value.checks.some(item => item.required && !item.ok)
)
const canStart = computed(
  () =>
    !checking.value &&
    !blocked.value &&
    !starting.value &&
    !readingPending.value &&
    !passwordDialog.value &&
    !snapshot.value?.busy &&
    !snapshot.value?.closing
)
const failedChecks = computed(() => snapshot.value?.checks.filter(check => !check.ok) ?? [])

const credentialErrors = new Set([
  'password_required',
  'password_invalid',
  'credential_unreadable',
  'account_mismatch',
])
const errorText = computed(() => {
  const code = snapshot.value?.code
  return code
    ? te(`bootstrap.desktopSession.errors.${code}`)
      ? t(`bootstrap.desktopSession.errors.${code}`)
      : t('bootstrap.desktopSession.operationFailed', { code })
    : ''
})

function reportBounds() {
  if (!preview.value) return
  const { x, y, width, height } = preview.value.getBoundingClientRect()
  if (width >= 1 && height >= 1) {
    api?.desktopSessionBounds?.({
      x: Math.round(x),
      y: Math.round(y),
      width: Math.round(width),
      height: Math.round(height),
    })
  }
}

async function check() {
  checking.value = true
  try {
    snapshot.value = (await api?.desktopSessionCheck?.()) ?? null
  } finally {
    checking.value = false
  }
  await readPending()
}

async function start(secret?: string) {
  if (!canStart.value) return
  const request = pending.value
  starting.value = true
  results.value = []
  reportBounds()
  try {
    const response = await api?.desktopSessionStart?.({
      queueIds: request?.queueIds ?? [],
      mode: mode.value,
      resolution: resolution.value,
      password: secret,
    })
    if (!response) return
    results.value = response.queues
    if (response.code && credentialErrors.has(response.code)) passwordDialog.value = true
    else if (!response.code) pending.value = null
    else if (snapshot.value) snapshot.value = { ...snapshot.value, code: response.code }
  } catch {
    message.error(t('bootstrap.desktopSession.startFailed'))
  } finally {
    starting.value = false
    if (!pending.value) void readPending()
  }
}

function submitPassword() {
  const input = password.value
  password.value = ''
  passwordDialog.value = false
  void start(input)
}

async function readPending() {
  if (readingPending.value || checking.value || starting.value || pending.value) return
  readingPending.value = true
  try {
    const request = await api?.desktopSessionPending?.()
    if (!request) return
    pending.value = request
    if (!running.value) {
      mode.value = request.mode
      resolution.value = request.resolution
    }
  } finally {
    readingPending.value = false
  }
  if (canStart.value) void start()
}

let observer: ResizeObserver | undefined
onMounted(async () => {
  const state = api?.onDesktopSessionState?.(value => {
    snapshot.value = value
  })
  const incoming = api?.onDesktopSessionPending?.(() => void readPending())
  if (state) disposers.push(state)
  if (incoming) disposers.push(incoming)
  if (preview.value) {
    observer = new ResizeObserver(reportBounds)
    observer.observe(preview.value)
  }
  reportBounds()
  await check()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  disposers.forEach(dispose => dispose())
})
</script>

<template>
  <main class="desktop-window">
    <header class="desktop-bar">
      <a-flex align="center" wrap="wrap" gap="small">
        <a-badge
          :status="
            snapshot?.closing || checking || starting
              ? 'processing'
              : blocked
                ? 'error'
                : running
                  ? 'success'
                  : 'default'
          "
          :text="statusText"
        />
        <a-typography-text v-if="running && snapshot?.size" type="secondary">
          {{ snapshot.size?.join(' × ') }}
        </a-typography-text>
        <a-tag v-if="running && snapshot?.windowState === 'hidden'">
          {{ t('bootstrap.desktopSession.hidden') }}</a-tag
        >
        <a-tag v-if="snapshot?.executing && !snapshot?.closing" color="processing">
          {{ t('bootstrap.desktopSession.running') }}</a-tag
        >
      </a-flex>
      <a-space wrap>
        <a-button
          v-if="!running || pending"
          :disabled="!canStart"
          :loading="starting"
          type="primary"
          @click="start()"
        >
          {{
            pending?.queueIds.length
              ? t('bootstrap.desktopSession.startSelected')
              : t('bootstrap.desktopSession.start')
          }}
        </a-button>
        <a-button
          v-if="running && snapshot?.windowState !== 'visible'"
          @click="api?.desktopSessionWindow?.('show')"
        >
          <template #icon><EyeOutlined /></template>
          {{ t('bootstrap.desktopSession.show') }}
        </a-button>
        <a-button v-else-if="running" @click="api?.desktopSessionWindow?.('hide')">
          <template #icon><EyeInvisibleOutlined /></template>
          {{ t('bootstrap.desktopSession.hide') }}
        </a-button>
        <a-button @click="api?.desktopSessionLogs?.()">
          {{ t('bootstrap.desktopSession.viewLogs') }}</a-button
        >
      </a-space>
    </header>
    <div v-if="running" class="desktop-options">
      <a-space wrap>
        <label for="desktop-volume">{{ t('bootstrap.desktopSession.volume') }}</label>
        <a-slider
          id="desktop-volume"
          v-model:value="volume"
          class="volume"
          @change="(value: number) => api?.desktopSessionVolume?.(value)"
        />
      </a-space>
    </div>
    <a-alert
      v-if="snapshot?.closing"
      type="info"
      show-icon
      :message="t('bootstrap.desktopSession.closingHint')"
    />
    <a-alert v-else-if="errorText" type="warning" show-icon :message="errorText" />
    <div ref="preview" class="desktop-viewport">
      <a-flex
        v-if="!running || snapshot?.windowState !== 'visible'"
        vertical
        gap="middle"
        class="empty"
      >
        <a-alert type="warning" show-icon :message="t('bootstrap.desktopSession.experimental')" />
        <template v-if="snapshot?.closing">
          <a-spin />
        </template>
        <template v-else-if="!running">
          <a-button :loading="checking" :disabled="starting" @click="check">
            {{ t('bootstrap.desktopSession.recheck') }}</a-button
          >
          <a-typography-text v-if="!checking && blocked" type="secondary">
            {{ t('bootstrap.desktopSession.recheckHint') }}
          </a-typography-text>
          <a-flex v-if="!checking && failedChecks.length" vertical gap="small">
            <a-typography-text
              v-for="item in failedChecks"
              :key="item.code"
              :type="item.required || item.code === 'hello_only' ? 'danger' : 'secondary'"
            >
              {{
                te(`bootstrap.desktopSession.diagnostics.${item.code}`)
                  ? t(`bootstrap.desktopSession.diagnostics.${item.code}`)
                  : item.code
              }}
            </a-typography-text>
          </a-flex>
        </template>
        <a-typography-text v-else type="secondary">
          {{ t('bootstrap.desktopSession.hiddenHint') }}</a-typography-text
        >
      </a-flex>
    </div>
    <a-flex v-if="results.length" vertical class="dispatch-results">
      <a-typography-text
        v-for="result in results"
        :key="result.queueId"
        :type="result.taskId ? 'success' : 'danger'"
      >
        {{ result.label }} ·
        {{
          result.taskId
            ? t('bootstrap.desktopSession.dispatched')
            : result.code === 'target_missing'
              ? t('bootstrap.desktopSession.targetMissing')
              : result.code === 'power_action'
                ? t('bootstrap.desktopSession.powerAction')
                : result.code === 'unsupported_target'
                  ? t('bootstrap.desktopSession.unsupportedTarget')
                  : t('bootstrap.desktopSession.dispatchFailed')
        }}
      </a-typography-text>
    </a-flex>
    <a-modal
      v-model:open="passwordDialog"
      :title="t('bootstrap.desktopSession.passwordTitle')"
      :ok-text="t('bootstrap.desktopSession.connect')"
      :cancel-text="t('bootstrap.desktopSession.cancel')"
      :ok-button-props="{ disabled: !password }"
      @ok="submitPassword"
      @cancel="password = ''"
    >
      <a-input-password
        v-model:value="password"
        :placeholder="t('bootstrap.desktopSession.password')"
        autocomplete="off"
        @press-enter="password && submitPassword()"
      />
    </a-modal>
  </main>
</template>

<style scoped>
.desktop-window {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  gap: 8px;
  box-sizing: border-box;
}
.desktop-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.desktop-options {
  display: flex;
  padding-block: 4px;
}
.desktop-viewport {
  display: grid;
  min-height: 180px;
  flex: 1;
  overflow: auto;
  background: var(--app-color-bg-container, var(--ant-color-bg-container));
}
.volume {
  min-width: 108px;
}
.empty {
  align-self: center;
  justify-self: center;
  padding: 16px;
  max-width: 680px;
}
.dispatch-results {
  max-height: 100px;
  overflow: auto;
}
</style>

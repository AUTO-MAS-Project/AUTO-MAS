<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { SectionCard } from '@/components/ui'
import DesktopSessionPasswordDialog from './components/DesktopSessionPasswordDialog.vue'
import { finishDesktopLogin, pendingDesktopLogin } from '@/composables/useDesktopSessionLogin'
import { PowerSignal } from '@/api'
import { useI18n } from 'vue-i18n'
import { fetchTaskTargets, type TaskTarget } from '@/composables/useTaskOptions'
import { getConfig, saveConfig } from '@/utils/config'
import {
  MAX_DESKTOP_SESSION_TARGETS,
  type DesktopSessionRequest,
} from '../../../electron/services/desktopSessionProtocol'

const props = defineProps<{ active: boolean }>()
const { t } = useI18n()
const selected = ref<string[]>([])
const targets = ref<TaskTarget[]>([])
const options = computed(() => {
  const atLimit = selected.value.length >= MAX_DESKTOP_SESSION_TARGETS
  const selection = new Set(selected.value)
  return targets.value.map(target => {
    const hasPowerAction = Boolean(
      target.afterAccomplish && target.afterAccomplish !== PowerSignal.NO_ACTION
    )
    const label = `${t(`core.scheduler.scope.${target.kind}`)} · ${target.name}`
    return {
      value: target.value,
      disabled: (hasPowerAction || atLimit) && !selection.has(target.value),
      label: hasPowerAction ? `${label} · ${t('bootstrap.desktopSession.powerAction')}` : label,
    }
  })
})
const loading = ref(false)
const starting = ref(false)
const mode = ref<DesktopSessionRequest['mode']>('proxy')
const resolution = ref<DesktopSessionRequest['resolution']>('1080p')
const supported = ref<boolean>()
const loginDialog = ref(false)
const loginError = ref('')

function closeLogin() {
  loginDialog.value = false
  loginError.value = ''
  finishDesktopLogin('cancelled')
}

watch(
  [pendingDesktopLogin, () => props.active, supported],
  ([waiting, active, available]) => {
    if (!active) {
      if (loginDialog.value) closeLogin()
      return
    }
    if (!waiting) return
    if (available === false) finishDesktopLogin('failed')
    if (available) loginDialog.value = true
  },
  { immediate: true }
)
onBeforeUnmount(closeLogin)

async function submitLogin(password: string) {
  if (starting.value) return
  const waiter = pendingDesktopLogin.value
  starting.value = true
  loginError.value = ''
  try {
    const result = await window.electronAPI.desktopSessionConnectForTask?.({
      password,
      mode: mode.value,
      resolution: resolution.value,
      forTask: !!waiter,
    })
    if (!loginDialog.value) return
    if (result !== 'connected') {
      if (result === 'cancelled') closeLogin()
      else
        loginError.value = t(
          result === 'credentials_rejected'
            ? 'bootstrap.desktopSession.loginRejected'
            : result === 'login_state_save_failed'
              ? 'bootstrap.desktopSession.loginStateSaveFailed'
              : result === 'preview_unavailable'
                ? 'bootstrap.desktopSession.errors.preview_unavailable'
                : 'bootstrap.desktopSession.startFailed'
        )
      return
    }
    loginDialog.value = false
    finishDesktopLogin('connected')
    if (!waiter && selected.value.length) {
      await window.electronAPI.desktopSessionOpen?.({
        queueIds: [...selected.value],
        mode: mode.value,
        resolution: resolution.value,
      })
    }
  } catch {
    if (loginDialog.value) loginError.value = t('bootstrap.desktopSession.startFailed')
    else message.error(t('bootstrap.desktopSession.openFailed'))
  } finally {
    starting.value = false
  }
}

async function loadQueues() {
  loading.value = true
  try {
    targets.value = await fetchTaskTargets()
    selected.value = selected.value.filter(id => options.value.some(item => item.value === id))
  } catch {
    message.error(t('bootstrap.desktopSession.loadTasksFailed'))
  } finally {
    loading.value = false
  }
}

function saveSelection(ids: string[]) {
  selected.value = ids
  // saveConfig 内部已按提交顺序串行落盘，这里不必再排一次队。
  void saveConfig({ desktopSessionQueueIds: ids }).catch(() => {
    message.error(t('bootstrap.desktopSession.saveFailed'))
  })
}

async function open() {
  const launch = window.electronAPI?.desktopSessionOpen
  if (!launch) return
  starting.value = true
  try {
    const result = await launch({
      queueIds: [...selected.value],
      mode: mode.value,
      resolution: resolution.value,
    })
    if (result === 'setup_required') {
      loginError.value = ''
      loginDialog.value = true
    }
  } catch {
    message.error(t('bootstrap.desktopSession.openFailed'))
  } finally {
    starting.value = false
  }
}

onMounted(async () => {
  try {
    supported.value = (await window.electronAPI?.desktopSessionSupported?.()) === true
  } catch {
    message.error(t('bootstrap.desktopSession.loadTasksFailed'))
    supported.value = false
    return
  }
  if (!supported.value) return
  try {
    const saved = (await getConfig()).desktopSessionQueueIds
    if (Array.isArray(saved)) selected.value = saved.filter(id => typeof id === 'string')
  } catch {
    message.warning(t('bootstrap.desktopSession.loadSelectionFailed'))
  }
  await loadQueues()
})
</script>

<template>
  <SectionCard :title="t('bootstrap.desktopSession.title')">
    <a-flex vertical gap="middle">
      <a-alert type="warning" show-icon :message="t('bootstrap.desktopSession.experimental')" />
      <a-alert v-if="supported === false" :message="t('bootstrap.desktopSession.unsupported')" />
      <template v-else-if="supported">
        <a-select
          :value="selected"
          :options="options"
          :loading="loading"
          :disabled="starting"
          mode="multiple"
          option-filter-prop="label"
          :placeholder="t('bootstrap.desktopSession.selectTasks')"
          @dropdown-visible-change="(visible: boolean) => visible && !loading && loadQueues()"
          @change="saveSelection"
        />
        <a-space wrap>
          <a-select
            v-model:value="resolution"
            :aria-label="t('bootstrap.desktopSession.resolution')"
            :options="[
              { value: '1080p', label: '1920 × 1080' },
              { value: 'primary', label: t('bootstrap.desktopSession.primaryResolution') },
            ]"
          />
          <a-select
            v-model:value="mode"
            :aria-label="t('bootstrap.desktopSession.minimizeMode')"
            :options="[
              { value: 'proxy', label: t('bootstrap.desktopSession.proxy') },
              { value: 'native', label: t('bootstrap.desktopSession.native') },
            ]"
          />
        </a-space>
        <a-flex justify="space-between" align="center" gap="middle">
          <a-typography-text type="secondary">{{
            t('bootstrap.desktopSession.emptySelection')
          }}</a-typography-text>
          <a-button
            type="primary"
            :loading="starting"
            :disabled="loading || selected.length > MAX_DESKTOP_SESSION_TARGETS"
            @click="open"
          >
            {{
              selected.length
                ? t('bootstrap.desktopSession.openWithTasks')
                : t('bootstrap.desktopSession.open')
            }}
          </a-button>
        </a-flex>
      </template>
    </a-flex>
    <DesktopSessionPasswordDialog
      v-model:open="loginDialog"
      first-login
      :submitting="starting"
      @submit="submitLogin"
      @cancel="closeLogin"
    >
      <a-typography-text>{{ t('bootstrap.desktopSession.firstLoginHint') }}</a-typography-text>
      <a-alert v-if="loginError" type="error" show-icon :message="loginError" />
    </DesktopSessionPasswordDialog>
  </SectionCard>
</template>

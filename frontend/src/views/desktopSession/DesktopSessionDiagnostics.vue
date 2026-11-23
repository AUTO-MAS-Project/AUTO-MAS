<script setup lang="ts">
import { computed, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import type {
  DesktopSessionRepair,
  DesktopSessionSnapshot,
} from '../../../electron/services/desktopSessionProtocol'

const { snapshot } = defineProps<{
  snapshot: DesktopSessionSnapshot | null
  blocked: boolean
  checking: boolean
  starting: boolean
}>()
const emit = defineEmits<{
  check: []
  'repair-finished': [code: string | undefined]
  'repair-cancelled': []
}>()
const repairing = defineModel<boolean>('repairing', { required: true })
const confirming = defineModel<boolean>('confirming', { required: true })
const { t, te } = useI18n()
const api = window.electronAPI
const repairConfirmation = shallowRef<DesktopSessionRepair[]>([])

function requestRepair() {
  repairConfirmation.value = [...(snapshot?.repairPlan ?? [])]
  confirming.value = true
}

const diagnosticGroups = computed(() => {
  const checks = snapshot?.checks ?? []
  const isAccountCheck = (code: string) =>
    code.startsWith('account_source_') ||
    code.startsWith('microsoft_internet_') ||
    code === 'hello_only'
  return [
    {
      title: 'environmentSection',
      items: checks.filter(check => !check.ok && !isAccountCheck(check.code)),
    },
    { title: 'accountSection', items: checks.filter(check => isAccountCheck(check.code)) },
  ].filter(group => group.items.length)
})

function cancelRepair() {
  confirming.value = false
  emit('repair-cancelled')
}

async function repairEnvironment() {
  const plan = repairConfirmation.value
  if (!plan.length || repairing.value) return
  let code: string | undefined
  repairing.value = true
  confirming.value = false
  try {
    code = await api?.desktopSessionRepair?.(plan)
  } catch {
    code = 'environment_repair_failed'
    message.error(t('bootstrap.desktopSession.errors.environment_repair_failed'))
  } finally {
    repairing.value = false
  }
  emit('repair-finished', code)
}

async function exportLogs() {
  try {
    await api?.desktopSessionExportLogs?.()
  } catch {
    message.error(t('bootstrap.desktopSession.exportLogsFailed'))
  }
}
</script>

<template>
  <template v-if="!snapshot?.closing">
    <a-button :loading="checking" :disabled="starting || repairing" @click="emit('check')">
      {{ t('bootstrap.desktopSession.recheck') }}</a-button
    >
    <a-button
      v-if="snapshot?.repairPlan?.length"
      type="primary"
      :loading="repairing"
      :disabled="checking || starting"
      @click="requestRepair"
    >
      {{ t('bootstrap.desktopSession.tryRepair') }}
    </a-button>
    <!-- TODO: 文档站发布环境修复指南后，在此提供链接。 -->
    <a-alert
      v-if="!checking && blocked && !snapshot?.repairPlan?.length"
      type="warning"
      show-icon
      :message="t('bootstrap.desktopSession.recheckHint')"
    />
    <a-button
      v-if="
        snapshot?.code === 'environment_recheck_failed' ||
        snapshot?.code === 'environment_restore_failed' ||
        snapshot?.code === 'environment_repair_failed'
      "
      @click="exportLogs"
    >
      {{ t('bootstrap.desktopSession.exportLogs') }}
    </a-button>
    <template v-if="!checking">
      <a-flex v-for="group in diagnosticGroups" :key="group.title" vertical gap="small">
        <a-typography-text strong>{{
          t(`bootstrap.desktopSession.${group.title}`)
        }}</a-typography-text>
        <a-typography-text
          v-for="item in group.items"
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
  </template>
  <a-modal
    :open="confirming"
    :title="t('bootstrap.desktopSession.repairTitle')"
    :ok-text="t('bootstrap.desktopSession.repairContinue')"
    :cancel-text="t('bootstrap.desktopSession.cancel')"
    :ok-button-props="{ danger: true }"
    @ok="repairEnvironment"
    @cancel="cancelRepair"
  >
    <a-alert type="warning" show-icon :message="t('bootstrap.desktopSession.repairConfirm')" />
    <ul>
      <li v-for="item in repairConfirmation" :key="item">
        {{ t(`bootstrap.desktopSession.repairs.${item}`) }}
      </li>
    </ul>
  </a-modal>
</template>

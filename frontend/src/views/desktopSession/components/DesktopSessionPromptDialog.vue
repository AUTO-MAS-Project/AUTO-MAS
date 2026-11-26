<script setup lang="ts">
import { computed, onMounted, onScopeDispose, shallowRef } from 'vue'
import { useI18n } from 'vue-i18n'
import AppModal from '@/components/ui/AppModal.vue'
import type {
  DesktopSessionPrompt,
  DesktopSessionPromptAction,
  DesktopSessionPromptTarget,
} from '../../../../electron/services/desktopSessionProtocol'

const { t } = useI18n()
const api = window.electronAPI
const logger = api?.getLogger('桌面分身')
const prompt = shallowRef<DesktopSessionPrompt | null>(null)
const modalOpen = computed({
  get: () => prompt.value !== null,
  set: () => {},
})
let lastRead = 0
let unsubscribe: (() => void) | undefined

const text = (key: string) => t(`bootstrap.desktopSession.${key}`)
const copy = {
  dispatch: ['mainFallbackTitle', 'mainFallbackConfirm'],
  takeover: ['takeoverTitle', 'takeoverConfirm'],
  close: ['closeTitle', 'closeQuestion'],
  'close-adopted': ['closeTitle', 'closeAdoptedQuestion'],
  quit: ['quitWithDesktopTitle', 'quitWithDesktopQuestion'],
  'close-failed': ['closeFailedTitle', 'closeFailed'],
} as const
const title = computed(() => (prompt.value ? text(copy[prompt.value.kind][0]) : ''))
const description = computed(() => (prompt.value ? text(copy[prompt.value.kind][1]) : ''))
const notice = computed(() => prompt.value?.kind === 'close-failed')
const closePrompt = computed(() => {
  const current = prompt.value
  return current?.kind === 'close' || current?.kind === 'close-adopted' || current?.kind === 'quit'
    ? current
    : undefined
})

function taskLabel(task: DesktopSessionPromptTarget): string {
  if (task.targetKind === 'unknown') return task.label
  return `${text(task.targetKind === 'queue' ? 'queueLabel' : 'scriptLabel')} · ${task.label}`
}

async function readPrompt() {
  const id = ++lastRead
  try {
    const current = await api?.desktopSessionGetPrompt?.()
    if (id === lastRead) prompt.value = current ?? null
  } catch (error) {
    logger?.warn('读取分身弹窗失败', error)
  }
}

async function respond(action: DesktopSessionPromptAction) {
  const selected = prompt.value
  if (!selected) return
  prompt.value = null
  try {
    await api?.desktopSessionRespondToPrompt?.(selected.id, action)
  } catch (error) {
    logger?.warn('提交分身弹窗选择失败', error)
  } finally {
    // 关闭窗口可在当前选择送达前替换弹窗，以主进程当前弹窗为准。
    void readPrompt()
  }
}

onMounted(() => {
  unsubscribe = api?.onDesktopSessionPrompt?.(() => void readPrompt())
  void readPrompt()
})
onScopeDispose(() => {
  lastRead++
  unsubscribe?.()
})
</script>

<template>
  <AppModal
    v-model:open="modalOpen"
    :title="title"
    :width="560"
    footer="custom"
    :closable="false"
    :mask-closable="false"
    wrap-class-name="desktop-session-prompt"
    @cancel="respond(notice ? 'acknowledge' : 'cancel')"
  >
    <a-flex v-if="prompt" vertical gap="middle">
      <a-typography-text>{{ description }}</a-typography-text>
      <template v-if="closePrompt">
        <a-flex v-if="closePrompt.risk.activeTasks" vertical>
          <a-typography-text strong>{{ text('closeActiveTasks') }}</a-typography-text>
          <a-typography-text type="secondary">{{ text('closeActiveTasksHint') }}</a-typography-text>
        </a-flex>
        <a-flex v-if="closePrompt.risk.unmanagedPrograms === true" vertical>
          <a-typography-text strong>{{ text('closeUnmanagedPrograms') }}</a-typography-text>
          <a-typography-text type="secondary">{{
            text('closeUnmanagedProgramsHint')
          }}</a-typography-text>
        </a-flex>
        <a-typography-text v-else-if="closePrompt.risk.unmanagedPrograms === null" type="secondary">
          {{ text('closeUnverifiedPrograms') }}
        </a-typography-text>
      </template>
      <section v-if="prompt.kind === 'dispatch'">
        <a-typography-text strong>{{ text('mainFallbackMainGroup') }}</a-typography-text>
        <ul class="task-list">
          <li v-for="(task, index) in prompt.main" :key="index">{{ taskLabel(task) }}</li>
        </ul>
      </section>
      <section v-if="prompt.kind === 'dispatch'">
        <a-typography-text strong>{{ text('mainFallbackDesktopGroup') }}</a-typography-text>
        <ul class="task-list">
          <li v-for="(task, index) in prompt.desktop" :key="index">{{ taskLabel(task) }}</li>
        </ul>
      </section>
    </a-flex>
    <template #footer>
      <a-space v-if="prompt" wrap>
        <a-button v-if="!notice" @click="respond('cancel')">{{ text('cancel') }}</a-button>
        <template v-if="prompt.kind === 'dispatch'">
          <a-button @click="respond('desktop')">{{ text('mainFallbackDesktopOnly') }}</a-button>
          <a-button type="primary" @click="respond('split')">{{
            text('mainFallbackContinue')
          }}</a-button>
        </template>
        <a-button v-if="prompt.kind === 'takeover'" type="primary" @click="respond('takeover')">
          {{ text('takeoverContinue') }}
        </a-button>
        <a-button v-if="prompt.kind === 'close-adopted'" @click="respond('disconnect')">
          {{ text('disconnectOnly') }}
        </a-button>
        <a-button v-if="closePrompt" type="primary" danger @click="respond('logoff')">
          {{ text(closePrompt.kind === 'quit' ? 'quitWithDesktopContinue' : 'closeLogoff') }}
        </a-button>
        <a-button v-if="notice" type="primary" @click="respond('acknowledge')">
          {{ text('acknowledge') }}
        </a-button>
      </a-space>
    </template>
  </AppModal>
</template>

<style scoped>
.task-list {
  margin: 4px 0 0;
  padding-inline-start: 24px;
  overflow-wrap: anywhere;
}

:global(body:not(:has(.title-bar)) .desktop-session-prompt .ant-modal-content) {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 32px);
}

:global(body:not(:has(.title-bar)) .desktop-session-prompt .ant-modal-body) {
  min-height: 0;
  overflow-y: auto;
}

:global(body:not(:has(.title-bar)) .desktop-session-prompt .ant-modal-header),
:global(body:not(:has(.title-bar)) .desktop-session-prompt .ant-modal-footer) {
  flex-shrink: 0;
}
</style>

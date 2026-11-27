<template>
  <div class="env-panel">
    <div class="env-panel-header">
      <span class="env-panel-title">{{ t('core.edit.envPanelTitle') }}</span>
      <!-- interface 是选完目录自动读的、项目不更新就不会变，手动入口只留「准备运行环境」：
           重读 interface 并重新准备（不沿用指纹缓存）；失败时它就是「重试」 -->
      <a-button size="small" :loading="loading" :disabled="disabled" @click="emit('prepare')">
        <template #icon>
          <ToolOutlined />
        </template>
        {{ envTone === 'failed' ? t('core.edit.envRetry') : t('core.edit.prepareRuntimeEnv') }}
      </a-button>
    </div>
    <!-- 任何状态都是「标题行 + 日志框」同一个布局，与「项目更新」的过程面板一致：
         日志常驻，结论（状态词 + 阶段 / 版本 / 失败原因）是框里最后一行，整行一个颜色 -->
    <div ref="logBoxRef" class="env-log-box maafw-log-box">
      <div v-for="(line, index) in envLogs" :key="index" class="maafw-log-line">
        {{ line }}
      </div>
      <div v-if="agentsLine" class="maafw-log-line">{{ agentsLine }}</div>
      <div
        v-if="envTone !== 'idle'"
        class="maafw-log-status"
        :class="`maafw-log-status--${envTone}`"
      >
        <LoadingOutlined v-if="envTone === 'running'" spin />
        <CheckCircleOutlined v-else-if="envTone === 'success'" />
        <CloseCircleOutlined v-else />
        <span>{{ envStatusText }}</span>
        <!-- 引导形态下「项目更新」是后面的步骤、这时走不到，只指向全局设置里的代理 -->
        <div v-if="envTone === 'failed'" class="env-status-hint">
          {{ isWizard ? t('core.edit.envFailedHintWizard') : t('core.edit.envFailedHint') }}
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, ref, watch } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'
import type { MaaFWEnvOutcome } from './sectionProps'

/**
 * 脚本页基础信息里的「运行环境」面板：标题行（右侧「准备运行环境」按钮）+ 常驻的定高日志框，
 * 结论写在日志框最后一行。
 */
const props = defineProps<{
  envPreparing: boolean
  envReady: boolean
  envFailed: boolean
  /** 准备中是后端当前阶段那句话；成功后是 MaaFramework 版本；失败时是错误原因。 */
  envMessage: string
  envPercent: number | null
  envLogs: string[]
  envAgents: Array<{ runtimeKind?: string | null; executable: string }>
  envOutcome: MaaFWEnvOutcome | null
  /** 引导形态：失败提示不指向本页后面步骤里的设置 */
  isWizard?: boolean
  /** 「准备运行环境」按钮转圈 */
  loading: boolean
  disabled: boolean
}>()

const emit = defineEmits<{
  prepare: []
}>()

const { t } = useI18n()

const envTone = computed<'idle' | 'running' | 'success' | 'failed'>(() => {
  if (props.envPreparing) return 'running'
  if (props.envFailed) return 'failed'
  if (props.envReady) return 'success'
  return 'idle'
})

// 状态词就是结论本身：准备完成 / 更新完成 / 无需更新 / 失败，不再另起一条绿色 alert
const envPhaseLabel = computed(() => {
  switch (envTone.value) {
    case 'running': {
      const label = t('core.edit.envStatusPreparing')
      return props.envPercent === null ? label : `${label} ${Math.round(props.envPercent)}%`
    }
    case 'failed':
      return t('core.edit.envStatusFailed')
    case 'success':
      if (props.envOutcome === 'cached') return t('core.edit.envStatusCached')
      if (props.envOutcome === 'updated') return t('core.edit.envStatusUpdated')
      return t('core.edit.envStatusPrepared')
    default:
      return ''
  }
})

// 失败时后端那句原因就是整行；其余是「状态词 · 阶段或版本」
const envStatusText = computed(() => {
  if (envTone.value === 'failed') return props.envMessage || envPhaseLabel.value
  return [envPhaseLabel.value, props.envMessage].filter(Boolean).join('  ·  ')
})

// Agent 运行时类型（后端的内部枚举）→ 给人看的叫法；不认识的值原样显示
const RUNTIME_KIND_LABEL_KEYS: Record<string, string> = {
  isolated_venv: 'core.edit.envRuntimeIsolatedVenv',
  project_python: 'core.edit.envRuntimeProjectPython',
  project_binary: 'core.edit.envRuntimeProjectBinary',
  shared_runtime: 'core.edit.envRuntimeSharedRuntime',
  external: 'core.edit.envRuntimeExternal',
}
const runtimeKindLabel = (kind: string | null | undefined) => {
  if (!kind) return t('core.common.unknown')
  const key = RUNTIME_KIND_LABEL_KEYS[kind]
  return key ? t(key) : kind
}

// 已就绪的组件不进结论行，写在日志末尾
const agentsLine = computed(() => {
  if (envTone.value !== 'success' || props.envAgents.length === 0) return ''
  const agents = [...new Set(props.envAgents.map(a => runtimeKindLabel(a.runtimeKind)))].join(
    t('core.edit.maafwListSeparator')
  )
  return `${t('core.edit.envReadyAgents')}: ${agents}`
})

// 新日志或结论进来就贴到底部；用户手动往上翻时不打断
const logBoxRef = ref<HTMLElement | null>(null)
watch(
  () => [props.envLogs.length, agentsLine.value, envStatusText.value],
  async () => {
    const box = logBoxRef.value
    const nearBottom = !box || box.scrollHeight - box.scrollTop - box.clientHeight < 40
    await nextTick()
    const current = logBoxRef.value
    if (current && nearBottom) current.scrollTop = current.scrollHeight
  }
)
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
/* 面板本身不画框：标题行 + 日志框 */
.env-panel {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.env-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  min-height: 24px;
}

/* 与左边项目名同一字号字重，两边标题齐平 */
.env-panel-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ant-color-text);
}

/* 定高、内部滚动：日志再多也不把页面撑长；与「项目更新」过程面板的日志框同高 */
.env-log-box {
  height: 170px;
}

/* 失败时的指路跟在结论后面另起一行 */
.env-status-hint {
  flex-basis: 100%;
  color: var(--ant-color-text-secondary);
}
</style>

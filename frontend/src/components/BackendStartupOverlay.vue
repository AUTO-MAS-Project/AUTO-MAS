<script setup lang="ts">
import { computed } from 'vue'
import {
  CheckOutlined,
  CloseOutlined,
  CopyOutlined,
  FileTextOutlined,
  LoadingOutlined,
  PoweroffOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import type { AppStartupStage, AppStartupState } from './app-shell/types.ts'

type StageVisualState = 'complete' | 'active' | 'pending' | 'error'

interface StartupStageDefinition {
  key: AppStartupStage
  title: string
  description: string
}

const props = defineProps<{
  visible: boolean
  state: AppStartupState
}>()

const emit = defineEmits<{
  (e: 'retry'): void
  (e: 'copy-diagnostics'): void
  (e: 'open-logs'): void
  (e: 'exit'): void
}>()

const stages: StartupStageDefinition[] = [
  { key: 'renderer', title: '界面就绪', description: '正在准备应用界面' },
  { key: 'runtime', title: '运行环境', description: '正在校验运行时与本地依赖' },
  { key: 'backend', title: '后端与插件', description: '正在加载配置、插件和服务' },
  { key: 'connection', title: '实时连接', description: '正在建立本地 WebSocket 连接' },
  { key: 'ready', title: '准备完成', description: '即将进入主界面' },
]

const isFailure = computed(() => ['offline', 'timeout', 'failed'].includes(props.state.status))

const fallbackStageByStatus: Record<AppStartupState['status'], AppStartupStage> = {
  initializing: 'renderer',
  'backend-starting': 'backend',
  connected: 'ready',
  offline: 'connection',
  reconnecting: 'connection',
  timeout: 'connection',
  failed: 'backend',
  closing: 'backend',
}

const activeStage = computed<AppStartupStage>(
  () => props.state.stage || fallbackStageByStatus[props.state.status]
)

const activeStageIndex = computed(() =>
  Math.max(
    0,
    stages.findIndex(stage => stage.key === activeStage.value)
  )
)

const visibleStages = computed(() =>
  stages.map((stage, index) => {
    let visualState: StageVisualState = 'pending'
    if (props.state.status === 'connected' || index < activeStageIndex.value) {
      visualState = 'complete'
    } else if (index === activeStageIndex.value) {
      visualState = isFailure.value ? 'error' : 'active'
    }

    return { ...stage, visualState }
  })
)

const currentStage = computed(() => stages[activeStageIndex.value])

const statusTitle = computed(() => {
  if (isFailure.value) return '启动需要处理'
  if (props.state.status === 'closing') return '正在安全退出'
  return '正在准备 AUTO-MAS'
})

const statusDetail = computed(
  () => props.state.detail || props.state.message || currentStage.value.description
)

const handleRetry = () => emit('retry')
const handleCopy = () => emit('copy-diagnostics')
const handleOpenLogs = () => emit('open-logs')
const handleExit = () => emit('exit')
</script>

<template>
  <Teleport to="body">
    <Transition name="startup-fade">
      <div
        v-if="visible"
        class="backend-startup-overlay"
        role="dialog"
        aria-modal="true"
        aria-labelledby="startup-title"
        aria-describedby="startup-desc"
      >
        <section class="startup-card">
          <div class="startup-brand" aria-label="AUTO-MAS">
            <img src="@/assets/AUTO-MAS.ico" alt="" class="startup-logo" />
            <span class="brand-text">AUTO-MAS</span>
            <span class="brand-divider" aria-hidden="true">/</span>
            <span class="brand-caption">启动检查</span>
          </div>

          <header class="startup-heading">
            <h2 id="startup-title" class="startup-title">{{ statusTitle }}</h2>
            <p id="startup-desc" class="startup-detail">{{ statusDetail }}</p>
          </header>

          <ol class="startup-stage-list" aria-label="启动阶段">
            <li
              v-for="stage in visibleStages"
              :key="stage.key"
              class="startup-stage"
              :class="`startup-stage--${stage.visualState}`"
            >
              <span class="startup-stage-marker" aria-hidden="true">
                <CheckOutlined v-if="stage.visualState === 'complete'" />
                <CloseOutlined v-else-if="stage.visualState === 'error'" />
                <LoadingOutlined v-else-if="stage.visualState === 'active'" class="stage-spinner" />
                <span v-else class="stage-dot"></span>
              </span>
              <span class="startup-stage-copy">
                <strong>{{ stage.title }}</strong>
                <small>{{ stage.description }}</small>
              </span>
            </li>
          </ol>

          <div v-if="isFailure" class="startup-diagnostic" role="status" aria-live="polite">
            <strong>停在「{{ currentStage.title }}」</strong>
            <span>{{ statusDetail }}</span>
          </div>

          <div v-if="isFailure" class="startup-actions" role="group" aria-label="启动失败操作">
            <button
              v-if="state.canRetry"
              type="button"
              class="action-button primary"
              aria-label="重试启动"
              @click="handleRetry"
            >
              <ReloadOutlined aria-hidden="true" />
              重试
            </button>
            <button
              v-if="state.canOpenLogs"
              type="button"
              class="action-button"
              aria-label="打开日志目录"
              @click="handleOpenLogs"
            >
              <FileTextOutlined aria-hidden="true" />
              打开日志
            </button>
            <button
              v-if="state.canCopyDiagnostics"
              type="button"
              class="action-button"
              aria-label="复制诊断信息"
              @click="handleCopy"
            >
              <CopyOutlined aria-hidden="true" />
              复制诊断信息
            </button>
            <button
              v-if="state.canExit"
              type="button"
              class="action-button danger"
              aria-label="安全退出应用"
              @click="handleExit"
            >
              <PoweroffOutlined aria-hidden="true" />
              安全退出
            </button>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.backend-startup-overlay {
  position: fixed;
  inset: 0;
  z-index: var(--v6-z-global-overlay);
  display: grid;
  place-items: center;
  padding: var(--v6-space-6);
  background: color-mix(in srgb, var(--v6-color-window) 88%, transparent);
  backdrop-filter: blur(18px) saturate(112%);
  -webkit-backdrop-filter: blur(18px) saturate(112%);
}

.startup-card {
  width: min(680px, 100%);
  padding: clamp(var(--v6-space-5), 4vw, var(--v6-space-8));
  border: 1px solid var(--v6-color-border);
  border-radius: calc(var(--v6-radius-card) + var(--v6-space-2));
  background: color-mix(in srgb, var(--v6-color-surface) 88%, transparent);
  box-shadow: var(--v6-shadow-lg);
  backdrop-filter: var(--v6-backdrop-vibrancy);
  -webkit-backdrop-filter: var(--v6-backdrop-vibrancy);
}

.startup-brand {
  display: flex;
  align-items: center;
  gap: var(--v6-space-2);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  line-height: 1;
}

.startup-logo {
  width: 22px;
  height: 22px;
}

.brand-text {
  color: var(--v6-color-text);
  font-weight: var(--v6-font-weight-semibold);
}

.brand-divider {
  color: var(--v6-color-text-tertiary);
}

.startup-heading {
  margin-top: clamp(var(--v6-space-5), 5vw, var(--v6-space-7));
}

.startup-title {
  margin: 0;
  color: var(--v6-color-text);
  font-size: clamp(var(--v6-font-size-xl), 3.6vw, var(--v6-font-size-2xl));
  font-weight: var(--v6-font-weight-semibold);
  letter-spacing: -0.025em;
  line-height: var(--v6-line-height-tight);
}

.startup-detail {
  margin: var(--v6-space-2) 0 0;
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  line-height: var(--v6-line-height-normal);
  overflow-wrap: anywhere;
}

.startup-stage-list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: var(--v6-space-2);
  margin: clamp(var(--v6-space-6), 6vw, var(--v6-space-8)) 0 0;
  padding: 0;
  list-style: none;
}

.startup-stage {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: var(--v6-space-2);
  color: var(--v6-color-text-tertiary);
}

.startup-stage-marker {
  width: 22px;
  height: 22px;
  flex: 0 0 22px;
  display: inline-grid;
  place-items: center;
  margin-top: 1px;
  border: 1px solid var(--v6-color-border-strong);
  border-radius: var(--v6-radius-full);
  background: color-mix(in srgb, var(--v6-color-surface) 76%, transparent);
  font-size: 11px;
}

.startup-stage-copy {
  min-width: 0;
  display: grid;
  gap: 2px;
}

.startup-stage-copy strong {
  overflow: hidden;
  color: inherit;
  font-size: var(--v6-font-size-sm);
  font-weight: var(--v6-font-weight-medium);
  line-height: 1.35;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.startup-stage-copy small {
  min-height: 2.6em;
  overflow: hidden;
  color: inherit;
  font-size: var(--v6-font-size-xs);
  line-height: 1.3;
}

.startup-stage--complete {
  color: var(--v6-color-success);
}

.startup-stage--complete .startup-stage-marker {
  border-color: var(--v6-color-success-border);
  background: var(--v6-color-success-bg);
}

.startup-stage--active {
  color: var(--v6-color-text);
}

.startup-stage--active .startup-stage-marker {
  border-color: color-mix(in srgb, var(--v6-color-info) 56%, var(--v6-color-border));
  color: var(--v6-color-info);
  background: var(--v6-color-info-bg);
}

.startup-stage--error {
  color: var(--v6-color-error);
}

.startup-stage--error .startup-stage-marker {
  border-color: var(--v6-color-error-border);
  background: var(--v6-color-error-bg);
}

.stage-spinner {
  animation: spin 1s linear infinite;
}

.stage-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--v6-radius-full);
  background: currentColor;
  opacity: 0.58;
}

.startup-diagnostic {
  display: grid;
  gap: var(--v6-space-1);
  margin-top: var(--v6-space-6);
  padding: var(--v6-space-3) 0 0;
  border-top: 1px solid var(--v6-color-border-subtle);
  color: var(--v6-color-text-secondary);
  font-size: var(--v6-font-size-sm);
  line-height: var(--v6-line-height-normal);
}

.startup-diagnostic strong {
  color: var(--v6-color-error);
  font-weight: var(--v6-font-weight-semibold);
}

.startup-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--v6-space-2);
  margin-top: var(--v6-space-5);
}

.action-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--v6-space-1);
  min-height: 34px;
  padding: 0 var(--v6-space-3);
  border: 1px solid var(--v6-color-border-strong);
  border-radius: var(--v6-radius-control);
  background: color-mix(in srgb, var(--v6-color-surface) 88%, transparent);
  color: var(--v6-color-text);
  font: inherit;
  font-size: var(--v6-font-size-sm);
  cursor: pointer;
  transition:
    background var(--v6-motion-fast) var(--v6-ease-out),
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    color var(--v6-motion-fast) var(--v6-ease-out);
}

.action-button:hover {
  border-color: var(--v6-color-info);
  background: var(--v6-color-info-bg);
  color: var(--v6-color-info);
}

.action-button:focus-visible {
  outline: none;
  box-shadow: var(--v6-focus-ring);
}

.action-button.primary {
  border-color: var(--v6-color-info);
  background: var(--v6-color-info);
  color: var(--v6-color-text-inverse);
}

.action-button.primary:hover {
  background: var(--v6-color-text-link-hover);
  color: var(--v6-color-text-inverse);
}

.action-button.danger {
  color: var(--v6-color-error);
  border-color: var(--v6-color-error-border);
}

.action-button.danger:hover {
  border-color: var(--v6-color-error);
  background: var(--v6-color-error-bg);
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }

  to {
    transform: rotate(360deg);
  }
}

.startup-fade-enter-active,
.startup-fade-leave-active {
  transition: opacity var(--v6-motion-base) var(--v6-ease-out);
}

.startup-fade-enter-from,
.startup-fade-leave-to {
  opacity: 0;
}

@media (max-width: 720px) {
  .startup-stage-list {
    grid-template-columns: 1fr;
    gap: var(--v6-space-3);
  }

  .startup-stage-copy small {
    min-height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .stage-spinner {
    animation: none;
  }

  .startup-fade-enter-active,
  .startup-fade-leave-active,
  .action-button {
    transition: none;
  }
}
</style>

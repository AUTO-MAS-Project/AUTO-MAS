<!-- 项目更新的过程面板：标题行（包类型 + 检查 / 更新按钮）和下面的日志框，进度与结论都写在日志框里 -->
<template>
  <div class="update-process">
    <div class="update-process-header">
      <span class="update-process-title">{{ t('core.edit.updateProcess') }}</span>
      <a-tag v-if="packageKindLabel" class="update-process-kind">{{ packageKindLabel }}</a-tag>
      <!-- 检查 / 更新的入口就放在过程面板标题行右侧：点完按钮，结果就在下面这个日志框里，
           与「运行环境」面板把「准备运行环境」放标题行右侧同一口径 -->
      <div class="update-process-actions">
        <!-- 检查与更新共用下面这个过程面板：一个在跑时另一个不能点，否则后点的那次把面板
             重置并先以终态收尾，正在跑的那次之后的进度全被当成迟到事件丢掉 -->
        <a-button
          size="small"
          :loading="updateChecking"
          :disabled="updateApplying"
          @click="emit('check-update')"
          >{{ t('core.edit.checkUpdates2') }}</a-button
        >
        <!-- apply 的响应沿用检查结果的 installable=true，更新成功后按钮还挂在那；updated 为真时隐藏。
             打开页面时接回的后台更新没有检查结果，进行中照样显示（转圈） -->
        <a-button
          v-if="
            updateApplying || (updateResult && updateResult.installable && !updateResult.updated)
          "
          type="primary"
          size="small"
          :loading="updateApplying"
          :disabled="updateChecking"
          @click="emit('apply-update')"
        >
          {{ t('core.edit.update') }}
        </a-button>
      </div>
    </div>
    <!-- 日志框一直在：面板高度不随「有没有开始更新」跳动；结论作为最后一行用强调色写出来 -->
    <div ref="logBoxRef" class="update-log-box maafw-log-box">
      <div
        v-if="updateProgress.phase === 'idle'"
        class="update-log-line maafw-log-line maafw-log-line--empty"
      >
        {{ t('core.edit.updateProcessPlaceholder') }}
      </div>
      <div
        v-for="(line, index) in updateProgress.logs"
        :key="index"
        class="update-log-line maafw-log-line"
        :class="{ 'update-log-line--alert': line.alert }"
      >
        {{ line.text }}
      </div>
      <div
        v-if="updateProgress.phase !== 'idle'"
        class="update-log-status maafw-log-status"
        :class="`maafw-log-status--${summaryTone}`"
      >
        <LoadingOutlined v-if="summaryTone === 'running'" spin class="update-log-status-icon" />
        <CheckCircleOutlined v-else-if="summaryTone === 'success'" class="update-log-status-icon" />
        <CloseCircleOutlined v-else class="update-log-status-icon" />
        <span>{{ statusText }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, nextTick, ref, watch } from 'vue'
import { CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined } from '@ant-design/icons-vue'
import type { MaaFWUpdateResult } from '@/composables/useMaaFWUpdateApi'
import {
  formatAppliedFiles,
  formatDownloadSize,
  formatDownloadSpeed,
  formatExtractedFiles,
  formatExtractedSize,
  progressBarPercent,
  type MaaFWUpdateProgressPhase,
  type MaaFWUpdateProgressState,
} from './updateProgress'

const { t } = useI18n()

const props = defineProps<{
  updateChecking: boolean
  updateApplying: boolean
  updateResult: MaaFWUpdateResult | null
  updateProgress: MaaFWUpdateProgressState
}>()

const emit = defineEmits<{
  'check-update': []
  'apply-update': []
}>()

const sourceLabel = (source: string | null | undefined) => {
  const normalized = (source ?? '').trim().toLowerCase()
  if (!normalized) return ''
  if (normalized === 'mirrorchyan') return t('core.edit.sourceMirrorChyan')
  if (normalized === 'github') return t('core.edit.sourceGithub')
  return source ?? ''
}

// 检查结果的补充信息：版本名 + 实际下载来源，跟在面板状态行下面。旧后端不返回这些字段时整行不显示。
const updateResultDetail = computed(() => {
  const result = props.updateResult
  if (!result) return ''
  const parts: string[] = []
  const versionName = result.versionName?.trim() || result.latestVersion?.trim() || ''
  if (versionName) parts.push(`${t('core.edit.updateResultVersion')}: ${versionName}`)
  const source = sourceLabel(result.source)
  if (source) parts.push(`${t('core.edit.updateResultSource')}: ${source}`)
  return parts.join('  ·  ')
})

const PHASE_LABEL_KEYS: Record<Exclude<MaaFWUpdateProgressPhase, 'idle'>, string> = {
  checking: 'core.edit.updatePhaseChecking',
  downloading: 'core.edit.updatePhaseDownloading',
  extracting: 'core.edit.updatePhaseExtracting',
  preparing: 'core.edit.updatePhasePreparing',
  applying: 'core.edit.updatePhaseApplying',
  validating: 'core.edit.updatePhaseValidating',
  completed: 'core.edit.updatePhaseCompleted',
  rolled_back: 'core.edit.updatePhaseRolledBack',
  failed: 'core.edit.updatePhaseFailed',
}

const phaseLabel = computed(() => {
  const phase = props.updateProgress.phase
  if (phase === 'idle') return ''
  const label = t(PHASE_LABEL_KEYS[phase])
  const percent = progressBarPercent(props.updateProgress)
  return percent === null ? label : `${label} ${percent}%`
})

const summaryTone = computed<'running' | 'success' | 'failed'>(() => {
  const phase = props.updateProgress.phase
  if (phase === 'completed') return 'success'
  if (phase === 'failed' || phase === 'rolled_back') return 'failed'
  return 'running'
})

// 下载阶段给「已下 / 总量 · 速度」，解压阶段给「n/m 个文件 · 已解压 / 总量」，覆盖阶段给
// 「n/m 个文件」，其余阶段给后端那句描述。
const summaryDetail = computed(() => {
  const state = props.updateProgress
  if (state.phase === 'downloading') {
    const parts = [formatDownloadSize(state), formatDownloadSpeed(state)].filter(Boolean)
    return parts.join('  ·  ')
  }
  if (state.phase === 'extracting') {
    const files = formatExtractedFiles(state)
    const parts = [
      files ? t('core.edit.updateFilesApplied', { files }) : '',
      formatExtractedSize(state),
    ].filter(Boolean)
    return parts.length ? parts.join('  ·  ') : state.message
  }
  if (state.phase === 'applying') {
    const files = formatAppliedFiles(state)
    return files ? t('core.edit.updateFilesApplied', { files }) : state.message
  }
  return state.message
})

// 整行一个颜色。进行中给「阶段 · 进度」，结束后直接用后端那句结论（已是最新 / 更新完成 /
// 失败原因），再跟上版本与下载来源；不另加一个「已完成」之类的状态词
const statusText = computed(() => {
  const state = props.updateProgress
  if (summaryTone.value === 'running') {
    return [phaseLabel.value, summaryDetail.value].filter(Boolean).join('  ·  ')
  }
  const parts = [state.message || phaseLabel.value]
  if (state.phase === 'completed' && updateResultDetail.value) parts.push(updateResultDetail.value)
  return parts.filter(Boolean).join('  ·  ')
})

const packageKindLabel = computed(() => {
  const kind = props.updateProgress.packageKind
  if (kind === 'full') return t('core.edit.updatePackageFull')
  if (kind === 'incremental') return t('core.edit.updatePackageIncremental')
  return ''
})

// 新日志进来时贴到底部，用户手动往上翻时不打扰
const logBoxRef = ref<HTMLElement | null>(null)
watch(
  () => [props.updateProgress.logs.length, props.updateProgress.phase, statusText.value],
  async () => {
    const box = logBoxRef.value
    if (!box) return
    const nearBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 40
    await nextTick()
    if (nearBottom) box.scrollTop = box.scrollHeight
  }
)
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
/* 面板本身不画框、不铺底色：标题 + 日志框就够了 */
.update-process {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.update-process-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* 与基础信息区「运行环境」面板标题同一字号字重 */
.update-process-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ant-color-text);
}

.update-process-kind {
  margin-inline-end: 0;
}

/* 按钮靠右贴边，用 margin-left 顶开，标题和包类型标签仍然紧挨在左边 */
.update-process-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

/* 定高、内部滚动：日志再长面板也不长个，左列小框才对得齐 */
.update-log-box {
  height: 170px;
}

/* 要用户留意的行（如项目发错版本号）整行标红 */
.update-log-line--alert {
  color: var(--ant-color-error);
}
</style>

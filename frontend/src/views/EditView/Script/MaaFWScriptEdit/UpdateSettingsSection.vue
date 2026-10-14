<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('edit.projectUpdate') }}</h3>
    </div>
    <a-alert
      v-if="isAutoUpdateDisabled"
      class="update-alert"
      type="warning"
      show-icon
      :message="autoUpdateDisabledMessage"
    />
    <a-row :gutter="24" class="update-config-row">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.autoUpdateModeTip')">
              <span class="form-label">
                {{ t('edit.autoUpdateMode') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Update.AutoUpdateMode"
            size="large"
            :disabled="isAutoUpdateDisabled"
            :options="autoUpdateModeOptions"
            @change="(value: string | number) => emit('change', 'Update', 'AutoUpdateMode', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.updateSourceTip')">
              <span class="form-label">
                {{ t('edit.updateSource') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-select
            v-model:value="maafwConfig.Update.Source"
            size="large"
            :options="updateSourceOptions"
            @change="(value: string | number) => emit('change', 'Update', 'Source', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="t('edit.updateChannel')">
          <a-select
            v-model:value="maafwConfig.Update.Channel"
            size="large"
            :options="updateChannelOptions"
            @change="(value: string | number) => emit('change', 'Update', 'Channel', value)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24" class="update-config-row">
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <!-- 说明全在问号里：悬停看文案，点问号直接去 Mirror 酱取 CDK；输入框下面不再放解释行，
                 只在「选了 Mirror 酱却没填」时冒一行警告 -->
            <a-tooltip>
              <template #title>
                {{ t('edit.cdkTip') }}
                <a :href="MIRRORCHYAN_CDK_URL" class="tooltip-link" @click="handleExternalLink">{{
                  t('edit.cdkGetLink')
                }}</a>
              </template>
              <span class="form-label">
                {{ t('edit.mirrorchyanCdk') }}
                <a
                  :href="MIRRORCHYAN_CDK_URL"
                  class="help-link"
                  :aria-label="t('edit.cdkGetLink')"
                  @click.stop="handleExternalLink"
                >
                  <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                </a>
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="maafwConfig.Update.MirrorChyanCDK"
            :placeholder="t('edit.cdkPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            @blur="handleCdkBlur"
          />
          <div v-if="isCdkMissingForMirror" class="form-hint form-hint--warning">
            {{ t('edit.cdkMissingForMirror') }}
          </div>
          <!-- CDK 还剩多久到期，或者 CDK 有什么问题；查询中、查不到、没有到期时间时整行不显示 -->
          <div
            v-if="cdkHintText"
            class="form-hint"
            :class="{ 'form-hint--warning': cdkHint?.warning }"
          >
            {{ cdkHintText }}
          </div>
          <div v-if="cdkPrefilled" class="form-hint">{{ t('edit.cdkPrefilledFromGlobal') }}</div>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('edit.proxyAddressTip')">
              <span class="form-label">
                {{ t('edit.proxyAddress') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="maafwConfig.Update.ProxyAddress"
            :placeholder="t('edit.proxyAddressPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            @blur="emit('change', 'Update', 'ProxyAddress', maafwConfig.Update.ProxyAddress)"
          />
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 检查 / 更新的结果不再单独弹一条绿色 alert：过程面板的状态行已经用强调色写了同一句；
         只有 CDK 有问题时才额外提示，那是面板里没有的信息 -->
    <a-alert
      v-if="updateResult && !updateError && cdkWarningMessage"
      class="update-alert"
      type="warning"
      show-icon
      :message="cdkWarningMessage"
    />

    <!-- 左边「当前版本」「GitHub」上下两个小框，右边一个更新过程面板；日志框定高、内部滚动 -->
    <div v-if="previewData" class="update-info-grid">
      <div class="update-info-column">
        <div class="update-info-item">
          <div class="update-info-label">{{ t('edit.currentVersion') }}</div>
          <div class="update-info-value">
            {{ previewData.project.version || t('edit.notDeclared') }}
          </div>
        </div>
        <div class="update-info-item">
          <div class="update-info-label">GitHub</div>
          <div class="update-info-value">
            {{ previewData.project.github || t('edit.notDeclared') }}
          </div>
        </div>
      </div>
      <div class="update-process">
        <div class="update-process-header">
          <span class="update-process-title">{{ t('edit.updateProcess') }}</span>
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
              >{{ t('edit.checkUpdates2') }}</a-button
            >
            <!-- apply 的响应沿用检查结果的 installable=true，更新成功后按钮还挂在那；updated 为真时隐藏 -->
            <a-button
              v-if="updateResult && updateResult.installable && !updateResult.updated"
              type="primary"
              size="small"
              :loading="updateApplying"
              :disabled="updateChecking"
              @click="emit('apply-update')"
            >
              {{ t('edit.update') }}
            </a-button>
          </div>
        </div>
        <!-- 日志框一直在：面板高度不随「有没有开始更新」跳动；结论作为最后一行用强调色写出来 -->
        <div ref="logBoxRef" class="update-log-box">
          <div
            v-if="updateProgress.phase === 'idle'"
            class="update-log-line update-log-line--empty"
          >
            {{ t('edit.updateProcessPlaceholder') }}
          </div>
          <div v-for="(line, index) in updateProgress.logs" :key="index" class="update-log-line">
            {{ line }}
          </div>
          <div
            v-if="updateProgress.phase !== 'idle'"
            class="update-log-status"
            :class="`update-log-status--${summaryTone}`"
          >
            <LoadingOutlined v-if="summaryTone === 'running'" spin class="update-log-status-icon" />
            <CheckCircleOutlined
              v-else-if="summaryTone === 'success'"
              class="update-log-status-icon"
            />
            <CloseCircleOutlined v-else class="update-log-status-icon" />
            <span>{{ statusText }}</span>
          </div>
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
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import {
  resolveCdkHint,
  resolveCdkWarning,
  type MaaFWAutoUpdateMode,
} from '@/composables/useMaaFWProjectUpdate'
import { useMaaFWUpdateApi, type MaaFWMirrorCdkState } from '@/composables/useMaaFWUpdateApi'
import { handleExternalLink } from '@/utils/openExternal'
import {
  formatAppliedFiles,
  formatDownloadSize,
  formatDownloadSpeed,
  formatExtractedFiles,
  formatExtractedSize,
  progressBarPercent,
  type MaaFWUpdateProgressPhase,
} from './updateProgress'
import type {
  MaaFWScriptUpdateSectionEmits,
  MaaFWScriptUpdateSectionProps,
} from '../../MaaFWFlavor/sectionContracts'

const MIRRORCHYAN_CDK_URL = 'https://mirrorchyan.com?source=automas_script_update'

const { t } = useI18n()

// props / 事件的契约在 sectionContracts（特调替换这个分节时按同一份契约接收）
const props = defineProps<MaaFWScriptUpdateSectionProps>()

const emit = defineEmits<MaaFWScriptUpdateSectionEmits>()

const autoUpdateModeOptions = computed<Array<{ label: string; value: MaaFWAutoUpdateMode }>>(() => [
  { label: t('edit.autoUpdateModeOff'), value: 'Off' },
  { label: t('edit.autoUpdateModeBeforeRun'), value: 'BeforeRun' },
  { label: t('edit.autoUpdateModeAfterRun'), value: 'AfterRun' },
])

// 自动更新为什么用不了：没声明版本，或没有接入 Mirror 酱、又不能只看 GitHub
// （下载源不是 GitHub，或 interface 没声明 github 仓库）
const autoUpdateDisabledMessage = computed(() =>
  props.previewData?.project.version
    ? t('edit.maafwNoMirrorchyanRid')
    : t('edit.thisScriptDeclaresNo')
)

const sourceLabel = (source: string | null | undefined) => {
  const normalized = (source ?? '').trim().toLowerCase()
  if (!normalized) return ''
  if (normalized === 'mirrorchyan') return t('edit.sourceMirrorChyan')
  if (normalized === 'github') return t('edit.sourceGithub')
  return source ?? ''
}

// 检查结果的补充信息：版本名 + 实际下载来源，跟在面板状态行下面。旧后端不返回这些字段时整行不显示。
const updateResultDetail = computed(() => {
  const result = props.updateResult
  if (!result) return ''
  const parts: string[] = []
  const versionName = result.versionName?.trim() || result.latestVersion?.trim() || ''
  if (versionName) parts.push(`${t('edit.updateResultVersion')}: ${versionName}`)
  const source = sourceLabel(result.source)
  if (source) parts.push(`${t('edit.updateResultSource')}: ${source}`)
  return parts.join('  ·  ')
})

// 选了 Mirror 酱却没填 CDK：下载注定失败，后端不会替用户改走 GitHub，输入框下方直接提醒。
const isCdkMissingForMirror = computed(
  () =>
    props.maafwConfig.Update.Source === 'MirrorChyan' &&
    !props.maafwConfig.Update.MirrorChyanCDK.trim()
)

// absent 且后端没给原因时不再提示：没填 CDK 已由输入框下那行说过；填了 CDK 时 absent 只是
// 查版本那次没带 CDK 留下的状态（version_only 查询固定不带），不代表用户没填
const cdkWarningMessage = computed(() => {
  const warning = resolveCdkWarning(props.updateResult, props.maafwConfig.Update.Source)
  if (!warning) return ''
  if (warning.message) return warning.message
  if (warning.status === 'absent') return ''
  return t('edit.cdkStatusIssue', { status: warning.status })
})

// ---- CDK 输入框下的剩余时间 / CDK 状态 ----
// 更新检查查版本从不带 CDK（不占下载额度），填错了平时看不出来；这里单独查一次：页面读完配置
// 后、从 MAS 设置预填之后、失焦且值变了时各查一次。结果只对查询时的那个值有效，输入框的值
// 改了（含清空）就先不显示，失焦再查；旧请求晚回来按序号丢掉。不管下载源选的是哪个都查。

const { queryMaaFWMirrorCdk } = useMaaFWUpdateApi()
const cdkState = ref<(MaaFWMirrorCdkState & { cdk: string }) | null>(null)
let cdkQuerySeq = 0
let lastQueriedCdk = ''

const currentCdk = () => (props.maafwConfig.Update.MirrorChyanCDK ?? '').trim()

const refreshCdkState = async () => {
  const cdk = currentCdk()
  if (!cdk) {
    cdkQuerySeq += 1
    lastQueriedCdk = ''
    cdkState.value = null
    return
  }
  if (!props.scriptId || cdk === lastQueriedCdk) return
  lastQueriedCdk = cdk
  const seq = ++cdkQuerySeq
  const state = await queryMaaFWMirrorCdk(props.scriptId, cdk)
  if (seq !== cdkQuerySeq) return
  cdkState.value = state ? { ...state, cdk } : null
  // 没查成（网络 / 服务端异常）的下次失焦再试
  if (!state || state.status === 'error') lastQueriedCdk = ''
}

const handleCdkBlur = () => {
  emit('change', 'Update', 'MirrorChyanCDK', props.maafwConfig.Update.MirrorChyanCDK)
  void refreshCdkState()
}

watch(
  () => props.scriptId,
  () => void refreshCdkState(),
  { immediate: true }
)
// 预填发生在页面读完配置之后，那时本分节已经挂上了
watch(
  () => props.cdkPrefilled,
  prefilled => {
    if (prefilled) void refreshCdkState()
  }
)

const cdkHint = computed(() => {
  const state = cdkState.value
  if (!state || state.cdk !== currentCdk()) return null
  return resolveCdkHint(state.status, state.expiredTime)
})

const cdkHintText = computed(() => {
  const hint = cdkHint.value
  if (!hint) return ''
  const date = hint.dateText ?? ''
  const remaining =
    hint.daysLeft === null || !date
      ? ''
      : hint.daysLeft < 1
        ? t('edit.cdkHintLessThanDay', { date })
        : t('edit.cdkHintRemaining', { days: hint.daysLeft, date })
  switch (hint.kind) {
    case 'remaining':
      return remaining
    case 'expired':
      return date ? t('edit.cdkHintExpiredOn', { date }) : t('edit.cdkHintExpired')
    case 'invalid':
      return t('edit.cdkHintInvalid')
    case 'quota':
      return remaining ? t('edit.cdkHintQuotaRemaining', { remaining }) : t('edit.cdkHintQuota')
    case 'mismatched':
      return t('edit.cdkHintMismatched')
    case 'blocked':
      return t('edit.cdkHintBlocked')
  }
  return ''
})

// ---- 更新过程面板 ----

const PHASE_LABEL_KEYS: Record<Exclude<MaaFWUpdateProgressPhase, 'idle'>, string> = {
  checking: 'edit.updatePhaseChecking',
  downloading: 'edit.updatePhaseDownloading',
  extracting: 'edit.updatePhaseExtracting',
  preparing: 'edit.updatePhasePreparing',
  applying: 'edit.updatePhaseApplying',
  validating: 'edit.updatePhaseValidating',
  completed: 'edit.updatePhaseCompleted',
  rolled_back: 'edit.updatePhaseRolledBack',
  failed: 'edit.updatePhaseFailed',
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
      files ? t('edit.updateFilesApplied', { files }) : '',
      formatExtractedSize(state),
    ].filter(Boolean)
    return parts.length ? parts.join('  ·  ') : state.message
  }
  if (state.phase === 'applying') {
    const files = formatAppliedFiles(state)
    return files ? t('edit.updateFilesApplied', { files }) : state.message
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
  if (kind === 'full') return t('edit.updatePackageFull')
  if (kind === 'incremental') return t('edit.updatePackageIncremental')
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

<style scoped>
.form-section {
  margin-bottom: 40px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 20px;
  background: var(--ant-color-text-quaternary);
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
}

.modern-input {
  border-radius: 8px;
}

.update-alert {
  margin-bottom: 16px;
}

.form-hint {
  margin-top: 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.5;
}

.form-hint--warning {
  color: var(--ant-color-warning);
}

/* 问号本身就是去 Mirror 酱的入口：样式与旁边的问号一致，只多一个手型 */
.help-link {
  display: inline-flex;
  color: inherit;
  cursor: pointer;
}

/* 提示气泡是深底白字，链接不能用主色（看不见），下划线就够 */
.tooltip-link {
  margin-left: 4px;
  color: inherit;
  text-decoration: underline;
}

.update-config-row {
  margin-top: 4px;
}

/* 左窄右宽：左列上下两个信息小框撑满面板高度，右列是过程面板；拉窄窗口时按比例缩 */
.update-info-grid {
  display: grid;
  grid-template-columns: minmax(180px, 1fr) 3fr;
  gap: 12px;
  align-items: stretch;
  margin-top: 8px;
}

.update-info-column {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.update-info-item {
  flex: 1;
  min-width: 0;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.update-info-label {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.update-info-value {
  margin-top: 4px;
  color: var(--ant-color-text);
  font-size: 14px;
  overflow-wrap: anywhere;
}

/* 面板本身不画框、不铺底色：标题 + 日志框就够了 */
.update-process {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

@media (max-width: 768px) {
  .update-info-grid {
    grid-template-columns: 1fr;
  }

  .update-info-column {
    flex-direction: row;
  }
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
  overflow-y: auto;
  padding: 8px 10px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  font-family: var(--ant-font-family-code, monospace);
  font-size: 12px;
  line-height: 1.6;
}

.update-log-line {
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--ant-color-text-secondary);
}

.update-log-line--empty {
  color: var(--ant-color-text-tertiary);
}

/* 结论就是日志的最后一行，整行一个强调色：成功绿、失败红、进行中主色，代替原来单独的一条结果 alert */
.update-log-status {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}

.update-log-status--running {
  color: var(--ant-color-primary);
}

.update-log-status--success {
  color: var(--ant-color-success);
}

.update-log-status--failed {
  color: var(--ant-color-error);
}
</style>

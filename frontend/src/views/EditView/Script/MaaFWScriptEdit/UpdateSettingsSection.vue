<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <MaaFWFormSection :title="t('core.edit.projectUpdate')">
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
            <a-tooltip :title="t('core.edit.autoUpdateModeTip')">
              <span class="form-label">
                {{ t('core.edit.autoUpdateMode') }}
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
            <a-tooltip :title="t('core.edit.updateSourceTip')">
              <span class="form-label">
                {{ t('core.edit.updateSource') }}
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
        <a-form-item :label="t('core.edit.updateChannel')">
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
                {{ t('core.edit.cdkTip') }}
                <a :href="MIRRORCHYAN_CDK_URL" class="tooltip-link" @click="handleExternalLink">{{
                  t('core.edit.cdkGetLink')
                }}</a>
              </template>
              <span class="form-label">
                {{ t('core.edit.mirrorchyanCdk') }}
                <a
                  :href="MIRRORCHYAN_CDK_URL"
                  class="help-link"
                  :aria-label="t('core.edit.cdkGetLink')"
                  @click.stop="handleExternalLink"
                >
                  <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
                </a>
              </span>
            </a-tooltip>
          </template>
          <a-input-password
            v-model:value="maafwConfig.Update.MirrorChyanCDK"
            :placeholder="t('core.edit.cdkPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            @blur="handleCdkBlur"
          />
          <div v-if="isCdkMissingForMirror" class="form-hint form-hint--warning">
            {{ t('core.edit.cdkMissingForMirror') }}
          </div>
          <!-- CDK 还剩多久到期，或者 CDK 有什么问题；查询中、查不到、没有到期时间时整行不显示 -->
          <div
            v-if="cdkHintText"
            class="form-hint"
            :class="{ 'form-hint--warning': cdkHint?.warning }"
          >
            {{ cdkHintText }}
          </div>
          <div v-if="cdkPrefilled" class="form-hint">
            {{ t('core.edit.cdkPrefilledFromGlobal') }}
          </div>
        </a-form-item>
      </a-col>
      <a-col :span="12">
        <a-form-item>
          <template #label>
            <a-tooltip :title="t('core.edit.proxyAddressTip')">
              <span class="form-label">
                {{ t('core.edit.proxyAddress') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <a-input
            v-model:value="maafwConfig.Update.ProxyAddress"
            :placeholder="t('core.edit.proxyAddressPlaceholder')"
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
          <div class="update-info-label">{{ t('core.edit.currentVersion') }}</div>
          <div class="update-info-value">
            {{ previewData.project.version || t('core.edit.notDeclared') }}
          </div>
        </div>
        <div class="update-info-item">
          <div class="update-info-label">GitHub</div>
          <div class="update-info-value">
            {{ previewData.project.github || t('core.edit.notDeclared') }}
          </div>
        </div>
      </div>
      <UpdateProcessPanel
        :update-checking="updateChecking"
        :update-applying="updateApplying"
        :update-result="updateResult"
        :update-progress="updateProgress"
        @check-update="emit('check-update')"
        @apply-update="emit('apply-update')"
      />
    </div>
  </MaaFWFormSection>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref, watch } from 'vue'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import {
  resolveCdkHint,
  resolveCdkWarning,
  type MaaFWAutoUpdateMode,
} from '@/composables/useMaaFWProjectUpdate'
import { useMaaFWUpdateApi, type MaaFWMirrorCdkState } from '@/composables/useMaaFWUpdateApi'
import { handleExternalLink } from '@/utils/openExternal'
import MaaFWFormSection from './MaaFWFormSection.vue'
import UpdateProcessPanel from './UpdateProcessPanel.vue'
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
  { label: t('core.edit.autoUpdateModeOff'), value: 'Off' },
  { label: t('core.edit.autoUpdateModeBeforeRun'), value: 'BeforeRun' },
])

// 自动更新为什么用不了：没声明版本，或没有接入 Mirror 酱、又不能只看 GitHub
// （下载源不是 GitHub，或 interface 没声明 github 仓库）
const autoUpdateDisabledMessage = computed(() =>
  props.previewData?.project.version
    ? t('core.edit.maafwNoMirrorchyanRid')
    : t('core.edit.thisScriptDeclaresNo')
)

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
  return t('core.edit.cdkStatusIssue', { status: warning.status })
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
        ? t('core.edit.cdkHintLessThanDay', { date })
        : t('core.edit.cdkHintRemaining', { days: hint.daysLeft, date })
  switch (hint.kind) {
    case 'remaining':
      return remaining
    case 'expired':
      return date ? t('core.edit.cdkHintExpiredOn', { date }) : t('core.edit.cdkHintExpired')
    case 'invalid':
      return t('core.edit.cdkHintInvalid')
    case 'quota':
      return remaining
        ? t('core.edit.cdkHintQuotaRemaining', { remaining })
        : t('core.edit.cdkHintQuota')
    case 'mismatched':
      return t('core.edit.cdkHintMismatched')
    case 'blocked':
      return t('core.edit.cdkHintBlocked')
  }
  return ''
})
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
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

@media (max-width: 768px) {
  .update-info-grid {
    grid-template-columns: 1fr;
  }

  .update-info-column {
    flex-direction: row;
  }
}
</style>

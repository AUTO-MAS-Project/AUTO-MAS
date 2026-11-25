<!-- eslint-disable vue/no-mutating-props -- This form section edits the parent-owned reactive draft; persistence stays in the parent. -->
<template>
  <MaaFWFormSection :title="t('core.edit.basicInfo')" :icon="AppstoreOutlined">
    <a-row :gutter="24">
      <!-- 还没导入、引导卡片在显示时目录字段不出现：选目录的按钮与说明只留卡片那一套，
           导入后字段显示副本路径 -->
      <a-col :xs="24" :md="12">
        <a-form-item name="name">
          <template #label>
            <span class="form-label">{{ t('core.edit.scriptName') }}</span>
          </template>
          <a-input
            v-model:value="formData.name"
            :placeholder="t('core.edit.enterScriptName')"
            class="modern-input"
            @blur="emit('change', 'Info', 'Name', formData.name)"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="!guideOwnsImport" :xs="24" :md="12">
        <a-form-item name="path" :rules="rules.path">
          <template #label>
            <a-tooltip :title="directoryHint">
              <span class="form-label">
                {{ sourceDirectoryLabel || t('core.edit.localProjectDirectory') }}
                <QuestionCircleOutlined class="help-icon" aria-hidden="true" />
              </span>
            </a-tooltip>
          </template>
          <!-- 导入完成后目录就固定在副本位置（运行、更新都在那里），字段与按钮一起锁死；
               要换项目请新建脚本。来源目录只在导入前选一次，之后只在运行环境日志里体现。 -->
          <a-input-group compact class="path-input-group">
            <a-input
              :value="displayedPath"
              :placeholder="sourcePlaceholder || t('core.edit.pickActualMfwProject')"
              class="path-input"
              readonly
              aria-readonly="true"
            />
            <a-tooltip :title="directoryLocked ? t('core.edit.maafwDirectoryLockedHint') : ''">
              <a-button
                class="path-button"
                :disabled="directoryLocked || interfaceLoading || updateApplying || embeddedBusy"
                @click="emit('select-path')"
              >
                <template #icon>
                  <FolderOpenOutlined />
                </template>
                {{ t('core.edit.pickProjectDirectory') }}
              </a-button>
            </a-tooltip>
          </a-input-group>
          <!-- 导入几十到几百 MB 时进度条顶在字段下面，别让用户对着一个转圈干等。
               首次导入时这个字段不显示，进度条在下面的引导卡片里 -->
          <div v-if="embeddedBusy" class="import-progress">
            <a-progress
              :percent="importPercent ?? 0"
              :status="importPercent === 100 ? 'success' : 'active'"
              size="small"
            />
            <span class="import-progress-text">{{
              importMessage || t('core.edit.maafwImportingCopy')
            }}</span>
          </div>
          <div v-else-if="importError" class="import-error">
            {{ importError }}
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <!-- 源码形态的项目必然跟随来源目录：状态行与「立即同步」是必要信息，紧跟在目录字段下面 -->
    <MaaFWFollowSourceStatus
      v-if="directoryLocked && sourceForm"
      class="follow-source-top"
      :embedded-status="embeddedStatus"
      :fallback-path="maafwConfig.Info.Path"
      :source-form="true"
      :syncing="embeddedBusy"
      :disabled="interfaceLoading || updateApplying || embeddedBusy"
      @sync="emit('sync-source')"
    />

    <!-- 左边项目名 · 版本 · 简介和一行计数，右边运行环境（平时一行结论，日志收着） -->
    <div v-if="previewData" class="interface-body">
      <div class="interface-summary">
        <div class="interface-summary-head">
          <span class="interface-summary-title">{{ previewProjectTitle }}</span>
          <!-- 版本与简介各自有就显示：没写 version 的老项目照样显示简介 -->
          <span v-if="projectSubtitle" class="interface-summary-subtitle">
            {{ projectSubtitle }}
          </span>
        </div>
        <div class="interface-summary-stats">{{ interfaceStatsText }}</div>
      </div>
      <MaaFWEnvPanel
        :env-preparing="envPreparing"
        :env-ready="envReady"
        :env-failed="envFailed"
        :env-message="envMessage"
        :env-percent="envPercent"
        :env-logs="envLogs"
        :env-agents="envAgents"
        :env-outcome="envOutcome"
        :is-wizard="isWizard"
        :loading="interfaceLoading || envPreparing"
        :disabled="!maafwConfig.Info.Path || updateApplying || embeddedBusy"
        @prepare="emit('preview-interface')"
      />
    </div>
    <div v-else-if="interfaceLoading" class="interface-loading">
      <a-spin :tip="t('core.edit.readingInterfaceJson')">
        <a-alert
          type="info"
          show-icon
          :message="t('core.edit.loadingMfwInterface')"
          :description="t('core.edit.readingControllersResourcesTasks')"
        />
      </a-spin>
    </div>
    <!-- 已导入（目录锁定）却没读到 interface：项目还在，只是这次没读出来。给出原因和「重试」，
         不给选目录——那会绕开目录锁把副本换成别的项目 -->
    <div v-else-if="directoryLocked" class="interface-guide-card">
      <WarningOutlined
        class="interface-guide-icon interface-guide-icon--warning"
        aria-hidden="true"
      />
      <h3>{{ t('core.edit.maafwPreviewFailed') }}</h3>
      <p v-if="previewError" class="interface-guide-error">{{ previewError }}</p>
      <a-button
        type="primary"
        :disabled="!maafwConfig.Info.Path || updateApplying || embeddedBusy"
        @click="emit('preview-interface')"
      >
        <template #icon>
          <ReloadOutlined />
        </template>
        {{ t('core.edit.envRetry') }}
      </a-button>
    </div>
    <div v-else class="interface-guide-card">
      <InboxOutlined class="interface-guide-icon" aria-hidden="true" />
      <h3>{{ t('core.edit.pickMfwProject') }}</h3>
      <p>{{ t('core.edit.pickProjectDirectoryContaining') }}</p>
      <a-button
        v-if="!embeddedBusy"
        type="primary"
        :disabled="interfaceLoading || updateApplying"
        @click="emit('select-path')"
      >
        <template #icon>
          <FolderOpenOutlined />
        </template>
        {{ t('core.edit.pickProjectDirectory') }}
      </a-button>
      <div v-else class="import-progress import-progress--guide">
        <a-progress
          :percent="importPercent ?? 0"
          :status="importPercent === 100 ? 'success' : 'active'"
          size="small"
        />
        <span class="import-progress-text">{{
          importMessage || t('core.edit.maafwImportingCopy')
        }}</span>
      </div>
      <p v-if="!embeddedBusy && (importError || previewError)" class="interface-guide-error">
        {{ importError || previewError }}
      </p>
    </div>
    <!-- 导入后才显示跟随开关；源码形态强制开启，状态行仍在目录字段下面 -->
    <div v-if="directoryLocked" class="follow-source">
      <SwitchTile
        :checked="followSource"
        :title="t('core.edit.maafwFollowSource')"
        :description="
          sourceForm ? t('core.edit.maafwSourceFormHint') : t('core.edit.maafwFollowSourceHint')
        "
        :disabled="sourceForm || interfaceLoading || updateApplying || embeddedBusy"
        @change="handleFollowSourceChange"
      />
      <MaaFWFollowSourceStatus
        v-if="followSource && !sourceForm"
        :embedded-status="embeddedStatus"
        :fallback-path="maafwConfig.Info.Path"
        :source-form="false"
        :syncing="embeddedBusy"
        :disabled="interfaceLoading || updateApplying || embeddedBusy"
        @sync="emit('sync-source')"
      />
    </div>
  </MaaFWFormSection>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { SwitchTile } from '@/components/ui'
import {
  AppstoreOutlined,
  FolderOpenOutlined,
  InboxOutlined,
  QuestionCircleOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons-vue'
import type {
  MaaFWScriptBasicInfoSectionEmits,
  MaaFWScriptBasicInfoSectionProps,
} from './sectionProps'
import MaaFWEnvPanel from './MaaFWEnvPanel.vue'
import MaaFWFollowSourceStatus from './MaaFWFollowSourceStatus.vue'
import MaaFWFormSection from './MaaFWFormSection.vue'

const { t } = useI18n()

// props / 事件见 sectionProps.ts
const props = defineProps<MaaFWScriptBasicInfoSectionProps>()

const emit = defineEmits<MaaFWScriptBasicInfoSectionEmits>()

// 副本一旦建好，目录就固定在副本位置：字段里显示副本路径而不是来源目录，按钮锁死。
// 副本还没建（新脚本刚建、或副本丢了来源也没了）时才允许选目录。
const directoryLocked = computed(() => props.embeddedStatus.copyHealthy)
const displayedPath = computed(() =>
  directoryLocked.value ? props.embeddedStatus.copyPath : props.formData.path
)
// 还没导入、引导卡片在显示：导入进度与失败原因都放在卡片里（按钮就在那），字段下面不再重复
const guideOwnsImport = computed(
  () => !props.previewData && !props.interfaceLoading && !directoryLocked.value
)
const directoryHint = computed(() =>
  directoryLocked.value
    ? t('core.edit.maafwDirectoryLockedHint')
    : props.sourceHint || t('core.edit.pickMfwProjectDirectory')
)

// 跟随来源目录（开发者模式）：开关只落盘配置，同步在下一次运行前由后端做（或点「立即同步」）。
// 源码形态的项目始终跟随（后端按导入报告认），开关显示为开着且不可改。
const sourceForm = computed(() => Boolean(props.embeddedStatus.sourceForm))
const followSource = computed(
  () => sourceForm.value || Boolean(props.maafwConfig.Embedded?.FollowSource)
)
const handleFollowSourceChange = (checked: boolean | string | number) => {
  const value = Boolean(checked)
  props.maafwConfig.Embedded.FollowSource = value
  emit('change', 'Embedded', 'FollowSource', value)
}

// 表头副标题：版本 · 简介，哪个没有就省掉哪个
const projectSubtitle = computed(() => {
  const project = props.previewData?.project
  return [project?.version, project?.description]
    .map(value => value?.trim())
    .filter(Boolean)
    .join(' · ')
})

// 计数收成一行小字：任务 12 · 预设 3 · ……
const interfaceStatsText = computed(() =>
  props.interfaceStats.map(item => `${item.label} ${item.value}`).join(' · ')
)
</script>

<style scoped src="./maafwSection.css"></style>

<style scoped>
.import-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 8px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.import-progress :deep(.ant-progress) {
  flex: 1;
  margin: 0;
}

.import-progress-text {
  white-space: nowrap;
}

.import-progress--guide {
  width: 100%;
  max-width: 520px;
  margin: 0 auto;
}

.import-error {
  margin-top: 8px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--ant-color-error);
  overflow-wrap: anywhere;
}

/* 开发者开关在本节最后：与上面的概览 / 运行环境隔开一点 */
.follow-source {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 16px;
}

/* 源码形态的状态行紧跟目录字段：收掉表单项的下距，与字段贴近 */
.follow-source-top {
  margin: -8px 0 16px;
}

.path-input {
  /* flex 子项默认 min-width:auto，窄屏下会被内容撑住不肯让位，
     把两个按钮挤出圆角容器；显式归零才能正常收缩。 */
  min-width: 0;
}

.path-button {
  /* 两个按钮共用一套样式：各自带左分隔线，与输入框拼成一条完整控件。 */
  flex: 0 0 auto;
  white-space: nowrap;
}

/* 自定义底色盖掉了 antd 的禁用态：导入后目录锁死时按钮要看得出点不了 */
.path-button:disabled,
.path-button.ant-btn-disabled {
  color: var(--ant-color-text-disabled);
  background: var(--ant-color-bg-container-disabled);
  cursor: not-allowed;
}

/* 左边项目名与一行计数，右边运行环境面板；各自按内容高，顶边对齐 */
.interface-body {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px 24px;
  align-items: start;
  margin-top: 8px;
}

.interface-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

/* 项目名在左，版本 · 简介跟在右边 */
.interface-summary-head {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 4px 12px;
}

.interface-summary-title {
  font-size: 16px;
  font-weight: 700;
  line-height: 1.5;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
}

.interface-summary-subtitle {
  min-width: 0;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  overflow-wrap: anywhere;
}

.interface-summary-stats {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.interface-guide-card {
  display: flex;
  max-width: 480px;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  margin: 8px auto 0;
  padding: 28px 24px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  text-align: center;
}

.interface-guide-card h3 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
}

.interface-guide-card p {
  max-width: 380px;
  margin: 0;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
}

.interface-guide-icon {
  color: var(--ant-color-primary);
  font-size: 64px;
}

.interface-guide-icon--warning {
  color: var(--ant-color-warning);
}

.interface-guide-card p.interface-guide-error {
  color: var(--ant-color-error);
  overflow-wrap: anywhere;
}

.interface-loading {
  margin-top: 8px;
  padding: 16px;
}

.interface-loading :deep(.ant-spin-container) {
  opacity: 1;
}

@media (max-width: 768px) {
  .interface-body {
    grid-template-columns: 1fr;
  }
}
</style>

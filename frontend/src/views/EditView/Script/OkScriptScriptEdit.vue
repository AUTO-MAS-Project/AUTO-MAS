<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img :src="SCRIPT_LOGOS.OkScript" alt="ok-script" class="breadcrumb-logo" />
            {{ t('edit.editScript') }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <!-- 原生界面会话遮罩：设置由项目自己保存，本软件不下发、不回写 -->
  <GuiSessionMask
    :open="showConfigMask"
    :icon="SettingOutlined"
    :title="t('edit.okscriptSessionTitle', { name: projectName })"
    :description="`${t('edit.okscriptSessionDesc')}\n${t('edit.okscriptSessionDesc2')}`"
  >
    <template #actions>
      <a-button v-if="sessionTaskId" type="primary" size="large" @click="saveSession">
        {{ t('edit.okscriptSessionClose') }}
      </a-button>
    </template>
  </GuiSessionMask>

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card
      :title="t('edit.okscriptScriptConfiguration')"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="cyan" class="type-tag">ok-script</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <!-- 基本信息 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.scriptName') }}
                    <a-tooltip :title="t('edit.okscriptScriptNameHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  :placeholder="t('edit.enterScriptName')"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Info', 'Name', formData.name)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 项目 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.okscriptProject') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.okscriptRootPath') }}
                    <a-tooltip :title="t('edit.okscriptRootPathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.rootPath"
                    :placeholder="t('edit.okscriptPickRootPath')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :loading="probing"
                    :disabled="isSaving || configLocked"
                    @click="selectRootPath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickDirectory') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>

          <a-alert
            v-if="probeError"
            type="error"
            show-icon
            :message="t('edit.okscriptProbeFailed')"
            :description="probeError"
            class="project-alert"
          />
          <template v-else-if="project">
            <a-descriptions :column="3" size="small" bordered class="project-info">
              <a-descriptions-item :label="t('edit.okscriptProjectName')">
                {{ project.appName }}
              </a-descriptions-item>
              <a-descriptions-item :label="t('edit.okscriptProjectVersion')">
                {{ project.version }}
              </a-descriptions-item>
              <a-descriptions-item :label="t('edit.okscriptTaskCount')">
                {{ runnableTaskCount }}
              </a-descriptions-item>
            </a-descriptions>
            <a-alert
              v-if="!project.verified"
              type="warning"
              show-icon
              :message="t('edit.okscriptUnverified', { name: project.appName })"
              class="project-alert"
            />
          </template>

          <div class="native-config-row">
            <span class="native-config-hint">{{ t('edit.okscriptNativeConfigHint') }}</span>
            <a-button
              :loading="sessionLoading"
              :disabled="!project || pageLoading || configLocked"
              @click="handleOpenNative"
            >
              <template #icon>
                <SettingOutlined />
              </template>
              {{ t('edit.okscriptOpenNative') }}
            </a-button>
          </div>
        </div>

        <!-- 运行配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runsPerDay') }}
                    <a-tooltip :title="t('edit.k0MeansNoLimit')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okScriptConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', okScriptConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.giveUpAfterThis')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okScriptConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', okScriptConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.okscriptRunTimeLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okScriptConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', okScriptConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </ConfigLockPanel>
</template>

<script setup lang="ts">
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import GuiSessionMask from '@/components/GuiSessionMask.vue'
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
  SettingOutlined,
} from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { useNativeGuiSession } from '@/composables/useNativeGuiSession'
import { OkScriptService, type OkScriptProjectInfo } from '@/api'
import { SCRIPT_LOGOS } from '@/utils/scriptLogos'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('OkScript脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const { configLocked } = useScriptConfigLock(() => scriptId)
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)

// 原生界面会话：打开项目自己的界面，关闭时由后端结束进程；设置由项目自行保存
const {
  configLoading: sessionLoading,
  taskId: sessionTaskId,
  showConfigMask,
  startSession,
  saveSession,
  stopSession,
} = useNativeGuiSession({
  loggerName: 'OkScript原生界面',
  keys: {
    stopFailed: 'edit.okscriptSessionStopFailed',
    startFailed: 'edit.okscriptSessionStartFailed',
    setupFailed: 'edit.okscriptSessionSetupFailed',
    opened: 'edit.okscriptSessionOpened',
    viewOpened: 'edit.okscriptSessionOpened',
    timeoutWarn: 'edit.okscriptSessionTimeoutWarn',
    saved: 'edit.okscriptSessionClosed',
    saveFailed: 'edit.okscriptSessionStopFailed',
  },
})

interface OkScriptScriptConfigForm {
  Info: { Name: string; RootPath: string }
  Run: { ProxyTimesLimit: number; RunTimesLimit: number; RunTimeLimit: number }
}

// 与后端 OkScriptConfig 的默认值保持一致
const okScriptConfig = reactive<OkScriptScriptConfigForm>({
  Info: { Name: '', RootPath: '' },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 2, RunTimeLimit: 30 },
})

// 表单绑定代理：直接读写 okScriptConfig，避免出现两份真相
const formData = reactive({
  get name() {
    return okScriptConfig.Info.Name
  },
  set name(value: string) {
    okScriptConfig.Info.Name = value
  },
  get rootPath() {
    return okScriptConfig.Info.RootPath
  },
  set rootPath(value: string) {
    okScriptConfig.Info.RootPath = value
  },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
}))

// 识别结果：安装目录变了或页面打开时向后端重新识别
const project = ref<OkScriptProjectInfo | null>(null)
const probeError = ref('')
const probing = ref(false)
const projectName = computed(() => project.value?.appName || 'ok-script')
const runnableTaskCount = computed(
  () => project.value?.tasks.filter(task => !task.continuous).length ?? 0
)

const probe = async (rootPath: string): Promise<OkScriptProjectInfo | null> => {
  probing.value = true
  try {
    const resp = await OkScriptService.probeOkscriptProjectApiApiScriptsOkscriptProbePost({
      rootPath,
    })
    if (resp.code !== 200 || !resp.data) {
      probeError.value = resp.message || t('edit.okscriptProbeFailed')
      return null
    }
    probeError.value = ''
    return resp.data
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`识别项目失败: ${errorMsg}`)
    probeError.value = errorMsg
    return null
  } finally {
    probing.value = false
  }
}

// 统一使用正斜杠落盘，与后端路径校验器的取值保持一致
const normalizePath = (path: string) => path.replace(/\\/g, '/').replace(/\/+$/, '')

// 局部更新：只提交变更的那个字段，不整体覆盖脚本配置
const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return false
  isSaving.value = true
  try {
    const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
    const success = await updateScript(scriptId, updateData)
    if (success) logger.info(`配置已保存: ${category}.${key}`)
    return Boolean(success)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
    return false
  } finally {
    isSaving.value = false
  }
}

// 选目录：先识别，识别不出就保留旧值并说明原因，不把无效目录存进配置
const selectRootPath = async () => {
  if (configLocked.value) return
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = normalizePath(picked)
  const previousProject = project.value
  const previousError = probeError.value
  const info = await probe(normalized)
  if (!info) {
    message.error(probeError.value || t('edit.okscriptProbeFailed'))
    project.value = previousProject
    probeError.value = previousError
    return
  }
  if (!(await handleChange('Info', 'RootPath', normalized))) {
    project.value = previousProject
    probeError.value = previousError
    return
  }
  okScriptConfig.Info.RootPath = normalized
  project.value = info
  message.success(t('edit.okscriptProbeSucceeded', { name: info.appName, version: info.version }))
}

const handleOpenNative = async () => {
  if (configLocked.value || !project.value) return
  await startSession(scriptId)
}

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      message.error(t('edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'OkScript') {
      message.error(t('edit.okscriptNotOkScript'))
      handleCancel()
      return
    }
    const config = detail.config as Partial<OkScriptScriptConfigForm>
    Object.assign(okScriptConfig.Info, config.Info || {})
    Object.assign(okScriptConfig.Run, config.Run || {})
    if (okScriptConfig.Info.RootPath) {
      project.value = await probe(okScriptConfig.Info.RootPath)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    message.error(t('edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const handleCancel = () => router.push('/scripts')

onMounted(() => {
  void loadScript()
})

onUnmounted(() => {
  // 离开页面时结束原生界面会话，避免后台残留项目进程与脚本锁
  void stopSession()
})
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  text-decoration: none;
}

.breadcrumb-current {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text);
  font-weight: 600;
}

.breadcrumb-logo {
  width: 20px;
  height: 20px;
  object-fit: contain;
}

.script-edit-content {
  flex: 1;
}

.config-card {
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
}

.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.modern-input {
  border-radius: 8px;
}

.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  flex-shrink: 0;
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.project-info {
  margin-bottom: 12px;
}

.project-alert {
  margin-bottom: 12px;
}

.native-config-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 24px;
}

.native-config-hint {
  color: var(--ant-color-text-secondary);
}

.cancel-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.cancel-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }

  .native-config-row {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>

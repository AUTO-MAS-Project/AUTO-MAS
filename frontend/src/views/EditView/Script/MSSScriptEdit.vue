<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/mss.png" alt="MSS" class="breadcrumb-logo" />
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

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card :title="t('edit.mssScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="orange" class="type-tag">MSS</a-tag>
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
                    <a-tooltip :title="t('edit.mssScriptNameHint')">
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

        <!-- 脚本配置 -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.scriptConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="24">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.mssRootPath') }}
                    <a-tooltip :title="t('edit.mssRootPathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.rootPath"
                    :placeholder="t('edit.mssRootPathHint')"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isSaving"
                    @click="selectRootPath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFile') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 游戏（桌面端） -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.mssGameSection') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchMode') }}
                    <a-tooltip :title="t('edit.mssLaunchModeHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="mssConfig.Game.LaunchMode"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'LaunchMode', $event)"
                >
                  <a-select-option value="DirectExe">
                    {{ t('edit.mssLaunchModeDirect') }}
                  </a-select-option>
                  <a-select-option value="AttachOnly">
                    {{ t('edit.mssLaunchModeAttach') }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.gamePath') }}
                    <a-tooltip :title="t('edit.mssLaunchPathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="mssConfig.Game.LaunchPath"
                    size="large"
                    class="path-input"
                    @blur="handleChange('Game', 'LaunchPath', mssConfig.Game.LaunchPath)"
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isSaving"
                    @click="selectGamePath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    {{ t('edit.pickFile') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">{{ t('edit.mssGameArguments') }}</span>
                </template>
                <a-input
                  v-model:value="mssConfig.Game.Arguments"
                  size="large"
                  @blur="handleChange('Game', 'Arguments', mssConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">{{ t('edit.mssGameWaitTime') }}</span>
                </template>
                <a-input-number
                  v-model:value="mssConfig.Game.WaitTime"
                  size="large"
                  :min="0"
                  :max="9999"
                  style="width: 100%"
                  @blur="handleChange('Game', 'WaitTime', mssConfig.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.mssUnityResolution') }}
                    <a-tooltip :title="t('edit.mssUnityResolutionHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="mssConfig.Game.UnityResolution"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'UnityResolution', $event)"
                >
                  <a-select-option value="Off">{{ t('edit.off') }}</a-select-option>
                  <a-select-option value="1920x1080">1920x1080</a-select-option>
                  <a-select-option value="1280x720">1280x720</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <!-- 模拟器管理（暂不适配） -->
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.emulators') }}</h3>
          </div>
          <a-alert
            class="emulator-unsupported-notice"
            type="warning"
            show-icon
            :message="t('edit.mssEmulatorUnsupported')"
          />
          <!-- 桌面端专用：模拟器端星塔旅人游戏起不来，未做适配，所以不给选择器 -->
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
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.mssRunTimesLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="mssConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', mssConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.mssRunTimeLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="mssConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', mssConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.mssUseAdmin') }}
                    <a-tooltip :title="t('edit.mssUseAdminHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="mssConfig.Run.UseAdmin"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Run', 'UseAdmin', $event)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('MSS脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)

interface MSSInfoForm {
  Name: string
  Path: string
}

interface MSSEmulatorForm {
  Id: string
  Index: string
  CloseOnFinish: boolean
}

interface MSSGameForm {
  LaunchMode: string
  LaunchPath: string
  Arguments: string
  WaitTime: number
  UnityResolution: string
}

interface MSSRunForm {
  RunTimesLimit: number
  RunTimeLimit: number
  UseAdmin: boolean
}

// 与后端 MSSConfig 的默认值保持一致（Emulator 的 '-' 表示尚未选择）
interface MSSScriptConfigForm {
  Info: MSSInfoForm
  Emulator: MSSEmulatorForm
  Game: MSSGameForm
  Run: MSSRunForm
}

const getDefaultMSSConfig = (): MSSScriptConfigForm => ({
  Info: {
    Name: '',
    Path: '',
  },
  Emulator: {
    Id: '-',
    Index: '-',
    CloseOnFinish: false,
  },
  Game: {
    LaunchMode: 'DirectExe',
    LaunchPath: '',
    Arguments: '',
    WaitTime: 60,
    UnityResolution: 'Off',
  },
  Run: {
    RunTimesLimit: 2,
    RunTimeLimit: 60,
    UseAdmin: true,
  },
})

const mssConfig = reactive<MSSScriptConfigForm>(getDefaultMSSConfig())

// 表单绑定代理：Info 直接读写 mssConfig，避免出现两份真相
const formData = reactive({
  get name() {
    return mssConfig.Info.Name
  },
  set name(value: string) {
    mssConfig.Info.Name = value
  },
  get rootPath() {
    return mssConfig.Info.Path
  },
  set rootPath(value: string) {
    mssConfig.Info.Path = value
  },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
}))

// 统一使用正斜杠落盘，与后端 FolderValidator/FileValidator 的取值保持一致
const normalizePath = (path: string) => path.replace(/\\/g, '/').replace(/\/+$/, '')

// 局部更新：只提交变更的那个字段，不整体覆盖脚本配置
const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存失败: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
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
    if (detail.type !== 'MSS') {
      message.error(t('edit.mssNotMssScript'))
      handleCancel()
      return
    }
    const config = detail.config as Partial<MSSScriptConfigForm>
    Object.assign(mssConfig.Info, config.Info || {})
    Object.assign(mssConfig.Emulator, config.Emulator || {})
    Object.assign(mssConfig.Game, config.Game || {})
    Object.assign(mssConfig.Run, config.Run || {})
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

const selectRootPath = async () => {
  try {
    const picked = await window.electronAPI?.selectFolder()
    if (!picked) return
    const normalized = normalizePath(picked)
    mssConfig.Info.Path = normalized
    await handleChange('Info', 'Path', normalized)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择 MSS 根目录失败: ${errorMsg}`)
    message.error(errorMsg)
  }
}

const selectGamePath = async () => {
  try {
    // selectFile 返回的是路径数组（与 selectFolder 返回单个路径不同）
    const picked = await window.electronAPI?.selectFile([
      { name: '可执行文件', extensions: ['exe'] },
      { name: '所有文件', extensions: ['*'] },
    ])
    if (!picked || picked.length === 0) return
    const normalized = normalizePath(picked[0])
    mssConfig.Game.LaunchPath = normalized
    await handleChange('Game', 'LaunchPath', normalized)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择游戏路径失败: ${errorMsg}`)
    message.error(errorMsg)
  }
}

onMounted(() => {
  void loadScript()
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

.emulator-unsupported-notice {
  margin-bottom: 12px;
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
}
</style>

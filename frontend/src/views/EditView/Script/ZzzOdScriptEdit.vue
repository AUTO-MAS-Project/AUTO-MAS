<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/zzz-od.ico" alt="ZZZ-OD" class="breadcrumb-logo" />
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
    <a-card :title="t('edit.zzzodScriptConfiguration')" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag">ZZZ-OD</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.basicInfo') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.scriptName') }}
                    <a-tooltip :title="t('edit.zzzodScriptNameHint')">
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
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodRootPath') }}
                    <a-tooltip :title="t('edit.zzzodRootPathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.zzzodRootPathPlaceholder')"
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
                    {{ t('edit.pickDirectory') }}
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>{{ t('edit.gameConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.enableGameConfiguration') }}
                    <a-tooltip :title="t('edit.masTakesOverStarting')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.Enabled"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'Enabled', zzzodConfig.Game.Enabled)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchGameBeforeTask') }}
                    <a-tooltip :title="t('edit.zzzodLaunchBeforeTaskHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.LaunchBeforeTask"
                  size="large"
                  style="width: 100%"
                  :disabled="!zzzodConfig.Game.Enabled"
                  @change="
                    handleChange('Game', 'LaunchBeforeTask', zzzodConfig.Game.LaunchBeforeTask)
                  "
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodGamePath') }}
                    <a-tooltip :title="t('edit.zzzodGamePathHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="zzzodConfig.Game.Path"
                    :placeholder="t('edit.zzzodGamePathPlaceholder')"
                    size="large"
                    class="path-input"
                    readonly
                    :disabled="!zzzodConfig.Game.Enabled"
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="!zzzodConfig.Game.Enabled || isSaving"
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
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.launchArguments') }}
                    <a-tooltip :title="t('edit.zzzodGameArgumentsHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="zzzodConfig.Game.Arguments"
                  :placeholder="t('edit.enterGameLaunchArguments')"
                  size="large"
                  style="width: 100%"
                  :disabled="!zzzodConfig.Game.Enabled"
                  @blur="handleChange('Game', 'Arguments', zzzodConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.startupWait') }}
                    <a-tooltip :title="t('edit.howLongWaitAfter')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  :disabled="!zzzodConfig.Game.Enabled"
                  @blur="handleChange('Game', 'WaitTime', zzzodConfig.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodCloseGameOnFinish') }}
                    <a-tooltip :title="t('edit.zzzodCloseGameOnFinishHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.CloseOnFinish"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'CloseOnFinish', zzzodConfig.Game.CloseOnFinish)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.zzzodAccountSwitch') }}
                    <a-tooltip :title="t('edit.zzzodAccountSwitchHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="zzzodConfig.Game.AccountSwitch"
                  :options="accountSwitchOptions"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'AccountSwitch', zzzodConfig.Game.AccountSwitch)"
                >
                  <!-- 逐选项悬停提示：鼠标停在哪个选项上就显示哪个的说明 -->
                  <template #option="{ label, hint }">
                    <a-tooltip :title="hint" placement="right" :mouse-enter-delay="0.3">
                      <div class="account-switch-option">{{ label }}</div>
                    </a-tooltip>
                  </template>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

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
                  v-model:value="zzzodConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', zzzodConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.zzzodRetryLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', zzzodConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.zzzodRunTimeoutHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="zzzodConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', zzzodConfig.Run.RunTimeLimit)"
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
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useSaveQueue } from '@/composables/useSaveQueue'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('ZZZ-OD脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()
const isInitializing = ref(true)

// ══ ZZZ-OD 项目结构常量（需与 app/task/ZzzOd/AutoProxy.py 的 _ZZZOD_LAUNCHERS 保持同步）══
const ZZZOD_LAUNCHER_NAMES = ['OneDragon-RuntimeLauncher.exe', 'OneDragon-Launcher.exe']

interface ZzzOdInfoForm {
  Name: string
  RootPath: string
}

interface ZzzOdRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface ZzzOdGameForm {
  Enabled: boolean
  LaunchBeforeTask: boolean
  Path: string
  Arguments: string
  WaitTime: number
  CloseOnFinish: boolean
  AccountSwitch: '单实例切换' | '多实例切换' | 'MAS切换'
}

interface ZzzOdScriptConfigForm {
  Info: ZzzOdInfoForm
  Run: ZzzOdRunForm
  Game: ZzzOdGameForm
}

const formData = reactive({
  name: '',
  get path() {
    return zzzodConfig.Info.RootPath
  },
  set path(value: string) {
    zzzodConfig.Info.RootPath = value
  },
})

const zzzodConfig = reactive<ZzzOdScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 180 },
  Game: {
    Enabled: false,
    LaunchBeforeTask: false,
    Path: '',
    Arguments: '',
    WaitTime: 60,
    CloseOnFinish: true,
    AccountSwitch: '单实例切换',
  },
})

// 账号切换方式（value 为后端 Game.AccountSwitch 取值，驱动逻辑需保持原样；label 走词表）
// hint 为逐选项悬停提示（下拉里鼠标停在哪个选项就显示哪个的说明）
const accountSwitchOptions = [
  {
    label: t('edit.zzzodAccountSwitchSingle'),
    value: '单实例切换',
    hint: t('edit.zzzodAccountSwitchSingleHint'),
  },
  {
    label: t('edit.zzzodAccountSwitchMulti'),
    value: '多实例切换',
    hint: t('edit.zzzodAccountSwitchMultiHint'),
  },
  {
    label: t('edit.zzzodAccountSwitchMas'),
    value: 'MAS切换',
    hint: t('edit.zzzodAccountSwitchMasHint'),
    disabled: true,
  },
]

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.zzzodRootPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value) return
  await enqueue(async () => {
    try {
      const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
      const success = await updateScript(scriptId, updateData)
      if (success) {
        logger.info(`配置已保存: ${category}.${key}`)
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e)
      logger.error(msg)
    }
  }, `${category}.${key}`)
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('edit.pickScriptRootDirectory'))
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = zzzodConfig.Info.RootPath
  zzzodConfig.Info.RootPath = norm

  return enqueue(async () => {
    try {
      const success = await updateScript(scriptId, {
        Info: { RootPath: norm },
      })
      if (success) {
        message.success(t('edit.zzzodRootPathSaved'))
        return true
      }
      zzzodConfig.Info.RootPath = previousPath
      return false
    } catch (error) {
      zzzodConfig.Info.RootPath = previousPath
      throw error
    }
  })
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
    if (detail.type !== 'ZzzOd') {
      message.error(t('edit.zzzodNotZzzodScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<ZzzOdScriptConfigForm>
    Object.assign(zzzodConfig.Info, config.Info || {})
    Object.assign(zzzodConfig.Run, config.Run || {})
    Object.assign(zzzodConfig.Game, config.Game || {})
  } catch {
    message.error(t('edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectGamePath = async () => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'ZenlessZoneZero.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return
  const fileName = path.split(/[\\/]/).pop()
  if (fileName?.toLowerCase() !== 'zenlesszonezero.exe') {
    message.error(t('edit.zzzodPickGameExe'))
    return
  }
  const normalized = path.replace(/\\/g, '/')
  const previous = zzzodConfig.Game.Path
  zzzodConfig.Game.Path = normalized
  try {
    await handleChange('Game', 'Path', normalized)
  } catch (error) {
    zzzodConfig.Game.Path = previous
    throw error
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  // 任一启动器存在即视为有效安装目录（RuntimeLauncher / 旧安装器 Launcher）
  const launcherChecks = await Promise.all(
    ZZZOD_LAUNCHER_NAMES.map(name => window.electronAPI.fileExists(`${normalized}/${name}`))
  )
  if (!launcherChecks.some(Boolean)) {
    Modal.error({
      title: t('edit.zzzodInvalidDirectory'),
      content: t('edit.zzzodLauncherNotFound', {
        p0: ZZZOD_LAUNCHER_NAMES[0],
        p1: ZZZOD_LAUNCHER_NAMES[1],
      }),
      okText: t('edit.gotIt'),
    })
    return
  }
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

onMounted(loadScript)
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

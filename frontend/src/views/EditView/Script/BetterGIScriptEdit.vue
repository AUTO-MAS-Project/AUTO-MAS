<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/bettergi.ico" alt="BetterGI" class="breadcrumb-logo" />
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

  <div class="script-edit-content">
    <a-card
      :title="t('edit.bettergiScriptConfiguration')"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-tag color="blue" class="type-tag">BetterGI</a-tag>
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
                    <a-tooltip :title="t('edit.bettergiInstanceNameHint')">
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
                    {{ t('edit.bettergiPath') }}
                    <a-tooltip :title="t('edit.bettergiPickExeDir')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.bettergiPickExeDirPlaceholder')"
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
                    {{ t('edit.controller') }}
                    <a-tooltip :title="t('edit.bettergiControllerHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.Controller"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'Controller', bettergiConfig.Game.Controller)"
                >
                  <a-select-option value="电脑端-前台">
                    {{ t('edit.bettergiControllerForeground') }}
                  </a-select-option>
                  <a-select-option value="电脑端-云原神" disabled>
                    {{ t('edit.bettergiControllerCloud') }}
                  </a-select-option>
                  <a-select-option value="电脑端-桌面分身" disabled>
                    {{ t('edit.bettergiControllerDesktopClone') }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.bettergiCloseGameOnFinish') }}
                    <a-tooltip :title="t('edit.bettergiCloseGameOnFinishHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="bettergiConfig.Game.CloseOnFinish"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Game', 'CloseOnFinish', bettergiConfig.Game.CloseOnFinish)"
                >
                  <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
                  <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
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
                  v-model:value="bettergiConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', bettergiConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.bettergiRetryLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="bettergiConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', bettergiConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.bettergiRunTimeoutHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="bettergiConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', bettergiConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
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

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BetterGI脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)

// ══ BetterGI 项目结构常量（需与 app/task/BetterGI/AutoProxy.py 中的 _BGI_REL_* 保持同步）══
const BGI_EXE_NAME = 'BetterGI.exe'

interface BetterGIInfoForm {
  Name: string
  RootPath: string
}

interface BetterGIRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface BetterGIGameForm {
  Controller: string
  CloseOnFinish: boolean
}

interface BetterGIScriptConfigForm {
  Info: BetterGIInfoForm
  Run: BetterGIRunForm
  Game: BetterGIGameForm
}

const formData = reactive({
  name: '',
  get path() {
    return bettergiConfig.Info.RootPath
  },
  set path(value: string) {
    bettergiConfig.Info.RootPath = value
  },
})

const bettergiConfig = reactive<BetterGIScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 10 },
  Game: { Controller: '电脑端-前台', CloseOnFinish: true },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.bettergiPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    logger.error(msg)
  } finally {
    isSaving.value = false
  }
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning(t('edit.pickScriptRootDirectory'))
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = bettergiConfig.Info.RootPath
  bettergiConfig.Info.RootPath = norm

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Info: { RootPath: norm },
    })
    if (success) {
      message.success(t('edit.bettergiRootPathSaved'))
      return true
    }
    bettergiConfig.Info.RootPath = previousPath
    return false
  } catch (error) {
    bettergiConfig.Info.RootPath = previousPath
    throw error
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
    if (detail.type !== 'BetterGI') {
      message.error(t('edit.bettergiNotBettergiScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<BetterGIScriptConfigForm>
    Object.assign(bettergiConfig.Info, config.Info || {})
    Object.assign(bettergiConfig.Run, config.Run || {})
    Object.assign(bettergiConfig.Game, config.Game || {})
  } catch {
    message.error(t('edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  const exePath = `${normalized}/${BGI_EXE_NAME}`
  const exists = await window.electronAPI.fileExists(exePath)
  if (!exists) {
    Modal.error({
      title: t('edit.bettergiInvalidDirectory'),
      content: t('edit.bettergiExeNotFound', { p0: BGI_EXE_NAME }),
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

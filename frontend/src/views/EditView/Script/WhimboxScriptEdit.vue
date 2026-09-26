<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">{{ t('edit.scripts') }}</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/whimbox.png" :alt="SCRIPT_LABELS.Whimbox" class="breadcrumb-logo" />
            {{ t('edit.editScript') }}
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <DocLink :url="MAS_DOC_URLS.scripts" />
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        {{ t('edit.back') }}
      </a-button>
    </a-space>
  </div>

  <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
    <a-card
      :title="t('edit.whimboxScriptConfiguration')"
      :loading="pageLoading"
      class="config-card"
    >
      <template #extra>
        <a-space :size="8">
          <a-tag v-if="upstreamVersion" color="blue" class="type-tag">
            v{{ upstreamVersion }}
          </a-tag>
          <a-tag color="pink" class="type-tag">{{ SCRIPT_LABELS.Whimbox }}</a-tag>
        </a-space>
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
                    <a-tooltip :title="t('edit.whimboxInstanceNameHint')">
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
                    {{ t('edit.whimboxPath') }}
                    <a-tooltip :title="t('edit.whimboxPickExeDir')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    :placeholder="t('edit.whimboxPickExeDirPlaceholder')"
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
            <h3>{{ t('edit.runConfiguration') }}</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="6">
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
                  v-model:value="whimboxConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', whimboxConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.retryLimit2') }}
                    <a-tooltip :title="t('edit.whimboxRetryLimitHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="whimboxConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', whimboxConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.runTimeoutMinutes') }}
                    <a-tooltip :title="t('edit.whimboxRunTimeoutHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="whimboxConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', whimboxConfig.Run.RunTimeLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    {{ t('edit.whimboxUseAdmin') }}
                    <a-tooltip :title="t('edit.whimboxUseAdminHint')">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-select
                  v-model:value="whimboxConfig.Run.UseAdmin"
                  size="large"
                  style="width: 100%"
                  @change="handleChange('Run', 'UseAdmin', whimboxConfig.Run.UseAdmin)"
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
import DocLink from '@/components/DocLink.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
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
import { useWhimboxTaskCatalog } from '@/composables/useWhimboxTaskCatalog'
import { SCRIPT_LABELS } from '@/utils/scriptLogos'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('奇想盒脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const { data: catalogData, fetchCatalog } = useWhimboxTaskCatalog()

const scriptId = route.params.id as string
const pageLoading = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { isSaving, enqueue } = useSaveQueue()
const isInitializing = ref(true)
const upstreamVersion = ref('')

// ══ 奇想盒项目结构常量（需与 app/task/Whimbox/tools/upstream.py 保持同步）══
const WHIMBOX_EXE_NAME = 'whimbox_app.exe'

interface WhimboxInfoForm {
  Name: string
  RootPath: string
}

interface WhimboxRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
  UseAdmin: boolean
}

interface WhimboxScriptConfigForm {
  Info: WhimboxInfoForm
  Run: WhimboxRunForm
}

const formData = reactive({
  name: '',
  get path() {
    return whimboxConfig.Info.RootPath
  },
  set path(value: string) {
    whimboxConfig.Info.RootPath = value
  },
})

const whimboxConfig = reactive<WhimboxScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 30, UseAdmin: true },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('edit.whimboxPathRequired'), trigger: 'blur' }],
}))

const handleCancel = () => router.push('/scripts')

const refreshUpstreamVersion = async () => {
  if (!whimboxConfig.Info.RootPath || whimboxConfig.Info.RootPath === '.') return
  const ok = await fetchCatalog(scriptId)
  if (ok && catalogData.value) {
    upstreamVersion.value = catalogData.value.upstream_version || ''
  }
}

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
  const previousPath = whimboxConfig.Info.RootPath
  whimboxConfig.Info.RootPath = norm

  return enqueue(async () => {
    try {
      const success = await updateScript(scriptId, {
        Info: { RootPath: norm },
      })
      if (success) {
        message.success(t('edit.whimboxRootPathSaved'))
        void refreshUpstreamVersion()
        return true
      }
      whimboxConfig.Info.RootPath = previousPath
      return false
    } catch {
      // updateScript 失败只返回 false 不抛错；此兜底防未来契约变化产生 unhandled rejection
      whimboxConfig.Info.RootPath = previousPath
      return false
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
    if (detail.type !== 'Whimbox') {
      message.error(t('edit.whimboxNotWhimboxScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<WhimboxScriptConfigForm>
    Object.assign(whimboxConfig.Info, config.Info || {})
    Object.assign(whimboxConfig.Run, config.Run || {})
    // 目录已配置时顺带拉一次目录接口，展示上游版本（refreshUpstreamVersion 自带空目录守卫）
    void refreshUpstreamVersion()
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
  const exePath = `${normalized}/${WHIMBOX_EXE_NAME}`
  const exists = await window.electronAPI.fileExists(exePath)
  if (!exists) {
    Modal.error({
      title: t('edit.whimboxInvalidDirectory'),
      content: t('edit.whimboxExeNotFound', { p0: WHIMBOX_EXE_NAME }),
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

/* 输入框的边框与圆角统一由外层 .path-input-group 提供（compact 拼接形制）；
   Ant 的默认边框写在更高优先级的选择器上，不用 !important 会被盖回来 */
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

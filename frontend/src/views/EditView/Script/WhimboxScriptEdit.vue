<template>
  <ScriptEditHeader
    script-type="Whimbox"
    :title="t('edit.editScript')"
    :doc-url="MAS_DOC_URLS.scripts"
    @cancel="handleCancel"
  />

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
          <ScriptHardTimeoutField
            v-model:value="whimboxConfig.Run.HardTimeLimit"
            @save="handleChange('Run', 'HardTimeLimit', whimboxConfig.Run.HardTimeLimit)"
          />
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
import ScriptHardTimeoutField from '@/views/EditView/Script/components/ScriptHardTimeoutField.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import { FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'
import { useWhimboxTaskCatalog } from '@/composables/useWhimboxTaskCatalog'
import { SCRIPT_LABELS } from '@/utils/scriptLogos'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('奇想盒脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript, error: scriptApiError } = useScriptApi()
const { data: catalogData, fetchCatalog } = useWhimboxTaskCatalog()

const scriptId = route.params.id as string
const pageLoading = ref(true)
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const isInitializing = ref(true)
const {
  isSaving,
  enqueue,
  saveField: handleChange,
} = useScriptSaveMutation({ scriptId, isInitializing, logger })
const upstreamVersion = ref('')

// ══ 奇想盒项目结构常量（需与 app/task/Whimbox/tools/upstream.py 保持同步）══
const WHIMBOX_EXE_NAME = 'whimbox_app.exe'

interface WhimboxInfoForm {
  Name: string
  RootPath: string
}

interface WhimboxRunForm {
  HardTimeLimit: number
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
  Run: {
    HardTimeLimit: 120,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    RunTimeLimit: 30,
    UseAdmin: true,
  },
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
      if (!scriptApiError.value) message.error(t('edit.scriptDoesNotExist'))
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
    if (!scriptApiError.value) message.error(t('edit.couldNotLoadScript'))
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

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped>
.section-header {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.path-input-group {
  border: 1px solid var(--ant-color-border);
}

.path-input {
  min-width: 0;
}

.path-button {
  flex-shrink: 0;
}
</style>

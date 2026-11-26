<template>
  <ConfigEditShell :surface="false">
    <template #header>
      <ScriptEditHeader
        script-type="Whimbox"
        :title="t('core.edit.editScript')"
        :doc-url="MAS_DOC_URLS.scripts"
        @cancel="handleCancel"
      />
    </template>

    <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content">
      <a-spin :spinning="pageLoading">
        <a-form
          :aria-label="t('core.edit.whimboxScriptConfiguration')"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <SectionCard variant="card" :title="t('core.edit.basicInfo')" :icon="AppstoreOutlined">
            <template #actions>
              <a-tag v-if="upstreamVersion" color="blue">v{{ upstreamVersion }}</a-tag>
            </template>
            <a-row :gutter="24">
              <a-col :xs="24" :md="12">
                <a-form-item name="name">
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.scriptName')"
                      :hint="t('core.edit.whimboxInstanceNameHint')"
                      variant="form"
                    />
                  </template>
                  <a-input
                    v-model:value="formData.name"
                    :placeholder="t('core.edit.enterScriptName')"
                    class="modern-input"
                    @blur="handleChange('Info', 'Name', formData.name)"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item name="path" :rules="rules.path">
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.whimboxPath')"
                      :hint="t('core.edit.whimboxPickExeDir')"
                      variant="form"
                    />
                  </template>
                  <PathPickerField
                    v-model="formData.path"
                    mode="folder"
                    :placeholder="t('core.edit.whimboxPickExeDirPlaceholder')"
                    :pick-label="t('core.edit.pickDirectory')"
                    :disabled="isSaving"
                    @pick="selectRootPath"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </SectionCard>

          <SectionCard
            variant="card"
            :title="t('core.edit.runConfiguration')"
            :icon="ThunderboltOutlined"
          >
            <ScriptRunLimitsSection
              v-model:hard-time-limit="whimboxConfig.Run.HardTimeLimit"
              v-model:daily-limit="whimboxConfig.Run.ProxyTimesLimit"
              v-model:retry-limit="whimboxConfig.Run.RunTimesLimit"
              v-model:timeout="whimboxConfig.Run.RunTimeLimit"
              hide-execution-session
              :retry-hint="t('core.edit.whimboxRetryLimitHint')"
              :timeout-hint="t('core.edit.whimboxRunTimeoutHint')"
              enhanced
              @save="key => handleChange('Run', key, whimboxConfig.Run[key])"
            />
            <a-row :gutter="24">
              <a-col :xs="24" :md="12">
                <SwitchTile
                  v-model:checked="whimboxConfig.Run.UseAdmin"
                  :title="t('core.edit.whimboxUseAdmin')"
                  :description="t('core.edit.whimboxUseAdminHint')"
                  @change="handleChange('Run', 'UseAdmin', whimboxConfig.Run.UseAdmin)"
                />
              </a-col>
            </a-row>
          </SectionCard>
          <WhimboxUpdateSettings
            v-model:update="whimboxConfig.Update"
            :ready="!pageLoading && !isInitializing"
            @change="handleChange('Update', 'TakeoverEnabled', $event)"
          />
        </a-form>
      </a-spin>
    </ConfigLockPanel>
  </ConfigEditShell>
</template>

<script setup lang="ts">
import { AppstoreOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import ScriptRunLimitsSection from '@/views/EditView/Script/components/ScriptRunLimitsSection.vue'
import WhimboxUpdateSettings from './WhimboxUpdateSettings.vue'
import type { WhimboxConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import { ConfigEditShell, SectionCard, SwitchTile } from '@/components/ui'
import { MAS_DOC_URLS } from '@/utils/openExternal'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useConfirm } from '@/composables/useConfirm'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'
import { useWhimboxTaskCatalog } from '@/views/whimbox/useWhimboxTaskCatalog'

const { t } = useI18n()
const { alert } = useConfirm()
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
  Update: WhimboxConfig_Update
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
  Update: { TakeoverEnabled: false },
  Run: {
    HardTimeLimit: 120,
    ProxyTimesLimit: 0,
    RunTimesLimit: 3,
    RunTimeLimit: 30,
    UseAdmin: true,
  },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
  path: [{ required: true, message: t('core.edit.whimboxPathRequired'), trigger: 'blur' }],
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
    message.warning(t('core.edit.pickScriptRootDirectory'))
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
        message.success(t('core.edit.whimboxRootPathSaved'))
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
      if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist'))
      handleCancel()
      return
    }
    if (detail.type !== 'Whimbox') {
      message.error(t('core.edit.whimboxNotWhimboxScript'))
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<WhimboxScriptConfigForm>
    Object.assign(whimboxConfig.Info, config.Info || {})
    Object.assign(whimboxConfig.Run, config.Run || {})
    Object.assign(whimboxConfig.Update, config.Update || {})
    // 目录已配置时顺带拉一次目录接口，展示上游版本（refreshUpstreamVersion 自带空目录守卫）
    void refreshUpstreamVersion()
  } catch {
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript'))
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
    void alert({
      tone: 'error',
      title: t('core.edit.whimboxInvalidDirectory'),
      description: t('core.edit.whimboxExeNotFound', { p0: WHIMBOX_EXE_NAME }),
      okText: t('core.edit.gotIt'),
    })
    return
  }
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

onMounted(loadScript)
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

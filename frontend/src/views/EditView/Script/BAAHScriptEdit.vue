<template>
  <ScriptEditLayout
    :script-id="scriptId"
    :loading="pageLoading"
    :header="{ scriptType: 'BAAH', title: t('core.edit.editScript') }"
    :form="{ model: formData, rules }"
    :form-label="t('core.edit.baahScriptConfiguration')"
    @cancel="handleCancel"
  >
    <template #basic>
      <ScriptBasicInfoCard
        v-model:name="formData.name"
        :name-hint="t('core.edit.baahScriptNameHint')"
        @save-name="handleChange('Info', 'Name', $event)"
      />
    </template>

    <template #script-config>
      <SectionCard
        variant="card"
        :title="t('core.edit.scriptConfiguration')"
        :icon="SettingOutlined"
      >
        <a-row :gutter="24">
          <a-col :xs="24" :md="12">
            <a-form-item>
              <template #label>
                <FieldLabelWithHint
                  :text="t('core.edit.mainProgramPath')"
                  :hint="t('core.edit.baahScriptPathHint')"
                  variant="form"
                />
              </template>
              <PathPickerField
                v-model="formData.baahPath"
                mode="file"
                :placeholder="t('core.edit.pickScriptSMain')"
                :pick-label="t('core.edit.pickFile')"
                :disabled="isSaving"
                @pick="selectBaahPath"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="[24, 12]">
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="baahConfig.Script.IfManageConfig"
              :title="t('core.edit.baahManageConfig')"
              :description="t('core.edit.baahManageConfigHint')"
              @change="handleChange('Script', 'IfManageConfig', $event)"
            />
          </a-col>
          <a-col :xs="24" :md="12">
            <SwitchTile
              v-model:checked="baahConfig.Script.PushLogEnabled"
              :title="t('core.edit.baahPushLogEnabled')"
              :description="t('core.edit.baahPushLogEnabledHint')"
              @change="handleChange('Script', 'PushLogEnabled', $event)"
            />
          </a-col>
        </a-row>

        <!-- 关闭托管时 BAAH 会用它自己的设置启动模拟器，两边抢同一台设备 -->
        <a-alert
          type="warning"
          show-icon
          :message="t('core.edit.baahAutoStartNotice')"
          style="margin-top: 16px"
        />
      </SectionCard>
    </template>

    <template #run>
      <SectionCard
        variant="card"
        :title="t('core.edit.runConfiguration')"
        :icon="ThunderboltOutlined"
      >
        <ScriptRunLimitsSection
          v-model:hard-time-limit="baahConfig.Run.HardTimeLimit"
          v-model:retry-limit="baahConfig.Run.RunTimesLimit"
          v-model:timeout="baahConfig.Run.RunTimeLimit"
          hide-execution-session
          hide-daily
          :retry-hint="t('core.edit.baahRunTimesLimitHint')"
          :timeout-hint="t('core.edit.baahRunTimeLimitHint')"
          enhanced
          @save="key => handleChange('Run', key, baahConfig.Run[key as keyof BAAHRunForm])"
        />
      </SectionCard>
    </template>

    <template #program-update>
      <ScriptTakeoverUpdateCard
        v-model:update="baahConfig.Update"
        :ready="!pageLoading && !isSaving"
        :title="t('core.edit.baahProgramUpdate')"
        :takeover-hint="t('core.edit.baahProgramUpdateHint')"
        @save="(key, value) => handleChange('Update', key, value)"
      />
    </template>
  </ScriptEditLayout>
</template>

<script setup lang="ts">
import { SettingOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import ScriptTakeoverUpdateCard from './components/ScriptTakeoverUpdateCard.vue'
import type { BAAHConfig_Update } from '@/api'
import ScriptRunLimitsSection from './components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import ScriptBasicInfoCard from '@/components/ScriptBasicInfoCard.vue'
import ScriptEditLayout from '@/components/ScriptEditLayout.vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('BAAH脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, error: scriptApiError } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isInitializing = ref(true)
const { isSaving, saveField: handleChange } = useScriptSaveMutation({
  scriptId,
  isInitializing,
  logger,
})

interface BAAHInfoForm {
  Name: string
}

interface BAAHScriptForm {
  BAAHPath: string
  IfManageConfig: boolean
  PushLogEnabled: boolean
}

interface BAAHRunForm {
  HardTimeLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface BAAHScriptConfigForm {
  Update: BAAHConfig_Update
  Info: BAAHInfoForm
  Script: BAAHScriptForm
  Run: BAAHRunForm
}

const getDefaultBAAHConfig = (): BAAHScriptConfigForm => ({
  Update: { TakeoverEnabled: false, Channel: 'stable', MirrorChyanCDK: '' },
  Info: {
    Name: '',
  },
  Script: {
    BAAHPath: '',
    IfManageConfig: true,
    PushLogEnabled: true,
  },
  Run: { HardTimeLimit: 120, RunTimesLimit: 2, RunTimeLimit: 60 },
})

const baahConfig = reactive<BAAHScriptConfigForm>(getDefaultBAAHConfig())

// 表单绑定代理：Info/Run 直接读写 baahConfig，避免出现两份真相
const formData = reactive({
  get name() {
    return baahConfig.Info.Name
  },
  set name(value: string) {
    baahConfig.Info.Name = value
  },
  get baahPath() {
    return baahConfig.Script.BAAHPath
  },
  set baahPath(value: string) {
    baahConfig.Script.BAAHPath = value
  },
})

const rules = computed(() => ({
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
}))

// 统一使用正斜杠落盘，与后端 FolderValidator/FileValidator 的取值保持一致
const normalizePath = (path: string) => path.replace(/\\/g, '/').replace(/\/+$/, '')

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
    if (detail.type !== 'BAAH') {
      message.error(t('core.edit.baahNotBaahScript'))
      handleCancel()
      return
    }
    const config = detail.config as Partial<BAAHScriptConfigForm>
    Object.assign(baahConfig.Update, config.Update || {})
    Object.assign(baahConfig.Info, config.Info || {})
    Object.assign(baahConfig.Script, config.Script || {})
    Object.assign(baahConfig.Run, config.Run || {})
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript'))
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const handleCancel = () => router.push('/scripts')

const selectBaahPath = async () => {
  const paths = await window.electronAPI?.selectFile([
    { name: 'BAAH.exe', extensions: ['exe'] },
    { name: t('core.edit.allFiles'), extensions: ['*'] },
  ])
  const path = paths?.[0]
  if (!path) return
  const normalized = normalizePath(path)
  baahConfig.Script.BAAHPath = normalized
  await handleChange('Script', 'BAAHPath', normalized)
}

onMounted(() => {
  void loadScript()
})
</script>

<template>
  <ConfigEditShell :surface="false">
    <template #header>
      <ScriptEditHeader
        script-type="BAAH"
        :title="t('core.edit.editScript')"
        @cancel="handleCancel"
      />
    </template>

    <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content" game-binding="none">
      <a-card
        :title="t('core.edit.baahScriptConfiguration')"
        :loading="pageLoading"
        class="config-card"
      >
        <template #extra>
          <a-tag color="magenta" class="type-tag">BAAH</a-tag>
        </template>

        <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
          <!-- 基本信息 -->
          <SectionCard variant="plain" :title="t('core.edit.basicInfo')">
            <a-row :gutter="24">
              <a-col :span="24">
                <a-form-item name="name">
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.scriptName')"
                      :hint="t('core.edit.baahScriptNameHint')"
                      variant="form"
                    />
                  </template>
                  <a-input
                    v-model:value="formData.name"
                    :placeholder="t('core.edit.enterScriptName')"
                    size="large"
                    class="modern-input"
                    @blur="handleChange('Info', 'Name', formData.name)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </SectionCard>

          <BAAHProgramUpdateSettings
            v-model:update="baahConfig.Update"
            :ready="!pageLoading && !isSaving"
            @save="(key, value) => handleChange('Update', key, value)"
          />

          <!-- 脚本配置 -->
          <SectionCard variant="plain" :title="t('core.edit.scriptConfiguration')">
            <a-row :gutter="24">
              <a-col :span="12">
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
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.baahManageConfig')"
                      :hint="t('core.edit.baahManageConfigHint')"
                      variant="form"
                    />
                  </template>
                  <a-select
                    v-model:value="baahConfig.Script.IfManageConfig"
                    size="large"
                    style="width: 100%"
                    @change="handleChange('Script', 'IfManageConfig', $event)"
                  >
                    <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
                    <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="6">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.baahPushLogEnabled')"
                      :hint="t('core.edit.baahPushLogEnabledHint')"
                      variant="form"
                    />
                  </template>
                  <a-select
                    v-model:value="baahConfig.Script.PushLogEnabled"
                    size="large"
                    style="width: 100%"
                    @change="handleChange('Script', 'PushLogEnabled', $event)"
                  >
                    <a-select-option :value="true">{{ t('core.edit.yes') }}</a-select-option>
                    <a-select-option :value="false">{{ t('core.edit.no') }}</a-select-option>
                  </a-select>
                </a-form-item>
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

          <!-- 模拟器 / 游戏客户端 -->
          <GameBindingSection :script-id="scriptId" variant="section" />

          <!-- 运行配置 -->
          <SectionCard variant="plain" :title="t('core.edit.runConfiguration')">
            <ScriptRunLimitsSection
              v-model:hard-time-limit="baahConfig.Run.HardTimeLimit"
              v-model:retry-limit="baahConfig.Run.RunTimesLimit"
              v-model:timeout="baahConfig.Run.RunTimeLimit"
              hide-execution-session
              hide-daily
              :retry-hint="t('core.edit.baahRunTimesLimitHint')"
              :timeout-hint="t('core.edit.baahRunTimeLimitHint')"
              @save="key => handleChange('Run', key, baahConfig.Run[key as keyof BAAHRunForm])"
            />
          </SectionCard>
        </a-form>
      </a-card>
    </ConfigLockPanel>
  </ConfigEditShell>
</template>

<script setup lang="ts">
import BAAHProgramUpdateSettings from './components/BAAHProgramUpdateSettings.vue'
import type { BAAHConfig_Update } from '@/api'
import ScriptRunLimitsSection from './components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import GameBindingSection from '@/components/GameBindingSection.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import { ConfigEditShell, SectionCard } from '@/components/ui'
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
const {
  isSaving,
  save,
  saveField: handleChange,
} = useScriptSaveMutation({ scriptId, isInitializing, logger })

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

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped>
.section-header {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  gap: 8px;
}

.modern-input {
  border-radius: 8px;
}
</style>

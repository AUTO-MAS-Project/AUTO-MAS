<template>
  <ScriptEditLayout
    :script-id="scriptId"
    :loading="pageLoading"
    :header="{ scriptType: 'SRC', title: t('core.edit.editScript') }"
    :form="{ model: formData, rules }"
    :form-label="t('core.edit.srcScriptConfiguration')"
    @cancel="handleCancel"
  >
    <template #basic>
      <ScriptBasicInfoCard
        v-model:name="formData.name"
        :name-hint="t('core.edit.giveScriptNameYou')"
        @save-name="handleChange('Info', 'Name', $event)"
      >
        <template #path>
          <a-form-item name="path" :rules="rules.path">
            <template #label>
              <FieldLabelWithHint
                :text="t('core.edit.srcPath')"
                :hint="t('core.edit.pickFolderHoldingSrc2')"
                variant="form"
              />
            </template>
            <PathPickerField
              v-model="formData.path"
              mode="folder"
              :placeholder="t('core.edit.pickFolderHoldingSrc')"
              :pick-label="t('core.edit.pickFolder')"
              @pick="selectSRCPath"
            />
          </a-form-item>
        </template>
      </ScriptBasicInfoCard>
    </template>

    <template #game-update>
      <ScriptGameUpdateCard
        v-model:check-update="srcConfig.Run.IfCheckGameUpdate"
        v-model:auto-install-apk="srcConfig.Run.IfAutoInstallGameApk"
        v-model:time-limit="srcConfig.Run.GameUpdateTimeLimit"
        :check-description="t('core.edit.checkGameUpdateBeforeLogin')"
        @save="(key, value) => handleChange('Run', key, value)"
      />
    </template>

    <template #run>
      <SectionCard
        variant="card"
        :title="t('core.edit.runConfiguration')"
        :icon="ThunderboltOutlined"
      >
        <ScriptRunLimitsSection
          v-model:hard-time-limit="srcConfig.Run.HardTimeLimit"
          v-model:daily-limit="srcConfig.Run.ProxyTimesLimit"
          v-model:retry-limit="srcConfig.Run.RunTimesLimit"
          v-model:timeout="srcConfig.Run.RunTimeLimit"
          :daily-label="t('core.edit.runsPerDayThis')"
          :daily-hint="t('core.edit.skipRunOnceThis')"
          :retry-label="t('core.edit.retryLimit')"
          :retry-hint="t('core.edit.ifRunStillUnfinished')"
          :timeout-label="t('core.edit.runTimeoutMinutes2')"
          :timeout-hint="t('core.edit.treatRunAsTimed2')"
          enhanced
          @save="key => handleChange('Run', key, srcConfig.Run[key])"
        >
          <template #before-limits>
            <a-col :xs="24" :md="12">
              <a-form-item>
                <template #label>
                  <FieldLabelWithHint
                    :text="t('core.edit.accountSwitchingMethod')"
                    :hint="t('core.edit.whatDoWhenSwitching')"
                    variant="form"
                  />
                </template>
                <a-segmented
                  :value="srcConfig.Run.TaskTransitionMethod"
                  :options="transitionOptions"
                  block
                  @change="handleTransitionChange"
                />
              </a-form-item>
            </a-col>
          </template>
        </ScriptRunLimitsSection>
      </SectionCard>
    </template>

    <template #program-update>
      <SwitchTile
        v-model:checked="srcConfig.Update.TakeoverEnabled"
        variant="card"
        :icon="CloudDownloadOutlined"
        :title="t('core.edit.updateTakeoverSwitch')"
        :description="t('core.edit.srcProgramUpdateHint')"
        :disabled="isInitializing"
        @change="handleChange('Update', 'TakeoverEnabled', $event)"
      />
    </template>
  </ScriptEditLayout>
</template>

<script setup lang="ts">
import { CloudDownloadOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import ScriptRunLimitsSection from '@/views/EditView/Script/components/ScriptRunLimitsSection.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { createSrcScriptDraft } from './srcScriptDraft'
import PathPickerField from '@/components/PathPickerField.vue'
import ScriptBasicInfoCard from '@/components/ScriptBasicInfoCard.vue'
import ScriptEditLayout from '@/components/ScriptEditLayout.vue'
import ScriptGameUpdateCard from '@/views/EditView/Script/components/ScriptGameUpdateCard.vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import type { SRCScriptConfig, ScriptType } from '@/types/script.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('SRC脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, error: scriptApiError } = useScriptApi()

const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true) // 标记是否正在初始化
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { saveField: handleChange } = useScriptSaveMutation({
  scriptId,
  isInitializing,
  logger,
  afterFieldSave: async (category, key) => {
    if (FIELDS_REQUIRE_REFRESH_AFTER_SAVE.has(`${category}.${key}`)) {
      await refreshNormalizedField(category, key)
    }
  },
})

const formData = reactive({
  name: '',
  type: 'SRC' as ScriptType,
  get path() {
    return srcConfig.Info?.Path || '.'
  },
  set path(value) {
    if (srcConfig.Info) {
      srcConfig.Info.Path = value
    }
  },
})

// SRC配置
const srcConfig = reactive(createSrcScriptDraft())

const rules = {
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
  type: [{ required: true, message: t('core.edit.pickScriptType'), trigger: 'change' }],
  path: [{ required: true, message: t('core.edit.pickSrcPath'), trigger: 'blur' }],
}

// 即时保存函数 - 只发送修改的字段（遵循最小原则）
// 后端会把这些路径字段规范化（相对路径转绝对、展开 %APPDATA%、解析 .lnk 等），
// 保存后只回读这一个字段，界面才与落盘值一致；其余字段保存即生效不再整份回读
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>(['Info.Path'])

const refreshNormalizedField = async (category: string, key: string) => {
  const scriptDetail = await getScript(scriptId)
  const normalized = (scriptDetail?.config as Record<string, any> | undefined)?.[category]?.[key]
  if (normalized !== undefined) {
    ;(srcConfig as Record<string, any>)[category][key] = normalized
  }
}

onMounted(async () => {
  // 两个请求互不依赖, 并行发出
  await Promise.all([loadScript()])
  // 初始化完成后允许自动保存
  isInitializing.value = false
})

const loadScript = async () => {
  pageLoading.value = true
  try {
    // 检查是否有通过路由状态传递的数据（新建脚本时）
    const routeState = history.state as any
    if (routeState?.scriptData) {
      // 有路由状态数据时，先使用它快速渲染，但仍然从API重新加载以确保数据完整性
      const scriptData = routeState.scriptData
      const config = scriptData.config as SRCScriptConfig
      formData.name = config.Info?.Name || '新建SRC脚本'
      Object.assign(srcConfig, config)

      // 从API重新加载完整数据（确保包含所有必要的配置）
      const scriptDetail = await getScript(scriptId)
      if (scriptDetail) {
        formData.type = scriptDetail.type
        formData.name = scriptDetail.name
        Object.assign(srcConfig, scriptDetail.config as SRCScriptConfig)
      }
    } else {
      // 编辑现有脚本时，从API获取数据
      const scriptDetail = await getScript(scriptId)

      if (!scriptDetail) {
        if (!scriptApiError.value) message.error(t('core.edit.scriptDoesNotExist'))
        router.push('/scripts')
        return
      }

      formData.type = scriptDetail.type
      formData.name = scriptDetail.name

      Object.assign(srcConfig, scriptDetail.config as SRCScriptConfig)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本失败: ${errorMsg}`)
    if (!scriptApiError.value) message.error(t('core.edit.couldNotLoadScript'))
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

const transitionOptions = computed(() => [
  { label: t('core.edit.restartEmulator'), value: 'ExitEmulator' },
  { label: t('core.edit.restartGame'), value: 'ExitGame' },
])

const handleTransitionChange = (value: string | number) => {
  const next = value as typeof srcConfig.Run.TaskTransitionMethod
  srcConfig.Run.TaskTransitionMethod = next
  void handleChange('Run', 'TaskTransitionMethod', next)
}

// 文件选择方法
const selectSRCPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error(t('core.edit.filePickingUnavailableRun'))
      return
    }

    const path = await window.electronAPI.selectFolder()
    if (path) {
      if (!srcConfig.Info) {
        srcConfig.Info = { Name: '', Path: '' }
      }
      srcConfig.Info.Path = path
      // 选择路径后立即保存
      await handleChange('Info', 'Path', path)
      message.success(t('core.edit.srcPathSelected'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择SRC路径失败: ${errorMsg}`)
    message.error(t('core.edit.couldNotPickFolder'))
  }
}
</script>

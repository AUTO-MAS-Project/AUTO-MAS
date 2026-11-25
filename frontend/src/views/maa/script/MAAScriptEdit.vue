<template>
  <ConfigEditShell :surface="false">
    <template #header>
      <ScriptEditHeader
        script-type="MAA"
        :title="t('core.edit.editScript')"
        @cancel="handleCancel"
      />
    </template>

    <ConfigLockPanel :script-id="scriptId" content-class="script-edit-content" game-binding="none">
      <a-spin :spinning="pageLoading">
        <a-alert :message="t('core.edit.howUseThis')" type="info" show-icon class="notice-alert">
          <template #description>
            <div class="notice-content">
              <p>{{ t('core.edit.annihilationLaunchesItsOwn') }}</p>
              <p>{{ t('plugins.maa_adapter.edit.maaAdapterSupportsEmulators') }}</p>
            </div>
          </template>
        </a-alert>

        <a-form
          ref="formRef"
          :model="formData"
          :rules="rules"
          layout="vertical"
          class="config-form"
        >
          <!-- 基本信息 -->
          <SectionCard variant="card" :title="t('core.edit.basicInfo')" :icon="AppstoreOutlined">
            <a-row :gutter="24">
              <a-col :xs="24" :md="12">
                <a-form-item name="name">
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.scriptName')"
                      :hint="t('core.edit.giveScriptNameYou')"
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
                      :text="t('plugins.maa_adapter.edit.maaPath')"
                      :hint="t('core.edit.pickFolderHoldingMaa2')"
                      variant="form"
                    />
                  </template>
                  <PathPickerField
                    v-model="formData.path"
                    mode="folder"
                    :placeholder="t('core.edit.pickFolderHoldingMaa')"
                    :pick-label="t('core.edit.pickFolder')"
                    @pick="selectMAAPath"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </SectionCard>

          <!-- 模拟器 / 游戏客户端 -->
          <GameBindingSection :script-id="scriptId" variant="card" />

          <!-- 运行配置 -->
          <SectionCard
            variant="card"
            :title="t('core.edit.runConfiguration')"
            :icon="ThunderboltOutlined"
          >
            <a-row :gutter="24">
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
                    :value="maaConfig.Run.TaskTransitionMethod"
                    :options="transitionOptions"
                    block
                    @change="handleTransitionChange"
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <ScriptRunLimitField
                  v-model="maaConfig.Run.ProxyTimesLimit"
                  kind="daily"
                  :label="t('core.edit.runsPerDayThis')"
                  :hint="t('core.edit.skipRunOnceThis')"
                  enhanced
                  @save="handleChange('Run', 'ProxyTimesLimit', maaConfig.Run.ProxyTimesLimit)"
                />
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :xs="24" :md="12">
                <ScriptHardTimeoutField
                  v-model:value="maaConfig.Run.HardTimeLimit"
                  full-width
                  @save="handleChange('Run', 'HardTimeLimit', maaConfig.Run.HardTimeLimit)"
                />
              </a-col>
              <a-col :xs="24" :md="12">
                <ScriptRunLimitField
                  v-model="maaConfig.Run.RunTimesLimit"
                  kind="retry"
                  :label="t('core.edit.retryLimit')"
                  :hint="t('core.edit.ifRunStillUnfinished')"
                  enhanced
                  @save="handleChange('Run', 'RunTimesLimit', maaConfig.Run.RunTimesLimit)"
                />
              </a-col>
            </a-row>
            <a-row :gutter="24">
              <a-col :xs="24" :md="12">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.annihilationTimeoutMinutes')"
                      :hint="t('core.edit.treatAnnihilationRunAs')"
                      variant="form"
                    />
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.AnnihilationTimeLimit"
                    :min="1"
                    :max="9999"
                    class="modern-number-input"
                    style="width: 100%"
                    @blur="
                      handleChange(
                        'Run',
                        'AnnihilationTimeLimit',
                        maaConfig.Run.AnnihilationTimeLimit
                      )
                    "
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="12">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.dailyRunTimeoutMinutes')"
                      :hint="t('core.edit.treatDailyRunAs2')"
                      variant="form"
                    />
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.RoutineTimeLimit"
                    :min="1"
                    :max="9999"
                    class="modern-number-input"
                    style="width: 100%"
                    @blur="handleChange('Run', 'RoutineTimeLimit', maaConfig.Run.RoutineTimeLimit)"
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </SectionCard>

          <!-- 游戏更新 -->
          <SectionCard variant="card" :title="t('core.edit.gameUpdate')" :icon="CloudSyncOutlined">
            <a-row :gutter="24" align="middle">
              <a-col :xs="24" :md="8">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.checkGameUpdateBefore')"
                      :hint="t('core.edit.beforeStartingMaaCompare')"
                      variant="form"
                    />
                  </template>
                  <a-switch
                    v-model:checked="maaConfig.Run.IfCheckGameUpdate"
                    @change="
                      (checked: boolean) => handleChange('Run', 'IfCheckGameUpdate', checked)
                    "
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="8">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.installGamePackageAutomatically')"
                      :hint="t('core.edit.whenClientDetectedAs')"
                      variant="form"
                    />
                  </template>
                  <a-switch
                    v-model:checked="maaConfig.Run.IfAutoInstallGameApk"
                    :disabled="!maaConfig.Run.IfCheckGameUpdate"
                    @change="
                      (checked: boolean) => handleChange('Run', 'IfAutoInstallGameApk', checked)
                    "
                  />
                </a-form-item>
              </a-col>
              <a-col :xs="24" :md="8">
                <a-form-item>
                  <template #label>
                    <FieldLabelWithHint
                      :text="t('core.edit.gameUpdateTimeoutMinutes')"
                      :hint="t('core.edit.timeoutDownloadingInstallingGame')"
                      variant="form"
                    />
                  </template>
                  <a-input-number
                    v-model:value="maaConfig.Run.GameUpdateTimeLimit"
                    :min="1"
                    :max="9999"
                    class="modern-number-input"
                    style="width: 100%"
                    :disabled="!maaConfig.Run.IfCheckGameUpdate"
                    @blur="
                      handleChange('Run', 'GameUpdateTimeLimit', maaConfig.Run.GameUpdateTimeLimit)
                    "
                  />
                </a-form-item>
              </a-col>
            </a-row>
          </SectionCard>

          <div class="update-settings-surface">
            <MaaUpdateSettings
              v-model:update="maaConfig.Update"
              :ready="!isInitializing"
              @change="(key, value) => handleChange('Update', key, value)"
            />
          </div>
        </a-form>
      </a-spin>
    </ConfigLockPanel>
  </ConfigEditShell>
</template>

<script setup lang="ts">
import ScriptRunLimitField from '@/views/EditView/Script/components/ScriptRunLimitField.vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import MaaUpdateSettings from './MaaUpdateSettings.vue'
import { createMaaScriptDraft } from './maaScriptDraft'
import ScriptHardTimeoutField from '@/views/EditView/Script/components/ScriptHardTimeoutField.vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import GameBindingSection from '@/components/GameBindingSection.vue'
import PathPickerField from '@/components/PathPickerField.vue'
import { AppstoreOutlined, CloudSyncOutlined, ThunderboltOutlined } from '@ant-design/icons-vue'
import { ConfigEditShell, SectionCard } from '@/components/ui'
import { useI18n } from 'vue-i18n'
import { computed, onMounted, reactive, ref } from 'vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { useRoute, useRouter } from 'vue-router'
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { MAAScriptConfig, ScriptType } from '@/types/script.ts'
import { useScriptApi } from '@/composables/useScriptApi.ts'
import { useScriptSaveMutation } from '@/composables/useScriptSaveMutation'

const { t } = useI18n()

const logger = window.electronAPI.getLogger('MAA脚本编辑')

const route = useRoute()
const router = useRouter()
const { getScript, updateScript, error: scriptApiError } = useScriptApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const scriptId = route.params.id as string
const isInitializing = ref(true) // 标记是否正在初始化
// 保存串行队列：连续改动按序写回，不再被布尔互斥丢掉
const { enqueue, saveField: handleChange } = useScriptSaveMutation({
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
  type: 'MAA' as ScriptType,
  get path() {
    return maaConfig.Info.Path
  },
  set path(value) {
    maaConfig.Info.Path = value
  },
})

// MAA配置
const maaConfig = reactive(createMaaScriptDraft())

const rules = {
  name: [{ required: true, message: t('core.edit.enterScriptName'), trigger: 'blur' }],
  type: [{ required: true, message: t('core.edit.pickScriptType'), trigger: 'change' }],
  path: [{ required: true, message: t('core.edit.pickMaaPath'), trigger: 'blur' }],
}

// 即时保存函数 - 只发送修改的字段（遵循最小原则）
// 后端会把这些路径字段规范化（相对路径转绝对、展开 %APPDATA%、解析 .lnk 等），
// 保存后只回读这一个字段，界面才与落盘值一致；其余字段保存即生效不再整份回读
const FIELDS_REQUIRE_REFRESH_AFTER_SAVE = new Set<string>(['Info.Path'])

const refreshNormalizedField = async (category: string, key: string) => {
  const scriptDetail = await getScript(scriptId)
  const normalized = (scriptDetail?.config as Record<string, any> | undefined)?.[category]?.[key]
  if (normalized !== undefined) {
    ;(maaConfig as Record<string, any>)[category][key] = normalized
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
      const config = scriptData.config as MAAScriptConfig
      formData.name = config.Info.Name || '新建MAA脚本'
      Object.assign(maaConfig, config)

      // 从API重新加载完整数据（确保包含所有必要的配置）
      const scriptDetail = await getScript(scriptId)
      if (scriptDetail) {
        formData.type = scriptDetail.type
        formData.name = scriptDetail.name
        Object.assign(maaConfig, scriptDetail.config as MAAScriptConfig)
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

      Object.assign(maaConfig, scriptDetail.config as MAAScriptConfig)
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

// 文件选择方法
const transitionOptions = computed(() => [
  { label: t('core.edit.restartEmulator'), value: 'ExitEmulator' },
  { label: t('core.edit.restartArknights'), value: 'ExitGame' },
  { label: t('core.edit.switchAccountDirectly'), value: 'NoAction' },
])

const handleTransitionChange = (value: string | number) => {
  const next = String(value) as typeof maaConfig.Run.TaskTransitionMethod
  maaConfig.Run.TaskTransitionMethod = next
  void handleChange('Run', 'TaskTransitionMethod', next)
}

const selectMAAPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error(t('core.edit.filePickingUnavailableRun'))
      return
    }

    const path = await window.electronAPI.selectFolder()
    if (path) {
      maaConfig.Info.Path = path
      // 选择路径后立即保存
      await handleChange('Info', 'Path', path)
      message.success(t('plugins.maa_adapter.edit.maaPathSelected'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`选择MAA路径失败: ${errorMsg}`)
    message.error(t('core.edit.couldNotPickFolder'))
  }
}
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped src="@/styles/scriptEdit.css"></style>

<style scoped>
.notice-alert {
  margin-bottom: 16px;
  border-radius: var(--ant-border-radius-lg);
}

.notice-content p {
  margin: 0;
}

.notice-content p + p {
  margin-top: 4px;
}

.update-settings-surface {
  padding: 20px 24px 8px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
}

html:not(.dark):not(.appearance-custom) .update-settings-surface {
  box-shadow:
    0 1px 2px rgba(16, 24, 40, 0.04),
    0 4px 12px -4px rgba(16, 24, 40, 0.06);
}
</style>

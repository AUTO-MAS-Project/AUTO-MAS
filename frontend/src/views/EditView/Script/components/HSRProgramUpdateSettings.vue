<template>
  <!-- 外部脚本更新 -->
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('core.edit.hsrExternalUpdate') }}</h3>
    </div>
    <div class="section-hint">{{ t('core.edit.hsrUpdateSectionHint') }}</div>
    <a-row :gutter="24">
      <a-col :xs="24" :lg="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.autoUpdateMode')"
              :hint="t('core.edit.hsrUpdateModeTip')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="update.AutoUpdateMode"
            :options="autoUpdateModeOptions"
            size="large"
            style="width: 100%"
            @change="handleChange('Update', 'AutoUpdateMode', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :lg="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.hsrUpdateChannel')"
              :hint="t('core.edit.hsrUpdateChannelTip')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="update.Channel"
            :options="updateChannelOptions"
            size="large"
            style="width: 100%"
            @change="handleChange('Update', 'Channel', $event)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <!-- 下载源按已填路径的引擎渲染；CDK 只在某个已渲染的源选了 Mirror 酱时需要 -->
    <a-row v-if="m7aPath || sraPath" :gutter="24">
      <a-col v-if="m7aPath" :xs="24" :lg="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.hsrUpdateM7ASource')"
              :hint="t('core.edit.hsrUpdateM7ASourceTip')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="update.M7ASource"
            :options="m7aSourceOptions"
            size="large"
            style="width: 100%"
            @change="handleChange('Update', 'M7ASource', $event)"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="sraPath" :xs="24" :lg="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.hsrUpdateSRASource')"
              :hint="t('core.edit.hsrUpdateSRASourceTip')"
              variant="form"
            />
          </template>
          <a-select
            v-model:value="update.SRASource"
            :options="sraSourceOptions"
            size="large"
            style="width: 100%"
            @change="handleChange('Update', 'SRASource', $event)"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row v-if="usesMirrorChyan" :gutter="24">
      <a-col :xs="24" :lg="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.hsrUpdateCdk')"
              :hint="t('core.edit.hsrUpdateCdkTip')"
              variant="form"
            />
          </template>
          <a-input-password
            v-model:value="update.MirrorChyanCDK"
            :placeholder="t('core.edit.hsrUpdateCdkPlaceholder')"
            size="large"
            autocomplete="off"
            @blur="handleChange('Update', 'MirrorChyanCDK', update.MirrorChyanCDK)"
          />
          <div class="form-item-hint" :class="{ 'form-item-hint--warning': isCdkMissingForMirror }">
            {{
              isCdkMissingForMirror
                ? t('core.edit.hsrUpdateCdkMissing')
                : t('core.edit.hsrUpdateCdkHint')
            }}
            <a :href="MIRRORCHYAN_CDK_URL" class="form-hint-link" @click="handleExternalLink">{{
              t('core.edit.hsrUpdateCdkGetLink')
            }}</a>
          </div>
        </a-form-item>
      </a-col>
    </a-row>

    <a-form-item>
      <template #label>
        <FieldLabelWithHint
          :text="t('core.edit.hsrUpdateManual')"
          :hint="t('core.edit.hsrUpdateManualTip')"
          variant="form"
        />
      </template>
      <a-typography-text v-if="!updateEngines.length" type="secondary">
        {{ t('core.edit.hsrUpdateNeedPath') }}
      </a-typography-text>
      <a-row v-else :gutter="24">
        <a-col v-for="engine in updateEngines" :key="engine" :xs="24" :lg="12">
          <div class="update-engine-card">
            <div class="update-engine-header">
              <span class="update-engine-name">{{ engineLabel(engine) }}</span>
              <a-typography-text type="secondary" class="update-engine-version">
                {{
                  t('core.edit.hsrUpdateInstalledVersion', {
                    version: installedVersion(engine) || t('core.edit.hsrUpdateVersionUnknown'),
                  })
                }}
              </a-typography-text>
            </div>
            <a-space wrap>
              <a-button
                :loading="updateStates[engine].checking"
                :disabled="updateStates[engine].applying"
                @click="runManualUpdate(engine, 'check')"
              >
                {{ t('core.edit.hsrUpdateCheckNow') }}
              </a-button>
              <a-button
                type="primary"
                :loading="updateStates[engine].applying"
                :disabled="updateStates[engine].checking"
                @click="runManualUpdate(engine, 'apply')"
              >
                {{ t('core.edit.hsrUpdateApplyNow') }}
              </a-button>
            </a-space>
            <a-alert
              v-if="updateStates[engine].error"
              type="error"
              show-icon
              class="update-alert"
              :message="t('core.edit.hsrUpdateRequestFailed', { engine: engineLabel(engine) })"
              :description="updateStates[engine].error"
            />
            <a-alert
              v-else-if="updateSummaries[engine]"
              :type="updateSummaries[engine]!.type"
              show-icon
              class="update-alert"
              :message="updateSummaries[engine]!.title"
              :description="updateSummaries[engine]!.description || undefined"
            />
          </div>
        </a-col>
      </a-row>
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import {
  useHSRPluginApi,
  type HSRCapabilitySnapshot,
  type HSREngine,
  type HSRUpdateAction,
  type HSRUpdateResult,
} from '@/composables/useHSRPluginApi'
import { handleExternalLink } from '@/utils/openExternal'
import type { HSRUpdateConfig } from '../hsrUpdateConfig'

const props = defineProps<{
  scriptId: string
  update: HSRUpdateConfig
  m7aPath: string
  sraPath: string
  capabilitySnapshot: HSRCapabilitySnapshot | null
}>()
const emit = defineEmits<{
  change: [key: keyof HSRUpdateConfig, value: string]
  updated: []
}>()
const { t } = useI18n()
const hsrPluginApi = useHSRPluginApi()
const logger = window.electronAPI.getLogger('HSR 更新设置')
const MIRRORCHYAN_CDK_URL = 'https://mirrorchyan.com?source=automas_script_update'
const handleChange = (_group: string, key: keyof HSRUpdateConfig, value: string) =>
  emit('change', key, value)

const autoUpdateModeOptions = computed(() => [
  { label: t('core.edit.hsrUpdateModeOff'), value: 'Off' },
  { label: t('core.edit.autoUpdateModeBeforeRun'), value: 'BeforeRun' },
])

const updateChannelOptions = computed(() => [
  { label: t('core.edit.hsrUpdateChannelStable'), value: 'stable' },
  { label: t('core.edit.hsrUpdateChannelBeta'), value: 'beta' },
])

const m7aSourceOptions = computed(() => [
  { label: t('core.edit.hsrUpdateSourceGithub'), value: 'GitHub' },
  { label: t('core.edit.hsrUpdateSourceMirrorChyan'), value: 'MirrorChyan' },
])

const sraSourceOptions = computed(() => [
  { label: t('core.edit.hsrUpdateSourceAutoSite'), value: 'AutoSite' },
  { label: t('core.edit.hsrUpdateSourceGithub'), value: 'GitHub' },
  { label: t('core.edit.hsrUpdateSourceMirrorChyan'), value: 'MirrorChyan' },
])

// 已渲染的下载源（对应引擎填了路径）里有一个选了 Mirror 酱，才需要 CDK 输入框。
const usesMirrorChyan = computed(
  () =>
    (Boolean(props.m7aPath) && props.update.M7ASource === 'MirrorChyan') ||
    (Boolean(props.sraPath) && props.update.SRASource === 'MirrorChyan')
)

// 选了 Mirror 酱却没填 CDK：后端会报错跳过，不会替用户改走 GitHub，输入框下方直接提醒。
const isCdkMissingForMirror = computed(
  () => usesMirrorChyan.value && !props.update.MirrorChyanCDK.trim()
)

// 保留立即检查和安装入口，只对已配置路径的引擎显示。
type HSRUpdateEngineState = {
  checking: boolean
  applying: boolean
  result: HSRUpdateResult | null
  error: string
}

const createUpdateEngineState = (): HSRUpdateEngineState => ({
  checking: false,
  applying: false,
  result: null,
  error: '',
})

const updateStates = reactive<Record<HSREngine, HSRUpdateEngineState>>({
  M7A: createUpdateEngineState(),
  SRA: createUpdateEngineState(),
})

const updateEngines = computed<HSREngine[]>(() => {
  const engines: HSREngine[] = []
  if (props.m7aPath) engines.push('M7A')
  if (props.sraPath) engines.push('SRA')
  return engines
})

const engineLabel = (engine: HSREngine) =>
  engine === 'M7A' ? t('core.edit.hsrUpdateEngineM7A') : t('core.edit.hsrUpdateEngineSRA')

// 能力快照里的 adapters 可能是数组或字典，两种形态都取一遍。
const installedVersion = (engine: HSREngine): string => {
  const adapters = props.capabilitySnapshot?.adapters
  const list = Array.isArray(adapters) ? adapters : Object.values(adapters ?? {})
  const adapter = list.find(item => item?.engine === engine)
  return adapter?.version?.trim() || ''
}

type HSRUpdateSummary = {
  type: 'success' | 'info' | 'warning' | 'error'
  title: string
  description: string
}

const describeUpdateResult = (
  engine: HSREngine,
  result: HSRUpdateResult | null
): HSRUpdateSummary | null => {
  if (!result) return null
  const name = engineLabel(engine)
  const unknown = t('core.edit.hsrUpdateVersionUnknown')
  const current = result.current_version?.trim() || unknown
  const latest = result.latest_version?.trim() || unknown
  if (result.updated) {
    return {
      type: 'success',
      title: t('core.edit.hsrUpdateDone', { engine: name, version: latest }),
      description: result.message,
    }
  }
  if (!result.checked) {
    return {
      type: 'error',
      title: t('core.edit.hsrUpdateCheckFailed', { engine: name }),
      description: result.message,
    }
  }
  if (!result.update_available) {
    return {
      type: 'success',
      title: t('core.edit.hsrUpdateUpToDate', { engine: name, version: current }),
      description: result.message,
    }
  }
  if (!result.installable) {
    // 有新版但装不了：多半是 CDK 问题，和「可更新」明确区分开。
    return {
      type: 'warning',
      title: t('core.edit.hsrUpdateNotInstallable', { engine: name, version: latest }),
      description: result.message || t('core.edit.hsrUpdateNotInstallableHint'),
    }
  }
  return {
    type: 'info',
    title: t('core.edit.hsrUpdateAvailable', { engine: name, latest, current }),
    description: result.message,
  }
}

const updateSummaries = computed<Record<HSREngine, HSRUpdateSummary | null>>(() => ({
  M7A: describeUpdateResult('M7A', updateStates.M7A.result),
  SRA: describeUpdateResult('SRA', updateStates.SRA.result),
}))

const runManualUpdate = async (engine: HSREngine, action: HSRUpdateAction) => {
  const state = updateStates[engine]
  if (state.checking || state.applying) return
  if (action === 'check') state.checking = true
  else state.applying = true
  state.error = ''
  const generation = requestGeneration
  try {
    const result = await hsrPluginApi.runEngineUpdate(props.scriptId, engine, action)
    if (generation !== requestGeneration) return
    state.result = result
    const summary = describeUpdateResult(engine, result)
    if (summary) {
      if (summary.type === 'success') message.success(summary.title)
      else if (summary.type === 'warning') message.warning(summary.title)
      else if (summary.type === 'error') message.error(summary.title)
      else message.info(summary.title)
    }
    // 装完后能力快照里的已安装版本会变，拉一次让「已安装」跟上。
    if (result.updated) emit('updated')
  } catch (error) {
    if (generation !== requestGeneration) return
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`${engine} ${action} 更新请求失败: ${errorMsg}`)
    state.result = null
    state.error = errorMsg
    message.error(
      `${t('core.edit.hsrUpdateRequestFailed', { engine: engineLabel(engine) })}: ${errorMsg}`
    )
  } finally {
    if (generation === requestGeneration) {
      state.checking = false
      state.applying = false
    }
  }
}

let requestGeneration = 0
watch(
  () => [props.scriptId, props.m7aPath, props.sraPath],
  () => {
    requestGeneration++
    Object.assign(updateStates.M7A, createUpdateEngineState())
    Object.assign(updateStates.SRA, createUpdateEngineState())
  },
  { flush: 'sync' }
)
onBeforeUnmount(() => {
  requestGeneration++
})
</script>

<style scoped>
.form-section {
  margin-bottom: 12px;
}

.section-header {
  margin-bottom: 6px;
}

.section-header h3::before {
  background: var(--ant-color-primary);
}

.section-hint {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  margin: 4px 0 12px 0;
}

.form-item-hint--warning {
  color: var(--ant-color-warning);
}

.form-hint-link {
  margin-left: 4px;
  color: var(--ant-color-primary);
  text-decoration: underline;
}

.form-hint-link:hover {
  color: var(--ant-color-primary-hover);
}

.update-engine-card {
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
  margin-bottom: 12px;
}

.update-engine-header {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 8px 12px;
  margin-bottom: 10px;
}

.update-engine-name {
  font-weight: 600;
  color: var(--ant-color-text);
}

.update-engine-version {
  font-size: 12px;
}

.update-alert {
  margin-top: 12px;
}
</style>

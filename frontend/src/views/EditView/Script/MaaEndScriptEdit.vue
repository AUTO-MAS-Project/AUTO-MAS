<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">鑴氭湰绠＄悊</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/MAA.png" alt="MaaEnd" class="breadcrumb-logo" />
            缂栬緫鑴氭湰
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        杩斿�?
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card title="MaaEnd 鑴氭湰閰嶇疆" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="orange" class="type-tag">MaaEnd</a-tag>
      </template>

      <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>鍩烘湰淇℃伅</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    鑴氭湰鍚嶇�?
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  placeholder="璇疯緭鍏ヨ剼鏈悕绉?
                  size="large"
                  class="modern-input"
                  @blur="handleNameBlur"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item name="path" :rules="rules.path">
                <template #label>
                  <span class="form-label">
                    MaaEnd 璺�?
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    placeholder="璇烽€夋�?MaaEnd 鎵€鍦ㄧ洰褰?
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectMaaEndPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    閫夋嫨鏂囦欢�?
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col v-if="config.Run.ControllerType !== 'ADB'" :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">Endfield 璺緞锛圵in32�?/span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="config.Run.GamePath"
                    placeholder="璇烽€夋�?Endfield.exe"
                    size="large"
                    class="path-input"
                    @blur="handleChange('Run', 'GamePath', config.Run.GamePath)"
                  />
                  <a-button size="large" class="path-button" @click="selectGamePath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    閫夋�?
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>杩愯閰嶇疆</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    鎺у埗鍣ㄧ被鍨?
                    <QuestionCircleOutlined class="help-icon" />
                  </span>
                </template>
                <a-select
                  v-model:value="config.Run.ControllerType"
                  size="large"
                  @change="handleChange('Run', 'ControllerType', $event)"
                >
                  <a-select-option value="Win32-Window">鐢佃剳绔?榛樿�?/a-select-option>
                  <a-select-option value="Win32-Window-Background">鐢佃剳绔?鍚庡�?/a-select-option>
                  <a-select-option value="Win32-Front">鐢佃剳绔?鍓嶅�?/a-select-option>
                  <a-select-option value="ADB">瀹夊崜绔?/a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">瓒呮椂锛堝垎閽燂�?/span>
                </template>
                <a-input-number
                  v-model:value="config.Run.Timeout"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'Timeout', config.Run.Timeout)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">閲嶈瘯娆℃暟</span>
                </template>
                <a-input-number
                  v-model:value="config.Run.Retry"
                  :min="0"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'Retry', config.Run.Retry)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">杩愯娆℃暟闄愬�?/span>
                </template>
                <a-input-number
                  v-model:value="config.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  class="modern-number-input"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', config.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">鏄惁鍚敤鍒囧�?/span>
                </template>
                <a-select
                  v-model:value="config.Run.IfAccountSwitch"
                  size="large"
                  @change="handleChange('Run', 'IfAccountSwitch', $event)"
                >
                  <a-select-option :value="true">�?/a-select-option>
                  <a-select-option :value="false">�?/a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">鍒囧彿鏂瑰紡</span>
                </template>
                <a-select
                  v-model:value="config.Run.AccountSwitchMethod"
                  size="large"
                  @change="handleChange('Run', 'AccountSwitchMethod', $event)"
                >
                  <a-select-option value="NoAction">涓嶅垏鎹?/a-select-option>
                  <a-select-option value="ExitGame">閲嶅惎娓告垙</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col v-if="config.Run.ControllerType !== 'ADB'" :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">缁撴潫鍚庡叧�?Endfield</span>
                </template>
                <a-select
                  v-model:value="config.Run.CloseGameOnFinish"
                  size="large"
                  @change="handleChange('Run', 'CloseGameOnFinish', $event)"
                >
                  <a-select-option :value="true">�?/a-select-option>
                  <a-select-option :value="false">�?/a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>MaaEnd 閰嶇�?/h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">璧勬簮閰嶇疆</span>
                </template>
                <a-select
                  v-model:value="config.MaaEnd.ResourceProfile"
                  mode="combobox"
                  :options="resourceProfileOptions"
                  placeholder="璇烽€夋嫨鎴栬緭鍏ヨ祫婧愰厤�?
                  size="large"
                  class="modern-input"
                  @change="handleChange('MaaEnd', 'ResourceProfile', config.MaaEnd.ResourceProfile)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">棰勮浠诲姟</span>
                </template>
                <a-select
                  v-if="presetOptions.length > 0"
                  v-model:value="config.MaaEnd.PresetTask"
                  size="large"
                  show-search
                  allow-clear
                  placeholder="璇烽€夋嫨棰勮浠诲�?
                  :options="presetOptions"
                  @change="handleChange('MaaEnd', 'PresetTask', $event || '')"
                />
                <a-input
                  v-else
                  v-model:value="config.MaaEnd.PresetTask"
                  placeholder="璇疯緭鍏ラ璁句换鍔?
                  size="large"
                  class="modern-input"
                  @blur="handleChange('MaaEnd', 'PresetTask', config.MaaEnd.PresetTask)"
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
import type { FormInstance } from 'ant-design-vue'
import { message } from 'ant-design-vue'
import type { ScriptType } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'

const logger = window.electronAPI.getLogger('MaaEnd鑴氭湰缂栬緫')

interface MaaEndScriptConfigLocal {
  Info: {
    Name: string
    Path: string
  }
  Run: {
    Timeout: number
    Retry: number
    RunTimesLimit: number
    IfAccountSwitch: boolean
    AccountSwitchMethod: 'ExitGame' | 'NoAction'
    GamePath: string
    CloseGameOnFinish: boolean
    ControllerType: 'Win32-Window' | 'Win32-Window-Background' | 'Win32-Front' | 'ADB'
  }
  MaaEnd: {
    ResourceProfile: string
    PresetTask: string
  }
}

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const formRef = ref<FormInstance>()
const pageLoading = ref(false)
const isInitializing = ref(true)
const isSaving = ref(false)
const presetOptions = ref<Array<{ label: string; value: string }>>([])

const scriptId = route.params.id as string

const config = reactive<MaaEndScriptConfigLocal>({
  Info: {
    Name: '',
    Path: '.',
  },
  Run: {
    Timeout: 10,
    Retry: 3,
    RunTimesLimit: 3,
    IfAccountSwitch: false,
    AccountSwitchMethod: 'NoAction',
    GamePath: '',
    CloseGameOnFinish: true,
    ControllerType: 'Win32-Window',
  },
  MaaEnd: {
    ResourceProfile: 'MaaEnd',
    PresetTask: '',
  },
})

const formData = reactive({
  name: '',
  type: 'MaaEnd' as ScriptType,
  get path() {
    return config.Info.Path
  },
  set path(value: string) {
    config.Info.Path = value
  },
})

const rules = {
  name: [{ required: true, message: '璇疯緭鍏ヨ剼鏈悕绉?, trigger: 'blur' }],
  path: [{ required: true, message: '璇烽€夋�?MaaEnd 璺�?, trigger: 'blur' }],
}

const resourceProfileOptions = computed(() => {
  const options = ['MaaEnd']
  const current = (config.MaaEnd.ResourceProfile || '').trim()
  if (current && !options.includes(current)) {
    options.unshift(current)
  }
  return options.map(value => ({ label: value, value }))
})

const applyConfig = (rawConfig: any, nameFallback = '鏂板缓MaaEnd鑴氭�?) => {
  config.Info.Name = rawConfig?.Info?.Name ?? nameFallback
  config.Info.Path = rawConfig?.Info?.Path ?? '.'

  config.Run.Timeout = rawConfig?.Run?.Timeout ?? 10
  config.Run.Retry = rawConfig?.Run?.Retry ?? 3
  config.Run.RunTimesLimit = rawConfig?.Run?.RunTimesLimit ?? 3
  config.Run.IfAccountSwitch = rawConfig?.Run?.IfAccountSwitch ?? false
  config.Run.AccountSwitchMethod = rawConfig?.Run?.AccountSwitchMethod ?? 'NoAction'
  config.Run.GamePath = rawConfig?.Run?.GamePath ?? ''
  config.Run.CloseGameOnFinish = rawConfig?.Run?.CloseGameOnFinish ?? true
  config.Run.ControllerType = rawConfig?.Run?.ControllerType ?? 'Win32-Window'

  config.MaaEnd.ResourceProfile = rawConfig?.MaaEnd?.ResourceProfile ?? 'MaaEnd'
  config.MaaEnd.PresetTask = rawConfig?.MaaEnd?.PresetTask ?? ''

  formData.name = config.Info.Name
}

const refreshScript = async () => {
  const scriptDetail = await getScript(scriptId)
  if (!scriptDetail) {
    return
  }
  if (scriptDetail.type !== 'MaaEnd') {
    message.error('鑴氭湰绫诲瀷涓嶅尮�?)
    router.push('/scripts')
    return
  }
  formData.type = scriptDetail.type
  applyConfig(scriptDetail.config, scriptDetail.name || '鏂板缓MaaEnd鑴氭�?)
}

const handleChange = async (category: string, key: string, value: any) => {
  if (isInitializing.value || isSaving.value) {
    return
  }

  isSaving.value = true
  try {
    const updateData: Record<string, any> = {
      [category]: {
        [key]: value,
      },
    }
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`閰嶇疆宸蹭繚�? ${category}.${key}`)
    }
    logger.error(`淇濆瓨澶辫触: ${errorMsg}`)
  } finally {
    isSaving.value = false
  }
}

const handleNameBlur = async () => {
  config.Info.Name = formData.name
  await handleChange('Info', 'Name', formData.name)
}

const resolveMaaEndConfigPaths = () => {
  const candidates: string[] = [`data/${scriptId}/Default/ConfigFile/mxu-MaaEnd.json`]
  const base = String(config.Info.Path || '').trim()
  if (base) {
    candidates.push(`${base.replace(/[\\/]+$/, '')}/config/mxu-MaaEnd.json`)
  }
  return Array.from(new Set(candidates))
}

const parsePresetOptions = (content: string) => {
  const parsed = JSON.parse(content)
  const instances = Array.isArray(parsed?.instances) ? parsed.instances : []

  const optionMap = new Map<string, string>()
  for (const item of instances) {
    const id = String(item?.id || '').trim()
    const name = String(item?.name || '').trim()
    if (!id || !name || optionMap.has(id)) {
      continue
    }
    optionMap.set(id, name)
  }

  return Array.from(optionMap.entries()).map(([id, name]) => ({
    label: name,
    value: id,
  }))
}

const loadPresetOptions = async () => {
  const configPaths = resolveMaaEndConfigPaths()
  if (configPaths.length === 0 || !window.electronAPI?.readFile) {
    presetOptions.value = []
    return
  }

  let lastError: unknown = null
  for (const configPath of configPaths) {
    try {
      const content = await window.electronAPI.readFile(configPath)
      presetOptions.value = parsePresetOptions(content)
      return
    } catch (error) {
      lastError = error
    }
  }

  presetOptions.value = []
  if (lastError) {
    const errorMsg = lastError instanceof Error ? lastError.message : String(lastError)
    logger.warn(`���� MaaEnd Ԥ������ѡ��ʧ��: ${errorMsg}`)
  }
}

const loadScript = async () => {
  pageLoading.value = true
  try {
    const routeState = history.state as any
    if (routeState?.scriptData?.config) {
      applyConfig(routeState.scriptData.config)
      await refreshScript()
      return
    }

    const scriptDetail = await getScript(scriptId)
    if (!scriptDetail) {
      message.error('鑴氭湰涓嶅瓨鍦ㄦ垨鍔犺浇澶辫�?)
      router.push('/scripts')
      return
    }
    if (scriptDetail.type !== 'MaaEnd') {
      message.error('鑴氭湰绫诲瀷涓嶅尮�?)
      router.push('/scripts')
      return
    }

    formData.type = scriptDetail.type
    applyConfig(scriptDetail.config, scriptDetail.name || '鏂板缓MaaEnd鑴氭�?)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`鍔犺浇鑴氭湰澶辫�? ${errorMsg}`)
    message.error('鍔犺浇鑴氭湰澶辫�?)
    router.push('/scripts')
  } finally {
    pageLoading.value = false
  }
}

const selectMaaEndPath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('鏂囦欢閫夋嫨鍔熻兘涓嶅彲鐢紝璇峰湪 Electron 鐜涓繍�?)
      return
    }

    const path = await (window.electronAPI as any).selectFolder()
    if (!path) {
      return
    }

    config.Info.Path = path
    formData.path = path
    await handleChange('Info', 'Path', path)
    await loadPresetOptions()
    message.success('MaaEnd 璺緞閫夋嫨鎴愬�?)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`閫夋�?MaaEnd 璺緞澶辫触: ${errorMsg}`)
    message.error('閫夋嫨鏂囦欢澶瑰け璐?)
  }
}

const selectGamePath = async () => {
  try {
    if (!window.electronAPI) {
      message.error('鏂囦欢閫夋嫨鍔熻兘涓嶅彲鐢紝璇峰湪 Electron 鐜涓繍�?)
      return
    }

    const selected = await (window.electronAPI as any).selectFile([
      { name: '鍙墽琛屾枃�?, extensions: ['exe'] },
      { name: '鎵€鏈夋枃浠?, extensions: ['*'] },
    ])
    const path = Array.isArray(selected) ? selected[0] : selected
    if (!path) {
      return
    }

    config.Run.GamePath = path
    await handleChange('Run', 'GamePath', path)
    message.success('Endfield 璺緞閫夋嫨鎴愬�?)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`閫夋�?Endfield 璺緞澶辫触: ${errorMsg}`)
    message.error('閫夋�?Endfield 璺緞澶辫触')
  }
}

const handleCancel = () => {
  router.push('/scripts')
}

onMounted(async () => {
  await loadScript()
  await loadPresetOptions()
  isInitializing.value = false
})
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  padding: 0 8px;
}

.breadcrumb-link {
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

.config-card {
  border-radius: 12px;
}

.form-section {
  margin-bottom: 24px;
}

.section-header h3 {
  margin: 0 0 16px;
  font-size: 16px;
  font-weight: 600;
}

.form-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.help-icon {
  color: var(--ant-color-text-description);
}

.path-input-group {
  display: flex;
}

.path-input {
  flex: 1;
}

.path-button {
  min-width: 110px;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
}
</style>


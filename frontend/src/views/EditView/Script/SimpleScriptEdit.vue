<template>
  <div class="simple-script-edit">
    <header class="edit-header">
      <a-breadcrumb>
        <a-breadcrumb-item><router-link to="/scripts">脚本管理</router-link></a-breadcrumb-item>
        <a-breadcrumb-item>编辑简易脚本</a-breadcrumb-item>
      </a-breadcrumb>
      <a-button size="large" @click="router.push('/scripts')">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
    </header>

    <a-spin :spinning="pageLoading">
      <a-form layout="vertical" class="config-form">
        <a-card title="基本信息" class="config-card">
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="脚本名称" required>
                <a-input
                  v-model:value="config.Info.Name"
                  size="large"
                  placeholder="请输入脚本名称"
                  @blur="saveField('Info', 'Name', config.Info.Name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="根目录">
                <a-input-group compact>
                  <a-input
                    v-model:value="config.Info.RootPath"
                    size="large"
                    style="width: calc(100% - 112px)"
                    placeholder="请选择脚本根目录"
                    @blur="saveField('Info', 'RootPath', config.Info.RootPath)"
                  />
                  <a-button size="large" style="width: 112px" @click="selectFolder('RootPath')">
                    <template #icon><FolderOpenOutlined /></template>
                    选择
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>

        <a-card title="程序与进程监控" class="config-card">
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="程序路径" required>
                <a-input-group compact>
                  <a-input
                    v-model:value="config.Script.ScriptPath"
                    size="large"
                    style="width: calc(100% - 112px)"
                    placeholder="请选择要启动的程序"
                    @blur="saveField('Script', 'ScriptPath', config.Script.ScriptPath)"
                  />
                  <a-button size="large" style="width: 112px" @click="selectFile('ScriptPath')">
                    <template #icon><FileOutlined /></template>
                    选择
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="启动参数">
                <a-input
                  v-model:value="config.Script.Arguments"
                  size="large"
                  placeholder="请输入普通命令行参数"
                  @blur="saveField('Script', 'Arguments', config.Script.Arguments)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24" align="middle">
            <a-col :span="8">
              <a-form-item label="追踪目标进程">
                <a-switch
                  v-model:checked="config.Script.IfTrackProcess"
                  @change="saveField('Script', 'IfTrackProcess', config.Script.IfTrackProcess)"
                />
                <span class="switch-description">启动器会转交子进程时启用</span>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="目标进程名称">
                <a-input
                  v-model:value="config.Script.TrackProcessName"
                  :disabled="!config.Script.IfTrackProcess"
                  placeholder="例如 script.exe"
                  @blur="saveField('Script', 'TrackProcessName', config.Script.TrackProcessName)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="目标进程命令行">
                <a-input
                  v-model:value="config.Script.TrackProcessCmdline"
                  :disabled="!config.Script.IfTrackProcess"
                  placeholder="完整命令行参数，可留空"
                  @blur="
                    saveField('Script', 'TrackProcessCmdline', config.Script.TrackProcessCmdline)
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-form-item label="目标进程路径">
            <a-input-group compact>
              <a-input
                v-model:value="config.Script.TrackProcessExe"
                :disabled="!config.Script.IfTrackProcess"
                style="width: calc(100% - 112px)"
                placeholder="可选；只会绑定本次启动后新出现的进程"
                @blur="saveField('Script', 'TrackProcessExe', config.Script.TrackProcessExe)"
              />
              <a-button
                style="width: 112px"
                :disabled="!config.Script.IfTrackProcess"
                @click="selectFile('TrackProcessExe')"
              >
                <template #icon><FileOutlined /></template>
                选择
              </a-button>
            </a-input-group>
          </a-form-item>
        </a-card>

        <a-card title="日志监控（可选）" class="config-card">
          <a-alert
            type="info"
            show-icon
            message="未填写日志路径时，将回落到仅监控进程并根据退出码判断结果。"
            class="section-alert"
          />
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="日志路径">
                <a-input-group compact>
                  <a-input
                    v-model:value="config.Script.LogPath"
                    style="width: calc(100% - 112px)"
                    placeholder="留空表示不监控日志文件"
                    @blur="saveField('Script', 'LogPath', config.Script.LogPath)"
                  />
                  <a-button style="width: 112px" @click="selectFile('LogPath')">
                    <template #icon><FileOutlined /></template>
                    选择
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="日志文件名格式">
                <a-input
                  v-model:value="config.Script.LogPathFormat"
                  :disabled="!config.Script.LogPath"
                  placeholder="固定文件名时留空"
                  @blur="saveField('Script', 'LogPathFormat', config.Script.LogPathFormat)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="6">
              <a-form-item label="时间戳开始位置">
                <a-input-number
                  v-model:value="config.Script.LogTimeStart"
                  :min="1"
                  :disabled="!config.Script.LogPath"
                  style="width: 100%"
                  @change="saveField('Script', 'LogTimeStart', config.Script.LogTimeStart)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="时间戳结束位置">
                <a-input-number
                  v-model:value="config.Script.LogTimeEnd"
                  :min="1"
                  :disabled="!config.Script.LogPath"
                  style="width: 100%"
                  @change="saveField('Script', 'LogTimeEnd', config.Script.LogTimeEnd)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="日志时间戳格式">
                <a-input
                  v-model:value="config.Script.LogTimeFormat"
                  :disabled="!config.Script.LogPath"
                  placeholder="%Y-%m-%d %H:%M:%S"
                  @blur="saveField('Script', 'LogTimeFormat', config.Script.LogTimeFormat)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="成功日志">
                <a-input
                  v-model:value="config.Script.SuccessLog"
                  :disabled="!config.Script.LogPath"
                  placeholder="多个关键字使用 | 分隔"
                  @blur="saveField('Script', 'SuccessLog', config.Script.SuccessLog)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="错误日志">
                <a-input
                  v-model:value="config.Script.ErrorLog"
                  :disabled="!config.Script.LogPath"
                  placeholder="多个关键字使用 | 分隔"
                  @blur="saveField('Script', 'ErrorLog', config.Script.ErrorLog)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>

        <a-card title="游戏与模拟器" class="config-card">
          <a-row :gutter="24" align="middle">
            <a-col :span="6">
              <a-form-item label="启用游戏管理">
                <a-switch
                  v-model:checked="config.Game.Enabled"
                  @change="saveField('Game', 'Enabled', config.Game.Enabled)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="类型">
                <a-select
                  v-model:value="config.Game.Type"
                  :disabled="!config.Game.Enabled"
                  @change="handleGameTypeChange"
                >
                  <a-select-option value="Emulator">模拟器</a-select-option>
                  <a-select-option value="Client">PC 客户端</a-select-option>
                  <a-select-option value="URL">URL 协议</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="等待启动（秒）">
                <a-input-number
                  v-model:value="config.Game.WaitTime"
                  :min="0"
                  :disabled="!config.Game.Enabled"
                  style="width: 100%"
                  @change="saveField('Game', 'WaitTime', config.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="强制关闭">
                <a-switch
                  v-model:checked="config.Game.IfForceClose"
                  :disabled="!config.Game.Enabled || config.Game.Type !== 'Client'"
                  @change="saveField('Game', 'IfForceClose', config.Game.IfForceClose)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-if="config.Game.Type === 'Emulator'" :gutter="24">
            <a-col :span="12">
              <a-form-item label="模拟器">
                <a-select
                  v-model:value="config.Game.EmulatorId"
                  :loading="emulatorLoading"
                  :disabled="!config.Game.Enabled"
                  @change="handleEmulatorChange"
                >
                  <a-select-option
                    v-for="option in emulatorOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="模拟器实例">
                <a-select
                  v-model:value="config.Game.EmulatorIndex"
                  :loading="emulatorDeviceLoading"
                  :disabled="!config.Game.Enabled || !config.Game.EmulatorId"
                  @change="saveField('Game', 'EmulatorIndex', config.Game.EmulatorIndex)"
                >
                  <a-select-option
                    v-for="option in emulatorDeviceOptions"
                    :key="option.value"
                    :value="option.value"
                  >
                    {{ option.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-else-if="config.Game.Type === 'Client'" :gutter="24">
            <a-col :span="12">
              <a-form-item label="客户端路径">
                <a-input-group compact>
                  <a-input
                    v-model:value="config.Game.Path"
                    :disabled="!config.Game.Enabled"
                    style="width: calc(100% - 112px)"
                    @blur="saveField('Game', 'Path', config.Game.Path)"
                  />
                  <a-button
                    style="width: 112px"
                    :disabled="!config.Game.Enabled"
                    @click="selectFile('GamePath')"
                  >
                    <template #icon><FileOutlined /></template>
                    选择
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="客户端参数">
                <a-input
                  v-model:value="config.Game.Arguments"
                  :disabled="!config.Game.Enabled"
                  @blur="saveField('Game', 'Arguments', config.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row v-else :gutter="24">
            <a-col :span="12">
              <a-form-item label="协议 URL">
                <a-input
                  v-model:value="config.Game.URL"
                  :disabled="!config.Game.Enabled"
                  placeholder="例如 game://launch"
                  @blur="saveField('Game', 'URL', config.Game.URL)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="游戏进程名称">
                <a-input
                  v-model:value="config.Game.ProcessName"
                  :disabled="!config.Game.Enabled"
                  placeholder="例如 game.exe"
                  @blur="saveField('Game', 'ProcessName', config.Game.ProcessName)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>

        <a-card title="运行配置" class="config-card">
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item label="每日代理次数限制">
                <a-input-number
                  v-model:value="config.Run.ProxyTimesLimit"
                  :min="0"
                  style="width: 100%"
                  @change="saveField('Run', 'ProxyTimesLimit', config.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="失败重试次数">
                <a-input-number
                  v-model:value="config.Run.RunTimesLimit"
                  :min="1"
                  style="width: 100%"
                  @change="saveField('Run', 'RunTimesLimit', config.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="单次总时长上限（分钟）">
                <a-input-number
                  v-model:value="config.Run.RunTimeLimit"
                  :min="0"
                  style="width: 100%"
                  @change="saveField('Run', 'RunTimeLimit', config.Run.RunTimeLimit)"
                />
                <span class="field-help">0 表示不限制</span>
              </a-form-item>
            </a-col>
          </a-row>
        </a-card>
      </a-form>
    </a-spin>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, FileOutlined, FolderOpenOutlined } from '@ant-design/icons-vue'
import { Service, type ComboBoxItem } from '@/api'
import type { SimpleScriptConfig } from '@/types/script'
import { useScriptApi } from '@/composables/useScriptApi'

const logger = window.electronAPI.getLogger('简易脚本编辑')
const route = useRoute()
const router = useRouter()
const scriptId = route.params.id as string
const { getScript, updateScript } = useScriptApi()

const pageLoading = ref(false)
const isInitializing = ref(true)
const isSaving = ref(false)
const emulatorLoading = ref(false)
const emulatorDeviceLoading = ref(false)
const emulatorOptions = ref<ComboBoxItem[]>([])
const emulatorDeviceOptions = ref<ComboBoxItem[]>([])

const config = reactive({
  Info: { Name: '新简易脚本', RootPath: '' },
  Script: {
    ScriptPath: '',
    Arguments: '',
    IfTrackProcess: false,
    TrackProcessName: '',
    TrackProcessExe: '',
    TrackProcessCmdline: '',
    LogPath: '',
    LogPathFormat: '',
    LogTimeStart: 1,
    LogTimeEnd: 1,
    LogTimeFormat: '%Y-%m-%d %H:%M:%S',
    SuccessLog: '',
    ErrorLog: '',
  },
  Game: {
    Enabled: false,
    Type: 'Emulator',
    Path: '',
    URL: '',
    ProcessName: '',
    Arguments: '',
    WaitTime: 0,
    IfForceClose: false,
    EmulatorId: '-',
    EmulatorIndex: '-',
  },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 10 },
})

const saveField = async (group: string, field: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, { [group]: { [field]: value } })
    if (!success) message.error('保存配置失败')
  } finally {
    isSaving.value = false
  }
}

const loadScript = async () => {
  pageLoading.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail || detail.type !== 'Simple') {
      message.error('简易脚本不存在或类型不匹配')
      router.push('/scripts')
      return
    }
    const data = detail.config as SimpleScriptConfig
    Object.assign(config.Info, data.Info)
    Object.assign(config.Script, data.Script)
    Object.assign(config.Game, data.Game)
    Object.assign(config.Run, data.Run)

    if (config.Game.Type === 'Emulator') {
      await loadEmulatorOptions()
      if (config.Game.EmulatorId && config.Game.EmulatorId !== '-') {
        await loadEmulatorDeviceOptions(config.Game.EmulatorId)
      }
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error)
    logger.error(`加载简易脚本失败: ${errorMessage}`)
    message.error('加载简易脚本失败')
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectFolder = async (field: 'RootPath') => {
  const path = await window.electronAPI.selectFolder()
  if (!path) return
  config.Info[field] = path
  await saveField('Info', field, path)
}

const selectFile = async (field: 'ScriptPath' | 'TrackProcessExe' | 'LogPath' | 'GamePath') => {
  const paths = await window.electronAPI.selectFile([{ name: '所有文件', extensions: ['*'] }])
  const path = paths?.[0]
  if (!path) return

  if (field === 'GamePath') {
    config.Game.Path = path
    await saveField('Game', 'Path', path)
    return
  }
  config.Script[field] = path
  await saveField('Script', field, path)
}

const loadEmulatorOptions = async () => {
  emulatorLoading.value = true
  try {
    const response = await Service.getEmulatorComboxApiInfoComboxEmulatorPost()
    emulatorOptions.value = response.code === 200 ? response.data || [] : []
  } finally {
    emulatorLoading.value = false
  }
}

const loadEmulatorDeviceOptions = async (emulatorId: string) => {
  emulatorDeviceLoading.value = true
  try {
    const response = await Service.getEmulatorDevicesComboxApiInfoComboxEmulatorDevicesPost({
      emulatorId,
    })
    emulatorDeviceOptions.value = response.code === 200 ? response.data || [] : []
  } finally {
    emulatorDeviceLoading.value = false
  }
}

const handleEmulatorChange = async (emulatorId: string) => {
  config.Game.EmulatorIndex = '-'
  await updateScript(scriptId, {
    Game: { EmulatorId: emulatorId, EmulatorIndex: '-' },
  })
  await loadEmulatorDeviceOptions(emulatorId)
}

const handleGameTypeChange = async (gameType: string) => {
  await saveField('Game', 'Type', gameType)
  if (gameType === 'Emulator' && emulatorOptions.value.length === 0) {
    await loadEmulatorOptions()
  }
}

onMounted(loadScript)
</script>

<style scoped>
.simple-script-edit {
  padding: 0 8px 32px;
}

.edit-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.config-form {
  max-width: 1200px;
  margin: 0 auto;
}

.config-card {
  margin-bottom: 20px;
  border-radius: 12px;
}

.section-alert {
  margin-bottom: 20px;
}

.switch-description,
.field-help {
  margin-left: 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
</style>

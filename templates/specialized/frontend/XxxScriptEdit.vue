<template>
  <div class="script-edit-page">
    <div class="page-header">
      <a-breadcrumb>
        <a-breadcrumb-item><router-link to="/scripts">脚本管理</router-link></a-breadcrumb-item>
        <a-breadcrumb-item>编辑专项脚本</a-breadcrumb-item>
      </a-breadcrumb>
      <a-button size="large" @click="handleCancel">返回</a-button>
    </div>

    <a-card title="专项显示名称脚本配置" :loading="pageLoading">
      <template #extra><a-tag color="blue">Xxx</a-tag></template>
      <a-form :model="formData" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header"><h3>基本信息</h3></div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item label="脚本名称">
                <a-input
                  v-model:value="formData.Info.Name"
                  size="large"
                  placeholder="请输入脚本名称"
                  @blur="handleChange('Info', 'Name', formData.Info.Name)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="16">
              <a-form-item label="脚本根目录" required>
                <a-input-group compact>
                  <a-input v-model:value="formData.Info.RootPath" readonly size="large" />
                  <a-button size="large" @click="selectRootPath">选择文件夹</a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header"><h3>脚本运行</h3></div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="主程序路径" required>
                <a-input-group compact>
                  <a-input v-model:value="formData.Script.ScriptPath" readonly size="large" />
                  <a-button size="large" @click="selectScriptPath">选择文件</a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="启动参数">
                <a-input
                  v-model:value="formData.Script.Arguments"
                  size="large"
                  placeholder="通用参数；专项参数在 AutoProxy 中构造"
                  @blur="handleChange('Script', 'Arguments', formData.Script.Arguments)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item label="追踪目标进程">
                <a-switch
                  v-model:checked="formData.Script.IfTrackProcess"
                  @change="handleChange('Script', 'IfTrackProcess', formData.Script.IfTrackProcess)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="进程名称">
                <a-input
                  v-model:value="formData.Script.TrackProcessName"
                  :disabled="!formData.Script.IfTrackProcess"
                  @blur="
                    handleChange('Script', 'TrackProcessName', formData.Script.TrackProcessName)
                  "
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item label="进程命令行">
                <a-input
                  v-model:value="formData.Script.TrackProcessCmdline"
                  :disabled="!formData.Script.IfTrackProcess"
                  @blur="
                    handleChange(
                      'Script',
                      'TrackProcessCmdline',
                      formData.Script.TrackProcessCmdline
                    )
                  "
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-form-item label="进程可执行文件">
            <a-input-group compact>
              <a-input v-model:value="formData.Script.TrackProcessExe" readonly />
              <a-button @click="selectTrackProcessExe">选择文件</a-button>
              <a-button @click="clearTrackProcessExe">清空</a-button>
            </a-input-group>
          </a-form-item>
        </div>

        <div class="form-section">
          <div class="section-header"><h3>配置与日志</h3></div>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="配置路径" required>
                <a-input-group compact>
                  <a-input v-model:value="formData.Script.ConfigPath" readonly size="large" />
                  <a-button size="large" @click="selectConfigPath">选择路径</a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="配置类型">
                <a-select
                  v-model:value="formData.Script.ConfigPathMode"
                  size="large"
                  @change="handleChange('Script', 'ConfigPathMode', formData.Script.ConfigPathMode)"
                >
                  <a-select-option value="File">单文件</a-select-option>
                  <a-select-option value="Folder">文件夹</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item label="回写时机">
                <a-select
                  v-model:value="formData.Script.UpdateConfigMode"
                  size="large"
                  @change="
                    handleChange('Script', 'UpdateConfigMode', formData.Script.UpdateConfigMode)
                  "
                >
                  <a-select-option value="Never">从不</a-select-option>
                  <a-select-option value="Success">成功时</a-select-option>
                  <a-select-option value="Failure">失败时</a-select-option>
                  <a-select-option value="Always">总是</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item label="日志文件路径" required>
                <a-input-group compact>
                  <a-input v-model:value="formData.Script.LogPath" readonly size="large" />
                  <a-button size="large" @click="selectLogPath">选择文件</a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="12">
              <a-form-item label="日志文件名格式">
                <a-input
                  v-model:value="formData.Script.LogPathFormat"
                  placeholder="固定文件名留空；日期+序号可用 ******"
                  @blur="handleChange('Script', 'LogPathFormat', formData.Script.LogPathFormat)"
                />
              </a-form-item>
            </a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="6"
              ><a-form-item label="时间戳起点"
                ><a-input-number
                  v-model:value="formData.Script.LogTimeStart"
                  :min="1"
                  style="width: 100%"
                  @blur="
                    handleChange('Script', 'LogTimeStart', formData.Script.LogTimeStart)
                  " /></a-form-item
            ></a-col>
            <a-col :span="6"
              ><a-form-item label="时间戳终点"
                ><a-input-number
                  v-model:value="formData.Script.LogTimeEnd"
                  :min="1"
                  style="width: 100%"
                  @blur="
                    handleChange('Script', 'LogTimeEnd', formData.Script.LogTimeEnd)
                  " /></a-form-item
            ></a-col>
            <a-col :span="12"
              ><a-form-item label="时间戳格式"
                ><a-input
                  v-model:value="formData.Script.LogTimeFormat"
                  @blur="
                    handleChange('Script', 'LogTimeFormat', formData.Script.LogTimeFormat)
                  " /></a-form-item
            ></a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="12"
              ><a-form-item label="成功日志关键词"
                ><a-textarea
                  v-model:value="formData.Script.SuccessLog"
                  :rows="2"
                  placeholder="多个关键词用 | 分隔"
                  @blur="
                    handleChange('Script', 'SuccessLog', formData.Script.SuccessLog)
                  " /></a-form-item
            ></a-col>
            <a-col :span="12"
              ><a-form-item label="失败日志关键词"
                ><a-textarea
                  v-model:value="formData.Script.ErrorLog"
                  :rows="2"
                  placeholder="多个关键词用 | 分隔"
                  @blur="
                    handleChange('Script', 'ErrorLog', formData.Script.ErrorLog)
                  " /></a-form-item
            ></a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header"><h3>游戏或模拟器</h3></div>
          <a-row :gutter="24">
            <a-col :span="6"
              ><a-form-item label="由 MAS 启动"
                ><a-switch
                  v-model:checked="formData.Game.Enabled"
                  @change="handleChange('Game', 'Enabled', formData.Game.Enabled)" /></a-form-item
            ></a-col>
            <a-col :span="6"
              ><a-form-item label="启动类型"
                ><a-select
                  v-model:value="formData.Game.Type"
                  :disabled="!formData.Game.Enabled"
                  @change="handleChange('Game', 'Type', formData.Game.Type)"
                  ><a-select-option value="Emulator">模拟器</a-select-option
                  ><a-select-option value="Client">PC 客户端</a-select-option
                  ><a-select-option value="URL">URL 协议</a-select-option></a-select
                ></a-form-item
              ></a-col
            >
            <a-col :span="12"
              ><a-form-item label="路径 / URL"
                ><a-input
                  v-model:value="formData.Game.Path"
                  :disabled="!formData.Game.Enabled || formData.Game.Type === 'URL'"
                  @blur="handleChange('Game', 'Path', formData.Game.Path)" /><a-input
                  v-if="formData.Game.Type === 'URL'"
                  v-model:value="formData.Game.URL"
                  class="stacked-input"
                  @blur="handleChange('Game', 'URL', formData.Game.URL)" /></a-form-item
            ></a-col>
          </a-row>
          <a-row :gutter="24">
            <a-col :span="8"
              ><a-form-item label="进程名称"
                ><a-input
                  v-model:value="formData.Game.ProcessName"
                  :disabled="!formData.Game.Enabled"
                  @blur="
                    handleChange('Game', 'ProcessName', formData.Game.ProcessName)
                  " /></a-form-item
            ></a-col>
            <a-col :span="8"
              ><a-form-item label="启动参数"
                ><a-input
                  v-model:value="formData.Game.Arguments"
                  :disabled="!formData.Game.Enabled"
                  @blur="handleChange('Game', 'Arguments', formData.Game.Arguments)" /></a-form-item
            ></a-col>
            <a-col :span="4"
              ><a-form-item label="等待秒数"
                ><a-input-number
                  v-model:value="formData.Game.WaitTime"
                  :min="0"
                  :disabled="!formData.Game.Enabled"
                  style="width: 100%"
                  @blur="handleChange('Game', 'WaitTime', formData.Game.WaitTime)" /></a-form-item
            ></a-col>
            <a-col :span="4"
              ><a-form-item label="强制关闭"
                ><a-switch
                  v-model:checked="formData.Game.IfForceClose"
                  :disabled="!formData.Game.Enabled"
                  @change="
                    handleChange('Game', 'IfForceClose', formData.Game.IfForceClose)
                  " /></a-form-item
            ></a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header"><h3>运行限制</h3></div>
          <a-row :gutter="24">
            <a-col :span="8"
              ><a-form-item label="每日代理次数上限"
                ><a-input-number
                  v-model:value="formData.Run.ProxyTimesLimit"
                  :min="0"
                  style="width: 100%"
                  @blur="
                    handleChange('Run', 'ProxyTimesLimit', formData.Run.ProxyTimesLimit)
                  " /></a-form-item
            ></a-col>
            <a-col :span="8"
              ><a-form-item label="重试次数"
                ><a-input-number
                  v-model:value="formData.Run.RunTimesLimit"
                  :min="1"
                  style="width: 100%"
                  @blur="
                    handleChange('Run', 'RunTimesLimit', formData.Run.RunTimesLimit)
                  " /></a-form-item
            ></a-col>
            <a-col :span="8"
              ><a-form-item label="超时分钟"
                ><a-input-number
                  v-model:value="formData.Run.RunTimeLimit"
                  :min="1"
                  style="width: 100%"
                  @blur="
                    handleChange('Run', 'RunTimeLimit', formData.Run.RunTimeLimit)
                  " /></a-form-item
            ></a-col>
          </a-row>
        </div>

        <!-- TODO(specialized): 加入专项脚本级配置，并接入真实运行时消费者。 -->
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { message } from 'ant-design-vue'
import { useRoute, useRouter } from 'vue-router'
import { useScriptApi } from '@/composables/useScriptApi'

interface XxxScriptFormData {
  Info: { Name: string; RootPath: string }
  Script: {
    ScriptPath: string
    Arguments: string
    IfTrackProcess: boolean
    TrackProcessName: string
    TrackProcessExe: string
    TrackProcessCmdline: string
    ConfigPath: string
    ConfigPathMode: 'File' | 'Folder'
    UpdateConfigMode: 'Never' | 'Success' | 'Failure' | 'Always'
    LogPath: string
    LogPathFormat: string
    LogTimeStart: number
    LogTimeEnd: number
    LogTimeFormat: string
    SuccessLog: string
    ErrorLog: string
  }
  Game: {
    Enabled: boolean
    Type: 'Emulator' | 'Client' | 'URL'
    Path: string
    URL: string
    ProcessName: string
    Arguments: string
    WaitTime: number
    IfForceClose: boolean
  }
  Run: { ProxyTimesLimit: number; RunTimesLimit: number; RunTimeLimit: number }
}

type ConfigGroup = keyof XxxScriptFormData

const defaultFormData = (): XxxScriptFormData => ({
  Info: { Name: '新专项脚本', RootPath: '' },
  Script: {
    ScriptPath: '',
    Arguments: '',
    IfTrackProcess: false,
    TrackProcessName: '',
    TrackProcessExe: '',
    TrackProcessCmdline: '',
    ConfigPath: '',
    ConfigPathMode: 'File',
    UpdateConfigMode: 'Never',
    LogPath: '',
    LogPathFormat: '%Y-%m-%d',
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
  },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 3, RunTimeLimit: 10 },
})

const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()
const scriptId = route.params.id as string
const formData = reactive<XxxScriptFormData>(defaultFormData())
const pageLoading = ref(false)

const mergeConfig = (config: unknown) => {
  const value = config as Partial<XxxScriptFormData>
  Object.assign(formData.Info, value.Info ?? {})
  Object.assign(formData.Script, value.Script ?? {})
  Object.assign(formData.Game, value.Game ?? {})
  Object.assign(formData.Run, value.Run ?? {})
}

const handleChange = async (group: ConfigGroup, key: string, value: unknown) => {
  const saved = await updateScript(scriptId, { [group]: { [key]: value } })
  if (!saved) message.error(`保存 ${group}.${key} 失败，请重试`)
}

const selectRootPath = async () => {
  const path = await window.electronAPI.selectFolder()
  if (path) {
    formData.Info.RootPath = path
    await handleChange('Info', 'RootPath', path)
  }
}

const selectScriptPath = async () => {
  const paths = await window.electronAPI.selectFile()
  if (paths[0]) {
    formData.Script.ScriptPath = paths[0]
    await handleChange('Script', 'ScriptPath', paths[0])
  }
}

const selectTrackProcessExe = async () => {
  const paths = await window.electronAPI.selectFile()
  if (paths[0]) {
    formData.Script.TrackProcessExe = paths[0]
    await handleChange('Script', 'TrackProcessExe', paths[0])
  }
}

const clearTrackProcessExe = async () => {
  formData.Script.TrackProcessExe = ''
  await handleChange('Script', 'TrackProcessExe', '')
}

const selectConfigPath = async () => {
  const path =
    formData.Script.ConfigPathMode === 'Folder'
      ? await window.electronAPI.selectFolder()
      : (await window.electronAPI.selectFile())[0]
  if (path) {
    formData.Script.ConfigPath = path
    await handleChange('Script', 'ConfigPath', path)
  }
}

const selectLogPath = async () => {
  const paths = await window.electronAPI.selectFile()
  if (paths[0]) {
    formData.Script.LogPath = paths[0]
    await handleChange('Script', 'LogPath', paths[0])
  }
}

const handleCancel = () => router.push('/scripts')

onMounted(async () => {
  if (!scriptId) {
    message.error('缺少脚本 ID')
    handleCancel()
    return
  }
  pageLoading.value = true
  try {
    const script = await getScript(scriptId)
    if (!script) {
      handleCancel()
      return
    }
    mergeConfig(script.config)
  } finally {
    pageLoading.value = false
  }
})
</script>

<style scoped>
.script-edit-page {
  max-width: 1280px;
  margin: 0 auto;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}

.form-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  padding-left: 12px;
  border-left: 4px solid var(--ant-color-primary);
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.stacked-input {
  margin-top: 8px;
}

@media (max-width: 900px) {
  .script-edit-page {
    max-width: 100%;
  }
}
</style>

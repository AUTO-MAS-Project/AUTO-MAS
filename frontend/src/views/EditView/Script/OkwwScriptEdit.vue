<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="../../../assets/ok-ww.ico" alt="ok-ww" class="breadcrumb-logo" />
            编辑脚本
          </div>
        </a-breadcrumb-item>
      </a-breadcrumb>
    </div>

    <a-space size="middle">
      <a-button size="large" class="cancel-button" @click="handleCancel">
        <template #icon>
          <ArrowLeftOutlined />
        </template>
        返回
      </a-button>
    </a-space>
  </div>

  <div class="script-edit-content">
    <a-card title="ok-ww 脚本配置" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-tag color="blue" class="type-tag">ok-ww</a-tag>
      </template>

      <a-form :model="formData" :rules="rules" layout="vertical" class="config-form">
        <div class="form-section">
          <div class="section-header">
            <h3>基本信息</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item name="name">
                <template #label>
                  <span class="form-label">
                    脚本名称
                    <a-tooltip title="用于区分不同的 ok-ww 脚本实例">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  placeholder="请输入脚本名称"
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
                    ok-ww 路径
                    <a-tooltip title="选择 ok-ww.exe 所在目录">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    placeholder="请选择 ok-ww.exe 所在目录"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectRootPath">
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择目录
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>游戏配置</h3>
          </div>
          <a-row :gutter="24" class="game-control-row">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="游戏管理总开关：关闭后 MAS 不启动也不关闭游戏；开启后可分别配置任务前启动与任务后关闭">
                    <span class="form-label">
                      启用游戏配置
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="okwwConfig.Game.Enabled"
                  size="large"
                  class="modern-input"
                  @change="handleGameEnabledChange"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="任务开始前是否由 MAS 启动游戏并等待">
                    <span class="form-label">
                      任务前启动游戏
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="okwwConfig.Game.LaunchBeforeTask"
                  size="large"
                  class="modern-input"
                  :disabled="!okwwConfig.Game.Enabled"
                  @change="handleChange('Game', 'LaunchBeforeTask', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <a-tooltip title="任务成功结束后是否由 MAS 关闭游戏；失败重试前若需重拉游戏也会尝试关闭">
                    <span class="form-label">
                      任务后关闭游戏
                      <QuestionCircleOutlined class="help-icon" />
                    </span>
                  </a-tooltip>
                </template>
                <a-select
                  v-model:value="okwwConfig.Game.CloseOnFinish"
                  size="large"
                  class="modern-input"
                  :disabled="!okwwConfig.Game.Enabled"
                  @change="handleChange('Game', 'CloseOnFinish', $event)"
                >
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    游戏根目录
                    <span class="label-hint">选择 <strong>Wuthering Waves Game</strong> 文件夹，自动匹配 Client-Win64-Shipping.exe</span>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="okwwConfig.Game.Path"
                    placeholder="请选择游戏根目录（自动匹配到 Client-Win64-Shipping.exe）"
                    size="large"
                    class="path-input"
                    readonly
                    :disabled="!okwwConfig.Game.Enabled"
                  />
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="!okwwConfig.Game.Enabled"
                    @click="selectGameRootPath"
                  >
                    <template #icon>
                      <FolderOpenOutlined />
                    </template>
                    选择目录
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    启动参数
                    <a-tooltip title="游戏启动参数（非 ok-ww 启动参数）">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="okwwConfig.Game.Arguments"
                  placeholder="请输入游戏启动参数"
                  size="large"
                  class="modern-input"
                  :disabled="!okwwConfig.Game.Enabled"
                  @blur="handleChange('Game', 'Arguments', okwwConfig.Game.Arguments)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    启动等待时间
                    <a-tooltip title="拉起游戏后的等待时间（秒）">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  :disabled="!okwwConfig.Game.Enabled"
                  @blur="handleChange('Game', 'WaitTime', okwwConfig.Game.WaitTime)"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>运行配置</h3>
          </div>
          <a-row :gutter="24">
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    单日代理次数上限
                    <a-tooltip title="阈值为 0 时表示不限制">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', okwwConfig.Run.ProxyTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    重试次数限制
                    <a-tooltip title="超过该次数仍失败则终止">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', okwwConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    代理超时限制（分钟）
                    <a-tooltip title="日志长期无变化将判定超时">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okwwConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', okwwConfig.Run.RunTimeLimit)"
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
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ArrowLeftOutlined, FolderOpenOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'
import { type OkwwConfig } from '@/api'
import { useScriptApi } from '@/composables/useScriptApi'

const logger = window.electronAPI.getLogger('ok-ww脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)

const formData = reactive({
  name: '',
  get path() {
    return okwwConfig.Info.RootPath
  },
  set path(value: string) {
    okwwConfig.Info.RootPath = value
  },
})

const okwwConfig = reactive<OkwwConfig>({
  Info: { Name: '', RootPath: '.' },
  Script: {
    ScriptPath: '.',
    Arguments: '',
    IfTrackProcess: true,
    TrackProcessExe: '',
    ConfigPath: '.',
    ConfigPathMode: 'Folder',
    UpdateConfigMode: 'Always',
    LogPath: '.',
    LogPathFormat: '',
    LogTimeStart: 1,
    LogTimeEnd: 23,
    LogTimeFormat: '%Y-%m-%d %H:%M:%S,%f',
    SuccessLog: '任务执行完成 | task completed',
    ErrorLog: 'connected:False|游戏更新成功, 游戏即将重启|错误',
  },
  Game: {
    Enabled: false,
    LaunchBeforeTask: false,
    Type: 'Client',
    Path: '.',
    WaitTime: 60,
    IfForceClose: true,
    CloseOnFinish: true,
    EmulatorId: '-',
    EmulatorIndex: '-',
  },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 1, RunTimeLimit: 60 },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 ok-ww 路径', trigger: 'blur' }],
}

const handleCancel = () => router.push('/scripts')

const handleGameEnabledChange = async (enabled: boolean) => {
  okwwConfig.Game.Enabled = enabled
  await handleChange('Game', 'Enabled', enabled)
}

const handleChange = async (category: string, key: string, value: unknown) => {
  if (isInitializing.value || isSaving.value) return
  isSaving.value = true
  try {
    const updateData = { [category]: { [key]: value } } as Record<string, Record<string, unknown>>
    const success = await updateScript(scriptId, updateData)
    if (success) {
      logger.info(`配置已保存: ${category}.${key}`)
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    logger.error(msg)
  } finally {
    isSaving.value = false
  }
}

const buildAutoPaths = (rootPath: string) => {
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  return {
    rootPath: norm,
    scriptPath: `${norm}/ok-ww.exe`,
    configPath: `${norm}/data/apps/ok-ww/working/configs`,
    logPath: `${norm}/data/apps/ok-ww/working/logs/ok-script.log`,
    trackProcessExe: `${norm}/data/apps/ok-ww/python/pythonw.exe`,
  }
}

const applyRootPathDefaults = async (rootPath: string) => {
  if (!rootPath || rootPath === '.') {
    message.warning('请先选择脚本根目录')
    return
  }
  const { rootPath: norm, scriptPath, configPath, logPath, trackProcessExe } = buildAutoPaths(rootPath)
  okwwConfig.Info.RootPath = norm
  okwwConfig.Script.ScriptPath = scriptPath
  okwwConfig.Script.ConfigPath = configPath
  okwwConfig.Script.LogPath = logPath
  okwwConfig.Script.TrackProcessName = 'pythonw.exe'
  okwwConfig.Script.TrackProcessExe = trackProcessExe
  okwwConfig.Script.TrackProcessCmdline = ''

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Info: { RootPath: norm },
      Script: {
        ScriptPath: scriptPath,
        ConfigPathMode: 'Folder',
        ConfigPath: configPath,
        UpdateConfigMode: 'Always',
        LogPath: logPath,
        LogPathFormat: '',
        IfTrackProcess: true,
        TrackProcessName: 'pythonw.exe',
        TrackProcessExe: trackProcessExe,
        TrackProcessCmdline: '',
      },
    })
    if (success) {
      message.success('ok-ww 路径已自动匹配')
    }
  } finally {
    isSaving.value = false
  }
}

const loadScript = async () => {
  pageLoading.value = true
  isInitializing.value = true
  try {
    const detail = await getScript(scriptId)
    if (!detail) {
      message.error('脚本不存在或加载失败')
      handleCancel()
      return
    }
    if (detail.type !== 'Okww') {
      message.error('脚本类型不是 ok-ww')
      handleCancel()
      return
    }
    formData.name = detail.name
    Object.assign(okwwConfig.Info, detail.config.Info || {})
    Object.assign(okwwConfig.Script, detail.config.Script || {})
    Object.assign(okwwConfig.Game, detail.config.Game || {})
    Object.assign(okwwConfig.Run, detail.config.Run || {})
  } catch {
    message.error('加载脚本失败')
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder({ title: '选择脚本根目录' })
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

const buildGameClientPath = (gameRootPath: string) => {
  const norm = gameRootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  return `${norm}/Client/Binaries/Win64/Client-Win64-Shipping.exe`
}

const selectGameRootPath = async () => {
  if (!okwwConfig.Game.Enabled) return
  const picked = await window.electronAPI.selectFolder({ title: '选择游戏根目录（Wuthering Waves Game）' })
  if (!picked) return
  okwwConfig.Game.Path = buildGameClientPath(picked)
  okwwConfig.Game.Type = 'Client'
  isSaving.value = true
  try {
    await updateScript(scriptId, {
      Game: {
        Path: okwwConfig.Game.Path,
        Type: 'Client',
      },
    })
  } finally {
    isSaving.value = false
  }
}

onMounted(loadScript)
</script>

<style scoped>
.script-edit-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 32px;
  padding: 0 8px;
}

.header-nav {
  flex: 1;
}

.breadcrumb {
  margin: 0;
}

.breadcrumb-link {
  align-items: center;
  gap: 8px;
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

.script-edit-content {
  flex: 1;
}

.config-card {
  border-radius: 16px;
  box-shadow:
    0 4px 20px rgba(0, 0, 0, 0.08),
    0 1px 3px rgba(0, 0, 0, 0.1);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 24px 32px;
}

.config-card :deep(.ant-card-body) {
  padding: 32px;
}

.type-tag {
  font-size: 14px;
  font-weight: 600;
  padding: 8px 16px;
  border-radius: 8px;
}

.form-section {
  margin-bottom: 12px;
  animation: fadeInUp 0.6s ease-out;
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.form-label {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
}

.label-hint {
  font-size: 12px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.label-hint strong {
  font-weight: 600;
  color: var(--ant-color-text-secondary);
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

.modern-input {
  border-radius: 8px;
  border: 2px solid var(--ant-color-border);
}

.path-input-group {
  display: flex;
  border-radius: 8px;
  overflow: hidden;
  border: 2px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  border: none !important;
  border-radius: 0 !important;
}

.path-button {
  border: none;
  border-radius: 0;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  font-weight: 600;
  padding: 0 20px;
  border-left: 1px solid var(--ant-color-border-secondary);
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.game-control-row {
  margin-bottom: 8px;
}

.game-control-row :deep(.ant-form-item) {
  margin-bottom: 0;
}

@media (max-width: 768px) {
  .script-edit-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }

  .config-card :deep(.ant-card-body) {
    padding: 20px;
  }
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(20px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>


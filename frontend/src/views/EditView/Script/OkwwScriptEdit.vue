<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">
            <img src="@/assets/ok-ww.ico" alt="ok-ww" class="breadcrumb-logo" />
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
                  <a-button
                    type="primary"
                    size="large"
                    class="auto-import-button"
                    :loading="isDiscoveringOkww"
                    :disabled="isSaving"
                    @click="discoverRootPath"
                  >
                    <template #icon>
                      <ImportOutlined />
                    </template>
                    一键导入
                  </a-button>
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="isDiscoveringOkww || isSaving"
                    @click="selectRootPath"
                  >
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
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <a-tooltip title="开启后由 MAS 接管游戏启停">
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
                  @change="handleChange('Game', 'Enabled', $event)"
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
                    游戏启动器
                    <span class="label-hint">支持鸣潮官方启动器与 WeGame</span>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="okwwConfig.Game.Path"
                    placeholder="请选择启动器所在目录"
                    size="large"
                    class="path-input"
                    readonly
                    :disabled="!okwwConfig.Game.Enabled"
                  />
                  <a-button
                    type="primary"
                    size="large"
                    class="auto-import-button"
                    :loading="isDiscoveringGame"
                    :disabled="!okwwConfig.Game.Enabled || isSaving"
                    @click="discoverGamePath"
                  >
                    <template #icon>
                      <ImportOutlined />
                    </template>
                    一键导入
                  </a-button>
                  <a-button
                    size="large"
                    class="path-button"
                    :disabled="!okwwConfig.Game.Enabled || isDiscoveringGame || isSaving"
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
import { message, Modal } from 'ant-design-vue'
import {
  ArrowLeftOutlined,
  FolderOpenOutlined,
  ImportOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'

const logger = window.electronAPI.getLogger('ok-ww脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)
const isDiscoveringOkww = ref(false)
const isDiscoveringGame = ref(false)

// ══ okww 项目结构常量（需与 app/task/Okww/AutoProxy.py 中的 _OKWW_REL_* 保持同步）══
const OKWW_EXE_NAME = 'ok-ww.exe'

interface OkwwInfoForm {
  Name: string
  RootPath: string
}

interface OkwwGameForm {
  Enabled: boolean
  Path: string
  Arguments: string
  WaitTime: number
}

interface OkwwRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface OkwwScriptConfigForm {
  Info: OkwwInfoForm
  Script: Record<string, never>
  Game: OkwwGameForm
  Run: OkwwRunForm
}

const formData = reactive({
  name: '',
  get path() {
    return okwwConfig.Info.RootPath
  },
  set path(value: string) {
    okwwConfig.Info.RootPath = value
  },
})

const okwwConfig = reactive<OkwwScriptConfigForm>({
  Info: { Name: '', RootPath: '.' },
  Script: {},
  Game: {
    Enabled: false,
    Path: '.',
    Arguments: '',
    WaitTime: 60,
  },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 1, RunTimeLimit: 60 },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 ok-ww 路径', trigger: 'blur' }],
}

const WUWA_LAUNCHER_CANDIDATES = ['launcher.exe', 'wegame.exe']

const showPathRejectModal = (title: string, content: string) => {
  Modal.error({ title, content, okText: '我知道了' })
}

const handleCancel = () => router.push('/scripts')

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

const applyRootPathDefaults = async (rootPath: string, successMessage = 'ok-ww 根目录已保存') => {
  if (!rootPath || rootPath === '.') {
    message.warning('请先选择脚本根目录')
    return false
  }
  const norm = rootPath.replace(/\\/g, '/').replace(/\/+$/g, '')
  const previousPath = okwwConfig.Info.RootPath
  okwwConfig.Info.RootPath = norm

  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Info: { RootPath: norm },
    })
    if (success) {
      message.success(successMessage)
      return true
    }
    okwwConfig.Info.RootPath = previousPath
    return false
  } catch (error) {
    okwwConfig.Info.RootPath = previousPath
    throw error
  } finally {
    isSaving.value = false
  }
}

const saveGamePath = async (launcherPath: string, successMessage: string) => {
  const normalized = launcherPath.replace(/\\/g, '/')
  const previousPath = okwwConfig.Game.Path
  okwwConfig.Game.Path = normalized
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Game: { Path: normalized },
    })
    if (success) {
      message.success(successMessage)
      return true
    }
    okwwConfig.Game.Path = previousPath
    return false
  } catch (error) {
    okwwConfig.Game.Path = previousPath
    throw error
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
    const config = detail.config as Partial<OkwwScriptConfigForm>
    Object.assign(okwwConfig.Info, config.Info || {})
    Object.assign(okwwConfig.Script, config.Script || {})
    Object.assign(okwwConfig.Game, config.Game || {})
    Object.assign(okwwConfig.Run, config.Run || {})
  } catch {
    message.error('加载脚本失败')
  } finally {
    isInitializing.value = false
    pageLoading.value = false
  }
}

const selectRootPath = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  const exePath = normalized + '/' + OKWW_EXE_NAME
  if (!(await window.electronAPI.fileExists(exePath))) {
    showPathRejectModal(
      '所选目录无效',
      `所选目录下未找到 ${OKWW_EXE_NAME}，请选择包含 ${OKWW_EXE_NAME} 的 OK-WW 脚本根目录。`
    )
    return
  }
  formData.path = normalized
  await applyRootPathDefaults(normalized)
}

const discoverRootPath = async () => {
  if (isDiscoveringOkww.value) return
  isDiscoveringOkww.value = true
  try {
    const result = await window.electronAPI.discoverOkwwPath()
    if (!result.success || !result.path) {
      showPathRejectModal('未找到 ok-ww', result.error || '未找到有效的 ok-ww 安装目录')
      return
    }
    await applyRootPathDefaults(result.path, '已从卸载信息导入 ok-ww 路径')
  } catch (error) {
    logger.error(`一键导入 ok-ww 路径失败: ${error instanceof Error ? error.message : error}`)
    showPathRejectModal('导入失败', '读取 ok-ww 安装信息时发生错误，请使用“选择目录”手动导入')
  } finally {
    isDiscoveringOkww.value = false
  }
}

const gameSourceLabel = (channel?: 'China' | 'Global' | 'WeGame') => {
  if (channel === 'China') return '官方启动器（国服）'
  if (channel === 'Global') return '官方启动器（Global）'
  if (channel === 'WeGame') return 'WeGame'
  return '官方启动器'
}

const discoverGamePath = async () => {
  if (!okwwConfig.Game.Enabled || isDiscoveringGame.value) return
  isDiscoveringGame.value = true
  try {
    const result = await window.electronAPI.discoverWutheringWavesPath()
    if (!result.success || !result.path) {
      showPathRejectModal('未找到鸣潮', result.error || '未找到有效的鸣潮启动器')
      return
    }
    await saveGamePath(result.path, `已从${gameSourceLabel(result.channel)}导入鸣潮启动器`)
  } catch (error) {
    logger.error(`一键导入鸣潮路径失败: ${error instanceof Error ? error.message : error}`)
    showPathRejectModal('导入失败', '读取鸣潮启动器信息时发生错误，请使用“选择目录”手动导入')
  } finally {
    isDiscoveringGame.value = false
  }
}

const selectGameRootPath = async () => {
  if (!okwwConfig.Game.Enabled) return
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return

  const normalized = picked.replace(/\\/g, '/')

  for (const executable of WUWA_LAUNCHER_CANDIDATES) {
    const candidateExe = normalized + '/' + executable
    if (await window.electronAPI.fileExists(candidateExe)) {
      await saveGamePath(candidateExe, '鸣潮启动器路径已保存')
      return
    }
  }

  showPathRejectModal(
    '所选目录无效',
    '所选目录下未找到 launcher.exe 或 wegame.exe，请选择鸣潮官方启动器或 WeGame 的安装目录。'
  )
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
  overflow: hidden;
}

.config-card :deep(.ant-card-head) {
  background: var(--ant-color-bg-container);
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
}

.section-header {
  margin-bottom: 6px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
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

.path-input-group {
  display: flex;
  overflow: hidden;
  border: 1px solid var(--ant-color-border);
}

.path-input {
  flex: 1;
  min-width: 0;
  border: none !important;
  border-radius: 0 !important;
}

.auto-import-button {
  flex-shrink: 0;
  border-radius: 0;
  padding: 0 18px;
}

.path-button {
  flex-shrink: 0;
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
</style>

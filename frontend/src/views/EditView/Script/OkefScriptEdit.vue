<template>
  <div class="script-edit-header">
    <div class="header-nav">
      <a-breadcrumb class="breadcrumb">
        <a-breadcrumb-item>
          <router-link to="/scripts" class="breadcrumb-link">脚本管理</router-link>
        </a-breadcrumb-item>
        <a-breadcrumb-item>
          <div class="breadcrumb-current">编辑脚本</div>
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
    <a-card :title="OK_SCRIPT_CARD_TITLE" :loading="pageLoading" class="config-card">
      <template #extra>
        <a-space size="small">
          <a-tag color="blue" class="type-tag">ok-script</a-tag>
          <a-tag v-if="projectMetadata?.adapter" class="type-tag">
            {{ projectMetadata.resourceName }}
          </a-tag>
          <a-tag v-else-if="projectMetadata" color="warning" class="type-tag">未适配</a-tag>
        </a-space>
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
                    项目名称
                    <a-tooltip title="选择 ok-script 项目后会根据资源名同步默认名称">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="formData.name"
                  placeholder="请输入项目名称"
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
                    ok-script 项目目录
                    <a-tooltip
                      title="选择 ok-script 项目根目录，源码态读取 pyappify.yml，安装态读取应用元数据"
                    >
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="formData.path"
                    placeholder="请选择 ok-script 项目目录"
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

          <div v-if="projectMetadata" class="adapter-summary">
            <a-descriptions :column="4" size="small" bordered>
              <a-descriptions-item label="项目">
                {{ projectMetadata.displayName }}
              </a-descriptions-item>
              <a-descriptions-item label="资源名">
                {{ projectMetadata.resourceName }}
              </a-descriptions-item>
              <a-descriptions-item label="来源">
                {{ projectMetadata.source }}
              </a-descriptions-item>
              <a-descriptions-item label="适配">
                {{ projectMetadata.adapter ? '已适配' : '未适配' }}
              </a-descriptions-item>
              <template v-if="projectMetadata.adapter">
                <a-descriptions-item label="入口">
                  {{ projectMetadata.adapter.exeName }}
                </a-descriptions-item>
                <a-descriptions-item label="配置">
                  {{ projectMetadata.adapter.configDir }}
                </a-descriptions-item>
                <a-descriptions-item label="日志">
                  {{ projectMetadata.adapter.logFile }}
                </a-descriptions-item>
                <a-descriptions-item label="游戏进程">
                  {{ projectMetadata.adapter.gameProcessName }}
                </a-descriptions-item>
              </template>
            </a-descriptions>
            <a-alert
              v-if="!projectMetadata.adapter"
              class="adapter-alert"
              type="warning"
              show-icon
              message="当前项目暂无内置适配"
            />
          </div>
          <a-empty v-else class="adapter-empty" description="尚未读取 ok-script 项目元数据" />
        </div>

        <div class="form-section">
          <div class="section-header">
            <h3>游戏配置</h3>
          </div>

          <a-row :gutter="24">
            <a-col :span="12">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    游戏程序路径
                    <a-tooltip title="选择游戏主程序 exe 文件">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-group compact class="path-input-group">
                  <a-input
                    v-model:value="okefConfig.Game.Path"
                    placeholder="请选择游戏主程序"
                    size="large"
                    class="path-input"
                    readonly
                  />
                  <a-button size="large" class="path-button" @click="selectGamePath">
                    <template #icon>
                      <FileOutlined />
                    </template>
                    选择文件
                  </a-button>
                </a-input-group>
              </a-form-item>
            </a-col>
            <a-col :span="6">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    启动参数
                    <a-tooltip title="游戏启动参数（非 ok-script 启动参数）">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input
                  v-model:value="okefConfig.Game.Arguments"
                  placeholder="请输入游戏启动参数"
                  size="large"
                  class="modern-input"
                  @blur="handleChange('Game', 'Arguments', okefConfig.Game.Arguments)"
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
                  v-model:value="okefConfig.Game.WaitTime"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Game', 'WaitTime', okefConfig.Game.WaitTime)"
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
                  v-model:value="okefConfig.Run.ProxyTimesLimit"
                  :min="0"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'ProxyTimesLimit', okefConfig.Run.ProxyTimesLimit)"
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
                  v-model:value="okefConfig.Run.RunTimesLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimesLimit', okefConfig.Run.RunTimesLimit)"
                />
              </a-form-item>
            </a-col>
            <a-col :span="8">
              <a-form-item>
                <template #label>
                  <span class="form-label">
                    代理超时限制（分钟）
                    <a-tooltip title="进程长时间未退出将判定超时">
                      <QuestionCircleOutlined class="help-icon" />
                    </a-tooltip>
                  </span>
                </template>
                <a-input-number
                  v-model:value="okefConfig.Run.RunTimeLimit"
                  :min="1"
                  :max="9999"
                  size="large"
                  style="width: 100%"
                  @blur="handleChange('Run', 'RunTimeLimit', okefConfig.Run.RunTimeLimit)"
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
  FileOutlined,
  FolderOpenOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { useScriptApi } from '@/composables/useScriptApi'

const logger = window.electronAPI.getLogger('ok-script脚本编辑')
const route = useRoute()
const router = useRouter()
const { getScript, updateScript } = useScriptApi()

const scriptId = route.params.id as string
const pageLoading = ref(true)
const isSaving = ref(false)
const isInitializing = ref(true)

const OK_SCRIPT_CARD_TITLE = 'ok-script 项目配置'
const OK_SCRIPT_PYAPPIFY_YML = 'pyappify.yml'

interface OkScriptAdapterDefinition {
  resourceName: string
  displayName: string
  exeName: string
  configDir: string
  appJsonFile: string
  logFile: string
  pythonwPath: string
  gameProcessName: string
  maxTaskIndex: number
}

const OK_SCRIPT_ADAPTERS: Record<string, OkScriptAdapterDefinition> = {
  'ok-ef': {
    resourceName: 'ok-ef',
    displayName: '终末地',
    exeName: 'ok-ef.exe',
    configDir: 'data/apps/ok-ef/working/configs',
    appJsonFile: 'data/apps/ok-ef/app.json',
    logFile: 'data/apps/ok-ef/working/logs/ok-script.log',
    pythonwPath: 'data/apps/ok-ef/python/pythonw.exe',
    gameProcessName: 'Endfield.exe',
    maxTaskIndex: 11,
  },
}
const OK_SCRIPT_ADAPTER_LIST = Object.values(OK_SCRIPT_ADAPTERS)
const OK_SCRIPT_DISPLAY_NAME_MAP: Record<string, string> = {
  'ok-ef': '终末地',
  'ok-ww': '鸣潮',
}

interface OkScriptProjectMetadata {
  resourceName: string
  displayName: string
  source: string
  adapter?: OkScriptAdapterDefinition
}

interface OkefInfoForm {
  Name: string
  ResourceName?: string
  ProjectLabel?: string
  RootPath: string
}

interface OkefGameForm {
  Enabled: boolean
  Path: string
  Arguments: string
  WaitTime: number
}

interface OkefRunForm {
  ProxyTimesLimit: number
  RunTimesLimit: number
  RunTimeLimit: number
}

interface OkefScriptConfigForm {
  Info: OkefInfoForm
  Script: Record<string, never>
  Game: OkefGameForm
  Run: OkefRunForm
}

const normalizePath = (path: string) => path.replace(/\\/g, '/').replace(/\/+$/g, '')

const getFileName = (path: string) => {
  const normalized = path.replace(/\\/g, '/')
  return normalized.split('/').pop() || ''
}

const normalizeResourceName = (value: unknown) => {
  const text = String(value || '')
    .trim()
    .replace(/^['"]|['"]$/g, '')
  if (!text) return ''
  const withoutVersion = text.replace(/[-_ ]?v?\d+(?:\.\d+)+(?:[-_.a-z0-9]*)?$/i, '').trim()
  return withoutVersion || text
}

const displayNameForResource = (resourceName: string) => {
  return (
    OK_SCRIPT_ADAPTERS[resourceName]?.displayName ||
    OK_SCRIPT_DISPLAY_NAME_MAP[resourceName] ||
    resourceName
  )
}

const getAdapterByResource = (resourceName?: string) => {
  if (!resourceName) return undefined
  return OK_SCRIPT_ADAPTERS[resourceName]
}

const buildMetadata = (resourceName: string, source: string): OkScriptProjectMetadata => {
  const adapter = getAdapterByResource(resourceName)
  return {
    resourceName,
    displayName: adapter?.displayName || displayNameForResource(resourceName),
    source,
    adapter,
  }
}

const readMetadataFromAppJson = async (rootPath: string) => {
  for (const adapter of OK_SCRIPT_ADAPTER_LIST) {
    const appJsonPath = `${rootPath}/${adapter.appJsonFile}`
    if (!(await window.electronAPI.fileExists(appJsonPath))) continue

    try {
      const raw = await window.electronAPI.readFile(appJsonPath)
      const data = JSON.parse(raw) as { name?: unknown }
      const resourceName = normalizeResourceName(data.name)
      if (resourceName) return buildMetadata(resourceName, 'app.json')
    } catch (e) {
      logger.warn(`读取 ok-script app.json 失败: ${e instanceof Error ? e.message : String(e)}`)
    }
  }

  return null
}

const readMetadataFromPyappify = async (rootPath: string) => {
  const pyappifyPath = `${rootPath}/${OK_SCRIPT_PYAPPIFY_YML}`
  if (!(await window.electronAPI.fileExists(pyappifyPath))) return null

  try {
    const raw = await window.electronAPI.readFile(pyappifyPath)
    const match = raw.match(/^\s*name\s*:\s*["']?([^"'\r\n#]+)["']?/m)
    const resourceName = normalizeResourceName(match?.[1])
    return resourceName ? buildMetadata(resourceName, 'pyappify.yml') : null
  } catch (e) {
    logger.warn(`读取 ok-script pyappify.yml 失败: ${e instanceof Error ? e.message : String(e)}`)
    return null
  }
}

const readMetadataFromKnownLayout = async (rootPath: string) => {
  for (const adapter of OK_SCRIPT_ADAPTER_LIST) {
    const hasExe = await window.electronAPI.fileExists(`${rootPath}/${adapter.exeName}`)
    const hasConfigDir = await window.electronAPI.fileExists(`${rootPath}/${adapter.configDir}`)
    if (hasExe && hasConfigDir) {
      return buildMetadata(adapter.resourceName, '目录结构')
    }
  }
  return null
}

const resolveOkScriptProjectMetadata = async (
  rootPath: string
): Promise<OkScriptProjectMetadata | null> => {
  return (
    (await readMetadataFromPyappify(rootPath)) ||
    (await readMetadataFromAppJson(rootPath)) ||
    (await readMetadataFromKnownLayout(rootPath))
  )
}

const isSupportedOkScriptRootPath = async (
  rootPath: string,
  metadata: OkScriptProjectMetadata | null
) => {
  const adapter = metadata?.adapter
  if (!rootPath || !adapter) return false
  return (
    (await window.electronAPI.fileExists(`${rootPath}/${adapter.exeName}`)) &&
    (await window.electronAPI.fileExists(`${rootPath}/${adapter.configDir}`))
  )
}

const formData = reactive({
  name: '',
  get path() {
    return okefConfig.Info.RootPath
  },
  set path(value: string) {
    okefConfig.Info.RootPath = value
  },
})

const okefConfig = reactive<OkefScriptConfigForm>({
  Info: { Name: '', ResourceName: '', ProjectLabel: '', RootPath: '' },
  Script: {},
  Game: {
    Enabled: true,
    Path: '',
    Arguments: '',
    WaitTime: 60,
  },
  Run: { ProxyTimesLimit: 0, RunTimesLimit: 1, RunTimeLimit: 60 },
})

const rules = {
  name: [{ required: true, message: '请输入脚本名称', trigger: 'blur' }],
  path: [{ required: true, message: '请选择 ok-script 项目目录', trigger: 'blur' }],
}

const projectMetadata = ref<OkScriptProjectMetadata | null>(null)

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

const saveProjectInfo = async (rootPath: string, metadata: OkScriptProjectMetadata) => {
  if (!rootPath) {
    message.warning('请先选择脚本根目录')
    return
  }

  projectMetadata.value = metadata
  formData.path = rootPath
  formData.name = metadata.displayName
  okefConfig.Info.Name = metadata.displayName
  okefConfig.Info.ResourceName = metadata.resourceName
  okefConfig.Info.ProjectLabel = metadata.displayName
  okefConfig.Game.Enabled = true
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Info: {
        RootPath: rootPath,
        Name: metadata.displayName,
        ResourceName: metadata.resourceName,
        ProjectLabel: metadata.displayName,
      },
      Game: {
        Enabled: true,
        LaunchBeforeTask: true,
      },
    })
    if (success) {
      message.success(`ok-script 项目已保存：${metadata.displayName}`)
    }
  } finally {
    isSaving.value = false
  }
}

const saveGamePath = async (gamePath: string) => {
  okefConfig.Game.Path = gamePath
  isSaving.value = true
  try {
    const success = await updateScript(scriptId, {
      Game: { Path: gamePath },
    })
    if (success) {
      message.success('游戏程序路径已保存')
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
    if (detail.type !== 'Okef') {
      message.error('脚本类型不是 ok-script 项目')
      handleCancel()
      return
    }
    formData.name = detail.name
    const config = detail.config as Partial<OkefScriptConfigForm>
    Object.assign(okefConfig.Info, config.Info || {})
    Object.assign(okefConfig.Script, config.Script || {})
    Object.assign(okefConfig.Game, config.Game || {})
    Object.assign(okefConfig.Run, config.Run || {})
    const normalizedRootPath = normalizePath(okefConfig.Info.RootPath || '')
    const metadata = normalizedRootPath
      ? await resolveOkScriptProjectMetadata(normalizedRootPath)
      : null
    if (await isSupportedOkScriptRootPath(normalizedRootPath, metadata)) {
      projectMetadata.value = metadata
    } else {
      projectMetadata.value = metadata
    }
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

  const normalized = normalizePath(picked)
  const metadata = await resolveOkScriptProjectMetadata(normalized)
  if (!metadata?.resourceName) {
    showPathRejectModal(
      '所选目录缺少 ok-script 项目元数据',
      '未找到 pyappify.yml，也未找到安装态应用元数据，请选择 ok-script 项目根目录。'
    )
    return
  }

  if (!metadata.adapter) {
    showPathRejectModal(
      '所选项目暂未适配',
      `已识别到资源 ${metadata.resourceName}，但当前 MAS 尚未内置该 ok-script 项目的适配。`
    )
    return
  }

  const exePath = `${normalized}/${metadata.adapter.exeName}`
  if (!(await window.electronAPI.fileExists(exePath))) {
    showPathRejectModal(
      '所选目录无效',
      '所选目录缺少当前落地点需要的运行入口，请确认该 ok-script 项目已经完成初始化。'
    )
    return
  }

  const configDir = `${normalized}/${metadata.adapter.configDir}`
  const hasConfigDir = await window.electronAPI.fileExists(configDir)
  if (!hasConfigDir) {
    showPathRejectModal(
      '所选目录缺少 ok-script 配置',
      '所选目录缺少当前落地点需要的运行配置目录，请先完成该 ok-script 项目的初始化。'
    )
    return
  }

  await saveProjectInfo(normalized, metadata)
}

const selectGamePath = async () => {
  const adapter =
    projectMetadata.value?.adapter || getAdapterByResource(okefConfig.Info.ResourceName)
  if (!adapter) {
    message.warning('请先选择已适配的 ok-script 项目')
    return
  }

  const paths = await window.electronAPI.selectFile([
    { name: '可执行文件', extensions: ['exe'] },
    { name: '所有文件', extensions: ['*'] },
  ])
  const picked = paths?.[0]
  if (!picked) return

  if (getFileName(picked).toLowerCase() !== adapter.gameProcessName.toLowerCase()) {
    showPathRejectModal(
      '所选文件无效',
      `请选择当前适配要求的游戏主程序 ${adapter.gameProcessName}，当前文件不能用于自动启动。`
    )
    return
  }

  await saveGamePath(normalizePath(picked))
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

.adapter-summary {
  margin-top: 8px;
}

.adapter-alert {
  margin-top: 12px;
}

.adapter-empty {
  margin-top: 8px;
  padding: 16px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
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

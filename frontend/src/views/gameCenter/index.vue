<!-- eslint-disable vue/multi-word-component-names -->
<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import {
  DeleteOutlined,
  DownloadOutlined,
  ExclamationCircleOutlined,
  FolderOpenOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import { Service } from '@/api'
import type { GameConfig, GameConfigIndexItem, GameCheckOut, GamePresetItem } from '@/api'
import { useWebSocket } from '@/composables/useWebSocket'

const logger = window.electronAPI.getLogger('游戏中心')
const { subscribe, unsubscribe } = useWebSocket()

const loading = ref(false)
const gameIndex = ref<GameConfigIndexItem[]>([])
const gameData = ref<Record<string, GameConfig>>({})
const presets = ref<GamePresetItem[]>([])

// 添加游戏弹窗
const showAddModal = ref(false)
const selectedPreset = ref<string | undefined>(undefined)
const adding = ref(false)

// 关联模拟器下拉
const emulatorOptions = ref<{ label: string; value: string }[]>([])

// 每个游戏的操作状态
interface GameActionState {
  checking: boolean
  installing: boolean
  launching: boolean
  closing: boolean
  canceling: boolean
  phase: string
  percent: number
  downloaded: number
  total: number
  speed: number
  detail: string
}
const actionStates = reactive<Record<string, GameActionState>>({})

const wsSubscriptions = ref<string[]>([])

const providerLabel: Record<string, string> = {
  mihoyo_pc: 'miHoYo PC',
  hypergryph_pc: '鹰角 PC',
  adb_apk: '模拟器 APK',
}

const platformTagColor: Record<string, string> = {
  pc: 'blue',
  emulator: 'green',
}

const platformLabel: Record<string, string> = {
  pc: 'PC 端',
  emulator: '模拟器',
}

const phaseLabel: Record<string, string> = {
  check: '检查中',
  download: '下载中',
  verify: '校验中',
  patch: '打补丁中',
  install: '安装中',
  done: '完成',
  error: '错误',
  cancelled: '已取消',
}

const games = computed(() =>
  gameIndex.value.map(item => ({
    uid: item.uid,
    config: gameData.value[item.uid] || ({} as GameConfig),
  }))
)

function getActionState(uid: string): GameActionState {
  if (!actionStates[uid]) {
    actionStates[uid] = {
      checking: false,
      installing: false,
      launching: false,
      closing: false,
      canceling: false,
      phase: '',
      percent: 0,
      downloaded: 0,
      total: 0,
      speed: 0,
      detail: '',
    }
  }
  return actionStates[uid]
}

function isHypergryph(uid: string): boolean {
  return gameData.value[uid]?.Info?.Provider === 'hypergryph_pc'
}

function isAdbApk(uid: string): boolean {
  return gameData.value[uid]?.Info?.Provider === 'adb_apk'
}

function isHgAutoPatchEnabled(uid: string): boolean {
  return gameData.value[uid]?.Data?.HgAutoPatchEnabled ?? false
}

function isInstalling(uid: string): boolean {
  return getActionState(uid).installing
}

// ======================== 数据加载 ========================

async function loadGames() {
  loading.value = true
  try {
    const res = await Service.getGameApiGameCenterGetPost({ gameId: null })
    if (res.code !== 200) {
      message.error(res.message || '加载游戏列表失败')
      return
    }
    gameIndex.value = res.index || []
    gameData.value = res.data || {}
    // 为新游戏初始化状态
    for (const item of gameIndex.value) {
      getActionState(item.uid)
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e)
    logger.error(`加载游戏列表失败: ${msg}`)
    message.error('加载游戏列表失败')
  } finally {
    loading.value = false
  }
}

async function loadPresets() {
  try {
    const res = await Service.getPresetsApiGameCenterPresetsPost()
    if (res.code === 200) presets.value = res.presets || []
  } catch (e) {
    logger.error(`加载预设失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

async function loadEmulators() {
  try {
    const res = await Service.getEmulatorApiEmulatorGetPost({ emulatorId: null })
    if (res.code === 200) {
      const opts: { label: string; value: string }[] = [{ label: '未关联', value: '-' }]
      for (const item of res.index || []) {
        const cfg = (res.data as Record<string, GameConfig>)[item.uid] as any
        opts.push({
          label: cfg?.Info?.Name || item.uid,
          value: item.uid,
        })
      }
      emulatorOptions.value = opts
    }
  } catch (e) {
    logger.error(`加载模拟器列表失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

// ======================== CRUD ========================

function openAddModal() {
  selectedPreset.value = presets.value[0]?.key
  showAddModal.value = true
}

async function confirmAdd() {
  if (!selectedPreset.value) {
    message.warning('请选择一个游戏预设')
    return
  }
  adding.value = true
  try {
    const res = await Service.addGameApiGameCenterAddPost({
      preset: selectedPreset.value,
    })
    if (res.code !== 200) {
      message.error(res.message || '添加失败')
      return
    }
    message.success('已添加游戏')
    showAddModal.value = false
    await loadGames()
  } catch (e) {
    message.error(`添加失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    adding.value = false
  }
}

async function updateField(
  uid: string,
  group: 'Info' | 'Data' | 'Cache',
  name: string,
  value: unknown
) {
  try {
    const res = await Service.updateGameApiGameCenterUpdatePost({
      gameId: uid,
      data: { [group]: { [name]: value } } as GameConfig,
    })
    if (res.code !== 200) {
      message.error(res.message || '保存失败')
      return
    }
    // 本地同步
    const cfg: any = gameData.value[uid] || {}
    cfg[group] = { ...(cfg[group] || {}), [name]: value }
    gameData.value = { ...gameData.value, [uid]: cfg }
  } catch (e) {
    message.error(`保存失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

async function pickInstallPath(uid: string) {
  const folder = await window.electronAPI.selectFolder()
  if (folder) {
    await updateField(uid, 'Data', 'InstallPath', folder)
    message.success('已设置游戏目录')
  }
}

async function pickLocalApk(uid: string) {
  const selectedFiles = await window.electronAPI.selectFile([
    { name: 'APK 文件', extensions: ['apk'] },
  ])
  const filePath = Array.isArray(selectedFiles) ? selectedFiles[0] : null
  if (!filePath) return
  const state = getActionState(uid)
  state.installing = true
  state.phase = 'install'
  state.detail = '正在安装本地 APK...'
  try {
    const res = await Service.installLocalApkApiGameCenterInstallLocalApkPost({
      gameId: uid,
      apkPath: filePath,
    })
    if (res.code !== 200) {
      message.error(res.message || 'APK 安装失败')
      return
    }
    message.success('APK 安装完成')
    await checkGame(uid)
  } catch (e) {
    message.error(`APK 安装失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    state.installing = false
    state.phase = ''
  }
}

function confirmDelete(uid: string, name: string) {
  Modal.confirm({
    title: '删除游戏',
    content: `确定要从游戏中心移除「${name}」吗？（不会删除本地游戏文件）`,
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      try {
        const res = await Service.deleteGameApiGameCenterDeletePost({ gameId: uid })
        if (res.code !== 200) {
          message.error(res.message || '删除失败')
          return
        }
        message.success('已删除')
        await loadGames()
      } catch (e) {
        message.error(`删除失败: ${e instanceof Error ? e.message : String(e)}`)
      }
    },
  })
}

// ======================== 操作 (检查/安装/取消/启动) ========================

async function checkGame(uid: string) {
  const state = getActionState(uid)
  state.checking = true
  try {
    const res: GameCheckOut = await Service.checkGameApiGameCenterCheckPost({ gameId: uid })
    if (res.code !== 200) {
      message.error(res.message || '检查更新失败')
      return
    }
    // 更新缓存到本地数据
    const cfg: any = gameData.value[uid] || {}
    cfg.Cache = {
      ...(cfg.Cache || {}),
      LocalVersion: res.local_version,
      LatestVersion: res.latest_version,
      NeedsUpdate: res.needs_update,
    }
    gameData.value = { ...gameData.value, [uid]: cfg }

    if (res.needs_update) {
      message.info(`${cfg.Info?.Name || '游戏'} 有新版本: ${res.latest_version}`)
    } else if (res.installed) {
      message.success(`${cfg.Info?.Name || '游戏'} 已是最新版本`)
    } else {
      message.warning(`${cfg.Info?.Name || '游戏'} 尚未安装`)
    }
  } catch (e) {
    message.error(`检查更新失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    state.checking = false
  }
}

async function installGame(uid: string) {
  const state = getActionState(uid)

  // 鹰角游戏且未开启高级更新 → 引导打开官方启动器
  if (isHypergryph(uid) && !isHgAutoPatchEnabled(uid)) {
    Modal.confirm({
      title: '鹰角游戏自动更新未开启',
      icon: () => null,
      content:
        '鹰角 PC 游戏的自动打补丁为高风险操作，默认关闭。你可以打开官方启动器自行更新，或在设置中开启「高级自动更新」。',
      okText: '打开官方启动器',
      cancelText: '关闭',
      async onOk() {
        await openOfficialLauncher(uid)
      },
    })
    return
  }

  state.installing = true
  state.phase = 'check'
  state.percent = 0
  state.detail = '准备中...'

  // 订阅 WS 进度
  const subId = subscribe({ id: `game_center/${uid}` }, (wsMessage: any) => {
    if (wsMessage.type === 'Update' && wsMessage.data) {
      const data = wsMessage.data
      state.phase = data.phase || ''
      state.percent = data.percent || 0
      state.downloaded = data.downloaded || 0
      state.total = data.total || 0
      state.speed = data.speed || 0
      state.detail = data.message || ''
      if (data.phase === 'done') {
        state.installing = false
        message.success('安装完成')
        checkGame(uid)
      } else if (data.phase === 'error') {
        state.installing = false
        message.error(data.message || '安装失败')
      } else if (data.phase === 'cancelled') {
        state.installing = false
      }
    }
  })
  wsSubscriptions.value.push(subId)

  try {
    const res = await Service.installGameApiGameCenterInstallPost({ gameId: uid })
    if (res.code === 409) {
      message.warning(res.message || '已有任务运行中')
      state.installing = false
      return
    }
    if (res.code !== 200) {
      message.error(res.message || '启动安装失败')
      state.installing = false
      return
    }
    message.success('安装任务已启动')
  } catch (e) {
    message.error(`安装失败: ${e instanceof Error ? e.message : String(e)}`)
    state.installing = false
  }
}

async function cancelInstall(uid: string) {
  const state = getActionState(uid)
  state.canceling = true
  try {
    const res = await Service.cancelGameApiGameCenterCancelPost({ gameId: uid })
    if (res.code === 200) {
      message.success('已发送取消信号')
    }
  } catch (e) {
    message.error(`取消失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    state.canceling = false
  }
}

async function launchGame(uid: string) {
  const state = getActionState(uid)
  state.launching = true
  try {
    const res = await Service.launchGameApiGameCenterLaunchPost({ gameId: uid })
    if (res.code !== 200) {
      message.error(res.message || '启动失败')
      return
    }
    message.success('已启动游戏')
  } catch (e) {
    message.error(`启动失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    state.launching = false
  }
}

async function closeGame(uid: string) {
  const state = getActionState(uid)
  state.closing = true
  try {
    const res = await Service.closeGameApiGameCenterClosePost({ gameId: uid })
    if (res.code !== 200) {
      message.error(res.message || '关闭失败')
      return
    }
    message.success('已关闭游戏')
  } catch (e) {
    message.error(`关闭失败: ${e instanceof Error ? e.message : String(e)}`)
  } finally {
    state.closing = false
  }
}

async function openOfficialLauncher(uid: string) {
  try {
    const res = await Service.openOfficialLauncherApiGameCenterOpenOfficialLauncherPost({
      gameId: uid,
    })
    if (res.code !== 200) {
      message.error(res.message || '打开失败')
      return
    }
    message.success('已打开官方启动器')
  } catch (e) {
    message.error(`打开失败: ${e instanceof Error ? e.message : String(e)}`)
  }
}

// ======================== 鹰角高级更新开关 ========================

function onHgAutoPatchChange(uid: string, checked: boolean) {
  if (checked) {
    Modal.confirm({
      title: '启用高级自动更新',
      icon: () => null,
      content:
        '鹰角 PC 游戏的自动打补丁是高风险操作：可能写坏游戏目录、需要管理员权限、补丁失败可能需要全量重装。确认你了解风险后开启。',
      okText: '我已了解风险，开启',
      okType: 'danger',
      cancelText: '取消',
      onOk: async () => {
        await updateField(uid, 'Data', 'HgAutoPatchEnabled', true)
        message.success('已开启高级自动更新')
      },
    })
  } else {
    updateField(uid, 'Data', 'HgAutoPatchEnabled', false)
  }
}

// ======================== 生命周期 ========================

onMounted(async () => {
  await Promise.all([loadPresets(), loadEmulators()])
  await loadGames()
})

onUnmounted(() => {
  wsSubscriptions.value.forEach(id => unsubscribe(id))
  wsSubscriptions.value = []
})
</script>

<template>
  <div class="game-center">
    <div class="header">
      <div class="title">游戏中心</div>
      <div class="actions">
        <a-button :loading="loading" @click="loadGames">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
        <a-button type="primary" @click="openAddModal">
          <template #icon><PlusOutlined /></template>
          添加游戏
        </a-button>
      </div>
    </div>

    <a-spin :spinning="loading">
      <a-empty v-if="games.length === 0" description="还没有添加游戏，点击右上角「添加游戏」开始" />

      <div v-else class="card-grid">
        <a-card v-for="g in games" :key="g.uid" class="game-card" size="small">
          <template #title>
            <span class="card-name">{{ g.config.Info?.Name || '未命名游戏' }}</span>
          </template>
          <template #extra>
            <a-tag :color="platformTagColor[g.config.Info?.Platform || 'pc']">
              {{ platformLabel[g.config.Info?.Platform || 'pc'] }}
            </a-tag>
          </template>

          <div class="row">
            <span class="label">类型</span>
            <span class="value">{{
              providerLabel[g.config.Info?.Provider || ''] || g.config.Info?.Provider
            }}</span>
          </div>

          <!-- PC: 安装目录 -->
          <div v-if="g.config.Info?.Platform === 'pc'" class="row">
            <span class="label">游戏目录</span>
            <span class="value path" :title="g.config.Data?.InstallPath || ''">
              {{ g.config.Data?.InstallPath || '未设置' }}
            </span>
            <a-button size="small" type="text" @click="pickInstallPath(g.uid)">
              <template #icon><FolderOpenOutlined /></template>
            </a-button>
          </div>

          <!-- 模拟器: 关联模拟器 -->
          <div v-else class="row">
            <span class="label">模拟器</span>
            <a-select
              class="value"
              size="small"
              :value="g.config.Data?.EmulatorId || '-'"
              :options="emulatorOptions"
              @change="(v: any) => updateField(g.uid, 'Data', 'EmulatorId', v)"
            />
          </div>

          <div class="row">
            <span class="label">本地版本</span>
            <span class="value">{{ g.config.Cache?.LocalVersion || '未知' }}</span>
          </div>
          <div class="row">
            <span class="label">最新版本</span>
            <span class="value">
              {{ g.config.Cache?.LatestVersion || '未检查' }}
              <a-tag v-if="g.config.Cache?.NeedsUpdate" color="orange"> 有更新 </a-tag>
            </span>
          </div>

          <!-- 进度条 -->
          <div v-if="isInstalling(g.uid)" class="progress-section">
            <a-progress
              :percent="Math.round(getActionState(g.uid).percent)"
              :status="
                getActionState(g.uid).phase === 'error'
                  ? 'exception'
                  : getActionState(g.uid).phase === 'done'
                    ? 'success'
                    : 'active'
              "
              size="small"
            />
            <div class="progress-detail">
              <span>{{
                phaseLabel[getActionState(g.uid).phase] || getActionState(g.uid).phase
              }}</span>
              <span v-if="getActionState(g.uid).speed > 0">
                {{ (getActionState(g.uid).speed / 1024 / 1024).toFixed(1) }} MB/s
              </span>
              <span v-if="getActionState(g.uid).detail" class="detail-text">
                {{ getActionState(g.uid).detail }}
              </span>
            </div>
          </div>

          <!-- 鹰角高级开关 -->
          <div v-if="isHypergryph(g.uid)" class="row hg-switch">
            <span class="label">
              <a-tooltip
                title="鹰角 PC 游戏自动打补丁为高风险操作，默认关闭。开启后可直接在游戏中心安装更新。"
              >
                <ExclamationCircleOutlined /> 高级自动更新
              </a-tooltip>
            </span>
            <a-switch
              :checked="isHgAutoPatchEnabled(g.uid)"
              size="small"
              @change="(checked: boolean) => onHgAutoPatchChange(g.uid, checked)"
            />
          </div>

          <template #actions>
            <span
              :class="{ disabled: getActionState(g.uid).checking || isInstalling(g.uid) }"
              @click="!getActionState(g.uid).checking && !isInstalling(g.uid) && checkGame(g.uid)"
            >
              <ReloadOutlined :spin="getActionState(g.uid).checking" />
              检查更新
            </span>
            <span
              v-if="!isInstalling(g.uid)"
              :class="{ disabled: getActionState(g.uid).checking }"
              @click="!getActionState(g.uid).checking && installGame(g.uid)"
            >
              <DownloadOutlined />
              安装/更新
            </span>
            <span
              v-else
              :class="{ disabled: getActionState(g.uid).canceling }"
              @click="!getActionState(g.uid).canceling && cancelInstall(g.uid)"
            >
              <StopOutlined />
              取消
            </span>
            <span
              :class="{ disabled: getActionState(g.uid).launching || isInstalling(g.uid) }"
              @click="!getActionState(g.uid).launching && !isInstalling(g.uid) && launchGame(g.uid)"
            >
              <PlayCircleOutlined />
              启动
            </span>
            <span
              :class="{ disabled: getActionState(g.uid).closing || isInstalling(g.uid) }"
              @click="!getActionState(g.uid).closing && !isInstalling(g.uid) && closeGame(g.uid)"
            >
              <PoweroffOutlined />
              关闭
            </span>
            <span
              v-if="isAdbApk(g.uid)"
              :class="{ disabled: isInstalling(g.uid) }"
              @click="!isInstalling(g.uid) && pickLocalApk(g.uid)"
            >
              <FolderOpenOutlined />
              本地 APK
            </span>
            <span
              v-if="isHypergryph(g.uid) && !isHgAutoPatchEnabled(g.uid)"
              @click="openOfficialLauncher(g.uid)"
            >
              <PlayCircleOutlined />
              官方启动器
            </span>
            <span class="danger" @click="confirmDelete(g.uid, g.config.Info?.Name || '')">
              <DeleteOutlined />
              删除
            </span>
          </template>
        </a-card>
      </div>
    </a-spin>

    <a-modal
      v-model:open="showAddModal"
      title="添加游戏"
      :confirm-loading="adding"
      ok-text="添加"
      cancel-text="取消"
      @ok="confirmAdd"
    >
      <div class="add-form">
        <div class="form-label">选择游戏</div>
        <a-select v-model:value="selectedPreset" style="width: 100%" placeholder="选择要添加的游戏">
          <a-select-option v-for="p in presets" :key="p.key" :value="p.key">
            {{ p.name }}
          </a-select-option>
        </a-select>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.game-center {
  padding: 16px;
}
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}
.header .title {
  font-size: 20px;
  font-weight: 600;
}
.header .actions {
  display: flex;
  gap: 8px;
}
.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}
.game-card .card-name {
  font-weight: 600;
}
.game-card .row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 6px 0;
  font-size: 13px;
}
.game-card .label {
  color: var(--ant-color-text-secondary, #888);
  width: 72px;
  flex-shrink: 0;
}
.game-card .value {
  flex: 1;
  min-width: 0;
}
.game-card .value.path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.game-card .danger {
  color: var(--ant-color-error, #ff4d4f);
}
.game-card .disabled {
  opacity: 0.4;
  pointer-events: none;
}
.progress-section {
  margin: 8px 0 4px;
}
.progress-detail {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--ant-color-text-secondary, #888);
  margin-top: 4px;
}
.progress-detail .detail-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.hg-switch {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid var(--ant-color-border-secondary, #f0f0f0);
}
.add-form .form-label {
  margin-bottom: 8px;
  font-weight: 500;
}
</style>

<template>
  <div class="game-instances-tab">
    <div class="page-toolbar">
      <div>
        <h2 class="page-title">游戏实例</h2>
        <p class="page-description">
          选择游戏后会自动应用对应运行方式；这里只保留确实需要用户填写的配置。
        </p>
      </div>
      <a-space wrap>
        <a-button type="primary" :loading="adding" @click="openPresetPicker">
          <template #icon><PlusOutlined /></template>
          添加游戏
        </a-button>
        <a-button :loading="loading" @click="onRefresh">
          <template #icon><ReloadOutlined /></template>
          刷新
        </a-button>
      </a-space>
    </div>

    <a-modal
      :open="presetPickerOpen"
      :width="720"
      :footer="null"
      :closable="!adding"
      :keyboard="!adding"
      :mask-closable="!adding"
      class="preset-picker-modal"
      title="添加游戏"
      @cancel="closePresetPicker"
    >
      <div class="preset-picker">
        <div class="step-heading">
          <h3>选择游戏预设</h3>
          <p>点选预设即创建实例；选择游戏后会自动应用对应的运行方式。</p>
        </div>
        <div v-if="availablePresets.length" class="preset-grid">
          <button
            v-for="preset in availablePresets"
            :key="preset.key"
            type="button"
            class="preset-card"
            :class="{ adding: addingPresetKey === preset.key }"
            :disabled="adding"
            @click="onPickPreset(preset.key)"
          >
            <span class="preset-icon" aria-hidden="true">
              <MobileOutlined v-if="preset.platform === 'emulator'" />
              <DesktopOutlined v-else />
            </span>
            <span class="choice-copy">
              <span class="choice-title">{{ preset.name }}</span>
              <span class="choice-description">
                {{ preset.platform === 'pc' ? '通过 PC 客户端运行' : '通过安卓模拟器运行' }}
              </span>
            </span>
            <a-tag
              class="preset-platform-tag"
              :color="preset.platform === 'pc' ? 'blue' : 'purple'"
            >
              {{ preset.platform === 'pc' ? 'PC' : '模拟器' }}
            </a-tag>
            <LoadingOutlined v-if="addingPresetKey === preset.key" class="preset-loading" />
          </button>
        </div>
        <a-empty v-else description="暂无可用游戏预设" />
      </div>
    </a-modal>

    <a-alert
      v-if="error"
      type="warning"
      show-icon
      class="load-warning"
      :message="error"
      description="部分数据未能加载；已成功加载的模块仍可使用。"
    />

    <a-empty v-if="!loading && visibleGames.length === 0" description="暂无游戏，请从预设添加">
      <template #image>
        <div class="empty-icon"><AppstoreOutlined /></div>
      </template>
    </a-empty>

    <div v-else class="game-grid">
      <a-card v-for="game in visibleGames" :key="game.id" class="game-card" :bordered="false">
        <template #title>
          <div class="card-title">
            <span class="game-icon" aria-hidden="true">
              <MobileOutlined v-if="platformFor(game.id) === 'emulator'" />
              <DesktopOutlined v-else />
            </span>
            <a-select
              :value="game.config.Info?.PresetKey"
              size="small"
              class="game-select"
              :options="presetOptions"
              placeholder="选择游戏"
              :disabled="stateFor(game.id).saving"
              @change="onPresetChange(game.id, $event)"
            />
          </div>
        </template>
        <template #extra>
          <a-space>
            <a-button
              size="small"
              aria-label="上移游戏"
              :disabled="gamePosition(game.id) === 0 || reordering"
              @click="moveGame(game.id, -1)"
            >
              <ArrowUpOutlined />
            </a-button>
            <a-button
              size="small"
              aria-label="下移游戏"
              :disabled="gamePosition(game.id) === visibleGames.length - 1 || reordering"
              @click="moveGame(game.id, 1)"
            >
              <ArrowDownOutlined />
            </a-button>
            <a-tag v-if="!providerFor(providerNameFor(game.id))" color="error">
              运行组件不可用
            </a-tag>
            <a-popconfirm
              title="只移除游戏中心配置，不会删除本地游戏。确认继续？"
              @confirm="onDelete(game.id)"
            >
              <a-button
                danger
                type="text"
                size="small"
                aria-label="移除游戏配置"
                :loading="stateFor(game.id).deleting"
              >
                <DeleteOutlined />
              </a-button>
            </a-popconfirm>
          </a-space>
        </template>

        <div class="game-fields">
          <template v-if="platformFor(game.id) === 'pc'">
            <div class="field-row">
              <label class="field-label">游戏路径</label>
              <div class="field-control">
                <a-space-compact block>
                  <a-input
                    :value="game.config.Data?.InstallPath || ''"
                    placeholder="选择游戏安装目录或可执行文件"
                    :disabled="stateFor(game.id).saving"
                    @blur="saveTextField(game.id, 'Data', 'InstallPath', $event)"
                  />
                  <a-button :disabled="stateFor(game.id).saving" @click="pickGamePath(game.id)">
                    <FolderOpenOutlined />
                  </a-button>
                </a-space-compact>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="field-row">
              <label class="field-label">模拟器配置</label>
              <div class="field-control">
                <a-select
                  :value="game.config.Data?.EmulatorId"
                  class="full-control"
                  placeholder="选择模拟器"
                  :options="emulatorOptions"
                  :disabled="stateFor(game.id).saving"
                  @change="onEmulatorChange(game.id, $event)"
                />
              </div>
            </div>
            <div class="field-row">
              <label class="field-label">模拟器实例</label>
              <div class="field-control">
                <a-select
                  :value="game.config.Data?.EmulatorIndex || '0'"
                  class="full-control"
                  placeholder="选择实例"
                  :options="deviceOptionsFor(game.config.Data?.EmulatorId)"
                  :loading="Boolean(emulatorDevicesLoading[game.config.Data?.EmulatorId || ''])"
                  :disabled="!game.config.Data?.EmulatorId || stateFor(game.id).saving"
                  @dropdown-visible-change="onDeviceDropdown($event, game.config.Data?.EmulatorId)"
                  @change="saveValue(game.id, 'Data', 'EmulatorIndex', $event)"
                />
              </div>
            </div>
          </template>

          <div class="field-row field-row--status">
            <span class="field-label">安装状态</span>
            <div class="field-value">
              <a-space wrap>
                <a-tag :color="game.config.Cache?.Installed ? 'success' : 'default'">
                  {{ game.config.Cache?.Installed ? '已安装' : '未确认安装' }}
                </a-tag>
                <span>本地 {{ game.config.Cache?.LocalVersion || '未知' }}</span>
                <span v-if="game.config.Cache?.LatestVersion">
                  已知版本 {{ game.config.Cache.LatestVersion }}
                </span>
                <a-tag v-if="game.config.Cache?.NeedsUpdate" color="warning">可更新</a-tag>
              </a-space>
            </div>
          </div>

          <div v-if="taskFor(game.id)?.taskStatus" class="task-status">
            <a-progress
              :percent="Math.round(taskFor(game.id)?.percent || 0)"
              :status="taskProgressStatus(game.id)"
              size="small"
            />
            <div class="task-detail">
              <a-tag :color="taskStatusColor(game.id)">
                {{ taskStatusLabel(game.id) }}
              </a-tag>
              <span class="task-message" :title="taskFor(game.id)?.detail || ''">
                {{ taskFor(game.id)?.detail || '等待任务状态' }}
              </span>
              <span v-if="(taskFor(game.id)?.speed || 0) > 0" class="task-speed">
                {{ formatSpeed(taskFor(game.id)?.speed || 0) }}
              </span>
            </div>
          </div>
          <a-alert
            v-if="taskErrorFor(game.id)"
            type="error"
            show-icon
            class="task-poll-error"
            message="任务状态刷新失败"
            :description="taskErrorFor(game.id)"
          >
            <template #action>
              <a-button size="small" @click="onRetryTask(game.id)">重试</a-button>
            </template>
          </a-alert>
        </div>

        <div class="card-actions">
          <a-button
            :disabled="
              stateFor(game.id).saving ||
              taskRunning(game.id) ||
              !providerSupports(game.id, 'check')
            "
            :loading="stateFor(game.id).checking"
            @click="onCheck(game.id)"
          >
            <ReloadOutlined />
            检查
          </a-button>
          <a-button
            v-if="!taskRunning(game.id)"
            :disabled="stateFor(game.id).saving || !providerSupports(game.id, 'install_or_update')"
            :loading="stateFor(game.id).installing"
            @click="onInstall(game.id)"
          >
            <DownloadOutlined />
            安装/更新
          </a-button>
          <a-button
            v-else
            danger
            :disabled="stateFor(game.id).saving"
            :loading="stateFor(game.id).canceling"
            @click="onCancel(game.id)"
          >
            <StopOutlined />
            取消
          </a-button>
          <a-button
            type="primary"
            :disabled="
              stateFor(game.id).saving ||
              taskRunning(game.id) ||
              !providerSupports(game.id, 'launch')
            "
            :loading="stateFor(game.id).launching"
            @click="onLaunch(game.id)"
          >
            <PlayCircleOutlined />
            启动
          </a-button>
          <a-button
            :disabled="
              stateFor(game.id).saving ||
              taskRunning(game.id) ||
              !providerSupports(game.id, 'close')
            "
            :loading="stateFor(game.id).closing"
            @click="onClose(game.id)"
          >
            <PoweroffOutlined />
            关闭
          </a-button>
        </div>
      </a-card>
    </div>

    <section class="sign-accounts-section">
      <div class="section-header">
        <h3>游戏签到账户</h3>
        <a-button size="small" :loading="gameSignLoading" @click="onLoadSignAccounts">
          <ReloadOutlined />
          刷新
        </a-button>
      </div>
      <a-empty v-if="gameSignAccounts.length === 0" description="暂无签到账户" />
      <a-table
        v-else
        class="sign-accounts-table"
        :columns="signColumns"
        :data-source="gameSignAccounts"
        :pagination="false"
        size="small"
        row-key="uid"
      >
        <template #bodyCell="{ column, record }">
          <template v-if="column.key === 'enabled'">
            <a-tag :color="record.enabled ? 'success' : 'default'">
              {{ record.enabled ? '已启用' : '已停用' }}
            </a-tag>
          </template>
        </template>
      </a-table>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import {
  ArrowDownOutlined,
  ArrowUpOutlined,
  AppstoreOutlined,
  DeleteOutlined,
  DesktopOutlined,
  DownloadOutlined,
  FolderOpenOutlined,
  LoadingOutlined,
  PlayCircleOutlined,
  PlusOutlined,
  PoweroffOutlined,
  ReloadOutlined,
  MobileOutlined,
  StopOutlined,
} from '@ant-design/icons-vue'
import type { GameConfig } from '@/api'
import {
  isMaaFWManagedIdentity,
  isMaaFWManagedProvider,
  useGameCenter,
} from '@/composables/useGameCenterApi'

const {
  loading,
  error,
  games,
  availablePresets,
  emulatorOptions,
  emulatorDeviceOptions,
  emulatorDevicesLoading,
  gameSignAccounts,
  gameSignLoading,
  stateFor,
  taskFor,
  taskErrorFor,
  providerFor,
  refresh,
  addGame,
  updateGame,
  deleteGame,
  reorderGames,
  checkGame,
  launchGame,
  closeGame,
  loadGameSignAccounts,
  loadEmulatorDevices,
  loadTaskStatus,
  installOrUpdateGame,
  cancelGameTask,
} = useGameCenter()

const TASK_POLL_INTERVAL_MS = 1000
const presetPickerOpen = ref(false)
const addingPresetKey = ref<string | null>(null)
const adding = ref(false)
const reordering = ref(false)
const presetOptions = computed(() =>
  availablePresets.value.map(preset => ({
    label: `${preset.name} · ${preset.platform === 'pc' ? 'PC' : '模拟器'}`,
    value: preset.key,
  }))
)
const visibleGames = computed(() =>
  games.value.filter(game => {
    const preset = availablePresets.value.find(item => item.key === game.config.Info?.PresetKey)
    const providerName = preset?.provider || game.config.Info?.Provider || ''
    const provider = providerFor(providerName)
    if (provider && isMaaFWManagedProvider(provider)) return false

    return !isMaaFWManagedIdentity(
      providerName,
      preset?.name,
      game.config.Info?.Name,
      game.config.Info?.Provider
    )
  })
)
const signColumns = [
  { title: '名称', dataIndex: 'name', key: 'name' },
  { title: '签到平台', dataIndex: 'game', key: 'game' },
  { title: '状态', dataIndex: 'enabled', key: 'enabled' },
]
const phaseLabels: Record<string, string> = {
  queued: '准备中',
  handoff: '官方启动器',
  download: '下载中',
  verify: '校验中',
  patch: '应用补丁',
  install: '安装中',
  awaiting_user: '等待用户操作',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
}
let taskPollTimer: ReturnType<typeof setInterval> | undefined
let taskPolling = false

const presetForGame = (gameId: string) => {
  const game = games.value.find(item => item.id === gameId)
  return availablePresets.value.find(item => item.key === game?.config.Info?.PresetKey)
}
const platformFor = (gameId: string) => {
  const game = games.value.find(item => item.id === gameId)
  return presetForGame(gameId)?.platform || game?.config.Info?.Platform || 'pc'
}
const providerNameFor = (gameId: string) => {
  const game = games.value.find(item => item.id === gameId)
  return presetForGame(gameId)?.provider || game?.config.Info?.Provider || ''
}

const gamePosition = (gameId: string) => visibleGames.value.findIndex(game => game.id === gameId)
const providerSupports = (
  gameId: string,
  capability: 'check' | 'install_or_update' | 'launch' | 'close'
) => {
  const provider = providerFor(providerNameFor(gameId))
  return provider?.capabilities?.includes(capability) === true
}
const taskRunning = (gameId: string) => taskFor(gameId)?.running === true
const taskProgressStatus = (gameId: string): 'active' | 'exception' | 'success' | 'normal' => {
  const status = taskFor(gameId)?.taskStatus
  if (status === 'failed') return 'exception'
  if (status === 'completed') return 'success'
  if (status === 'handed_off') return 'normal'
  if (status === 'running') return 'active'
  return 'normal'
}
const taskStatusColor = (gameId: string) => {
  const status = taskFor(gameId)?.taskStatus
  if (status === 'failed') return 'error'
  if (status === 'completed') return 'success'
  if (status === 'handed_off') return 'warning'
  if (status === 'running') return 'processing'
  return 'default'
}
const taskStatusLabel = (gameId: string) => {
  const task = taskFor(gameId)
  if (task?.taskStatus === 'handed_off') return '已交给启动器'
  return phaseLabels[task?.phase || ''] || task?.phase || '任务状态'
}
const formatSpeed = (bytesPerSecond: number) => `${(bytesPerSecond / 1024 / 1024).toFixed(1)} MB/s`

const moveGame = async (gameId: string, offset: -1 | 1) => {
  const visibleOrder = visibleGames.value.map(game => game.id)
  const from = visibleOrder.indexOf(gameId)
  const to = from + offset
  if (from < 0 || to < 0 || to >= visibleOrder.length) return
  ;[visibleOrder[from], visibleOrder[to]] = [visibleOrder[to], visibleOrder[from]]
  const visibleIds = new Set(visibleOrder)
  let visibleIndex = 0
  const fullOrder = games.value.map(game =>
    visibleIds.has(game.id) ? visibleOrder[visibleIndex++] : game.id
  )
  reordering.value = true
  try {
    await reorderGames(fullOrder)
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  } finally {
    reordering.value = false
  }
}

const eventText = (event: Event): string =>
  (event.target as HTMLInputElement | null)?.value.trim() || ''

const saveValue = async (gameId: string, group: 'Info' | 'Data', name: string, value: unknown) => {
  try {
    await updateGame(gameId, { [group]: { [name]: value } } as GameConfig)
    message.success('游戏配置已保存')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}

const saveTextField = (gameId: string, group: 'Info' | 'Data', name: string, event: Event) =>
  saveValue(gameId, group, name, eventText(event))

const onPresetChange = async (gameId: string, presetKey: string) => {
  const preset = availablePresets.value.find(item => item.key === presetKey)
  if (!preset) {
    message.error('游戏预设不可用')
    return
  }
  const game = games.value.find(item => item.id === gameId)
  const emulatorId =
    preset.platform === 'emulator'
      ? game?.config.Data?.EmulatorId || emulatorOptions.value[0]?.value || null
      : null
  try {
    const options = emulatorId ? await loadEmulatorDevices(emulatorId) : []
    await updateGame(gameId, {
      Info: { PresetKey: presetKey },
      Data: {
        EmulatorId: emulatorId,
        EmulatorIndex: options[0]?.value || '0',
      },
    })
    message.success('游戏预设已更新')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}

const deviceOptionsFor = (emulatorId: string | null | undefined) => {
  if (!emulatorId) return []
  const options = emulatorDeviceOptions[emulatorId] || []
  return options.length > 0 ? options : [{ label: '实例 0（默认）', value: '0' }]
}

const onDeviceDropdown = async (open: boolean, emulatorId: string | null | undefined) => {
  if (!open || !emulatorId) return
  try {
    await loadEmulatorDevices(emulatorId)
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}

const onEmulatorChange = async (gameId: string, emulatorId: string) => {
  try {
    const options = await loadEmulatorDevices(emulatorId)
    const emulatorIndex = options[0]?.value || '0'
    await updateGame(gameId, {
      Data: { EmulatorId: emulatorId, EmulatorIndex: emulatorIndex },
    })
    message.success('模拟器与实例已更新')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}

const onRefresh = () => refresh()
const openPresetPicker = () => {
  presetPickerOpen.value = true
}
const closePresetPicker = () => {
  if (!adding.value) presetPickerOpen.value = false
}
const onPickPreset = async (presetKey: string) => {
  if (adding.value) return
  adding.value = true
  addingPresetKey.value = presetKey
  try {
    await addGame(presetKey)
    message.success('游戏已添加')
    presetPickerOpen.value = false
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  } finally {
    adding.value = false
    addingPresetKey.value = null
  }
}
const onDelete = async (gameId: string) => {
  try {
    await deleteGame(gameId)
    message.success('游戏配置已移除')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const onCheck = async (gameId: string) => {
  try {
    const result = await checkGame(gameId)
    message.success(result.installed ? '安装状态检查完成' : '未检测到游戏安装')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const onLaunch = async (gameId: string) => {
  try {
    await launchGame(gameId)
    message.success('游戏启动指令已执行')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const onClose = async (gameId: string) => {
  try {
    await closeGame(gameId)
    message.success('游戏关闭指令已执行')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const onInstall = async (gameId: string) => {
  try {
    await installOrUpdateGame(gameId)
    message.success('安装/更新任务已启动')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const onCancel = async (gameId: string) => {
  try {
    await cancelGameTask(gameId)
    message.success('任务已取消')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const onRetryTask = async (gameId: string) => {
  try {
    await loadTaskStatus(gameId)
    message.success('任务状态已刷新')
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}
const pickGamePath = async (gameId: string) => {
  try {
    const path = await window.electronAPI.selectFolder()
    if (path) await saveValue(gameId, 'Data', 'InstallPath', path)
  } catch (cause) {
    message.error(`选择游戏路径失败：${cause instanceof Error ? cause.message : String(cause)}`)
  }
}
const onLoadSignAccounts = async () => {
  try {
    await loadGameSignAccounts()
  } catch (cause) {
    message.error(cause instanceof Error ? cause.message : String(cause))
  }
}

const pollRunningTasks = async () => {
  if (taskPolling) return
  const gameIds = visibleGames.value.map(game => game.id).filter(gameId => taskRunning(gameId))
  if (gameIds.length === 0) return
  taskPolling = true
  try {
    await Promise.allSettled(gameIds.map(gameId => loadTaskStatus(gameId)))
  } finally {
    taskPolling = false
  }
}

onMounted(async () => {
  await refresh()
  const emulatorIds = [
    ...new Set(
      visibleGames.value
        .map(game => game.config.Data?.EmulatorId)
        .filter((value): value is string => Boolean(value))
    ),
  ]
  await Promise.allSettled(emulatorIds.map(emulatorId => loadEmulatorDevices(emulatorId)))
  taskPollTimer = setInterval(pollRunningTasks, TASK_POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (taskPollTimer) clearInterval(taskPollTimer)
})
</script>

<style scoped>
.game-instances-tab {
  height: 100%;
  min-height: 0;
  padding: var(--v6-space-1) 0 var(--v6-space-3);
  overflow-y: auto;
  container: game-instances / inline-size;
}

.page-toolbar,
.section-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--v6-space-4);
}

.page-toolbar {
  margin-bottom: var(--v6-space-3);
  padding: var(--v6-space-2) 0 var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.page-title,
.section-header h3 {
  margin: 0 0 6px;
  color: var(--v6-color-text);
  font-size: 16px;
  font-weight: 650;
}

.page-description {
  color: var(--v6-color-text-secondary);
  font-size: 13px;
}

.load-warning {
  margin-bottom: var(--v6-space-3);
}

.game-instances-tab > :deep(.ant-empty) {
  margin-block: 0;
  padding: var(--v6-space-4) 0 var(--v6-space-3);
}

.game-instances-tab > :deep(.ant-empty .ant-empty-image) {
  height: 48px;
  margin-bottom: var(--v6-space-2);
}

/* iPad 设置式双列瀑布流：两列各自纵向堆叠，卡片保持内容自然高度，避免同行等高拉伸留白。 */
.game-grid {
  columns: 2;
  column-gap: var(--v6-space-4);
}

.game-card {
  display: inline-block;
  width: 100%;
  min-width: 0;
  margin-bottom: var(--v6-space-4);
  vertical-align: top;
  break-inside: avoid;
  overflow: hidden;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: var(--v6-radius-card);
  background: color-mix(in srgb, var(--v6-color-surface) 82%, transparent);
  box-shadow: var(--v6-shadow-card);
  backdrop-filter: var(--v6-backdrop-vibrancy);
}

.game-card :deep(.ant-card-head) {
  min-height: 48px;
  padding-inline: var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.game-card :deep(.ant-card-head-wrapper) {
  gap: var(--v6-space-3);
}

.game-card :deep(.ant-card-extra) {
  min-width: 0;
}

.game-card :deep(.ant-card-body) {
  padding: var(--v6-space-4);
  display: flex;
  flex-direction: column;
}

.card-title,
.card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.game-icon {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--v6-color-primary);
  font-size: 16px;
  border-radius: 9px;
  background: color-mix(in srgb, var(--v6-color-primary) 11%, transparent);
}

.game-select {
  width: min(260px, 26vw);
  font-weight: 600;
}

.game-fields {
  display: flex;
  flex-direction: column;
}

.field-row {
  min-height: 46px;
  padding-block: 8px;
  display: grid;
  grid-template-columns: 104px minmax(0, 1fr);
  gap: var(--v6-space-3);
  align-items: center;
  border-bottom: 1px solid var(--v6-color-border-subtle);
}

.field-row:last-child {
  border-bottom: none;
}

.field-label {
  color: var(--v6-color-text-secondary);
  font-size: 12px;
}

.field-value {
  min-width: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
}

.field-control,
.full-control {
  width: 100%;
  min-width: 0;
}

.task-status {
  margin-top: var(--v6-space-3);
  padding: 10px 12px;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: 10px;
  background: color-mix(in srgb, var(--v6-color-fill-tertiary) 34%, transparent);
}

.task-detail {
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--v6-color-text-secondary);
  font-size: 12px;
}

.task-message {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.task-speed {
  flex: 0 0 auto;
  font-variant-numeric: tabular-nums;
}

.task-poll-error {
  margin-top: var(--v6-space-3);
}

.card-actions {
  justify-content: flex-end;
  margin-top: auto;
  padding-top: var(--v6-space-4);
}

.empty-icon {
  color: var(--v6-color-text-tertiary);
  font-size: 42px;
}

.sign-accounts-section {
  margin-top: var(--v6-space-4);
  padding: var(--v6-space-3) 0 0;
  border-top: 1px solid var(--v6-color-border-subtle);
}

.section-header {
  margin-bottom: var(--v6-space-2);
}

.sign-accounts-section > :deep(.ant-empty) {
  margin-block: 0;
  padding: var(--v6-space-3) 0 var(--v6-space-1);
}

.sign-accounts-section > :deep(.ant-empty .ant-empty-image) {
  height: 40px;
  margin-bottom: var(--v6-space-1);
}

.sign-accounts-table {
  overflow: hidden;
  border: 1px solid var(--v6-color-border-subtle);
  border-radius: 10px;
}

.sign-accounts-table :deep(.ant-table),
.sign-accounts-table :deep(.ant-table-cell) {
  background: transparent;
}

.sign-accounts-table :deep(.ant-table-thead > tr > th) {
  color: var(--v6-color-text-secondary);
  font-size: 12px;
  background: color-mix(in srgb, var(--v6-color-fill-tertiary) 54%, transparent);
}

:root[data-perf-mode='low'] .game-card {
  backdrop-filter: none;
}

/* 以真实内容区宽度而非窗口宽度决定列数，避免侧栏展开后卡片被误降级。 */
@container game-instances (max-width: 1180px) {
  .game-select {
    width: min(320px, 42cqw);
  }
}

/* 窄内容区退回单列纵向堆叠（与旧行为一致）。 */
@container game-instances (max-width: 980px) {
  .game-grid {
    columns: 1;
  }
}

@container game-instances (max-width: 700px) {
  .page-toolbar {
    flex-direction: column;
  }

  .game-select {
    width: min(100%, 320px);
  }
}

@container game-instances (max-width: 520px) {
  .field-row {
    grid-template-columns: 1fr;
    gap: 4px;
  }

  .card-actions {
    justify-content: flex-start;
    flex-wrap: wrap;
  }
}

@media (prefers-reduced-motion: reduce) {
  .game-card {
    backdrop-filter: none;
  }
}

/* 添加游戏预设选择弹窗：复用新建脚本弹窗的卡片选择视觉模式。
   弹窗内容 teleport 到页面容器之外，声明自己的容器驱动内部响应式。 */
.preset-picker {
  container: game-preset-picker / inline-size;
}

.preset-picker .step-heading h3 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
}

.preset-picker .step-heading p {
  margin: 6px 0 20px;
  color: var(--ant-color-text-secondary);
}

.preset-grid {
  display: grid;
  width: 100%;
  max-height: 420px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  overflow-y: auto;
  scrollbar-color: var(--ant-color-border) transparent;
  scrollbar-width: thin;
}

.preset-card {
  display: flex;
  min-width: 0;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  text-align: left;
  font: inherit;
  cursor: pointer;
}

.preset-card:hover:not(:disabled),
.preset-card.adding {
  border-color: var(--ant-color-primary);
}

.preset-card.adding {
  background: var(--ant-color-primary-bg);
}

.preset-card:disabled:not(.adding) {
  cursor: not-allowed;
  opacity: 0.55;
}

.preset-icon {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  font-size: 19px;
}

.preset-picker .choice-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.preset-picker .choice-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.preset-picker .choice-description {
  margin-top: 3px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.preset-platform-tag {
  flex: 0 0 auto;
  margin-inline-end: 0;
}

.preset-loading {
  flex: 0 0 auto;
  color: var(--ant-color-primary);
}

@container game-preset-picker (max-width: 560px) {
  .preset-grid {
    grid-template-columns: 1fr;
  }
}
</style>

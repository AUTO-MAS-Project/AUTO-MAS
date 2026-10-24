<script setup lang="ts">
import { computed, ref, onScopeDispose } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  FolderOpenOutlined,
  QuestionCircleOutlined,
  ThunderboltOutlined,
} from '@ant-design/icons-vue'
import { BetterGiService, type BetterGIUserConfig_Switch } from '@/api'
import { useBetterGIUpdate } from '../useBetterGIUpdate'

type GameClientDraft = { [K in 'GamePath' | 'Resource']: NonNullable<BetterGIUserConfig_Switch[K]> }
const props = defineProps<{
  scriptId: string
  userId: string
  config: GameClientDraft
  loading: boolean
  locked: boolean
  saveField: (key: 'Switch.GamePath' | 'Switch.Resource', value: string) => Promise<boolean>
}>()
const { t } = useI18n()
let active = true
let readVersion = 0
let saveVersion = 0
let failedPath: string | null = null
let failedResource: string | null = null
let pendingPathSave: { config: GameClientDraft; path: string; result: Promise<boolean> } | null =
  null
onScopeDispose(() => {
  active = false
  readVersion += 1
  saveVersion += 1
})
const { updateModal, handleCheckUpdate, startUpdate, handleUpdateModalCancel } = useBetterGIUpdate(
  () => props.userId
)

// ══ 游戏客户端（用户级覆盖）：透传 BetterGI 配置 + config.ini 渠道识别 ══
// 输入框直接以 BGI 维护的路径为默认值（可编辑）；存值规则：输入值与 BGI 当前
// 路径一致 → 存空（跟随语义，BGI 改了自动跟），否则存显式覆盖值。
// 渠道可识别时自动联动「游戏服务器」（国际服分不出区服，弹提示手选）；
// 渠道无法识别、或手选服务器与识别渠道不一致时气泡提醒（check() 运行时仍硬拦截）。
const gameClientInfo = ref<{
  installPath: string
  globalPath: string
  channel: string
} | null>(null)

const gamePathInput = ref('')

// BGI 全局路径缺失时的兜底提示（正常情况输入框默认值直接显示 BGI 路径）
const gamePathPlaceholder = computed(
  () => gameClientInfo.value?.globalPath || t('edit.bettergiGameClientPlaceholder')
)

const normalizePath = (path: string) =>
  path.replace(/\\/g, '/').replace(/\/+$/, '').trim().toLowerCase()

/** 用户服务器（Switch.Resource）→ 应使用的客户端渠道（与后端校验同口径） */
const RESOURCE_EXPECTED_CHANNEL: Record<string, string> = {
  官服: '官服',
  B服: 'B服',
  亚服: '国际服',
  欧服: '国际服',
  美服: '国际服',
  港澳台服: '国际服',
}

const channelLabel = (channel: string) => {
  switch (channel) {
    case '官服':
      return t('edit.bettergiChannelOfficial')
    case 'B服':
      return t('edit.bettergiChannelBili')
    case '国际服':
      return t('edit.bettergiChannelGlobal')
    default:
      return channel
  }
}

// 「检查更新」只在官服/国际服客户端上可用：后端对 B 服硬拒（版本节奏与官服
// 不同，用官服清单更新会写坏客户端）。以实际识别到的客户端为准，识别不出时
// 退回用户选的服务器推断。
const updateUnsupported = computed(() => {
  const channel =
    gameClientInfo.value?.channel || RESOURCE_EXPECTED_CHANNEL[props.config.Resource] || ''
  return channel === 'B服'
})

const updateCheckDisabled = computed(
  () => props.loading || !props.userId || props.locked || updateUnsupported.value
)

const syncGamePathInput = () => {
  gamePathInput.value = props.config.GamePath || gameClientInfo.value?.globalPath || ''
}

/**
 * 渠道可识别时联动「游戏服务器」：
 * - 官服/B服客户端 → 自动切换（弹气泡告知）；
 * - 国际服客户端分不出区服 → 不猜，当前不是四服之一时提示手动指定；
 * - 渠道无法识别 → 提示手动指定区服。
 */
const syncResourceWithChannel = async () => {
  const channel = gameClientInfo.value?.channel
  if (channel !== '官服' && channel !== 'B服' && channel !== '国际服') {
    message.warning(t('edit.bettergiGameClientUnknownWarning'))
    return
  }
  if (channel === '国际服') {
    const intlServers = ['亚服', '欧服', '美服', '港澳台服']
    if (!intlServers.includes(props.config.Resource)) {
      message.warning(t('edit.bettergiGameClientIntlWarning'))
    }
    return
  }
  if (props.config.Resource !== channel || failedResource === channel) {
    props.config.Resource = channel
    const saved = await props.saveField('Switch.Resource', channel)
    failedResource = saved ? null : channel
    if (!saved || !active) return
    message.success(
      t('edit.bettergiGameClientSynced', {
        server: channel === '官服' ? t('edit.bettergiServerCn') : t('edit.bettergiServerBili'),
      })
    )
  }
}

const loadGameClientInfo = async () => {
  const version = ++readVersion
  const config = props.config
  const path = config.GamePath
  const inputAtStart = gamePathInput.value
  const current = () =>
    active && version === readVersion && config === props.config && path === props.config.GamePath
  try {
    const resp = await BetterGiService.getBettergiGameInfoApiApiScriptsBettergiGameInfoGet(
      props.scriptId,
      props.config.GamePath || ''
    )
    if (!current()) return
    if (resp.status === 'success') {
      gameClientInfo.value = {
        installPath: resp.installPath || '',
        globalPath: resp.globalPath || '',
        channel: resp.channel || '',
      }
    } else {
      gameClientInfo.value = null
    }
  } catch {
    if (!current()) return
    // 展示旁路：识别失败不影响配置编辑
    gameClientInfo.value = null
  }
  // 输入框默认值：用户配置优先，否则直接显示 BGI 维护的路径（可编辑）
  if (gamePathInput.value === inputAtStart) syncGamePathInput()
}

const saveGamePath = async () => {
  if (props.locked || !active) return
  const version = ++saveVersion
  const config = props.config
  const input = (gamePathInput.value || '').trim()
  const globalPath = gameClientInfo.value?.globalPath || ''
  // 输入值与 BGI 当前路径一致 → 存空（跟随），否则存显式覆盖
  const followsGlobal = !!globalPath && normalizePath(input) === normalizePath(globalPath)
  const next = followsGlobal ? '' : input
  const existingSave =
    pendingPathSave?.config === config && pendingPathSave.path === next ? pendingPathSave : null
  if (next !== props.config.GamePath || failedPath === next || existingSave) {
    props.config.GamePath = next
    const pending = existingSave ?? {
      config,
      path: next,
      result: props.saveField('Switch.GamePath', next),
    }
    pendingPathSave = pending
    const saved = await pending.result
    if (pendingPathSave === pending) pendingPathSave = null
    if (!active || version !== saveVersion || config !== props.config) return
    failedPath = saved ? null : next
    if (!saved) return
  }
  if (!active || version !== saveVersion || config !== props.config) return
  await loadGameClientInfo()
  if (!active || version !== saveVersion || config !== props.config) return
  await syncResourceWithChannel()
}

// 路径写入后还需识别渠道并保存服务器；父页离开/恢复前等待整个关联流程。
const pendingPathSaves = new Set<Promise<void>>()
const handleGamePathSaved = () => {
  const pending = saveGamePath()
  pendingPathSaves.add(pending)
  void pending.then(
    () => pendingPathSaves.delete(pending),
    () => pendingPathSaves.delete(pending)
  )
  return pending
}
const waitForPendingSaves = async () => {
  while (pendingPathSaves.size) await Promise.all([...pendingPathSaves])
}
const hasPendingSaves = () => pendingPathSaves.size > 0

/** 弹出文件选择并校验为原神主程序，取消/选错返回 null */
const pickGenshinExe = async (): Promise<string | null> => {
  const paths = await window.electronAPI?.selectFile([
    {
      name: 'YuanShen.exe / GenshinImpact.exe',
      extensions: ['exe'],
    },
  ])
  const path = paths?.[0]
  if (!path) return null
  const fileName = path.split(/[\\/]/).pop()?.toLowerCase()
  if (fileName !== 'yuanshen.exe' && fileName !== 'genshinimpact.exe') {
    message.error(t('edit.bettergiGameClientInvalid'))
    return null
  }
  return path
}

const selectGameClient = async () => {
  const path = await pickGenshinExe()
  if (!path) return
  gamePathInput.value = path
  await handleGamePathSaved()
}

const clearGameClient = async () => {
  gamePathInput.value = gameClientInfo.value?.globalPath || ''
  await handleGamePathSaved()
}

const handleResourceChange = async (value: string) => {
  const saved = await props.saveField('Switch.Resource', value)
  failedResource = saved ? null : value
  if (!saved || !active) return
  const channel = gameClientInfo.value?.channel
  const expected = RESOURCE_EXPECTED_CHANNEL[value]
  if (!channel || !expected || expected === channel) return
  message.warning(
    t('edit.bettergiServerMismatchWarning', {
      server: channelLabel(value),
      channel: channelLabel(channel),
    })
  )
}

defineExpose({ reload: loadGameClientInfo, waitForPendingSaves, hasPendingSaves })
</script>

<template>
  <a-row :gutter="24">
    <slot name="uid" />
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <span class="form-label">
            {{ t('edit.bettergiGameServer') }}
            <a-tooltip :title="t('edit.bettergiGameServerHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-select
          v-model:value="props.config.Resource"
          size="large"
          class="modern-select"
          @change="handleResourceChange"
        >
          <a-select-option value="官服">{{ t('edit.bettergiServerCn') }}</a-select-option>
          <a-select-option value="B服">{{ t('edit.bettergiServerBili') }}</a-select-option>
          <a-select-option value="亚服">{{ t('edit.bettergiServerAsia') }}</a-select-option>
          <a-select-option value="欧服">{{ t('edit.bettergiServerEurope') }}</a-select-option>
          <a-select-option value="美服">{{ t('edit.bettergiServerAmerica') }}</a-select-option>
          <a-select-option value="港澳台服">
            {{ t('edit.bettergiServerTwHkMo') }}
          </a-select-option>
        </a-select>
      </a-form-item>
    </a-col>
  </a-row>

  <a-row :gutter="24">
    <a-col :span="24">
      <div class="game-client-row">
        <a-form-item>
          <template #label>
            <span class="form-label">
              {{ t('edit.bettergiGameClient') }}
              <a-tooltip :title="t('edit.bettergiGameClientHint')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </span>
          </template>
          <a-input-group compact class="path-input-group">
            <a-input
              v-model:value="gamePathInput"
              :placeholder="gamePathPlaceholder"
              size="large"
              class="path-input"
              @blur="handleGamePathSaved"
            />
            <a-button size="large" class="path-button" @click="selectGameClient">
              <template #icon>
                <FolderOpenOutlined />
              </template>
              {{ t('edit.pickFile') }}
            </a-button>
            <a-button
              size="large"
              class="path-button"
              :disabled="!gamePathInput"
              @click="clearGameClient"
            >
              {{ t('edit.bettergiGameClientRestore') }}
            </a-button>
          </a-input-group>
        </a-form-item>
        <a-tooltip :title="updateUnsupported ? t('edit.bettergiUpdateUnsupportedHint') : ''">
          <span class="game-client-check">
            <a-button size="large" :disabled="updateCheckDisabled" @click="handleCheckUpdate">
              <template #icon>
                <ThunderboltOutlined />
              </template>
              {{ t('edit.checkUpdates') }}
            </a-button>
          </span>
        </a-tooltip>
      </div>
    </a-col>
  </a-row>

  <a-modal
    v-model:open="updateModal.open"
    :title="
      updateModal.running
        ? t('edit.bettergiUpdateProgressTitle')
        : t('edit.bettergiCheckUpdateTitle')
    "
    :confirm-loading="updateModal.starting"
    :mask-closable="!updateModal.running"
    :footer="updateModal.running || updateModal.done ? null : undefined"
    @ok="startUpdate"
    @cancel="handleUpdateModalCancel"
  >
    <!-- 出结论后也要留着日志：后端专门推的「已是最新 / 更新完成 x -> y」就在里面 -->
    <template v-if="updateModal.running || updateModal.done">
      <div class="update-log-area">
        <pre class="update-log-content">{{
          updateModal.log || t('edit.bettergiUpdateConnecting')
        }}</pre>
      </div>
    </template>
    <template v-else>
      <a-alert type="info" show-icon :message="t('edit.bettergiWillBeUpdated')" />
    </template>
  </a-modal>
</template>

<style scoped>
@import './bettergiFormControls.css';

/* 游戏客户端路径（用户级覆盖）：输入组与信息行 */
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

/* 「检查更新」独立于路径输入组：输入框与它共占一行，按钮贴右并与输入框底对齐 */
.game-client-row {
  display: flex;
  align-items: flex-end;
  gap: 12px;
  margin-bottom: 24px;
}

.game-client-row :deep(.ant-form-item) {
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
}

.game-client-check {
  flex-shrink: 0;
}

.update-log-area {
  max-height: 320px;
  overflow-y: auto;
  padding: 12px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  background: var(--ant-color-bg-layout);
}

.update-log-content {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--ant-color-text);
}
</style>

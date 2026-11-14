<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef } from 'vue'
import { message } from 'ant-design-vue'
import { EyeOutlined, EyeInvisibleOutlined, MinusOutlined } from '@ant-design/icons-vue'
import type {
  DesktopSessionRequest,
  DesktopSessionSnapshot,
  DesktopQueueResult,
} from '../../../electron/services/desktopSessionProtocol'

const preview = ref<HTMLElement | null>(null)
const snapshot = shallowRef<DesktopSessionSnapshot | null>(null)
const pending = shallowRef<DesktopSessionRequest | null>(null)
const results = shallowRef<DesktopQueueResult[]>([])
const mode = ref<DesktopSessionRequest['mode']>('proxy')
const resolution = ref<DesktopSessionRequest['resolution']>('1080p')
const password = ref('')
const passwordDialog = ref(false)
const starting = ref(false)
const checking = ref(true)
const volume = ref(0)
const disposers: (() => void)[] = []
const api = window.electronAPI

const statusText = computed(() => {
  if (snapshot.value?.closing) return '关闭中'
  if (checking.value) return '环境检测中'
  if (snapshot.value?.state === 'blocked') return '环境检测异常'
  if (starting.value || snapshot.value?.state === 'connecting') return '启动中'
  return snapshot.value?.state === 'connected'
    ? '已连接'
    : snapshot.value?.state === 'disconnected'
      ? '连接已断开'
      : '未连接'
})
const running = computed(() => snapshot.value?.state === 'connected')
const blocked = computed(
  () =>
    snapshot.value?.state === 'blocked' ||
    !snapshot.value?.checks.length ||
    snapshot.value.checks.some(item => item.required && !item.ok)
)
const canStart = computed(
  () =>
    !checking.value &&
    !blocked.value &&
    !starting.value &&
    !snapshot.value?.busy &&
    !snapshot.value?.closing
)
const canConfigure = computed(() => !running.value && !starting.value && !snapshot.value?.busy)

const errors: Record<string, string> = {
  password_required: '请输入当前 Windows 账户的密码。',
  password_invalid: 'Windows 密码验证失败，请重新输入账户密码。',
  account_mismatch: '凭据所属账户与当前 Windows 账户不一致。',
  credential_unreadable: '无法解密保存的凭据，请重新输入密码。',
  credential_save_failed: '分身已连接，但密码保存失败。',
  environment_blocked: '当前环境未通过检测，请查看下方检查结果。',
  main_busy: '主会话有任务、更新或配置操作正在运行，请等收尾完成后重试。',
  rdp_disconnected: '桌面分身连接已断开。',
  connection_failed: '桌面分身连接失败，请查看分身日志。',
  handoff_unconfirmed: '无法确认调度交接或收尾，请查看分身日志。',
  main_resume_failed: '分身已释放配置，主会话后端恢复失败，请查看日志。',
  executor_failed: '子会话执行器启动失败，请查看分身日志。',
  executor_interrupted: '子会话执行器已中断，请查看分身日志中的任务记录。',
  desktop_size_changed: '子桌面分辨率与连接时的设置不一致。',
  session_changed: '子会话已变化，任务派发已停止。',
  host_exited: '桌面分身预览进程已退出。',
}
const diagnostics: Record<string, string> = {
  windows: '仅支持 Windows 10 1809 及以上或 Windows 11 客户端。',
  x64: '请使用 Windows x64 和 MAS 的 x64 Python。',
  edition: 'Windows 版本',
  interactive: '请在已登录的交互桌面打开 MAS。',
  components: '检查系统的 ATL、远程桌面及凭据保护组件是否完整。',
  service_dll: '远程桌面服务未使用原生 DLL。请处理 RDP Wrapper 或系统组件修改。',
  service_signature: '无法确认远程桌面系统文件签名。请检查 Windows 系统文件完整性。',
  term_service: '远程桌面服务未运行，请在 Windows 服务中检查。',
  task_scheduler: '任务计划程序未运行，请在 Windows 服务中检查。',
  child_enabled: 'Windows 子会话尚未启用。请由管理员按系统指引处理后重检。',
  rdp_policy: '远程桌面已被关闭。请检查 Windows 设置或联系策略管理员。',
  hello_only: '系统可能只允许 Windows Hello 登录。遇到密码验证失败时请检查登录选项。',
  rdp_listener: '找不到预期的本机 RDP 监听。请检查远程桌面相关服务与设置。',
}
const credentialErrors = new Set([
  'password_required',
  'password_invalid',
  'credential_unreadable',
  'account_mismatch',
])
const errorText = computed(() => {
  const code = snapshot.value?.code
  return code ? errors[code] || `桌面分身操作失败（${code}），详情见日志。` : ''
})

function reportBounds() {
  if (!preview.value) return
  const { x, y, width, height } = preview.value.getBoundingClientRect()
  if (width >= 1 && height >= 1) {
    api?.desktopSessionBounds?.({
      x: Math.round(x),
      y: Math.round(y),
      width: Math.round(width),
      height: Math.round(height),
    })
  }
}

async function check() {
  checking.value = true
  try {
    snapshot.value = (await api?.desktopSessionCheck?.()) ?? null
  } finally {
    checking.value = false
  }
}

async function start(secret?: string) {
  if (!canStart.value) return
  starting.value = true
  results.value = []
  reportBounds()
  try {
    const response = await api?.desktopSessionStart?.({
      queueIds: pending.value?.queueIds ?? [],
      mode: mode.value,
      resolution: resolution.value,
      password: secret,
    })
    if (!response) return
    results.value = response.queues
    if (response.code && credentialErrors.has(response.code)) passwordDialog.value = true
    else if (!response.code) pending.value = null
    else if (snapshot.value) snapshot.value = { ...snapshot.value, code: response.code }
  } catch {
    message.error('启动桌面分身失败，请查看日志。')
  } finally {
    starting.value = false
  }
}

function submitPassword() {
  const input = password.value
  password.value = ''
  passwordDialog.value = false
  void start(input)
}

async function readPending() {
  const request = await api?.desktopSessionPending?.()
  if (!request) return
  pending.value = request
  if (!running.value) {
    mode.value = request.mode
    resolution.value = request.resolution
  }
  if (canStart.value) void start()
}

let observer: ResizeObserver | undefined
onMounted(async () => {
  const state = api?.onDesktopSessionState?.(value => {
    snapshot.value = value
  })
  const incoming = api?.onDesktopSessionPending?.(() => void readPending())
  if (state) disposers.push(state)
  if (incoming) disposers.push(incoming)
  if (preview.value) {
    observer = new ResizeObserver(reportBounds)
    observer.observe(preview.value)
  }
  reportBounds()
  await check()
  await readPending()
})
onBeforeUnmount(() => {
  observer?.disconnect()
  disposers.forEach(dispose => dispose())
})
</script>

<template>
  <main class="desktop-window">
    <header class="desktop-bar">
      <a-flex align="center" wrap="wrap" gap="small">
        <a-badge
          :status="
            snapshot?.closing || checking || starting
              ? 'processing'
              : blocked
                ? 'error'
                : running
                  ? 'success'
                  : 'default'
          "
          :text="statusText"
        />
        <a-typography-text v-if="snapshot?.sessionId" type="secondary">
          会话 {{ snapshot.sessionId }} · {{ snapshot.size?.join(' × ') }}
        </a-typography-text>
        <a-tag v-if="running && snapshot?.windowState === 'hidden'">预览已隐藏</a-tag>
        <a-tag v-if="snapshot?.executing && !snapshot?.closing" color="processing"
          >任务运行中</a-tag
        >
      </a-flex>
      <a-space wrap>
        <a-button
          v-if="!running || pending"
          :disabled="!canStart"
          :loading="starting"
          type="primary"
          @click="start()"
        >
          {{ pending?.queueIds.length ? '启动所选任务' : '启动' }}
        </a-button>
        <a-button
          v-if="running && snapshot?.windowState !== 'visible'"
          @click="api?.desktopSessionWindow?.('show')"
        >
          <template #icon><EyeOutlined /></template>显示
        </a-button>
        <a-button v-else :disabled="!running" @click="api?.desktopSessionWindow?.('hide')">
          <template #icon><EyeInvisibleOutlined /></template>隐藏
        </a-button>
        <a-button aria-label="最小化" @click="api?.desktopSessionWindow?.('minimize')">
          <template #icon><MinusOutlined /></template>
        </a-button>
        <a-button @click="api?.desktopSessionLogs?.()">查看分身日志</a-button>
      </a-space>
    </header>
    <div class="desktop-options">
      <a-space wrap>
        <a-select
          v-model:value="resolution"
          aria-label="分身分辨率"
          :disabled="!canConfigure"
          :options="[
            { value: '1080p', label: '1920 × 1080' },
            { value: 'primary', label: '同步主屏分辨率' },
          ]"
        />
        <a-select
          v-model:value="mode"
          aria-label="最小化模式"
          :disabled="!canConfigure"
          :options="[
            { value: 'proxy', label: '后台最小化' },
            { value: 'native', label: '原生最小化' },
          ]"
        />
        <label for="desktop-volume">分身音量</label>
        <a-slider
          id="desktop-volume"
          v-model:value="volume"
          class="volume"
          :disabled="!running"
          @change="(value: number) => api?.desktopSessionVolume?.(value)"
        />
      </a-space>
    </div>
    <a-alert
      v-if="snapshot?.closing"
      type="info"
      show-icon
      message="正在关闭桌面分身，请等待任务收尾和会话注销。"
    />
    <a-alert
      v-else-if="errorText"
      type="warning"
      show-icon
      :message="errorText"
      :description="snapshot?.interruptedTaskIds?.join(' · ')"
    />
    <div ref="preview" class="desktop-viewport">
      <a-flex
        v-if="!running || snapshot?.windowState !== 'visible'"
        vertical
        gap="middle"
        class="empty"
      >
        <a-alert type="warning" show-icon message="风险提示：该功能为实验功能" />
        <template v-if="snapshot?.closing">
          <a-spin />
        </template>
        <template v-else-if="!running">
          <a-button :loading="checking" :disabled="starting" @click="check">重新检测环境</a-button>
          <a-typography-text v-if="!checking && blocked" type="secondary">
            请按下方检查结果手动处理后重新检测。自动修复将在后续版本提供。
          </a-typography-text>
          <a-typography-text
            v-for="item in snapshot?.checks.filter(check => !check.ok)"
            :key="item.code"
            :type="item.required ? 'danger' : 'secondary'"
          >
            {{ diagnostics[item.code] || item.code }}
          </a-typography-text>
        </template>
        <a-typography-text v-else type="secondary"
          >预览已隐藏，子会话仍保持连接。</a-typography-text
        >
      </a-flex>
    </div>
    <a-flex v-if="results.length" vertical class="dispatch-results">
      <a-typography-text
        v-for="result in results"
        :key="result.queueId"
        :type="result.taskId ? 'success' : 'danger'"
      >
        {{ result.label }} · {{ result.taskId ? '已派发，进度请查看主窗口调度页' : result.message }}
      </a-typography-text>
    </a-flex>
    <a-modal
      v-model:open="passwordDialog"
      title="验证 Windows 密码"
      ok-text="连接"
      cancel-text="取消"
      :ok-button-props="{ disabled: !password }"
      @ok="submitPassword"
      @cancel="password = ''"
    >
      <a-input-password
        v-model:value="password"
        placeholder="当前 Windows 账户的密码"
        autocomplete="off"
        @press-enter="password && submitPassword()"
      />
    </a-modal>
  </main>
</template>

<style scoped>
.desktop-window {
  display: flex;
  flex-direction: column;
  height: 100vh;
  padding: 12px;
  gap: 8px;
  box-sizing: border-box;
}
.desktop-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.desktop-options {
  display: flex;
  padding-block: 4px;
}
.desktop-viewport {
  display: grid;
  min-height: 180px;
  flex: 1;
  overflow: auto;
  background: var(--app-color-bg-container, var(--ant-color-bg-container));
}
.volume {
  min-width: 108px;
}
.empty {
  align-self: center;
  justify-self: center;
  padding: 16px;
  max-width: 680px;
}
.dispatch-results {
  max-height: 100px;
  overflow: auto;
}
</style>

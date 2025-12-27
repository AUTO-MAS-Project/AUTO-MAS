<template>
  <div class="ws-debug-page">
    <!-- 页面标题 -->
    <div class="page-header">
      <h1>WebSocket 客户端调试</h1>
      <p class="description">后端作为 WebSocket 客户端连接外部服务器（如 Koishi）进行调试</p>
    </div>

    <!-- 客户端概览 -->
    <a-card class="overview-card" :bordered="false">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic title="客户端总数" :value="clientList.length">
            <template #prefix>
              <ApiOutlined />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic title="已连接" :value="connectedCount">
            <template #prefix>
              <CheckCircleOutlined style="color: #52c41a" />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic title="未连接" :value="clientList.length - connectedCount">
            <template #prefix>
              <CloseCircleOutlined style="color: #ff4d4f" />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic title="消息总数" :value="totalMessageCount">
            <template #prefix>
              <MessageOutlined />
            </template>
          </a-statistic>
        </a-col>
      </a-row>
    </a-card>

    <a-row :gutter="16" class="main-content">
      <!-- 左侧：客户端管理 -->
      <a-col :span="10">
        <a-card title="客户端管理" :bordered="false" class="client-card">
          <template #extra>
            <a-space>
              <a-button type="primary" size="small" @click="showCreateModal">
                <template #icon><PlusOutlined /></template>
                新建客户端
              </a-button>
              <a-button size="small" @click="refreshClientList">
                <template #icon><ReloadOutlined /></template>
              </a-button>
            </a-space>
          </template>

          <!-- 客户端列表 -->
          <div class="client-list">
            <a-empty v-if="clientList.length === 0" description="暂无客户端，点击上方按钮创建" />
            <div
              v-for="client in clientList"
              :key="client.name"
              class="client-item"
              :class="{ active: selectedClient === client.name, connected: client.is_connected }"
              @click="selectClient(client.name)"
            >
              <div class="client-info">
                <div class="client-name">
                  <a-badge :status="client.is_connected ? 'success' : 'default'" />
                  {{ client.name }}
                </div>
                <div class="client-url">{{ client.url }}</div>
              </div>
              <div class="client-actions">
                <a-button
                  v-if="!client.is_connected"
                  type="link"
                  size="small"
                  :loading="connectingClients[client.name]"
                  @click.stop="connectClient(client.name)"
                >
                  连接
                </a-button>
                <a-button
                  v-else
                  type="link"
                  size="small"
                  danger
                  @click.stop="disconnectClient(client.name)"
                >
                  断开
                </a-button>
                <a-button
                  type="link"
                  size="small"
                  danger
                  @click.stop="removeClient(client.name)"
                >
                  <DeleteOutlined />
                </a-button>
              </div>
            </div>
          </div>
        </a-card>

        <!-- 发送消息面板 -->
        <a-card title="发送消息" :bordered="false" class="send-card" style="margin-top: 16px">
          <a-form layout="vertical">
            <a-form-item label="消息类型">
              <a-radio-group v-model:value="sendMode" button-style="solid">
                <a-radio-button value="formatted">格式化消息</a-radio-button>
                <a-radio-button value="raw">原始 JSON</a-radio-button>
                <a-radio-button value="auth">认证消息</a-radio-button>
              </a-radio-group>
            </a-form-item>

            <!-- 格式化消息 -->
            <template v-if="sendMode === 'formatted'">
              <a-row :gutter="12">
                <a-col :span="12">
                  <a-form-item label="消息 ID">
                    <a-input v-model:value="formattedMessage.id" placeholder="Client" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="消息类型">
                    <a-input v-model:value="formattedMessage.type" placeholder="command" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="消息数据 (JSON)">
                <a-textarea
                  v-model:value="formattedMessage.data"
                  :rows="4"
                  placeholder='{"key": "value"}'
                />
              </a-form-item>
            </template>

            <!-- 原始 JSON -->
            <template v-else-if="sendMode === 'raw'">
              <a-form-item label="JSON 消息">
                <a-textarea
                  v-model:value="rawMessage"
                  :rows="6"
                  placeholder='{"id": "Client", "type": "command", "data": {}}'
                />
              </a-form-item>
            </template>

            <!-- 认证消息 -->
            <template v-else-if="sendMode === 'auth'">
              <a-row :gutter="12">
                <a-col :span="12">
                  <a-form-item label="认证 Token">
                    <a-input-password v-model:value="authMessage.token" placeholder="输入 Token" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="认证类型">
                    <a-input v-model:value="authMessage.type" placeholder="auth" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="额外数据 (JSON, 可选)">
                <a-textarea
                  v-model:value="authMessage.extra"
                  :rows="2"
                  placeholder='{"extra_key": "extra_value"}'
                />
              </a-form-item>
            </template>

            <a-form-item>
              <a-button
                type="primary"
                block
                :loading="sending"
                @click="sendMessage"
              >
                <template #icon><SendOutlined /></template>
                发送消息
              </a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-col>

      <!-- 右侧：消息记录 -->
      <a-col :span="14">
        <a-card title="消息记录" :bordered="false" class="message-card">
          <template #extra>
            <a-space>
              <a-switch
                v-model:checked="autoScroll"
                checked-children="自动滚动"
                un-checked-children="手动滚动"
              />
              <a-select
                v-model:value="messageFilter"
                style="width: 120px"
                size="small"
              >
                <a-select-option value="all">全部消息</a-select-option>
                <a-select-option value="sent">仅发送</a-select-option>
                <a-select-option value="received">仅接收</a-select-option>
              </a-select>
              <a-button size="small" danger @click="clearHistory">
                <template #icon><DeleteOutlined /></template>
                清空
              </a-button>
            </a-space>
          </template>

          <div ref="messageContainer" class="message-container">
            <template v-if="filteredMessages.length > 0">
              <div
                v-for="(msg, index) in filteredMessages"
                :key="index"
                class="message-item"
                :class="msg.direction"
              >
                <div class="message-header">
                  <a-tag :color="msg.direction === 'sent' ? 'blue' : 'green'" size="small">
                    {{ msg.direction === 'sent' ? '发送' : '接收' }}
                  </a-tag>
                  <span class="message-client">{{ msg.client }}</span>
                  <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
                </div>
                <pre class="message-content">{{ formatJson(msg.data) }}</pre>
              </div>
            </template>
            <a-empty v-else description="暂无消息记录" />
          </div>
        </a-card>
      </a-col>
    </a-row>

    <!-- 创建客户端弹窗 -->
    <a-modal
      v-model:open="createModalVisible"
      title="创建 WebSocket 客户端"
      @ok="createClient"
      :confirmLoading="creating"
    >
      <a-form layout="vertical">
        <a-form-item label="客户端名称" required>
          <a-input
            v-model:value="createForm.name"
            placeholder="输入客户端名称，如 Koishi"
          />
        </a-form-item>
        <a-form-item label="服务器 URL" required>
          <a-input
            v-model:value="createForm.url"
            placeholder="ws://localhost:5140/AUTO_MAS"
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="心跳间隔（秒）">
              <a-input-number
                v-model:value="createForm.pingInterval"
                :min="1"
                :max="300"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="心跳超时（秒）">
              <a-input-number
                v-model:value="createForm.pingTimeout"
                :min="5"
                :max="600"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="重连间隔（秒）">
              <a-input-number
                v-model:value="createForm.reconnectInterval"
                :min="1"
                :max="60"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="最大重连次数">
              <a-input-number
                v-model:value="createForm.maxReconnectAttempts"
                :min="-1"
                style="width: 100%"
              />
              <div class="form-tip">-1 表示无限重连</div>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </a-modal>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from 'vue'
import {
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  MessageOutlined,
  PlusOutlined,
  ReloadOutlined,
  DeleteOutlined,
  SendOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { WebSocketService } from '@/api'

// ============== 类型定义 ==============

interface ClientInfo {
  name: string
  url: string
  is_connected: boolean
  ping_interval: number
  ping_timeout: number
  reconnect_interval: number
  max_reconnect_attempts: number
  message_count: number
}

interface MessageRecord {
  direction: 'sent' | 'received'
  timestamp: number
  data: any
  client: string
}

// ============== 状态定义 ==============

// 客户端列表
const clientList = ref<ClientInfo[]>([])
const selectedClient = ref<string | null>(null)
const connectingClients = ref<Record<string, boolean>>({})

// 消息相关
const messages = ref<MessageRecord[]>([])
const messageFilter = ref<'all' | 'sent' | 'received'>('all')
const autoScroll = ref(true)
const messageContainer = ref<HTMLElement | null>(null)

// 发送消息
const sendMode = ref<'formatted' | 'raw' | 'auth'>('formatted')
const sending = ref(false)

const formattedMessage = ref({
  id: 'Client',
  type: 'command',
  data: '{}',
})

const rawMessage = ref('{\n  "id": "Client",\n  "type": "command",\n  "data": {}\n}')

const authMessage = ref({
  token: '',
  type: 'auth',
  extra: '',
})

// 创建客户端弹窗
const createModalVisible = ref(false)
const creating = ref(false)
const createForm = ref({
  name: '',
  url: 'ws://localhost:5140/AUTO_MAS',
  pingInterval: 15,
  pingTimeout: 30,
  reconnectInterval: 5,
  maxReconnectAttempts: -1,
})

// 实时 WebSocket 连接
let liveWs: WebSocket | null = null

// ============== 计算属性 ==============

const connectedCount = computed(() => {
  return clientList.value.filter((c) => c.is_connected).length
})

const totalMessageCount = computed(() => {
  return messages.value.length
})

const isSelectedClientConnected = computed(() => {
  if (!selectedClient.value) return false
  const client = clientList.value.find((c) => c.name === selectedClient.value)
  return client?.is_connected ?? false
})

const filteredMessages = computed(() => {
  if (messageFilter.value === 'all') {
    return messages.value
  }
  return messages.value.filter((m) => m.direction === messageFilter.value)
})

// ============== 方法 ==============

// 格式化 JSON
function formatJson(data: any): string {
  try {
    if (typeof data === 'string') {
      return JSON.stringify(JSON.parse(data), null, 2)
    }
    return JSON.stringify(data, null, 2)
  } catch {
    return String(data)
  }
}

// 格式化时间戳
function formatTime(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return (
    date.toLocaleTimeString('zh-CN', { hour12: false }) +
    '.' +
    String(date.getMilliseconds()).padStart(3, '0')
  )
}

// 刷新客户端列表
async function refreshClientList() {
  try {
    const response = await WebSocketService.listClientsApiWsDebugClientListGet()
    if (response.code === 200 && response.data) {
      clientList.value = response.data.clients || []
    }
  } catch (error: any) {
    console.error('刷新客户端列表失败:', error)
  }
}

// 选择客户端
function selectClient(name: string) {
  selectedClient.value = name
}

// 显示创建弹窗
function showCreateModal() {
  createForm.value = {
    name: '',
    url: 'ws://localhost:5140/AUTO_MAS',
    pingInterval: 15,
    pingTimeout: 30,
    reconnectInterval: 5,
    maxReconnectAttempts: -1,
  }
  createModalVisible.value = true
}

// 记录 API 请求到消息记录
function logApiRequest(endpoint: string, method: string, body: any) {
  addMessage({
    direction: 'sent',
    timestamp: Date.now() / 1000,
    data: {
      _type: 'API_REQUEST',
      endpoint,
      method,
      body,
    },
    client: 'Frontend',
  })
}

// 记录 API 响应到消息记录
function logApiResponse(endpoint: string, response: any) {
  addMessage({
    direction: 'received',
    timestamp: Date.now() / 1000,
    data: {
      _type: 'API_RESPONSE',
      endpoint,
      response,
    },
    client: 'Backend',
  })
}

// 创建客户端
async function createClient() {
  if (!createForm.value.name) {
    message.error('请输入客户端名称')
    return
  }
  if (!createForm.value.url) {
    message.error('请输入服务器 URL')
    return
  }

  creating.value = true
  try {
    const requestBody = {
      name: createForm.value.name,
      url: createForm.value.url,
      ping_interval: createForm.value.pingInterval,
      ping_timeout: createForm.value.pingTimeout,
      reconnect_interval: createForm.value.reconnectInterval,
      max_reconnect_attempts: createForm.value.maxReconnectAttempts,
    }
    logApiRequest('/api/ws_debug/client/create', 'POST', requestBody)
    const response = await WebSocketService.createClientApiWsDebugClientCreatePost(requestBody)
    logApiResponse('/api/ws_debug/client/create', response)

    if (response.code === 200) {
      message.success(`客户端 [${createForm.value.name}] 创建成功`)
      createModalVisible.value = false
      await refreshClientList()
      selectedClient.value = createForm.value.name
    } else {
      message.error(response.message || '创建失败')
    }
  } catch (error: any) {
    message.error(error.message || '创建失败')
  } finally {
    creating.value = false
  }
}

// 连接客户端
async function connectClient(name: string) {
  connectingClients.value[name] = true
  try {
    const requestBody = { name }
    logApiRequest('/api/ws_debug/client/connect', 'POST', requestBody)
    const response = await WebSocketService.connectClientApiWsDebugClientConnectPost(requestBody)
    logApiResponse('/api/ws_debug/client/connect', response)

    if (response.code === 200) {
      message.success(`客户端 [${name}] 连接成功`)
      await refreshClientList()
    } else {
      message.error(response.message || '连接失败')
    }
  } catch (error: any) {
    message.error(error.message || '连接失败')
  } finally {
    connectingClients.value[name] = false
  }
}

// 断开客户端
async function disconnectClient(name: string) {
  try {
    const requestBody = { name }
    logApiRequest('/api/ws_debug/client/disconnect', 'POST', requestBody)
    const response = await WebSocketService.disconnectClientApiWsDebugClientDisconnectPost(requestBody)
    logApiResponse('/api/ws_debug/client/disconnect', response)

    if (response.code === 200) {
      message.success(`客户端 [${name}] 已断开`)
      await refreshClientList()
    } else {
      message.error(response.message || '断开失败')
    }
  } catch (error: any) {
    message.error(error.message || '断开失败')
  }
}

// 删除客户端
async function removeClient(name: string) {
  try {
    const requestBody = { name }
    logApiRequest('/api/ws_debug/client/remove', 'POST', requestBody)
    const response = await WebSocketService.removeClientApiWsDebugClientRemovePost(requestBody)
    logApiResponse('/api/ws_debug/client/remove', response)

    if (response.code === 200) {
      message.success(`客户端 [${name}] 已删除`)
      if (selectedClient.value === name) {
        selectedClient.value = null
      }
      await refreshClientList()
    } else {
      message.error(response.message || '删除失败')
    }
  } catch (error: any) {
    message.error(error.message || '删除失败')
  }
}

// 发送消息
async function sendMessage() {
  if (!selectedClient.value) {
    message.error('请先选择一个客户端')
    return
  }

  sending.value = true
  try {
    let response: any

    if (sendMode.value === 'formatted') {
      let data: any
      try {
        data = JSON.parse(formattedMessage.value.data)
      } catch {
        message.error('消息数据不是有效的 JSON')
        return
      }

      const jsonRequestBody = {
        name: selectedClient.value,
        msg_id: formattedMessage.value.id,
        msg_type: formattedMessage.value.type,
        data,
      }
      logApiRequest('/api/ws_debug/message/send_json', 'POST', jsonRequestBody)
      response = await WebSocketService.sendJsonMessageApiWsDebugMessageSendJsonPost(jsonRequestBody)
      logApiResponse('/api/ws_debug/message/send_json', response)
    } else if (sendMode.value === 'raw') {
      let messageObj: any
      try {
        messageObj = JSON.parse(rawMessage.value)
      } catch {
        message.error('消息内容不是有效的 JSON')
        return
      }

      const rawRequestBody = {
        name: selectedClient.value,
        message: messageObj,
      }
      logApiRequest('/api/ws_debug/message/send', 'POST', rawRequestBody)
      response = await WebSocketService.sendMessageApiWsDebugMessageSendPost(rawRequestBody)
      logApiResponse('/api/ws_debug/message/send', response)
    } else if (sendMode.value === 'auth') {
      if (!authMessage.value.token) {
        message.error('请输入认证 Token')
        return
      }

      let extraData: any = undefined
      if (authMessage.value.extra) {
        try {
          extraData = JSON.parse(authMessage.value.extra)
        } catch {
          message.error('额外数据不是有效的 JSON')
          return
        }
      }

      const authRequestBody = {
        name: selectedClient.value,
        token: authMessage.value.token,
        auth_type: authMessage.value.type,
        extra_data: extraData,
      }
      logApiRequest('/api/ws_debug/message/auth', 'POST', authRequestBody)
      response = await WebSocketService.sendAuthApiWsDebugMessageAuthPost(authRequestBody)
      logApiResponse('/api/ws_debug/message/auth', response)
    }

    if (response?.code === 200) {
      message.success('消息发送成功')
    } else {
      message.error(response?.message || '发送失败')
    }
  } catch (error: any) {
    message.error(error.message || '发送失败')
  } finally {
    sending.value = false
  }
}

// 清空历史
async function clearHistory() {
  try {
    await WebSocketService.clearHistoryApiWsDebugHistoryClearPost({
      name: selectedClient.value || undefined,
    })
    messages.value = []
    message.success('已清空消息历史')
  } catch (error: any) {
    message.error('清空失败')
  }
}

// 添加消息
function addMessage(record: MessageRecord) {
  messages.value.push(record)

  if (autoScroll.value) {
    nextTick(() => {
      if (messageContainer.value) {
        messageContainer.value.scrollTop = messageContainer.value.scrollHeight
      }
    })
  }
}

// 建立实时 WebSocket 连接
function connectLiveWs() {
  const wsUrl = `ws://${window.location.host}/api/ws_debug/live`

  try {
    liveWs = new WebSocket(wsUrl)

    liveWs.onopen = () => {
      console.log('实时消息连接已建立')
    }

    liveWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'init') {
          // 初始化客户端列表
          clientList.value = data.clients || []
        } else if (data.type === 'message') {
          // 添加消息记录
          addMessage({
            direction: data.direction,
            timestamp: data.timestamp,
            data: data.data,
            client: data.client,
          })
        } else if (data.type === 'event') {
          // 处理事件
          if (data.event === 'connected' || data.event === 'disconnected') {
            refreshClientList()
          }
        }
      } catch (error) {
        console.error('解析实时消息失败:', error)
      }
    }

    liveWs.onerror = (error) => {
      console.error('实时消息连接错误:', error)
    }

    liveWs.onclose = () => {
      console.log('实时消息连接已关闭')
      liveWs = null
      // 5秒后重连
      setTimeout(connectLiveWs, 5000)
    }
  } catch (error) {
    console.error('创建实时消息连接失败:', error)
  }
}

// 断开实时 WebSocket
function disconnectLiveWs() {
  if (liveWs) {
    liveWs.close()
    liveWs = null
  }
}

// 加载历史消息
async function loadHistory() {
  try {
    const response = await WebSocketService.getHistoryApiWsDebugHistoryGet()
    if (response.code === 200 && response.data?.history) {
      messages.value = []
      const history = response.data.history
      for (const clientName of Object.keys(history)) {
        for (const msg of history[clientName]) {
          messages.value.push({
            ...msg,
            client: clientName,
          })
        }
      }
      // 按时间排序
      messages.value.sort((a, b) => a.timestamp - b.timestamp)
    }
  } catch (error: any) {
    console.error('加载历史消息失败:', error)
  }
}

// 页面加载时
onMounted(async () => {
  await refreshClientList()
  await loadHistory()
  connectLiveWs()
})

// 页面卸载时
onUnmounted(() => {
  disconnectLiveWs()
})
</script>

<style scoped>
.ws-debug-page {
  padding: 24px;
  max-width: 1600px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: 24px;
}

.page-header h1 {
  margin: 0 0 8px;
  font-size: 24px;
  font-weight: 600;
}

.page-header .description {
  margin: 0;
  color: var(--ant-color-text-secondary);
}

.overview-card {
  margin-bottom: 24px;
}

.main-content {
  margin-top: 16px;
}

.client-card,
.send-card,
.message-card {
  height: 100%;
}

.client-list {
  max-height: 200px;
  overflow-y: auto;
}

.client-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  cursor: pointer;
  transition: all 0.2s;
}

.client-item:hover {
  background: var(--ant-color-fill-tertiary);
}

.client-item.active {
  background: var(--ant-color-primary-bg);
  border: 1px solid var(--ant-color-primary);
}

.client-item.connected {
  border-left: 3px solid var(--ant-color-success);
}

.client-info {
  flex: 1;
  min-width: 0;
}

.client-name {
  font-weight: 500;
  margin-bottom: 4px;
}

.client-url {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.client-actions {
  display: flex;
  gap: 4px;
}

.message-container {
  max-height: 400px;
  overflow-y: auto;
  padding: 8px;
}

.message-item {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.message-item.sent {
  background: var(--ant-color-primary-bg);
  border-left: 3px solid var(--ant-color-primary);
}

.message-item.received {
  background: var(--ant-color-success-bg-hover);
  border-left: 3px solid var(--ant-color-success);
}

.message-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.message-client {
  font-weight: 500;
  font-size: 13px;
}

.message-time {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  font-family: monospace;
  margin-left: auto;
}

.message-content {
  margin: 0;
  padding: 8px;
  background: var(--ant-color-bg-container);
  border-radius: 4px;
  font-size: 13px;
  font-family: 'Consolas', 'Monaco', monospace;
  white-space: pre-wrap;
  word-break: break-all;
  overflow-x: auto;
}

.form-tip {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  margin-top: 4px;
}
</style>

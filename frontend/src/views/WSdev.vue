<template>
  <div class="ws-debug-page">
    <!-- 标题 -->
    <div class="page-header">
      <h1>WebSocket 测试页面</h1>
      <p class="description">测试与后端 WebSocket 连接、认证、消息收发功能</p>
      <p class="description">别忘了它只是个孩子，可能出现各种奇怪的问题</p>
    </div>

    <!-- 连接状态 -->
    <a-card class="status-card">
      <a-row :gutter="16">
        <a-col :span="8">
          <a-statistic title="连接状态">
            <template #value>
              <a-badge :status="connectionStatusBadge" :text="connectionStatusText" />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="8">
          <a-statistic title="认证状态">
            <template #value>
              <a-tag :color="isAuthenticated ? 'success' : 'warning'">
                {{ isAuthenticated ? '已认证' : '未认证' }}
              </a-tag>
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="8">
          <a-statistic title="收到消息数" :value="messageCount" />
        </a-col>
      </a-row>
    </a-card>

    <!-- 功能选项卡 -->
    <a-tabs v-model:active-key="activeTab" type="card">
      <!-- 连接配置 -->
      <a-tab-pane key="connection" tab="连接配置">
        <a-card title="WebSocket 连接配置" class="config-card">
          <a-form :model="connectionForm" layout="vertical">
            <a-row :gutter="16">
              <a-col :span="16">
                <a-form-item label="WebSocket URL">
                  <a-input v-model:value="connectionForm.url" placeholder="例如: ws://127.0.0.1:8000/ws/external"
                    :disabled="isConnected" />
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="认证 Token">
                  <a-input-password v-model:value="connectionForm.token" placeholder="输入认证 Token"
                    :disabled="isConnected" />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item>
              <a-space>
                <a-button v-if="!isConnected" type="primary" :loading="connecting" @click="connect">
                  <template #icon>
                    <ApiOutlined />
                  </template>
                  连接
                </a-button>
                <a-button v-else danger @click="disconnect">
                  <template #icon>
                    <DisconnectOutlined />
                  </template>
                  断开连接
                </a-button>
                <a-button v-if="isConnected && !isAuthenticated" type="primary" @click="authenticate">
                  <template #icon>
                    <SafetyOutlined />
                  </template>
                  发送认证
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 发送消息 -->
      <a-tab-pane key="send" tab="发送消息">
        <a-card title="发送消息" class="config-card">
          <a-form :model="messageForm" layout="vertical">
            <a-row :gutter="16">
              <a-col :span="8">
                <a-form-item label="消息类型">
                  <a-select v-model:value="messageForm.type">
                    <a-select-option value="ping">ping (心跳)</a-select-option>
                    <a-select-option value="auth">auth (认证)</a-select-option>
                    <a-select-option value="message">message (消息)</a-select-option>
                    <a-select-option value="custom">custom (自定义)</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="消息子类型 (msgtype)">
                  <a-select v-model:value="messageForm.msgtype" :disabled="messageForm.type !== 'message'">
                    <a-select-option value="text">text</a-select-option>
                    <a-select-option value="html">html</a-select-option>
                    <a-select-option value="picture">picture</a-select-option>
                  </a-select>
                </a-form-item>
              </a-col>
              <a-col :span="8">
                <a-form-item label="用户 ID">
                  <a-input v-model:value="messageForm.userId" placeholder="可选"
                    :disabled="messageForm.type !== 'message'" />
                </a-form-item>
              </a-col>
            </a-row>

            <a-row :gutter="16">
              <a-col :span="24">
                <a-form-item label="消息内容">
                  <a-textarea v-model:value="messageForm.message" :rows="4"
                    placeholder="输入消息内容（如果选择自定义类型，请输入完整的 JSON 对象）" />
                </a-form-item>
              </a-col>
            </a-row>

            <a-form-item>
              <a-space>
                <a-button type="primary" :disabled="!isConnected" @click="sendMessage">
                  <template #icon>
                    <SendOutlined />
                  </template>
                  发送消息
                </a-button>
                <a-button @click="resetMessageForm">
                  <template #icon>
                    <ClearOutlined />
                  </template>
                  重置
                </a-button>
              </a-space>
            </a-form-item>
          </a-form>
        </a-card>
      </a-tab-pane>

      <!-- 快捷操作 -->
      <a-tab-pane key="quick" tab="快捷操作">
        <a-card title="快捷操作" class="config-card">
          <a-space wrap>
            <a-button :disabled="!isConnected" @click="sendPing">
              <template #icon>
                <ThunderboltOutlined />
              </template>
              发送 Ping
            </a-button>
            <a-button :disabled="!isConnected" @click="sendTestMessage">
              <template #icon>
                <MessageOutlined />
              </template>
              发送测试消息
            </a-button>
            <a-button danger @click="clearMessages">
              <template #icon>
                <DeleteOutlined />
              </template>
              清空消息记录
            </a-button>
          </a-space>
        </a-card>
      </a-tab-pane>
    </a-tabs>

    <!-- 消息记录 -->
    <a-card title="消息记录" class="messages-card">
      <template #extra>
        <a-space>
          <a-switch v-model:checked="autoScroll" checked-children="自动滚动" un-checked-children="手动滚动" />
          <a-tag color="blue">{{ messages.length }} 条消息</a-tag>
        </a-space>
      </template>

      <div ref="messageContainer" class="message-container">
        <div v-for="(msg, index) in messages" :key="index" class="message-item" :class="msg.direction">
          <div class="message-meta">
            <span class="message-time">{{ msg.time }}</span>
            <a-tag :color="msg.direction === 'sent' ? 'blue' : 'green'" size="small">
              {{ msg.direction === 'sent' ? '发送' : '接收' }}
            </a-tag>
          </div>
          <pre class="message-content">{{ formatJson(msg.data) }}</pre>
        </div>
        <a-empty v-if="messages.length === 0" description="暂无消息记录" />
      </div>
    </a-card>
  </div>
</template>

<script lang="ts" setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import {
  ApiOutlined,
  DisconnectOutlined,
  SafetyOutlined,
  SendOutlined,
  ClearOutlined,
  ThunderboltOutlined,
  MessageOutlined,
  DeleteOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

// 连接状态
const connecting = ref(false)
const isConnected = ref(false)
const isAuthenticated = ref(false)
const messageCount = ref(0)
const autoScroll = ref(true)
const activeTab = ref('connection')

// WebSocket 实例
let ws: WebSocket | null = null

// 连接配置表单
const connectionForm = ref({
  url: 'ws://127.0.0.1:8000/ws/external',
  token: '',
})

// 消息表单
const messageForm = ref({
  type: 'message' as 'ping' | 'auth' | 'message' | 'custom',
  msgtype: 'text' as 'text' | 'html' | 'picture',
  userId: '',
  message: '',
})

// 消息记录
interface MessageRecord {
  time: string
  direction: 'sent' | 'received'
  data: any
}
const messages = ref<MessageRecord[]>([])
const messageContainer = ref<HTMLElement | null>(null)

// 连接状态显示
const connectionStatusBadge = computed(() => {
  if (connecting.value) return 'processing'
  if (isConnected.value) return 'success'
  return 'default'
})

const connectionStatusText = computed(() => {
  if (connecting.value) return '连接中...'
  if (isConnected.value) return '已连接'
  return '未连接'
})

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

// 获取当前时间字符串
function getCurrentTime(): string {
  const now = new Date()
  return (
    now.toLocaleTimeString('zh-CN', { hour12: false }) +
    '.' +
    String(now.getMilliseconds()).padStart(3, '0')
  )
}

// 添加消息记录
function addMessage(direction: 'sent' | 'received', data: any) {
  messages.value.push({
    time: getCurrentTime(),
    direction,
    data,
  })
  if (direction === 'received') {
    messageCount.value++
  }
  // 自动滚动到底部
  if (autoScroll.value) {
    nextTick(() => {
      if (messageContainer.value) {
        messageContainer.value.scrollTop = messageContainer.value.scrollHeight
      }
    })
  }
}

// 连接 WebSocket
function connect() {
  if (!connectionForm.value.url) {
    message.error('请输入 WebSocket URL')
    return
  }

  connecting.value = true

  try {
    ws = new WebSocket(connectionForm.value.url)

    ws.onopen = () => {
      connecting.value = false
      isConnected.value = true
      message.success('WebSocket 连接成功')
      addMessage('received', { event: 'connected', message: '连接已建立' })
    }

    ws.onmessage = event => {
      try {
        const data = JSON.parse(event.data)
        addMessage('received', data)

        // 检查认证结果
        if (data.type === 'auth_result' && data.success) {
          isAuthenticated.value = true
          message.success('认证成功')
        }
      } catch {
        addMessage('received', event.data)
      }
    }

    ws.onerror = error => {
      connecting.value = false
      message.error('WebSocket 连接错误')
      addMessage('received', { event: 'error', message: '连接错误' })
      console.error('WebSocket error:', error)
    }

    ws.onclose = event => {
      connecting.value = false
      isConnected.value = false
      isAuthenticated.value = false
      message.info('WebSocket 连接已关闭')
      addMessage('received', {
        event: 'closed',
        code: event.code,
        reason: event.reason || '连接已关闭',
      })
      ws = null
    }
  } catch (error) {
    connecting.value = false
    message.error('创建 WebSocket 连接失败')
    console.error('WebSocket creation error:', error)
  }
}

// 断开连接
function disconnect() {
  if (ws) {
    ws.close(1000, '用户主动断开')
  }
}

// 发送认证
function authenticate() {
  if (!ws || !isConnected.value) {
    message.error('请先连接 WebSocket')
    return
  }

  const authMessage = {
    type: 'auth',
    token: connectionForm.value.token,
  }

  ws.send(JSON.stringify(authMessage))
  addMessage('sent', authMessage)
}

// 发送消息
function sendMessage() {
  if (!ws || !isConnected.value) {
    message.error('请先连接 WebSocket')
    return
  }

  let messageData: any

  if (messageForm.value.type === 'custom') {
    try {
      messageData = JSON.parse(messageForm.value.message)
    } catch {
      message.error('自定义消息必须是有效的 JSON 格式')
      return
    }
  } else if (messageForm.value.type === 'ping') {
    messageData = { type: 'ping' }
  } else if (messageForm.value.type === 'auth') {
    messageData = {
      type: 'auth',
      token: connectionForm.value.token,
    }
  } else {
    messageData = {
      type: messageForm.value.type,
      msgtype: messageForm.value.msgtype,
      user_id: messageForm.value.userId || undefined,
      message: messageForm.value.message,
    }
  }

  ws.send(JSON.stringify(messageData))
  addMessage('sent', messageData)
}

// 发送 Ping
function sendPing() {
  if (!ws || !isConnected.value) return
  const pingMessage = { type: 'ping' }
  ws.send(JSON.stringify(pingMessage))
  addMessage('sent', pingMessage)
}

// 发送测试消息
function sendTestMessage() {
  if (!ws || !isConnected.value) return
  const testMessage = {
    type: 'message',
    msgtype: 'text',
    message: `测试消息 - ${getCurrentTime()}`,
  }
  ws.send(JSON.stringify(testMessage))
  addMessage('sent', testMessage)
}

// 清空消息记录
function clearMessages() {
  messages.value = []
  messageCount.value = 0
}

// 重置消息表单
function resetMessageForm() {
  messageForm.value = {
    type: 'message',
    msgtype: 'text',
    userId: '',
    message: '',
  }
}

// 组件卸载时断开连接
onUnmounted(() => {
  if (ws) {
    ws.close()
  }
})

// 监听连接状态变化
watch(isConnected, connected => {
  if (!connected) {
    isAuthenticated.value = false
  }
})
</script>

<style scoped>
.ws-debug-page {
  max-width: 1400px;
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
  margin: 4px 0;
  color: var(--ant-color-text-secondary);
}

.status-card {
  margin-bottom: 24px;
}

.config-card {
  margin-bottom: 16px;
}

.messages-card {
  margin-top: 24px;
}

.message-container {
  max-height: 500px;
  overflow-y: auto;
  padding: 12px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
}

.message-item {
  margin-bottom: 12px;
  padding: 12px;
  border-radius: 6px;
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

.message-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.message-time {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  font-family: monospace;
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

:deep(.ant-tabs) {
  margin-bottom: 24px;
}
</style>

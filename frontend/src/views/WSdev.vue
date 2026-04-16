<template>
  <div class="ws-debug-page">
    <!-- 椤甸潰鏍囬 -->
    <div class="page-header">
      <h1>WebSocket 瀹㈡埛绔皟璇?/h1>
      <p class="description">鍚庣浣滀负 WebSocket 瀹㈡埛绔繛鎺ュ閮ㄦ湇鍔″櫒锛堝 Koishi锛夎繘琛岃皟璇?/p>
    </div>

    <!-- 瀹㈡埛绔瑙?-->
    <a-card class="overview-card" :bordered="false">
      <a-row :gutter="16">
        <a-col :span="6">
          <a-statistic title="瀹㈡埛绔€绘暟" :value="clientList.length">
            <template #prefix>
              <ApiOutlined />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic title="宸茶繛鎺? :value="connectedCount">
            <template #prefix>
              <CheckCircleOutlined style="color: #52c41a" />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic title="鏈繛鎺? :value="clientList.length - connectedCount">
            <template #prefix>
              <CloseCircleOutlined style="color: #ff4d4f" />
            </template>
          </a-statistic>
        </a-col>
        <a-col :span="6">
          <a-statistic title="娑堟伅鎬绘暟" :value="totalMessageCount">
            <template #prefix>
              <MessageOutlined />
            </template>
          </a-statistic>
        </a-col>
      </a-row>
    </a-card>

    <a-row :gutter="16" class="main-content">
      <!-- 宸︿晶锛氬鎴风绠＄悊 -->
      <a-col :span="10">
        <a-card title="瀹㈡埛绔鐞? :bordered="false" class="client-card">
          <template #extra>
            <a-space>
              <a-button type="primary" size="small" @click="showCreateModal">
                <template #icon><PlusOutlined /></template>
                鏂板缓瀹㈡埛绔?
              </a-button>
              <a-button size="small" @click="refreshClientList">
                <template #icon><ReloadOutlined /></template>
              </a-button>
            </a-space>
          </template>

          <!-- 瀹㈡埛绔垪琛?-->
          <div class="client-list">
            <a-empty v-if="clientList.length === 0" description="鏆傛棤瀹㈡埛绔紝鐐瑰嚮涓婃柟鎸夐挳鍒涘缓" />
            <div
              v-for="client in sortedClientList"
              :key="client.name"
              class="client-item"
              :class="{ active: selectedClient === client.name, connected: client.is_connected, system: client.is_system }"
              @click="selectClient(client.name)"
            >
              <div class="client-info">
                <div class="client-name">
                  <a-badge :status="client.is_connected ? 'success' : 'default'" />
                  <LockOutlined v-if="client.is_system" style="margin-right: 4px; color: var(--ant-color-warning)" />
                  {{ client.name }}
                  <a-tag v-if="client.is_system" color="orange" size="small" style="margin-left: 4px">绯荤粺</a-tag>
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
                  杩炴帴
                </a-button>
                <a-button
                  v-else
                  type="link"
                  size="small"
                  danger
                  @click.stop="disconnectClient(client.name)"
                >
                  鏂紑
                </a-button>
                <a-button
                  v-if="!client.is_system"
                  type="link"
                  size="small"
                  danger
                  @click.stop="removeClient(client.name)"
                >
                  <DeleteOutlined />
                </a-button>
                <a-tooltip v-else title="绯荤粺瀹㈡埛绔笉鍙垹闄?>
                  <a-button
                    type="link"
                    size="small"
                    disabled
                  >
                    <DeleteOutlined />
                  </a-button>
                </a-tooltip>
              </div>
            </div>
          </div>
        </a-card>

        <!-- 鍙戦€佹秷鎭潰鏉?-->
        <a-card title="鍙戦€佹秷鎭? :bordered="false" class="send-card" style="margin-top: 16px">
          <a-form layout="vertical">
            <a-form-item label="娑堟伅绫诲瀷">
              <a-radio-group v-model:value="sendMode" button-style="solid">
                <a-radio-button value="formatted">鏍煎紡鍖栨秷鎭?/a-radio-button>
                <a-radio-button value="raw">鍘熷 JSON</a-radio-button>
                <a-radio-button value="auth">璁よ瘉娑堟伅</a-radio-button>
              </a-radio-group>
            </a-form-item>

            <!-- 鏍煎紡鍖栨秷鎭?-->
            <template v-if="sendMode === 'formatted'">
              <a-row :gutter="12">
                <a-col :span="12">
                  <a-form-item label="娑堟伅 ID">
                    <a-input v-model:value="formattedMessage.id" placeholder="Client" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="娑堟伅绫诲瀷">
                    <a-input v-model:value="formattedMessage.type" placeholder="command" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="娑堟伅鏁版嵁 (JSON)">
                <a-textarea
                  v-model:value="formattedMessage.data"
                  :rows="4"
                  placeholder='{"key": "value"}'
                />
              </a-form-item>
            </template>

            <!-- 鍘熷 JSON -->
            <template v-else-if="sendMode === 'raw'">
              <a-form-item label="JSON 娑堟伅">
                <a-textarea
                  v-model:value="rawMessage"
                  :rows="6"
                  placeholder='{"id": "Client", "type": "command", "data": {}}'
                />
              </a-form-item>
            </template>

            <!-- 璁よ瘉娑堟伅 -->
            <template v-else-if="sendMode === 'auth'">
              <a-row :gutter="12">
                <a-col :span="12">
                  <a-form-item label="璁よ瘉 Token">
                    <a-input-password v-model:value="authMessage.token" placeholder="杈撳叆 Token" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="璁よ瘉绫诲瀷">
                    <a-input v-model:value="authMessage.type" placeholder="auth" />
                  </a-form-item>
                </a-col>
              </a-row>
              <a-form-item label="棰濆鏁版嵁 (JSON, 鍙€?">
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
                鍙戦€佹秷鎭?
              </a-button>
            </a-form-item>
          </a-form>
        </a-card>
      </a-col>

      <!-- 鍙充晶锛氭秷鎭褰?-->
      <a-col :span="14">
        <a-card title="娑堟伅璁板綍" :bordered="false" class="message-card">
          <template #extra>
            <a-space>
              <a-switch
                v-model:checked="autoScroll"
                checked-children="鑷姩婊氬姩"
                un-checked-children="鎵嬪姩婊氬姩"
              />
              <a-select
                v-model:value="messageFilter"
                style="width: 120px"
                size="small"
              >
                <a-select-option value="all">鍏ㄩ儴娑堟伅</a-select-option>
                <a-select-option value="sent">浠呭彂閫?/a-select-option>
                <a-select-option value="received">浠呮帴鏀?/a-select-option>
              </a-select>
              <a-button size="small" danger @click="clearHistory">
                <template #icon><DeleteOutlined /></template>
                娓呯┖
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
                    {{ msg.direction === 'sent' ? '鍙戦€? : '鎺ユ敹' }}
                  </a-tag>
                  <span class="message-client">{{ msg.client }}</span>
                  <span class="message-time">{{ formatTime(msg.timestamp) }}</span>
                </div>
                <pre class="message-content">{{ formatJson(msg.data) }}</pre>
              </div>
            </template>
            <a-empty v-else description="鏆傛棤娑堟伅璁板綍" />
          </div>
        </a-card>
      </a-col>
    </a-row>

    <!-- 鍒涘缓瀹㈡埛绔脊绐?-->
    <a-modal
      v-model:open="createModalVisible"
      title="鍒涘缓 WebSocket 瀹㈡埛绔?
      @ok="createClient"
      :confirmLoading="creating"
    >
      <a-form layout="vertical">
        <a-form-item label="瀹㈡埛绔悕绉? required>
          <a-input
            v-model:value="createForm.name"
            placeholder="杈撳叆瀹㈡埛绔悕绉帮紝濡?Koishi"
          />
        </a-form-item>
        <a-form-item label="鏈嶅姟鍣?URL" required>
          <a-input
            v-model:value="createForm.url"
            placeholder="ws://localhost:5140/AUTO_MAS"
          />
        </a-form-item>
        <a-row :gutter="12">
          <a-col :span="12">
            <a-form-item label="蹇冭烦闂撮殧锛堢锛?>
              <a-input-number
                v-model:value="createForm.pingInterval"
                :min="1"
                :max="300"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="蹇冭烦瓒呮椂锛堢锛?>
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
            <a-form-item label="閲嶈繛闂撮殧锛堢锛?>
              <a-input-number
                v-model:value="createForm.reconnectInterval"
                :min="1"
                :max="60"
                style="width: 100%"
              />
            </a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="鏈€澶ч噸杩炴鏁?>
              <a-input-number
                v-model:value="createForm.maxReconnectAttempts"
                :min="-1"
                style="width: 100%"
              />
              <div class="form-tip">-1 琛ㄧず鏃犻檺閲嶈繛</div>
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
  LockOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { wsDebugApi } from '@/api'

// ============== 绫诲瀷瀹氫箟 ==============

interface ClientInfo {
  name: string
  url: string
  is_connected: boolean
  is_system: boolean
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

// ============== 鐘舵€佸畾涔?==============

// 瀹㈡埛绔垪琛?
const clientList = ref<ClientInfo[]>([])
const selectedClient = ref<string | null>(null)
const connectingClients = ref<Record<string, boolean>>({})

// 娑堟伅鐩稿叧
const messages = ref<MessageRecord[]>([])
const messageFilter = ref<'all' | 'sent' | 'received'>('all')
const autoScroll = ref(true)
const messageContainer = ref<HTMLElement | null>(null)

// 鍙戦€佹秷鎭?
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

// 鍒涘缓瀹㈡埛绔脊绐?
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

// 瀹炴椂 WebSocket 杩炴帴
let liveWs: WebSocket | null = null

// ============== 璁＄畻灞炴€?==============

const connectedCount = computed(() => {
  return clientList.value.filter((c) => c.is_connected).length
})

const totalMessageCount = computed(() => {
  return messages.value.length
})

// 鎺掑簭鍚庣殑瀹㈡埛绔垪琛細绯荤粺瀹㈡埛绔疆椤?
const sortedClientList = computed(() => {
  return [...clientList.value].sort((a, b) => {
    // 绯荤粺瀹㈡埛绔帓鍦ㄥ墠闈?
    if (a.is_system && !b.is_system) return -1
    if (!a.is_system && b.is_system) return 1
    // 鍚岀被鍨嬫寜鍚嶇О鎺掑簭
    return a.name.localeCompare(b.name)
  })
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

// ============== 鏂规硶 ==============

// 鏍煎紡鍖?JSON
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

// 鏍煎紡鍖栨椂闂存埑
function formatTime(timestamp: number): string {
  const date = new Date(timestamp * 1000)
  return (
    date.toLocaleTimeString('zh-CN', { hour12: false }) +
    '.' +
    String(date.getMilliseconds()).padStart(3, '0')
  )
}

// 鍒锋柊瀹㈡埛绔垪琛?
async function refreshClientList() {
  try {
    const response = await wsDebugApi.listClients()
    if (response.code === 200 && response.data) {
      clientList.value = response.data.clients || []
    }
  } catch (error: any) {
    console.error('鍒锋柊瀹㈡埛绔垪琛ㄥけ璐?', error)
  }
}

// 閫夋嫨瀹㈡埛绔?
function selectClient(name: string) {
  selectedClient.value = name
}

// 鏄剧ず鍒涘缓寮圭獥
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

// 璁板綍 API 璇锋眰鍒版秷鎭褰?
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

// 璁板綍 API 鍝嶅簲鍒版秷鎭褰?
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

// 鍒涘缓瀹㈡埛绔?
async function createClient() {
  if (!createForm.value.name) {
    message.error('璇疯緭鍏ュ鎴风鍚嶇О')
    return
  }
  if (!createForm.value.url) {
    message.error('璇疯緭鍏ユ湇鍔″櫒 URL')
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
    const response = await wsDebugApi.createClient(requestBody)
    logApiResponse('/api/ws_debug/client/create', response)

    if (response.code === 200) {
      message.success(`瀹㈡埛绔?[${createForm.value.name}] 鍒涘缓鎴愬姛`)
      createModalVisible.value = false
      await refreshClientList()
      selectedClient.value = createForm.value.name
    } else {
      message.error(response.message || '鍒涘缓澶辫触')
    }
  } catch (error: any) {
    message.error(error.message || '鍒涘缓澶辫触')
  } finally {
    creating.value = false
  }
}

// 杩炴帴瀹㈡埛绔?
async function connectClient(name: string) {
  connectingClients.value[name] = true
  try {
    const requestBody = { name }
    logApiRequest('/api/ws_debug/client/connect', 'POST', requestBody)
    const response = await wsDebugApi.connectClient(requestBody)
    logApiResponse('/api/ws_debug/client/connect', response)

    if (response.code === 200) {
      message.success(`瀹㈡埛绔?[${name}] 杩炴帴鎴愬姛`)
      await refreshClientList()
    } else {
      message.error(response.message || '杩炴帴澶辫触')
    }
  } catch (error: any) {
    message.error(error.message || '杩炴帴澶辫触')
  } finally {
    connectingClients.value[name] = false
  }
}

// 鏂紑瀹㈡埛绔?
async function disconnectClient(name: string) {
  try {
    const requestBody = { name }
    logApiRequest('/api/ws_debug/client/disconnect', 'POST', requestBody)
    const response = await wsDebugApi.disconnectClient(requestBody)
    logApiResponse('/api/ws_debug/client/disconnect', response)

    if (response.code === 200) {
      message.success(`瀹㈡埛绔?[${name}] 宸叉柇寮€`)
      await refreshClientList()
    } else {
      message.error(response.message || '鏂紑澶辫触')
    }
  } catch (error: any) {
    message.error(error.message || '鏂紑澶辫触')
  }
}

// 鍒犻櫎瀹㈡埛绔?
async function removeClient(name: string) {
  try {
    const requestBody = { name }
    logApiRequest('/api/ws_debug/client/remove', 'POST', requestBody)
    const response = await wsDebugApi.removeClient(requestBody)
    logApiResponse('/api/ws_debug/client/remove', response)

    if (response.code === 200) {
      message.success(`瀹㈡埛绔?[${name}] 宸插垹闄)
      if (selectedClient.value === name) {
        selectedClient.value = null
      }
      await refreshClientList()
    } else {
      message.error(response.message || '鍒犻櫎澶辫触')
    }
  } catch (error: any) {
    message.error(error.message || '鍒犻櫎澶辫触')
  }
}

// 鍙戦€佹秷鎭?
async function sendMessage() {
  if (!selectedClient.value) {
    message.error('璇峰厛閫夋嫨涓€涓鎴风')
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
        message.error('娑堟伅鏁版嵁涓嶆槸鏈夋晥鐨?JSON')
        return
      }

      const jsonRequestBody = {
        name: selectedClient.value,
        msg_id: formattedMessage.value.id,
        msg_type: formattedMessage.value.type,
        data,
      }
      logApiRequest('/api/ws_debug/message/send_json', 'POST', jsonRequestBody)
      response = await wsDebugApi.sendJson(jsonRequestBody)
      logApiResponse('/api/ws_debug/message/send_json', response)
    } else if (sendMode.value === 'raw') {
      let messageObj: any
      try {
        messageObj = JSON.parse(rawMessage.value)
      } catch {
        message.error('娑堟伅鍐呭涓嶆槸鏈夋晥鐨?JSON')
        return
      }

      const rawRequestBody = {
        name: selectedClient.value,
        message: messageObj,
      }
      logApiRequest('/api/ws_debug/message/send', 'POST', rawRequestBody)
      response = await wsDebugApi.sendMessage(rawRequestBody)
      logApiResponse('/api/ws_debug/message/send', response)
    } else if (sendMode.value === 'auth') {
      if (!authMessage.value.token) {
        message.error('璇疯緭鍏ヨ璇?Token')
        return
      }

      let extraData: any = undefined
      if (authMessage.value.extra) {
        try {
          extraData = JSON.parse(authMessage.value.extra)
        } catch {
          message.error('棰濆鏁版嵁涓嶆槸鏈夋晥鐨?JSON')
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
      response = await wsDebugApi.sendAuth(authRequestBody)
      logApiResponse('/api/ws_debug/message/auth', response)
    }

    if (response?.code === 200) {
      message.success('娑堟伅鍙戦€佹垚鍔?)
    } else {
      message.error(response?.message || '鍙戦€佸け璐?)
    }
  } catch (error: any) {
    message.error(error.message || '鍙戦€佸け璐?)
  } finally {
    sending.value = false
  }
}

// 娓呯┖鍘嗗彶
async function clearHistory() {
  try {
    await wsDebugApi.clearHistory({
      name: selectedClient.value || undefined,
    })
    messages.value = []
    message.success('宸叉竻绌烘秷鎭巻鍙?)
  } catch (error: any) {
    message.error('娓呯┖澶辫触')
  }
}

// 娣诲姞娑堟伅
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

// 寤虹珛瀹炴椂 WebSocket 杩炴帴
function connectLiveWs() {
  const wsUrl = `ws://${window.location.host}/api/ws_debug/live`

  try {
    liveWs = new WebSocket(wsUrl)

    liveWs.onopen = () => {
      console.log('瀹炴椂娑堟伅杩炴帴宸插缓绔?)
    }

    liveWs.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === 'init') {
          // 鍒濆鍖栧鎴风鍒楄〃
          clientList.value = data.clients || []
        } else if (data.type === 'message') {
          // 娣诲姞娑堟伅璁板綍
          addMessage({
            direction: data.direction,
            timestamp: data.timestamp,
            data: data.data,
            client: data.client,
          })
        } else if (data.type === 'event') {
          // 澶勭悊浜嬩欢
          if (data.event === 'connected' || data.event === 'disconnected') {
            refreshClientList()
          }
        }
      } catch (error) {
        console.error('瑙ｆ瀽瀹炴椂娑堟伅澶辫触:', error)
      }
    }

    liveWs.onerror = (error) => {
      console.error('瀹炴椂娑堟伅杩炴帴閿欒:', error)
    }

    liveWs.onclose = () => {
      console.log('瀹炴椂娑堟伅杩炴帴宸插叧闂?)
      liveWs = null
      // 5绉掑悗閲嶈繛
      setTimeout(connectLiveWs, 5000)
    }
  } catch (error) {
    console.error('鍒涘缓瀹炴椂娑堟伅杩炴帴澶辫触:', error)
  }
}

// 鏂紑瀹炴椂 WebSocket
function disconnectLiveWs() {
  if (liveWs) {
    liveWs.close()
    liveWs = null
  }
}

// 鍔犺浇鍘嗗彶娑堟伅
async function loadHistory() {
  try {
    const response = await wsDebugApi.getHistory()
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
      // 鎸夋椂闂存帓搴?
      messages.value.sort((a, b) => a.timestamp - b.timestamp)
    }
  } catch (error: any) {
    console.error('鍔犺浇鍘嗗彶娑堟伅澶辫触:', error)
  }
}

// 椤甸潰鍔犺浇鏃?
onMounted(async () => {
  await refreshClientList()
  await loadHistory()
  connectLiveWs()
})

// 椤甸潰鍗歌浇鏃?
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

.client-item.system {
  background: var(--ant-color-warning-bg);
}

.client-item.system:hover {
  background: var(--ant-color-warning-bg-hover);
}

.client-item.system.active {
  background: var(--ant-color-warning-bg);
  border: 1px solid var(--ant-color-warning);
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


<template>
  <!-- 加载状态 -->
  <div v-if="loading" class="loading-container">
    <a-spin size="large" tip="加载中，请稍候..." />
  </div>

  <!-- 主要内容 -->
  <div v-else class="queue-main">
    <!-- 页面头部 -->
    <div class="queue-header">
      <div class="header-left">
        <h1 class="page-title">调度队列</h1>
      </div>
      <div class="header-actions">
        <a-space size="middle">
          <a-button
            type="primary"
            size="large"
            @click="handleAddQueue"
          >
            <template #icon>
              <PlusOutlined />
            </template>
            新建队列
          </a-button>

          <a-popconfirm
            v-if="queueList.length > 0"
            title="确定要删除这个队列吗？"
            ok-text="确定"
            cancel-text="取消"
            @confirm="handleRemoveQueue(activeQueueId)"
          >
            <a-button danger size="large" :disabled="!activeQueueId">
              <template #icon>
                <DeleteOutlined />
              </template>
              删除当前队列
            </a-button>
          </a-popconfirm>

          <a-button size="large" @click="handleRefresh">
            <template #icon>
              <ReloadOutlined />
            </template>
            刷新
          </a-button>
        </a-space>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!queueList.length || !currentQueueData" class="empty-state">
      <div class="empty-content">
        <div class="empty-image-container">
          <img src="@/assets/NoData.png" alt="暂无数据" class="empty-image" />
        </div>
        <div class="empty-text-content">
          <h3 class="empty-title">暂无队列</h3>
          <p class="empty-description">您还没有创建任何队列</p>
        </div>
      </div>
    </div>

    <!-- 队列内容 -->
    <div v-else class="queue-content">
      <!-- 队列选择卡片 -->
      <a-card class="queue-selector-card" :bordered="false">
        <template #title>
          <div class="card-title">
            <span>队列选择</span>
            <a-tag :color="queueList.length > 0 ? 'success' : 'default'">
              {{ queueList.length }} 个队列
            </a-tag>
          </div>
        </template>

        <div class="queue-selection-container">
          <!-- 队列按钮组 -->
          <div class="queue-buttons-container">
            <a-space wrap size="middle">
              <a-button
                v-for="queue in queueList"
                :key="queue.id"
                :type="activeQueueId === queue.id ? 'primary' : 'default'"
                size="large"
                @click="onQueueChange(queue.id)"
                class="queue-button"
              >
                {{ queue.name }}
              </a-button>
            </a-space>
          </div>
        </div>
      </a-card>

      <!-- 队列配置卡片 -->
      <a-card class="queue-config-card" :bordered="false">
        <template #title>
          <div class="queue-title-container">
            <div v-if="!isEditingQueueName" class="queue-title-display">
              <span class="queue-title-text">{{ currentQueueName || '队列配置' }}</span>
              <a-button type="text" size="small" @click="startEditQueueName" class="queue-edit-btn">
                <template #icon>
                  <EditOutlined />
                </template>
              </a-button>
            </div>
            <div v-else class="queue-title-edit">
              <a-input
                v-model:value="currentQueueName"
                placeholder="请输入队列名称"
                size="small"
                class="queue-title-input"
                @blur="finishEditQueueName"
                @pressEnter="finishEditQueueName"
                :maxlength="50"
                ref="queueNameInputRef"
              />
            </div>
          </div>
        </template>

        <!-- 队列开关配置 -->
        <div class="config-section">
          <div class="queue-switches">
            <div class="switch-item">
              <div class="switch-label">
                <span class="switch-title">启动时运行</span>
                <span class="switch-description">程序启动时自动运行此队列</span>
              </div>
              <a-switch
                v-model:checked="currentStartUpEnabled"
                @change="onQueueSwitchChange"
                size="default"
              />
            </div>
            <div class="switch-item">
              <div class="switch-label">
                <span class="switch-title">定时运行</span>
                <span class="switch-description">按照设定的时间自动运行此队列</span>
              </div>
              <a-switch
                v-model:checked="currentTimeEnabled"
                @change="onQueueSwitchChange"
                size="default"
              />
            </div>
          </div>
        </div>

        <!-- 完成后操作配置 -->
        <div class="config-section">
          <div class="after-accomplish-settings">
            <div class="setting-item">
              <div class="setting-label">
                <span class="setting-title">完成后操作</span>
                <span class="setting-description">队列完成后执行的操作</span>
              </div>
              <a-select
                v-model:value="currentAfterAccomplish"
                @change="onAfterAccomplishChange"
                size="default"
                :options="afterAccomplishOptions"
                placeholder="请选择操作"
                style="min-width: 200px"
              />
            </div>
          </div>
        </div>
        <a-divider />

        <!-- 定时项管理 -->
        <div class="config-section">
          <TimeSetManager
            v-if="activeQueueId && currentQueueData"
            :queue-id="activeQueueId"
            :time-sets="currentTimeSets"
            @refresh="refreshTimeSets"
          />
        </div>

        <!-- 队列项管理 -->
        <div class="config-section">
          <QueueItemManager
            v-if="activeQueueId && currentQueueData"
            :queue-id="activeQueueId"
            :queue-items="currentQueueItems"
            @refresh="refreshQueueItems"
          />
        </div>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { Service } from '@/api'
import TimeSetManager from '@/components/queue/TimeSetManager.vue'
import QueueItemManager from '@/components/queue/QueueItemManager.vue'

// 队列列表和当前选中的队列
const queueList = ref<Array<{ id: string; name: string }>>([])
const activeQueueId = ref<string>('')
const currentQueueData = ref<Record<string, any> | null>(null)

// 当前队列的名称和状态
const currentQueueName = ref<string>('')
const currentQueueEnabled = ref<boolean>(true)
// 新增：启动时运行和定时运行的开关状态
const currentStartUpEnabled = ref<boolean>(false)
const currentTimeEnabled = ref<boolean>(false)
// 新增：完成后操作状态
const currentAfterAccomplish = ref<string>('NoAction')
// 队列名称编辑状态
const isEditingQueueName = ref<boolean>(false)

// 完成后操作选项
const afterAccomplishOptions = [
  { label: '无操作', value: 'NoAction' },
  { label: '退出软件', value: 'KillSelf' },
  { label: '睡眠', value: 'Sleep' },
  { label: '休眠', value: 'Hibernate' },
  { label: '关机', value: 'Shutdown' },
  { label: '强制关机', value: 'ShutdownForce' },
]

// 当前队列的定时项和队列项
const currentTimeSets = ref<any[]>([])
const currentQueueItems = ref<any[]>([])

const loading = ref(true)

// 获取队列列表
const fetchQueues = async () => {
  loading.value = true
  try {
    const response = await Service.getQueuesApiQueueGetPost({})
    if (response.code === 200) {
      // 处理队列数据
      console.log('API Response:', response) // 调试日志

      if (response.index && response.index.length > 0) {
        queueList.value = response.index.map((item: any, index: number) => {
          try {
            // API响应格式: {"uid": "xxx", "type": "QueueConfig"}
            const queueId = item.uid
            const queueName = response.data[queueId]?.Info?.Name || `新调度队列`
            console.log('Queue ID:', queueId, 'Name:', queueName, 'Type:', typeof queueId) // 调试日志
            return {
              id: queueId,
              name: queueName,
            }
          } catch (itemError) {
            console.warn('解析队列项失败:', itemError, item)
            return {
              id: `queue_${index}`,
              name: `新调度队列`,
            }
          }
        })

        // 如果有队列且没有选中的队列，默认选中第一个
        if (queueList.value.length > 0 && !activeQueueId.value) {
          activeQueueId.value = queueList.value[0].id
          console.log('Selected queue ID:', activeQueueId.value) // 调试日志
          // 使用nextTick确保DOM更新后再加载数据
          nextTick(() => {
            loadQueueData(activeQueueId.value).catch(error => {
              console.error('加载队列数据失败:', error)
            })
          })
        }
      } else {
        console.log('No queues found in response') // 调试日志
        queueList.value = []
        currentQueueData.value = null
      }
    } else {
      console.error('API响应错误:', response)
      queueList.value = []
      currentQueueData.value = null
    }
  } catch (error) {
    console.error('获取队列列表失败:', error)
    queueList.value = []
    currentQueueData.value = null
  } finally {
    loading.value = false
  }
}

// 加载队列数据
const loadQueueData = async (queueId: string) => {
  if (!queueId) return

  try {
    const response = await Service.getQueuesApiQueueGetPost({})
    currentQueueData.value = response.data

    // 根据API响应数据更新队列信息
    if (response.data && response.data[queueId]) {
      const queueData = response.data[queueId]

      // 更新队列名称和状态
      const currentQueue = queueList.value.find(queue => queue.id === queueId)
      if (currentQueue) {
        currentQueueName.value = currentQueue.name
      }
      currentQueueEnabled.value = queueData.enabled ?? true

      // 使用nextTick确保DOM更新后再加载数据
      await nextTick()

      // 更新开关状态 - 从API响应中获取
      currentStartUpEnabled.value = queueData.Info?.StartUpEnabled ?? false
      currentTimeEnabled.value = queueData.Info?.TimeEnabled ?? false
      // 更新完成后操作状态 - 从API响应中获取
      currentAfterAccomplish.value = queueData.Info?.AfterAccomplish ?? 'NoAction'
      await new Promise(resolve => setTimeout(resolve, 50))

      // 加载定时项和队列项数据 - 添加错误处理
      try {
        await refreshTimeSets()
      } catch (timeError) {
        console.error('刷新定时项失败:', timeError)
      }

      try {
        await refreshQueueItems()
      } catch (itemError) {
        console.error('刷新队列项失败:', itemError)
      }
    }
  } catch (error) {
    console.error('加载队列数据失败:', error)
    // 不显示错误消息，避免干扰用户体验
  }
}

// 刷新定时项数据
const refreshTimeSets = async () => {
  if (!activeQueueId.value) {
    currentTimeSets.value = []
    return
  }

  try {
    // 使用专门的定时项API获取数据
    const response = await Service.getTimeSetApiQueueTimeGetPost({
      queueId: activeQueueId.value,
    })

    if (response.code !== 200) {
      console.error('获取定时项数据失败:', response)
      currentTimeSets.value = []
      return
    }

    const timeSets: any[] = []

    // 处理定时项数据
    if (response.index && Array.isArray(response.index)) {
      response.index.forEach((item: any) => {
        try {
          const timeSetId = item.uid
          if (!timeSetId || !response.data || !response.data[timeSetId]) return

          const timeSetData = response.data[timeSetId]
          if (timeSetData?.Info) {
            // 解析时间字符串 "HH:mm"
            const originalTimeString = timeSetData.Info.Set || timeSetData.Info.Time || '00:00'
            const [hours = 0, minutes = 0] = originalTimeString.split(':').map(Number)

            // 创建标准化的时间字符串
            const validHours = Math.max(0, Math.min(23, hours))
            const validMinutes = Math.max(0, Math.min(59, minutes))
            const timeString = `${validHours.toString().padStart(2, '0')}:${validMinutes.toString().padStart(2, '0')}`

            timeSets.push({
              id: timeSetId,
              time: timeString,
              enabled: Boolean(timeSetData.Info.Enabled),
              description: timeSetData.Info?.Description || '',
            })
          }
        } catch (itemError) {
          console.warn('解析单个定时项失败:', itemError, item)
        }
      })
    }

    // 使用nextTick确保数据更新不会导致渲染问题
    await nextTick()
    currentTimeSets.value = [...timeSets]
    console.log('刷新后的定时项数据:', timeSets) // 调试日志
  } catch (error) {
    console.error('刷新定时项列表失败:', error)
    currentTimeSets.value = []
    // 不显示错误消息，避免干扰用户
  }
}

// 刷新队列项数据
const refreshQueueItems = async () => {
  if (!activeQueueId.value) {
    currentQueueItems.value = []
    return
  }

  try {
    // 使用专门的队列项API获取数据
    const response = await Service.getItemApiQueueItemGetPost({
      queueId: activeQueueId.value,
    })

    if (response.code !== 200) {
      console.error('获取队列项数据失败:', response)
      currentQueueItems.value = []
      return
    }

    const queueItems: any[] = []

    // 处理队列项数据
    if (response.index && Array.isArray(response.index)) {
      response.index.forEach((item: any) => {
        try {
          const queueItemId = item.uid
          if (!queueItemId || !response.data || !response.data[queueItemId]) return

          const queueItemData = response.data[queueItemId]
          if (queueItemData?.Info) {
            queueItems.push({
              id: queueItemId,
              script: queueItemData.Info.ScriptId || '',
            })
          }
        } catch (itemError) {
          console.warn('解析单个队列项失败:', itemError, item)
        }
      })
    }

    // 使用nextTick确保数据更新不会导致渲染问题
    await nextTick()
    currentQueueItems.value = [...queueItems]
    console.log('刷新后的队列项数据:', queueItems) // 调试日志
  } catch (error) {
    console.error('刷新队列项列表失败:', error)
    currentQueueItems.value = []
    // 不显示错误消息，避免干扰用户
  }
}

// 队列名称编辑失焦处理
const onQueueNameBlur = () => {
  // 当用户编辑完队列名称后，更新按钮显示的名称
  if (activeQueueId.value) {
    const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
    if (currentQueue) {
      currentQueue.name =
        currentQueueName.value || `队列 ${queueList.value.indexOf(currentQueue) + 1}`
    }
  }
}

// 开始编辑队列名称
const startEditQueueName = () => {
  isEditingQueueName.value = true
  // 使用 nextTick 确保 DOM 更新后再获取焦点
  setTimeout(() => {
    const input = document.querySelector('.queue-title-input input') as HTMLInputElement
    if (input) {
      input.focus()
      input.select()
    }
  }, 100)
}

// 完成编辑队列名称
const finishEditQueueName = () => {
  isEditingQueueName.value = false
  onQueueNameBlur()
}

// 队列开关切换处理
const onQueueSwitchChange = () => {
  // 开关切换时自动保存
  autoSave()
}

// 完成后操作切换处理
const onAfterAccomplishChange = () => {
  // 完成后操作切换时自动保存
  autoSave()
}

// 队列状态切换处理
const onQueueStatusChange = () => {
  // 状态切换时自动保存
  autoSave()
}

// 添加队列
const handleAddQueue = async () => {
  try {
    const response = await Service.addQueueApiQueueAddPost()

    if (response.code === 200 && response.queueId) {
      const defaultName = '新队列'
      const newQueue = {
        id: response.queueId,
        name: defaultName,
      }
      queueList.value.push(newQueue)
      activeQueueId.value = newQueue.id

      // 设置默认名称到输入框中
      currentQueueName.value = defaultName
      currentQueueEnabled.value = true

      await loadQueueData(newQueue.id)

      // 显示名称修改提示
      message.info('已创建新的调度队列，建议您修改为更有意义的名称', 3)
    } else {
      message.error('队列创建失败: ' + (response.message || '未知错误'))
    }
  } catch (error) {
    console.error('添加队列失败:', error)
    message.error('添加队列失败: ' + (error?.message || '网络错误'))
  }
}

// 删除队列
const handleRemoveQueue = async (queueId: string) => {
  try {
    const response = await Service.deleteQueueApiQueueDeletePost({ queueId })

    if (response.code === 200) {
      const index = queueList.value.findIndex(queue => queue.id === queueId)
      if (index > -1) {
        queueList.value.splice(index, 1)
        if (activeQueueId.value === queueId) {
          activeQueueId.value = queueList.value[0]?.id || ''
          if (activeQueueId.value) {
            await loadQueueData(activeQueueId.value)
          } else {
            currentQueueData.value = null
          }
        }
      }
      message.success('队列删除成功')
    } else {
      message.error('删除队列失败: ' + (response.message || '未知错误'))
    }
  } catch (error) {
    console.error('删除队列失败:', error)
    message.error('删除队列失败: ' + (error?.message || '网络错误'))
  }
}

// 队列切换
const onQueueChange = async (queueId: string) => {
  if (!queueId) return

  try {
    // 立即更新activeQueueId以确保按钮高亮切换
    activeQueueId.value = queueId
    // 清空当前数据，避免渲染问题
    currentTimeSets.value = []
    currentQueueItems.value = []

    await loadQueueData(queueId)
  } catch (error) {
    console.error('队列切换失败:', error)
  }
}

// 自动保存处理
const autoSave = async () => {
  if (!activeQueueId.value) return
  try {
    await saveQueueData()
  } catch (error) {
    console.error('自动保存失败:', error)
  }
}

// 保存队列数据
const saveQueueData = async () => {
  if (!activeQueueId.value) return

  try {
    // 构建符合API要求的数据结构，包含开关状态和完成后操作
    const queueData: Record<string, any> = {
      Info: {
        Name: currentQueueName.value,
        StartUpEnabled: currentStartUpEnabled.value,
        TimeEnabled: currentTimeEnabled.value,
        AfterAccomplish: currentAfterAccomplish.value,
      },
    }

    const response = await Service.updateQueueApiQueueUpdatePost({
      queueId: activeQueueId.value,
      data: queueData,
    })

    if (response.code !== 200) {
      throw new Error(response.message || '保存失败')
    }
  } catch (error) {
    console.error('保存队列数据失败:', error)
    throw error
  }
}

// 刷新队列列表
const handleRefresh = async () => {
  loading.value = true
  await fetchQueues()
  loading.value = false
}

// 自动保存功能
watch(
  () => [
    currentQueueName.value,
    currentQueueEnabled.value,
    currentStartUpEnabled.value,
    currentTimeEnabled.value,
    currentAfterAccomplish.value,
  ],
  async () => {
    await nextTick()
    autoSave()
  },
  { deep: true }
)

// 初始化
onMounted(async () => {
  try {
    await fetchQueues()
  } catch (error) {
    console.error('初始化失败:', error)
    loading.value = false
  }
})
</script>

<style scoped>
.queue-container {
  min-height: 100vh;
  background: var(--ant-color-bg-layout);
  padding: 24px;
}

.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.queue-main {
  max-width: 1400px;
  margin: 0 auto;
}

/* 页面头部 */
.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}

.header-left {
  flex: 1;
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.page-description {
  margin: 0;
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
}

.header-actions {
  flex-shrink: 0;
}


/* 空状态 */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 500px;
  padding: 60px 20px;
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.02), rgba(24, 144, 255, 0.01));
  border-radius: 16px;
  margin: 20px 0;
}

.empty-content {
  text-align: center;
  max-width: 480px;
  animation: fadeInUp 0.8s ease-out;
}

.empty-image-container {
  position: relative;
  margin-bottom: 32px;
  display: inline-block;
}

.empty-image-container::before {
  content: '';
  position: absolute;
  top: -20px;
  left: -20px;
  right: -20px;
  bottom: -20px;
  background: radial-gradient(circle, rgba(24, 144, 255, 0.1) 0%, transparent 70%);
  border-radius: 50%;
  animation: pulse 3s ease-in-out infinite;
}

.empty-image {
  max-width: 200px;
  height: auto;
  opacity: 0.9;
  filter: drop-shadow(0 8px 24px rgba(0, 0, 0, 0.1));
  transition: all 0.3s ease;
  position: relative;
  z-index: 1;
}

.empty-image:hover {
  transform: translateY(-4px);
  filter: drop-shadow(0 12px 32px rgba(0, 0, 0, 0.15));
}

.empty-text-content {
  margin-top: 16px;
}

.empty-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 12px 0;
  background: linear-gradient(135deg, var(--ant-color-text), var(--ant-color-text-secondary));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.empty-description {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  line-height: 1.6;
  margin: 0;
  opacity: 0.8;
}

@keyframes fadeInUp {
  from {
    opacity: 0;
    transform: translateY(30px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes pulse {
  0%, 100% {
    opacity: 0.6;
    transform: scale(1);
  }
  50% {
    opacity: 0.8;
    transform: scale(1.05);
  }
}

/* 队列内容 */
.queue-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 队列选择卡片 */
.queue-selector-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
}

.queue-selection-container {
  padding: 16px;
}

/* 队列按钮组 */
.queue-buttons-container {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.queue-button {
  flex: 1 1 120px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

/* 队列配置卡片 */
.queue-config-card {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  border: 1px solid var(--ant-color-border-secondary);
  min-height: 600px;
}

.status-label {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
}

/* 队列名称编辑 */
.queue-title-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.queue-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.queue-title-text {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.queue-edit-btn {
  color: var(--ant-color-primary);
  padding: 0;
}

/* 队列名称输入框 */
.queue-title-input {
  flex: 1;
  max-width: 400px;
  border-radius: 8px;
  transition: all 0.2s ease;
}

/* 配置区域 */
.config-section {
  margin-bottom: 24px;
}

/* 开关配置 */
.queue-switches {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.switch-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.switch-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.switch-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.switch-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

/* 完成后操作配置 */
.after-accomplish-settings {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.setting-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.setting-label {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.setting-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.setting-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .queue-container {
    padding: 16px;
  }

  .queue-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }

  .page-title {
    font-size: 28px;
  }
}

@media (max-width: 768px) {
  .queue-container {
    padding: 12px;
  }

  .page-title {
    font-size: 24px;
  }

  .page-description {
    font-size: 14px;
  }

  .queue-title-input {
    max-width: 100%;
  }

  .header-actions {
    width: 100%;
    display: flex;
    justify-content: center;
  }
}

/* 深度样式使用全局CSS变量 */
.queue-selector-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}

.queue-config-card :deep(.ant-card-head) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
  padding: 16px 24px;
}

.queue-config-card :deep(.ant-card-head-title) {
  font-size: 18px;
  font-weight: 600;
}

.queue-title-input :deep(.ant-input) {
  font-size: 16px;
  font-weight: 500;
}

.queue-title-input :deep(.ant-input:focus) {
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .queue-selector-card {
    background: var(--ant-color-bg-container);
  }

  .queue-config-card {
    background: var(--ant-color-bg-container);
  }
}
</style>

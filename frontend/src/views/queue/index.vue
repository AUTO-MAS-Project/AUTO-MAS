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
          <a-button type="primary" size="large" @click="handleAddQueue">
            <template #icon>
              <PlusOutlined />
            </template>
            新建队列
          </a-button>

          <a-popconfirm v-if="queueList.length > 0" title="确定要删除这个队列吗？" ok-text="确定" cancel-text="取消"
            @confirm="handleRemoveQueue(activeQueueId)">
            <a-button danger size="large" :disabled="!activeQueueId">
              <template #icon>
                <DeleteOutlined />
              </template>
              删除当前队列
            </a-button>
          </a-popconfirm>
        </a-space>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!queueList.length || !currentQueueData" class="empty-state">
      <div class="empty-content">
        <div class="empty-image-container">
          <img src="../../assets/NoData.png" alt="暂无数据" class="empty-image" />
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
              <a-button v-for="queue in queueList" :key="queue.id"
                :type="activeQueueId === queue.id ? 'primary' : 'default'" size="large" class="queue-button"
                @click="onQueueChange(queue.id)">
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
              <a-button type="text" size="small" class="queue-edit-btn" @click="startEditQueueName">
                <template #icon>
                  <EditOutlined />
                </template>
              </a-button>
            </div>
            <div v-else class="queue-title-edit">
              <a-input ref="queueNameInputRef" v-model:value="currentQueueName" placeholder="请输入队列名称"
                class="queue-title-input" :maxlength="50" @blur="finishEditQueueName"
                @press-enter="finishEditQueueName" />
            </div>
          </div>
        </template>

        <!-- 队列开关配置 -->
        <div class="config-section">
          <a-row :gutter="24">
            <a-col :span="6">
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">启动时运行</span>
                  <a-tooltip title="软件启动时自动运行此队列">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select v-model:value="currentStartUpEnabled" style="width: 100%" size="large"
                  @change="(value: any) => handleConfigChange('StartUpEnabled', value)">
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </div>
            </a-col>
            <a-col :span="6">
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">定时运行</span>
                  <a-tooltip title="在设定的时间自动运行此队列">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select v-model:value="currentTimeEnabled" style="width: 100%" size="large"
                  @change="(value: any) => handleConfigChange('TimeEnabled', value)">
                  <a-select-option :value="true">是</a-select-option>
                  <a-select-option :value="false">否</a-select-option>
                </a-select>
              </div>
            </a-col>
            <a-col :span="12">
              <div class="form-item-vertical">
                <div class="form-label-wrapper">
                  <span class="form-label">完成后操作</span>
                  <a-tooltip title="队列完成后执行的操作">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <a-select v-model:value="currentAfterAccomplish" style="width: 100%" :options="afterAccomplishOptions"
                  placeholder="请选择操作" size="large"
                  @change="(value: any) => handleConfigChange('AfterAccomplish', value)" />
              </div>
            </a-col>
          </a-row>
        </div>
        <a-divider />

        <!-- 定时项与队列项并排布局 -->
        <a-row :gutter="24" class="managers-row">
          <!-- 定时项管理 -->
          <a-col :span="12" class="manager-col">
            <TimeSetManager v-if="activeQueueId && currentQueueData" :queue-id="activeQueueId"
              :time-sets="currentTimeSets" style="font-size: 14px" @refresh="refreshTimeSets" />
          </a-col>

          <!-- 队列项管理 -->
          <a-col :span="12" class="manager-col">
            <QueueItemManager v-if="activeQueueId && currentQueueData" :queue-id="activeQueueId"
              :queue-items="currentQueueItems" style="font-size: 14px" @refresh="refreshQueueItems" />
          </a-col>
        </a-row>
      </a-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Service } from '@/api'
import QueueItemManager from '@/views/queue/components/QueueItemManager.vue'
import TimeSetManager from '@/views/queue/components/TimeSetManager.vue'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { getLogger } from '@/utils/logger'
import { useAudioPlayer } from '@/composables/useAudioPlayer'
import { nextTick, onMounted, ref, watch } from 'vue'

const logger = getLogger('调度队列')
const { playSound } = useAudioPlayer()

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
      logger.debug('API Response:', response) // 调试日志

      if (response.index && response.index.length > 0) {
        queueList.value = response.index.map((item: any, index: number) => {
          try {
            // API响应格式: {"uid": "xxx", "type": "QueueConfig"}
            const queueId = item.uid
            const queueName = response.data[queueId]?.Info?.Name || `新调度队列`
            logger.debug('Queue ID:', queueId, 'Name:', queueName, 'Type:', typeof queueId) // 调试日志
            return {
              id: queueId,
              name: queueName,
            }
          } catch (itemError) {
            logger.warn('解析队列项失败:', itemError, item)
            return {
              id: `queue_${index}`,
              name: `新调度队列`,
            }
          }
        })

        // 如果有队列且没有选中的队列，默认选中第一个
        if (queueList.value.length > 0 && !activeQueueId.value) {
          activeQueueId.value = queueList.value[0].id
          logger.debug('Selected queue ID:', activeQueueId.value) // 调试日志
          // 使用nextTick确保DOM更新后再加载数据
          nextTick(() => {
            loadQueueData(activeQueueId.value).catch(error => {
              logger.error('加载队列数据失败:', error)
            })
          })
        }
      } else {
        logger.debug('No queues found in response') // 调试日志
        queueList.value = []
        currentQueueData.value = null
      }
    } else {
      logger.error('API响应错误:', response)
      queueList.value = []
      currentQueueData.value = null
    }
  } catch (error) {
    logger.error('获取队列列表失败:', error)
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
        logger.error('刷新定时项失败:', timeError)
      }

      try {
        await refreshQueueItems()
      } catch (itemError) {
        logger.error('刷新队列项失败:', itemError)
      }
    }
  } catch (error) {
    logger.error('加载队列数据失败:', error)
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
      logger.error('获取定时项数据失败:', response)
      // 不清空数组，避免骨架屏闪现
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
            const originalTimeString = timeSetData.Info.Time || '00:00'
            const [hours = 0, minutes = 0] = originalTimeString.split(':').map(Number)

            // 创建标准化的时间字符串
            const validHours = Math.max(0, Math.min(23, hours))
            const validMinutes = Math.max(0, Math.min(59, minutes))
            const timeString = `${validHours.toString().padStart(2, '0')}:${validMinutes.toString().padStart(2, '0')}`

            timeSets.push({
              id: timeSetId,
              time: timeString,
              enabled: Boolean(timeSetData.Info.Enabled),
            })
          }
        } catch (itemError) {
          logger.warn('解析单个定时项失败:', itemError, item)
        }
      })
    }

    // 使用nextTick确保数据更新不会导致渲染问题
    await nextTick()
    // 直接替换数组内容，而不是清空再赋值，避免骨架屏闪现
    currentTimeSets.value.splice(0, currentTimeSets.value.length, ...timeSets)
    logger.debug('刷新后的定时项数据:', timeSets) // 调试日志
  } catch (error) {
    logger.error('刷新定时项列表失败:', error)
    // 不清空数组，避免骨架屏闪现
  }
}

// 刷新队列项数据
const refreshQueueItems = async () => {
  if (!activeQueueId.value) {
    // 不清空数组，避免骨架屏闪现
    return
  }

  try {
    // 使用专门的队列项API获取数据
    const response = await Service.getItemApiQueueItemGetPost({
      queueId: activeQueueId.value,
    })

    if (response.code !== 200) {
      logger.error('获取队列项数据失败:', response)
      // 不清空数组，避免骨架屏闪现
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
          logger.warn('解析单个队列项失败:', itemError, item)
        }
      })
    }

    // 使用nextTick确保数据更新不会导致渲染问题
    await nextTick()
    // 直接替换数组内容，而不是清空再赋值，避免骨架屏闪现
    currentQueueItems.value.splice(0, currentQueueItems.value.length, ...queueItems)
    logger.debug('刷新后的队列项数据:', queueItems) // 调试日志
  } catch (error) {
    logger.error('刷新队列项列表失败:', error)
    // 不清空数组，避免骨架屏闪现
  }
}

// 队列名称编辑失焦处理 - 保存到后端
const onQueueNameBlur = async () => {
  // 当用户编辑完队列名称后，更新按钮显示的名称并保存
  if (activeQueueId.value) {
    const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
    if (currentQueue) {
      currentQueue.name =
        currentQueueName.value || `队列 ${queueList.value.indexOf(currentQueue) + 1}`
    }
    // 保存到后端
    await handleSaveChange('Name', currentQueueName.value)
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

// 统一的配置字段变更处理 - 即时保存单个字段
const handleConfigChange = async (key: string, value: any) => {
  await handleSaveChange(key, value)
}

// 添加队列
const handleAddQueue = async () => {
  try {
    const response = await Service.addQueueApiQueueAddPost()

    if (response.code === 200 && response.queueId) {
      // 播放添加队列成功音频
      const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
      const { playSound } = useAudioPlayer()
      await playSound('add_queue')

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
    logger.error('添加队列失败:', error)
    message.error('添加队列失败: ' + (error instanceof Error ? error.message : '网络错误'))
  }
}

// 删除队列
const handleRemoveQueue = async (queueId: string) => {
  try {
    const response = await Service.deleteQueueApiQueueDeletePost({ queueId })

    if (response.code === 200) {
      // 播放删除队列成功音频
      const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
      const { playSound } = useAudioPlayer()
      await playSound('delete_queue')

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
    logger.error('删除队列失败:', error)
    message.error('删除队列失败: ' + (error instanceof Error ? error.message : '网络错误'))
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
    logger.error('队列切换失败:', error)
  }
}

// 刷新当前队列配置 - 保存成功后调用
const refreshQueueConfig = async () => {
  if (!activeQueueId.value) return

  try {
    const response = await Service.getQueuesApiQueueGetPost({})
    if (response.code === 200 && response.data && response.data[activeQueueId.value]) {
      currentQueueData.value = response.data
      const queueData = response.data[activeQueueId.value]

      // 更新本地状态
      if (queueData.Info) {
        currentQueueName.value = queueData.Info.Name || ''
        currentStartUpEnabled.value = queueData.Info.StartUpEnabled ?? false
        currentTimeEnabled.value = queueData.Info.TimeEnabled ?? false
        currentAfterAccomplish.value = queueData.Info.AfterAccomplish ?? 'NoAction'

        // 更新队列列表中的名称
        const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
        if (currentQueue) {
          currentQueue.name = queueData.Info.Name || currentQueue.name
        }
      }
    }
  } catch (error) {
    logger.error('刷新队列配置失败:', error)
  }
}

// 即时保存单个字段变更 - 只发送修改的字段（遵循最小原则）
const handleSaveChange = async (key: string, value: any): Promise<boolean> => {
  if (!activeQueueId.value) return false

  try {
    // 构建只包含变更字段的数据
    const queueData: Record<string, any> = {
      Info: { [key]: value },
    }

    const response = await Service.updateQueueApiQueueUpdatePost({
      queueId: activeQueueId.value,
      data: queueData,
    })

    if (response.code !== 200) {
      message.error(response.message || '保存失败')
      return false
    }

    // 保存成功后重新获取最新配置
    await refreshQueueConfig()
    return true
  } catch (error) {
    logger.error('保存队列数据失败:', error)
    message.error('保存队列数据失败')
    return false
  }
}

// 注意：配置保存已改为即时保存，由各个 @change 事件触发，不再使用 watch 自动保存

// 初始化
onMounted(async () => {
  try {
    await fetchQueues()
  } catch (error) {
    logger.error('初始化失败:', error)
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

  0%,
  100% {
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
  margin-bottom: 12px;
}

/* 定时项与队列项并排布局 */
.managers-row {
  margin-bottom: 24px;
}

.manager-col {
  display: flex;
  flex-direction: column;
  height: 100%;
}

/* 垂直排列的表单项 */
.form-item-vertical {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表单标签 */
.form-label {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: #8c8c8c;
  font-size: 14px;
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

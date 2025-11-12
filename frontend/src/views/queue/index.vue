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
          <a-space wrap size="middle">
            <a-button
              v-for="queue in queueList"
              :key="queue.id"
              :type="activeQueueId === queue.id ? 'primary' : 'default'"
              size="large"
              @click="onQueueChange(queue.id)"
            >
              {{ queue.name }}
            </a-button>
          </a-space>
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
              <a-input
                ref="queueNameInputRef"
                v-model:value="currentQueueName"
                placeholder="请输入队列名称"
                class="queue-title-input"
                :maxlength="50"
                @blur="finishEditQueueName"
                @press-enter="finishEditQueueName"
              />
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
                <a-select
                  v-model:value="currentStartUpEnabled"
                  style="width: 100%"
                  size="large"
                  @change="onQueueSwitchChange"
                >
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
                <a-select
                  v-model:value="currentTimeEnabled"
                  style="width: 100%"
                  size="large"
                  @change="onQueueSwitchChange"
                >
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
                <a-select
                  v-model:value="currentAfterAccomplish"
                  style="width: 100%"
                  :options="afterAccomplishOptions"
                  placeholder="请选择操作"
                  size="large"
                  @change="onAfterAccomplishChange"
                />
              </div>
            </a-col>
          </a-row>
        </div>
        <a-divider />

        <!-- 定时项和队列项管理 - 左右两列布局 -->
        <div class="managers-container">
          <div class="manager-column">
            <TimeSetManager
              v-if="activeQueueId && currentQueueData"
              :queue-id="activeQueueId"
              :time-sets="currentTimeSets"
              @refresh="refreshTimeSets"
            />
          </div>
          <div class="manager-column">
            <QueueItemManager
              v-if="activeQueueId && currentQueueData"
              :queue-id="activeQueueId"
              :queue-items="currentQueueItems"
              @refresh="refreshQueueItems"
            />
          </div>
        </div>
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
import { nextTick, onMounted, ref, watch } from 'vue'

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
    // 直接替换数组内容，而不是清空再赋值，避免骨架屏闪现
    currentTimeSets.value.splice(0, currentTimeSets.value.length, ...timeSets)
    console.log('刷新后的定时项数据:', timeSets) // 调试日志
  } catch (error) {
    console.error('刷新定时项列表失败:', error)
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
      console.error('获取队列项数据失败:', response)
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
          console.warn('解析单个队列项失败:', itemError, item)
        }
      })
    }

    // 使用nextTick确保数据更新不会导致渲染问题
    await nextTick()
    // 直接替换数组内容，而不是清空再赋值，避免骨架屏闪现
    currentQueueItems.value.splice(0, currentQueueItems.value.length, ...queueItems)
    console.log('刷新后的队列项数据:', queueItems) // 调试日志
  } catch (error) {
    console.error('刷新队列项列表失败:', error)
    // 不清空数组，避免骨架屏闪现
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
.loading-container {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
}

.queue-main {
  margin: 0 auto;
  padding: 24px;
}

/* 页面头部 */
.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
}

/* 空状态 */
.empty-state {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 400px;
  padding: 60px 20px;
}

.empty-content {
  text-align: center;
}

.empty-image {
  max-width: 200px;
  height: auto;
  margin-bottom: 24px;
}

.empty-title {
  font-size: 24px;
  font-weight: 600;
  margin: 0 0 12px 0;
}

.empty-description {
  font-size: 16px;
  color: var(--ant-color-text-secondary);
  margin: 0;
}

/* 队列内容 */
.queue-content {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

/* 卡片样式 */
.queue-selector-card,
.queue-config-card {
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 18px;
  font-weight: 600;
}

.queue-selection-container {
  padding: 8px;
}

/* 队列名称编辑 */
.queue-title-container {
  margin-bottom: 0;
}

.queue-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.queue-title-text {
  font-size: 18px;
  font-weight: 600;
}

.queue-edit-btn {
  color: var(--ant-color-primary);
}

.queue-title-input {
  max-width: 400px;
}

/* 配置区域 */
.config-section {
  margin-bottom: 24px;
}

.form-item-vertical {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

.form-label {
  font-weight: 600;
  font-size: 14px;
}

.help-icon {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
}

/* 定时项和队列项管理容器 - 左右两列布局 */
.managers-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  margin-top: 24px;
}

.manager-column {
  min-width: 0;
}

/* 响应式设计 */
@media (max-width: 1200px) {
  .managers-container {
    grid-template-columns: 1fr;
  }

  .queue-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
  }
}

@media (max-width: 768px) {
  .queue-main {
    padding: 12px;
  }

  .page-title {
    font-size: 24px;
  }
}
</style>

<template>
  <div v-if="loading" class="loading-box">
    <a-spin tip="加载中，请稍候..." size="large" />
  </div>

  <div v-else class="queue-content">
    <!-- 队列头部 -->
    <div class="queue-header">
      <div class="header-title">
        <h1>调度队列</h1>
      </div>
      <a-space size="middle">
        <a-button type="primary" size="large" @click="handleAddQueue">
          <template #icon>
            <PlusOutlined />
          </template>
          新建队列
        </a-button>
        <a-button size="large" @click="handleRefresh">
          <template #icon>
            <ReloadOutlined />
          </template>
          刷新
        </a-button>
      </a-space>
    </div>

    <!-- 空状态 -->
    <div v-if="!queueList.length || !currentQueueData" class="empty-state">
      <div
        class="empty-content empty-content-fancy"
        @click="handleAddQueue"
        style="cursor: pointer"
      >
        <div class="empty-icon">
          <PlusOutlined />
        </div>
        <h2>你还没有创建过队列</h2>
        <h1>点击此处来新建队列</h1>
      </div>
    </div>

    <!-- 队列内容 -->
    <div class="queue-main-content" v-else-if="currentQueueData">
      <!-- 队列选择器 -->
      <div class="queue-selector">
        <a-tabs
          v-model:activeKey="activeQueueId"
          type="editable-card"
          @edit="onTabEdit"
          @change="onQueueChange"
          class="queue-tabs"
        >
          <a-tab-pane
            v-for="queue in queueList"
            :key="queue.id"
            :tab="queue.name"
            :closable="queueList.length > 1"
          />
        </a-tabs>
      </div>

      <!-- 队列配置区域 -->
      <div class="queue-config-section">
        <div class="section-header">
          <div class="section-title">
            <div class="queue-name-editor">
              <a-input
                v-model:value="currentQueueName"
                placeholder="请输入队列名称"
                size="large"
                class="queue-name-input"
                @blur="onQueueNameBlur"
                @pressEnter="onQueueNameBlur"
              />
            </div>
          </div>
          <!--          <div class="section-controls">-->
          <!--            <a-space>-->
          <!--              <span class="status-label">状态：</span>-->
          <!--              <a-switch -->
          <!--                v-model:checked="currentQueueEnabled" -->
          <!--                @change="onQueueStatusChange"-->
          <!--                checked-children="启用"-->
          <!--                un-checked-children="禁用"-->
          <!--              />-->
          <!--            </a-space>-->
          <!--          </div>-->
        </div>

        <!-- 定时项组件 -->
        <TimeSetManager
          v-if="activeQueueId && currentQueueData"
          :queue-id="activeQueueId"
          :time-sets="currentTimeSets"
          @refresh="refreshTimeSets"
        />

        <!-- 队列项组件 -->
        <QueueItemManager
          v-if="activeQueueId && currentQueueData"
          :queue-id="activeQueueId"
          :queue-items="currentQueueItems"
          @refresh="refreshQueueItems"
        />
      </div>
    </div>
  </div>

  <!-- 悬浮保存按钮 -->
  <a-float-button
    type="primary"
    @click="handleSave"
    class="float-button"
    :style="{ right: '24px' }"
  >
    <template #icon>
      <SaveOutlined />
    </template>
  </a-float-button>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, nextTick } from 'vue'
import { message } from 'ant-design-vue'
import { PlusOutlined, ReloadOutlined, SaveOutlined } from '@ant-design/icons-vue'
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
            const queueName = response.data[queueId]?.Info?.Name || `队列 ${index + 1}`
            console.log('Queue ID:', queueId, 'Name:', queueName, 'Type:', typeof queueId) // 调试日志
            return {
              id: queueId,
              name: queueName,
            }
          } catch (itemError) {
            console.warn('解析队列项失败:', itemError, item)
            return {
              id: `queue_${index}`,
              name: `队列 ${index + 1}`,
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
    // 重新从API获取最新的队列数据
    const response = await Service.getQueuesApiQueueGetPost({})
    if (response.code !== 200) {
      console.error('获取队列数据失败:', response)
      currentTimeSets.value = []
      return
    }

    // 更新缓存的队列数据
    currentQueueData.value = response.data

    // 从最新的队列数据中获取定时项信息
    if (response.data && response.data[activeQueueId.value]) {
      const queueData = response.data[activeQueueId.value]
      const timeSets: any[] = []

      // 检查是否有TimeSet配置
      if (queueData?.SubConfigsInfo?.TimeSet) {
        const timeSetConfig = queueData.SubConfigsInfo.TimeSet

        // 遍历instances数组获取所有定时项ID
        if (Array.isArray(timeSetConfig.instances)) {
          timeSetConfig.instances.forEach((instance: any) => {
            try {
              const timeSetId = instance?.uid
              if (!timeSetId) return

              const timeSetData = timeSetConfig[timeSetId]
              if (timeSetData?.Info) {
                // 解析时间字符串 "HH:mm" - 修复字段名
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
                  description: timeSetData.Info.Description || '',
                })
              }
            } catch (itemError) {
              console.warn('解析单个定时项失败:', itemError, instance)
            }
          })
        }
      }

      // 使用nextTick确保数据更新不会导致渲染问题
      await nextTick()
      currentTimeSets.value = [...timeSets]
      console.log('刷新后的定时项数据:', timeSets) // 调试日志
    } else {
      currentTimeSets.value = []
    }
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
    // 重新从API获取最新的队列数据
    const response = await Service.getQueuesApiQueueGetPost({})
    if (response.code !== 200) {
      console.error('获取队列数据失败:', response)
      currentQueueItems.value = []
      return
    }

    // 更新缓存的队列数据
    currentQueueData.value = response.data

    // 从最新的队列数据中获取队列项信息
    if (response.data && response.data[activeQueueId.value]) {
      const queueData = response.data[activeQueueId.value]
      const queueItems: any[] = []

      // 检查是否有QueueItem配置
      if (queueData?.SubConfigsInfo?.QueueItem) {
        const queueItemConfig = queueData.SubConfigsInfo.QueueItem

        // 遍历instances数组获取所有队列项ID
        if (Array.isArray(queueItemConfig.instances)) {
          queueItemConfig.instances.forEach((instance: any) => {
            try {
              const queueItemId = instance?.uid
              if (!queueItemId) return

              const queueItemData = queueItemConfig[queueItemId]
              if (queueItemData?.Info) {
                queueItems.push({
                  id: queueItemId,
                  script: queueItemData.Info.ScriptId || '',
                })
              }
            } catch (itemError) {
              console.warn('解析单个队列项失败:', itemError, instance)
            }
          })
        }
      }

      // 使用nextTick确保数据更新不会导致渲染问题
      await nextTick()
      currentQueueItems.value = [...queueItems]
      console.log('刷新后的队列项数据:', queueItems) // 调试日志
    } else {
      currentQueueItems.value = []
    }
  } catch (error) {
    console.error('刷新队列项列表失败:', error)
    currentQueueItems.value = []
    // 不显示错误消息，避免干扰用户
  }
}

// 队列名称编辑失焦处理
const onQueueNameBlur = () => {
  if (activeQueueId.value) {
    const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
    if (currentQueue) {
      currentQueue.name =
        currentQueueName.value || `队列 ${queueList.value.indexOf(currentQueue) + 1}`
    }
  }
}

// 队列状态切换处理
const onQueueStatusChange = () => {
  // 状态切换时只更新本地状态，不自动保存
}

// 标签页编辑处理
const onTabEdit = async (targetKey: string | MouseEvent, action: 'add' | 'remove') => {
  try {
    if (action === 'add') {
      await handleAddQueue()
    } else if (action === 'remove' && typeof targetKey === 'string') {
      await handleRemoveQueue(targetKey)
    }
  } catch (error) {
    console.error('标签页操作失败:', error)
  }
}

// 添加队列
const handleAddQueue = async () => {
  try {
    const response = await Service.addQueueApiQueueAddPost()

    if (response.code === 200 && response.queueId) {
      const defaultName = `队列 ${queueList.value.length + 1}`
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
      message.success('队列创建成功')
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
    // 清空当前数据，避免渲染问题
    currentTimeSets.value = []
    currentQueueItems.value = []

    await loadQueueData(queueId)
  } catch (error) {
    console.error('队列切换失败:', error)
  }
}

// 手动保存处理
const handleSave = async () => {
  if (!activeQueueId.value) {
    message.warning('请先选择一个队列')
    return
  }
  try {
    await saveQueueData()
    message.success('保存成功')
  } catch (error) {
    message.error('保存失败')
  }
}

// 保存队列数据
const saveQueueData = async () => {
  if (!activeQueueId.value) return

  try {
    // 构建符合API要求的数据结构
    const queueData: Record<string, any> = {
      name: currentQueueName.value,
      enabled: currentQueueEnabled.value,
      // 这里可以添加其他需要保存的队列配置
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
/* 空状态样式 */
.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.empty-content {
  text-align: center;
  padding: 48px;
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--ant-color-border-secondary);
}

.empty-icon {
  font-size: 64px;
  color: var(--ant-color-text-tertiary);
  margin-bottom: 24px;
}

.empty-content h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin: 0 0 8px 0;
}

.empty-content p {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 32px 0;
}

/* 队列内容区域 */
.queue-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: var(--ant-color-bg-container);
  border-radius: 16px;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

/* 队列头部样式 */
.queue-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 24px 32px;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
  margin-bottom: 5px;
}

.header-title h1 {
  margin: 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

/* 队列选择器 */
.queue-selector {
  padding: 0 32px;
  background: var(--ant-color-bg-container);
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

/* 队列主内容 */
.queue-main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* 队列配置区域 */
.queue-config-section {
  flex: 1;
  padding: 24px 32px;
  overflow: auto;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 20px 24px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  margin-bottom: 24px;
  background: var(--ant-color-bg-container);
}

.section-title h3 {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
}

.section-controls {
  display: flex;
  align-items: center;
}

.status-label {
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
}

/* 队列名称编辑器样式 */
.queue-name-editor {
  display: flex;
  align-items: center;
}

.queue-name-input {
  max-width: 300px;
  font-size: 18px;
  font-weight: 600;
}

.queue-name-input :deep(.ant-input) {
  border: 1px solid transparent;
  background: transparent;
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 600;
  padding: 4px 8px;
  border-radius: 6px;
  transition: all 0.3s ease;
}

.queue-name-input :deep(.ant-input:hover) {
  border-color: var(--ant-color-border);
}

.queue-name-input :deep(.ant-input:focus) {
  border-color: var(--ant-color-primary);
  box-shadow: 0 0 0 2px rgba(24, 144, 255, 0.2);
}

.loading-box {
  min-height: 400px;
  display: flex;
  justify-content: center;
  align-items: center;
}

.float-button {
  width: 60px;
  height: 60px;
}

.empty-content-fancy {
  transition:
    box-shadow 0.3s,
    transform 0.2s;
  border: none;
  border-radius: 24px;
}

.empty-icon {
  font-size: 80px;
  margin-bottom: 32px;
  border-radius: 50%;
  width: 100px;
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-left: auto;
  margin-right: auto;
}

.empty-content-fancy h2 {
  font-size: 26px;
  font-weight: 700;
  margin: 0 0 12px 0;
  letter-spacing: 1px;
  color: var(--ant-color-text);
}

.empty-content-fancy h1 {
  font-size: 16px;
  border-radius: 8px;
  padding: 8px 16px;
  margin: 0 0 12px 0;
  display: inline-block;
  color: var(--ant-color-text-secondary);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .queue-config-section {
    border-color: var(--ant-color-border-secondary);
    border-radius: 16px;
  }

  .section-header {
    border-color: var(--ant-color-border-secondary);
    border-radius: 16px;
  }
}
</style>
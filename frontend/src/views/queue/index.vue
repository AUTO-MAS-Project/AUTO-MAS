<template>
  <!-- 加载状态 -->
  <div v-if="loading" class="loading-container">
    <a-spin size="large" :tip="t('core.queue.loading')" />
  </div>

  <!-- 主要内容 -->
  <div v-else class="queue-main">
    <!-- 页面头部 -->
    <div class="queue-header app-page-header">
      <div class="header-left">
        <h1 class="page-title app-page-title">{{ t('core.queue.title') }}</h1>
      </div>
      <div class="header-actions">
        <a-space size="middle">
          <a-button type="primary" size="large" @click="handleAddQueue">
            <template #icon>
              <PlusOutlined />
            </template>
            {{ t('core.queue.create') }}
          </a-button>

          <QueueDeleteButton
            v-if="queueList.length > 0"
            :title="t('core.queue.deleteConfirm')"
            :text="t('core.queue.deleteCurrent')"
            size="large"
            :disabled="!activeQueueId"
            :confirm="() => handleRemoveQueue(activeQueueId)"
          />
        </a-space>
      </div>
    </div>

    <!-- 空状态 -->
    <div v-if="!queueList.length || !currentQueueData" class="empty-state">
      <NoData :image-style="{ height: '200px' }">
        <template #description>
          <div class="empty-title">{{ t('core.queue.emptyTitle') }}</div>
          <div class="empty-description">{{ t('core.queue.emptyDesc') }}</div>
        </template>
      </NoData>
    </div>

    <!-- 队列内容 -->
    <div v-else class="queue-content">
      <!-- 队列选择卡片 -->
      <SectionCard class="queue-selector-card">
        <template #title>
          <span>{{ t('core.queue.selectLabel') }}</span>
          <a-tag color="success">
            {{ t('core.queue.count', { count: queueList.length }, queueList.length) }}
          </a-tag>
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
                class="queue-button"
                @click="onQueueChange(queue.id)"
              >
                {{ queue.name }}
              </a-button>
            </a-space>
          </div>
        </div>
      </SectionCard>

      <!-- 队列配置卡片 -->
      <SectionCard class="queue-config-card">
        <template #title>
          <span v-if="!isEditingQueueName" class="queue-title-display">
            <span class="queue-title-text">{{
              currentQueueName || t('core.queue.configTitle')
            }}</span>
            <a-button
              type="text"
              size="small"
              class="queue-edit-btn"
              :aria-label="t('core.comp.edit')"
              @click="startEditQueueName"
            >
              <template #icon>
                <EditOutlined />
              </template>
            </a-button>
          </span>
          <a-input
            v-else
            ref="queueNameInputRef"
            v-model:value="currentQueueName"
            :placeholder="t('core.queue.namePlaceholder')"
            class="queue-title-input"
            :maxlength="50"
            @blur="finishEditQueueName"
            @press-enter="finishEditQueueName"
          />
        </template>

        <QueueTriggerSettings
          :key="activeQueueId"
          :queue-id="activeQueueId"
          :info="currentQueueData?.[activeQueueId]?.Info"
          @refresh="refreshQueueConfig()"
        />
        <TimeSetManager
          v-if="activeQueueId && currentQueueData?.[activeQueueId]?.Info?.TimeEnabled"
          :key="`time-${activeQueueId}`"
          :queue-id="timeSetsQueueId"
          :time-sets="currentTimeSets"
          :pending="timeSetsLocked"
          :dimmed="timeSetsDimmed"
          @refresh="refreshTimeSets"
          @saved="onTimeSetSaved"
        />
        <QueueCycleSettings
          v-if="activeQueueId && currentQueueData?.[activeQueueId]?.Info?.CycleEnabled"
          :key="`cycle-${activeQueueId}`"
          :queue-id="activeQueueId"
          :cycle="currentQueueData?.[activeQueueId]?.Cycle"
          @refresh="refreshQueueConfig()"
        />
        <QueueItemManager
          v-if="activeQueueId && currentQueueData"
          :key="`items-${activeQueueId}`"
          :queue-id="queueItemsQueueId"
          :queue-items="currentQueueItems"
          :pending="queueItemsLocked"
          :dimmed="queueItemsDimmed"
          @refresh="refreshQueueItems"
          @saved="onQueueItemSaved"
        />
        <a-form layout="vertical" class="queue-extra-settings">
          <ExtraScriptSection
            :key="activeQueueId"
            v-model:form-data="extraScriptFormData"
            :loading="
              queueConfigLoading || extraScriptSaving || extraScriptConfigQueueId !== activeQueueId
            "
            scope="queue"
            @save="handleExtraScriptSave"
          />
        </a-form>
      </SectionCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useConfigLoader } from '@/services/configUiSync'
import { useI18n } from 'vue-i18n'
import type { QueueConfig_Info } from '@/api'
import { useQueueTimeSets } from './useQueueTimeSets'
import { useQueueItems } from './useQueueItems'
import { nextQueuePageInstance } from './useQueueScopedList'
import { queueApi } from '@/composables/useQueueApi'
import QueueItemManager from '@/views/queue/components/QueueItemManager.vue'
import QueueDeleteButton from './components/QueueDeleteButton.vue'
import QueueTriggerSettings from './components/QueueTriggerSettings.vue'
import QueueCycleSettings from './components/QueueCycleSettings.vue'
import TimeSetManager from '@/views/queue/components/TimeSetManager.vue'
import ExtraScriptSection from '@/components/ExtraScriptSection.vue'
import { SectionCard } from '@/components/ui'
import { EditOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { nextTick, onMounted, onUnmounted, ref } from 'vue'

const { t } = useI18n()

defineOptions({ name: 'QueueManager' })

const logger = window.electronAPI.getLogger('调度队列')

// 卸载守卫：防止组件卸载后的 async 回调写入响应式状态，导致 Vue 运行时错误
let isMounted = true
// 队列列表和当前选中的队列
const queueList = ref<Array<{ id: string; name: string }>>([])
const activeQueueId = ref<string>('')
const currentQueueData = ref<Record<string, any> | null>(null)

// 当前队列的名称和状态
const currentQueueName = ref<string>('')
const currentQueueEnabled = ref<boolean>(true)
const extraScriptFormData = ref({
  Info: {
    IfScriptBeforeTask: false,
    ScriptBeforeTask: '',
    IfScriptAfterTask: false,
    ScriptAfterTask: '',
  },
})
const queueConfigLoading = ref(false)
const extraScriptSaving = ref(false)
const extraScriptConfigQueueId = ref('')
// 队列名称编辑状态
const isEditingQueueName = ref<boolean>(false)

// 回读的 query key 带上页面实例编号：离开再回来时不会并进旧实例还在途的请求
const pageInstance = nextQueuePageInstance()

// 当前队列的定时项和队列项。切换队列时不清空：有缓存先显示缓存，没有就保留旧内容，
// 都锁住直到新队列读回来；写请求始终发往显示内容所属的队列（ownerQueueId）。
const { timeSetList, currentTimeSets, refreshTimeSets, onTimeSetSaved } = useQueueTimeSets(
  activeQueueId,
  pageInstance
)
const { queueItemList, currentQueueItems, refreshQueueItems, onQueueItemSaved } = useQueueItems(
  activeQueueId,
  pageInstance
)
const {
  ownerQueueId: timeSetsQueueId,
  locked: timeSetsLocked,
  dimmed: timeSetsDimmed,
} = timeSetList
const {
  ownerQueueId: queueItemsQueueId,
  locked: queueItemsLocked,
  dimmed: queueItemsDimmed,
} = queueItemList

// 切换选中队列：两张表先显示缓存或保留旧内容并锁住，由 loadQueueData 回读后替换
const selectQueue = (queueId: string) => {
  // 重复点当前队列不算切换，保留正在编辑的内容
  if (activeQueueId.value === queueId) return
  activeQueueId.value = queueId
  // 队列删光时两张表不再显示，不用锁（否则禁用样式会带到下一个新建的队列）
  if (!queueId) return
  queueItemList.select(queueId)
  timeSetList.select(queueId)
}

// 这次切换的回读没能发出（队列数据读取失败等）：按读失败处理，不能一直锁着
const failQueueLists = (queueId: string) => {
  queueItemList.fail(queueId)
  timeSetList.fail(queueId)
}

const loading = ref(true)

// 获取队列列表
const fetchQueues = useConfigLoader(['config', 'queues', pageInstance], async read => {
  if (!queueList.value.length) loading.value = true
  try {
    const response = await queueApi.getQueues({})
    read(response)
    if (!isMounted) return
    if (response.code === 200) {
      // 处理队列数据
      logger.debug(`API Response: ${JSON.stringify(response)}`) // 调试日志

      if (response.index && response.index.length > 0) {
        // API响应格式: {"uid": "xxx", "type": "QueueConfig"}
        queueList.value = response.index.map((item: any) => ({
          id: item.uid,
          name: response.data[item.uid]?.Info?.Name || t('core.queue.newQueueName'),
        }))

        // 如果有队列且没有选中的队列，默认选中第一个
        if (!queueList.value.some(queue => queue.id === activeQueueId.value)) {
          selectQueue(queueList.value[0].id)
          logger.debug(`Selected queue ID: ${activeQueueId.value}`) // 调试日志
          // 首屏直接复用这次拉回来的数据，不再为同一份内容再请求一次
          nextTick(() => {
            loadQueueData(activeQueueId.value, response.data).catch(error => {
              const errorMsg = error instanceof Error ? error.message : String(error)
              logger.error(`加载队列数据失败: ${errorMsg}`)
            })
          })
        }
      } else {
        logger.debug('队列列表为空') // 调试日志
        queueList.value = []
        currentQueueData.value = null
      }
    } else {
      logger.error(`API响应错误: ${response.message}`)
      queueList.value = []
      currentQueueData.value = null
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`获取队列列表失败: ${errorMsg}`)
    queueList.value = []
    currentQueueData.value = null
  } finally {
    loading.value = false
  }
})

// 加载队列数据；调用方手里已有整份队列数据时直接传入，省一次请求
const loadQueueData = async (queueId: string, queuesData?: Record<string, any>) => {
  if (!queueId) return

  queueConfigLoading.value = true
  let listsRequested = false
  try {
    const data = queuesData ?? (await queueApi.getQueues({})).data
    if (!isMounted || queueId !== activeQueueId.value) return
    currentQueueData.value = data

    // 根据API响应数据更新队列信息
    if (data && data[queueId]) {
      const queueData = data[queueId]

      // 更新队列名称和状态
      const currentQueue = queueList.value.find(queue => queue.id === queueId)
      if (currentQueue) {
        currentQueueName.value = currentQueue.name
      }

      // 使用nextTick确保DOM更新后再加载数据
      await nextTick()
      if (!isMounted || queueId !== activeQueueId.value) return

      loadExtraScriptConfig(queueData.Info)

      // 定时项和队列项互不依赖，并行拉取
      listsRequested = true
      await Promise.all([
        refreshTimeSets().catch(timeError => {
          const errorMsg = timeError instanceof Error ? timeError.message : String(timeError)
          logger.error(`刷新定时项失败: ${errorMsg}`)
        }),
        refreshQueueItems().catch(itemError => {
          const errorMsg = itemError instanceof Error ? itemError.message : String(itemError)
          logger.error(`刷新队列项失败: ${errorMsg}`)
        }),
      ])
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载队列数据失败: ${errorMsg}`)
    if (isMounted) message.error(t('core.queue.toast.loadQueueFailed'))
  } finally {
    if (queueId === activeQueueId.value) queueConfigLoading.value = false
    if (!listsRequested && isMounted && queueId === activeQueueId.value) failQueueLists(queueId)
  }
}

// 队列名称编辑失焦处理 - 保存到后端
const onQueueNameBlur = async () => {
  // 当用户编辑完队列名称后，更新按钮显示的名称并保存
  if (activeQueueId.value) {
    const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
    if (currentQueue) {
      currentQueue.name =
        currentQueueName.value ||
        t('core.queue.unnamedIndexed', { index: queueList.value.indexOf(currentQueue) + 1 })
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

const loadExtraScriptConfig = (info?: QueueConfig_Info) => {
  extraScriptConfigQueueId.value = activeQueueId.value
  extraScriptFormData.value = {
    Info: {
      IfScriptBeforeTask: info?.IfScriptBeforeTask ?? false,
      ScriptBeforeTask: info?.ScriptBeforeTask ?? '',
      IfScriptAfterTask: info?.IfScriptAfterTask ?? false,
      ScriptAfterTask: info?.ScriptAfterTask ?? '',
    },
  }
}

const handleExtraScriptSave = async (key: string, value: boolean | string) => {
  extraScriptSaving.value = true
  try {
    await handleSaveChange(key.replace(/^Info\./, ''), value)
  } finally {
    extraScriptSaving.value = false
  }
}

// 添加队列
const handleAddQueue = async () => {
  try {
    const response = await queueApi.createQueue()

    if (response.code === 200 && response.queueId) {
      // 播放添加队列成功音频
      const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
      const { playSound } = useAudioPlayer()
      await playSound('add_queue')

      const defaultName = t('core.queue.defaultName')
      const newQueue = {
        id: response.queueId,
        name: defaultName,
      }
      queueList.value.push(newQueue)
      selectQueue(newQueue.id)

      // 设置默认名称到输入框中
      currentQueueName.value = defaultName
      currentQueueEnabled.value = true

      await loadQueueData(newQueue.id)

      // 显示名称修改提示
      message.info(t('core.queue.toast.created'), 3)
    } else {
      message.error(
        t('core.queue.toast.createFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加队列失败: ${errorMsg}`)
    message.error(t('core.queue.toast.addQueueFailed', { error: errorMsg }))
  }
}

// 删除队列
const handleRemoveQueue = async (queueId: string) => {
  try {
    const response = await queueApi.deleteQueue({ queueId })

    if (response.code === 200) {
      // 播放删除队列成功音频
      const { useAudioPlayer } = await import('@/composables/useAudioPlayer')
      const { playSound } = useAudioPlayer()
      await playSound('delete_queue')

      queueItemList.forget(queueId)
      timeSetList.forget(queueId)
      const index = queueList.value.findIndex(queue => queue.id === queueId)
      if (index > -1) {
        queueList.value.splice(index, 1)
        if (activeQueueId.value === queueId) {
          selectQueue(queueList.value[0]?.id || '')
          if (activeQueueId.value) {
            await loadQueueData(activeQueueId.value)
          } else {
            currentQueueData.value = null
          }
        }
      }
      message.success(t('core.queue.toast.deleted'))
    } else {
      message.error(
        t('core.queue.toast.deleteFailed', {
          error: response.message || t('core.queue.toast.unknownError'),
        })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`删除队列失败: ${errorMsg}`)
    message.error(t('core.queue.toast.deleteFailed', { error: errorMsg }))
  }
}

// 队列切换
const onQueueChange = async (queueId: string) => {
  if (!queueId) return

  try {
    // 立即更新activeQueueId以确保按钮高亮切换；不清空两张表，避免先闪一下空状态
    selectQueue(queueId)

    await loadQueueData(queueId)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`队列切换失败: ${errorMsg}`)
  }
}

// 刷新当前队列配置 - 保存成功后调用
const refreshQueueConfig = async (queueId = activeQueueId.value) => {
  if (!queueId) return

  try {
    const response = await queueApi.getQueues({})
    if (!isMounted || queueId !== activeQueueId.value) return
    if (response.code === 200 && response.data && response.data[activeQueueId.value]) {
      currentQueueData.value = response.data
      const queueData = response.data[activeQueueId.value]

      // 更新本地状态
      if (queueData.Info) {
        currentQueueName.value = queueData.Info.Name || ''
        loadExtraScriptConfig(queueData.Info)

        // 更新队列列表中的名称
        const currentQueue = queueList.value.find(queue => queue.id === activeQueueId.value)
        if (currentQueue) {
          currentQueue.name = queueData.Info.Name || currentQueue.name
        }
      }
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`刷新队列配置失败: ${errorMsg}`)
  }
}

// 保存成功后把这次变更写进本地快照；各控件已 v-model 到对应 ref，这里只补快照与列表名
const applyLocalQueueChange = (queueId: string, key: string, value: any) => {
  const queueData = currentQueueData.value?.[queueId]
  if (queueData) {
    queueData.Info = { ...(queueData.Info ?? {}), [key]: value }
  }
  if (key === 'Name') {
    const currentQueue = queueList.value.find(queue => queue.id === queueId)
    if (currentQueue && value) currentQueue.name = value
  }
}

// 即时保存单个字段变更 - 只发送修改的字段（遵循最小原则）
const handleSaveChange = async (key: string, value: any): Promise<boolean> => {
  const queueId = activeQueueId.value
  if (!queueId) return false

  try {
    // 构建只包含变更字段的数据
    const queueData: Record<string, any> = {
      Info: { [key]: value },
    }

    const response = await queueApi.updateQueue({ queueId, data: queueData })

    if (response.code !== 200) {
      message.error(response.message || t('core.queue.toast.saveFailed'))
      // 保存失败时界面控件仍停在用户刚选的值，回读真实配置以纠正显示
      await refreshQueueConfig(queueId)
      return false
    }

    // 保存成功：更新接口不带最新 Info，本地应用这次变更即可，不再整份回读
    applyLocalQueueChange(queueId, key, value)
    return true
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存队列数据失败: ${errorMsg}`)
    message.error(t('core.queue.toast.saveQueueFailed', { error: errorMsg }))
    // 同上：网络异常等情况也要回读，避免界面与后端配置不一致
    await refreshQueueConfig(queueId)
    return false
  }
}

// 注意：配置保存已改为即时保存，由各个 @change 事件触发，不再使用 watch 自动保存

// 初始化
onMounted(async () => {
  try {
    await fetchQueues()
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`初始化失败: ${errorMsg}`)
    loading.value = false
  }
})

onUnmounted(() => {
  isMounted = false
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
}

.header-left {
  flex: 1;
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
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  margin: 20px 0;
}

/* 队列内容 */
.queue-content {
  display: flex;
  flex-direction: column;
  gap: var(--app-page-content-gap);
}

.queue-content > .ui-section-card {
  margin-bottom: 0;
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
  min-height: 600px;
}

/* 队列名称编辑 */
.queue-title-display {
  display: flex;
  align-items: center;
  gap: 8px;
}

.queue-title-text {
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

.queue-extra-settings :deep(.form-section) {
  margin-bottom: 0;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .queue-title-input {
    max-width: 100%;
  }

  .header-actions {
    width: 100%;
    display: flex;
    justify-content: center;
  }
}

.empty-title {
  color: var(--ant-color-text);
  font-size: 18px;
  font-weight: 500;
  margin-bottom: 8px;
}
.empty-description {
  color: var(--ant-color-text-secondary);
}
</style>

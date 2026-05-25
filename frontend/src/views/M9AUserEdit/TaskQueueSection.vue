<template>
  <div class="task-queue-section">
    <div class="section-header">
      <h3>任务队列配置</h3>
    </div>
    
    <a-row :gutter="24" class="task-queue-layout">
      <a-col :span="12" class="left-column">
        <div class="column-header">
          <span>任务队列</span>
          <a-dropdown v-model:visible="addTaskDropdownVisible" trigger="click">
            <a-button type="primary" size="middle" :loading="loading">
              <template #icon><PlusOutlined /></template>
              添加任务 ({{ availableTasks.length }})
            </a-button>
            <template #overlay>
              <a-menu @click="handleAddTask">
                <a-menu-item v-for="task in availableTasks" :key="task.name" :value="task.name">
                  {{ task.name }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
        </div>
        
        <div class="task-list">
          <!-- 预设模板区域（队列为空时显示） -->
          <div v-if="localTaskQueue.length === 0" class="preset-section">
            <div class="preset-card">
              <div class="preset-card-inner">
                <div class="preset-header">
                  <div class="preset-icon-wrap">
                    <span class="preset-icon">📋</span>
                  </div>
                  <div class="preset-info">
                    <h3 class="preset-name">{{ dailyPreset.name }}</h3>
                    <p class="preset-desc">{{ dailyPreset.description }}</p>
                  </div>
                  <div class="preset-badge">
                    <a-tag :color="matchedCount > 0 ? 'processing' : 'default'">
                      {{ matchedCount }}/{{ dailyPreset.taskNames.length }} 可用
                    </a-tag>
                  </div>
                </div>

                <div class="preset-tasks-preview">
                  <div class="task-chip" v-for="(item, idx) in matchedTasks" :key="idx">
                    <span class="task-dot" :class="{ 'task-dot-miss': !item.matched }"></span>
                    <span class="task-name" :class="{ 'task-name-miss': !item.matched }">{{ item.name }}</span>
                    <CheckCircleFilled v-if="item.matched" class="task-check" />
                    <CloseCircleFilled v-else class="task-check task-check-miss" />
                  </div>
                </div>

                <div class="preset-actions">
                  <a-button type="primary" size="large" block :loading="addingFromPreset"
                    :disabled="matchedCount === 0"
                    @click="addFromPreset">
                    <template #icon><ThunderboltOutlined /></template>
                    一键添加 {{ matchedCount }} 个任务
                  </a-button>
                  <p v-if="matchedCount < dailyPreset.taskNames.length" class="preset-hint">
                    部分任务未找到对应脚本，已自动跳过
                  </p>
                </div>
              </div>
            </div>
          </div>

          <draggable
            v-else
            v-model="localTaskQueue"
            item-key="name"
            :animation="200"
            ghost-class="ghost"
            chosen-class="chosen"
            drag-class="drag"
            class="task-queue-list"
            @end="onDragEnd"
          >
            <template #item="{ element: item, index }">
              <div
                class="draggable-task-item"
                :class="{ 'selected-item': selectedTaskIndex === index }"
                @click="selectTask(index)"
              >
                <div class="task-item-content">
                  <span class="task-name">{{ item.name }}</span>
                  <div class="task-actions">
                    <a-button
                      type="text"
                      size="middle"
                      :disabled="index === 0"
                      @click.stop="moveTaskUp(index)"
                    >
                      <UpOutlined />
                    </a-button>
                    <a-button
                      type="text"
                      size="middle"
                      :disabled="index === localTaskQueue.length - 1"
                      @click.stop="moveTaskDown(index)"
                    >
                      <DownOutlined />
                    </a-button>
                  </div>
                </div>
              </div>
            </template>
          </draggable>
        </div>
      </a-col>
      
      <a-col :span="12" class="right-column">
        <div class="column-header">
          <span>任务配置</span>
        </div>
        
        <div class="task-config" v-if="selectedTaskIndex !== null && taskQueue[selectedTaskIndex]">
          <div class="selected-task-name">
            {{ taskQueue[selectedTaskIndex].name }}
          </div>
          
          <TaskOptionRenderer
            :task-options="taskQueue[selectedTaskIndex].options"
            :option-definitions="getOptionDefinitions(selectedTaskIndex)"
            @update="handleOptionUpdate"
          />
          
          <a-popconfirm title="确定要删除这个任务吗？" ok-text="确定" cancel-text="取消" @confirm="deleteSelectedTask">
            <a-button danger block style="margin-top: 24px; height: 40px; font-size: 14px;">
              <template #icon><DeleteOutlined /></template>
              删除此任务
            </a-button>
          </a-popconfirm>
        </div>
        
        <div class="no-selection" v-else>
          <Empty description="请从左侧选择一个任务进行配置" />
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { PlusOutlined, UpOutlined, DownOutlined, DeleteOutlined, ThunderboltOutlined, CheckCircleFilled, CloseCircleFilled } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import draggable from 'vuedraggable'
import { Service } from '@/api'
import type { M9ATaskQueueItem, M9ATaskOption } from '@/types/script'
import TaskOptionRenderer from './TaskOptionRenderer.vue'

const logger = window.electronAPI.getLogger('M9A任务队列')

const props = defineProps<{
  scriptId: string
  taskQueue: M9ATaskQueueItem[]
  loading: boolean
}>()

const emit = defineEmits<{
  'update:taskQueue': [value: M9ATaskQueueItem[]]
}>()

const addTaskDropdownVisible = ref(false)
const availableTasks = ref<any[]>([])
const selectedTaskIndex = ref<number | null>(null)
const taskDefinitions = ref<Record<string, any>>({})
const localTaskQueue = ref<M9ATaskQueueItem[]>([])
const isDragging = ref(false)

// 预设模板常量
const dailyPreset = {
  name: '日常-长草',
  description: '无活动或换完商店时使用，进行常规刷取',
  taskNames: [
    '收取荒原',
    '每日心相（意志解析）',
    '常规作战',
    '自动深眠',
    '自动醒梦',
    '银行购物',
    '领取奖励',
    '使用兑换码',
  ],
}

// 一键添加状态
const addingFromPreset = ref(false)

// 匹配预设任务（根据 availableTasks 做名称匹配）
interface MatchedTaskItem {
  name: string
  matched: boolean
}

const matchedTasks = computed<MatchedTaskItem[]>(() => {
  return dailyPreset.taskNames.map(name => ({
    name,
    matched: availableTasks.value.some(t => t.name === name),
  }))
})

const matchedCount = computed(() => matchedTasks.value.filter(t => t.matched).length)

const buildDefaultOptions = (taskDef: any): M9ATaskOption[] => {
  const options: M9ATaskOption[] = []
  const optionNames = taskDef.option || []
  const optionDefs = taskDef._option_definitions || {}
  
  for (const optName of optionNames) {
    const optItem: M9ATaskOption = { name: optName, index: 0 }
    
    const optDef = optionDefs[optName]
    if (optDef) {
      if (optDef.type === 'input' && optDef.inputs) {
        optItem.input_values = {}
        for (const input of optDef.inputs) {
          if (input.default !== undefined) {
            if (input.pipeline_type === 'int') {
              optItem.input_values[input.name] = parseInt(input.default)
            } else {
              optItem.input_values[input.name] = input.default
            }
          }
        }
      } else if (optDef.cases && optDef.cases.length > 0) {
        const currentCase = optDef.cases[0]
        if (currentCase.option) {
          const subOpts = buildDefaultOptions({
            option: currentCase.option,
            _option_definitions: optionDefs
          })
          if (subOpts.length > 0) {
            optItem.sub_options = subOpts
          }
        }
      }
    }
    
    options.push(optItem)
  }
  
  return options
}

const loadAvailableTasks = async () => {
  try {
    logger.info(`loadAvailableTasks called, scriptId: ${props.scriptId}`)
    const response = await Service.getM9AAvailableTasksApiScriptsM9ATasksAvailablePost(props.scriptId)
    logger.info(`API response: ${JSON.stringify(response)}`)
    
    if (response && response.code === 200 && response.data) {
      availableTasks.value = []
      taskDefinitions.value = {}
      
      const RESERVED_ENTRIES = ['StartUp', 'Close1999', 'SwitchAccount']

      response.data.forEach((task: any) => {
        if (
          (!task.group || !task.group.includes('standalone')) &&
          !RESERVED_ENTRIES.includes(task.entry)
        ) {
          availableTasks.value.push(task)
          taskDefinitions.value[task.name] = task
        }
      })
      
      logger.info(`availableTasks set to: ${JSON.stringify(availableTasks.value)}`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载可用任务失败: ${errorMsg}`)
    message.error('加载可用任务失败')
  }
}

const handleAddTask = ({ key }: { key: string }) => {
  logger.info(`handleAddTask called, key: ${key}`)
  const taskDef = taskDefinitions.value[key]
  if (taskDef) {
    const newTask: M9ATaskQueueItem = {
      name: key,
      options: buildDefaultOptions(taskDef)
    }
    const newQueue = [...localTaskQueue.value, newTask]
    emit('update:taskQueue', newQueue)
    selectedTaskIndex.value = newQueue.length - 1
  }
  addTaskDropdownVisible.value = false
}

// 从预设模板一键添加任务
const addFromPreset = () => {
  const validTasks = matchedTasks.value.filter(t => t.matched)
  if (validTasks.length === 0) return

  addingFromPreset.value = true
  let newQueue = [...localTaskQueue.value]

  try {
    for (const task of validTasks) {
      const taskDef = taskDefinitions.value[task.name]
      if (taskDef) {
        newQueue.push({
          name: task.name,
          options: buildDefaultOptions(taskDef),
        })
      }
    }

    emit('update:taskQueue', newQueue)
    message.success(`成功添加 ${validTasks.length} 个任务`)
  } finally {
    addingFromPreset.value = false
  }
}

const selectTask = (index: number) => {
  selectedTaskIndex.value = index
}

const moveTaskUp = (index: number) => {
  if (index > 0) {
    const newQueue = [...localTaskQueue.value]
    ;[newQueue[index - 1], newQueue[index]] = [newQueue[index], newQueue[index - 1]]
    emit('update:taskQueue', newQueue)
    if (selectedTaskIndex.value === index) {
      selectedTaskIndex.value = index - 1
    } else if (selectedTaskIndex.value === index - 1) {
      selectedTaskIndex.value = index
    }
  }
}

const moveTaskDown = (index: number) => {
  if (index < localTaskQueue.value.length - 1) {
    const newQueue = [...localTaskQueue.value]
    ;[newQueue[index], newQueue[index + 1]] = [newQueue[index + 1], newQueue[index]]
    emit('update:taskQueue', newQueue)
    if (selectedTaskIndex.value === index) {
      selectedTaskIndex.value = index + 1
    } else if (selectedTaskIndex.value === index + 1) {
      selectedTaskIndex.value = index
    }
  }
}

const deleteTask = (index: number) => {
  const newQueue = localTaskQueue.value.filter((_, i) => i !== index)
  emit('update:taskQueue', newQueue)
  if (selectedTaskIndex.value === index) {
    selectedTaskIndex.value = newQueue.length > 0 ? Math.min(index, newQueue.length - 1) : null
  } else if (selectedTaskIndex.value !== null && selectedTaskIndex.value > index) {
    selectedTaskIndex.value -= 1
  }
}

const deleteSelectedTask = () => {
  if (selectedTaskIndex.value !== null) {
    deleteTask(selectedTaskIndex.value)
  }
}

const getOptionDefinitions = (index: number) => {
  if (index === null || !localTaskQueue.value[index]) return {}
  const taskName = localTaskQueue.value[index].name
  return taskDefinitions.value[taskName]?._option_definitions || {}
}

const handleOptionUpdate = (newOptions: M9ATaskOption[]) => {
  if (selectedTaskIndex.value !== null) {
    const newQueue = [...localTaskQueue.value]
    newQueue[selectedTaskIndex.value] = {
      ...newQueue[selectedTaskIndex.value],
      options: newOptions
    }
    emit('update:taskQueue', newQueue)
  }
}

const onDragEnd = () => {
  isDragging.value = true
  emit('update:taskQueue', localTaskQueue.value)
  nextTick(() => {
    isDragging.value = false
  })
}

watch(
  () => props.taskQueue,
  (newQueue) => {
    if (!isDragging.value) {
      localTaskQueue.value = [...newQueue]
    }
  },
  { immediate: true, deep: true }
)

onMounted(() => {
  loadAvailableTasks()
})
</script>

<style scoped>
.task-queue-section {
  margin-bottom: 32px;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

.task-queue-layout {
  min-height: 400px;
}

.left-column,
.right-column {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.column-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.task-list {
  flex: 1;
  overflow-y: auto;
}

.task-queue-list {
  height: 100%;
  border: 1px solid var(--ant-color-border);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  overflow: hidden;
}

.draggable-task-item {
  padding: 16px 20px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  transition: all 0.25s ease;
  border-left: 3px solid transparent;
}

/* 未选中状态的 hover 效果 */
.draggable-task-item:not(.selected-item):hover {
  background-color: var(--ant-color-primary-bg-hover);
  border-left-color: var(--ant-color-primary);
}

.draggable-task-item:last-child {
  border-bottom: none;
}

.task-item-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
  width: 100%;
}

.task-name {
  flex: 1;
  font-size: 15px;
  font-weight: 500;
  color: var(--ant-color-text);
}

.task-actions {
  display: flex;
  gap: 8px;
}

.task-actions :deep(.ant-btn) {
  transition: all 0.2s ease;
  border-radius: 6px;
}

.task-actions :deep(.ant-btn:hover) {
  background-color: var(--ant-color-primary-bg-hover);
}

/* 选中状态的样式（始终显示，使用 !important 确保不被 hover 覆盖）*/
.selected-item {
  background-color: var(--ant-color-primary-bg) !important;
  border-left-color: var(--ant-color-primary) !important;
}

/* 选中 + hover 时：保持高亮不变 */
.selected-item:hover {
  background-color: var(--ant-color-primary-bg) !important;
  border-left-color: var(--ant-color-primary-hover, #1890ff) !important;
}

.task-config {
  padding: 24px;
  border: 1px solid var(--ant-color-border);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  background: var(--ant-color-bg-container);
}

.selected-task-name {
  font-size: 20px;
  font-weight: 700;
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 10px;
}

.no-selection {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 300px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
}

.ghost {
  opacity: 0.5;
  background: var(--ant-color-primary-bg);
}

.chosen {
  background-color: var(--ant-color-primary-bg);
}

.drag {
  opacity: 0.8;
}

/* 预设模板区域 */
.preset-section {
  height: 100%;
}

.preset-card {
  height: 100%;
  border-radius: 10px;
  overflow: hidden;
  animation: presetFadeIn 0.4s ease-out;
}

.preset-card-inner {
  background: linear-gradient(135deg, rgba(24, 144, 255, 0.04) 0%, rgba(24, 144, 255, 0.01) 100%);
  border: 1px solid rgba(24, 144, 255, 0.15);
  border-radius: 10px;
  padding: 18px 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  transition: all 0.3s ease;
}

.preset-card-inner:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 4px 16px rgba(24, 144, 255, 0.1);
}

.preset-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}

.preset-icon-wrap {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  background: linear-gradient(135deg, #1677ff 0%, #4096ff 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.25);
}

.preset-icon {
  font-size: 20px;
  line-height: 1;
}

.preset-info {
  flex: 1;
  min-width: 0;
}

.preset-name {
  margin: 0 0 3px 0;
  font-size: 16px;
  font-weight: 700;
  color: var(--ant-color-text);
  letter-spacing: -0.2px;
}

.preset-desc {
  margin: 0;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
}

.preset-badge {
  flex-shrink: 0;
}

.preset-tasks-preview {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 16px;
  padding: 10px 12px;
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border-secondary);
}

.task-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 3px 10px 3px 7px;
  border-radius: 20px;
  font-size: 13px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text);
  transition: all 0.2s ease;
}

.task-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--ant-color-success);
  flex-shrink: 0;
  box-shadow: 0 0 4px rgba(82, 196, 26, 0.35);
}

.task-dot-miss {
  background: var(--ant-color-text-disabled);
  box-shadow: none;
}

.task-name {
  white-space: nowrap;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.task-name-miss {
  text-decoration: line-through;
  opacity: 0.45;
}

.task-check {
  font-size: 11px;
  color: var(--ant-color-success);
  flex-shrink: 0;
}

.task-check-miss {
  color: var(--ant-color-text-disabled);
}

.preset-actions {
  margin-top: auto;
}

.preset-actions :deep(.ant-btn-primary) {
  height: 40px;
  font-size: 14px;
  font-weight: 600;
  border-radius: 8px;
  background: linear-gradient(135deg, #1677ff 0%, #4096ff 100%);
  border: none;
  box-shadow: 0 2px 8px rgba(22, 119, 255, 0.2);
  transition: all 0.25s ease;
}

.preset-actions :deep(.ant-btn-primary:hover:not(:disabled)) {
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(22, 119, 255, 0.3);
}

.preset-actions :deep(.ant-btn-primary:active:not(:disabled)) {
  transform: translateY(0);
  box-shadow: 0 2px 6px rgba(22, 119, 255, 0.2);
}

.preset-hint {
  margin: 8px 0 0 0;
  text-align: center;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  line-height: 1.4;
}

@keyframes presetFadeIn {
  from {
    opacity: 0;
    transform: translateY(12px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>

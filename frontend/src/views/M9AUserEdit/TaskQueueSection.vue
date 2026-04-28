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
            <a-button type="primary" size="small" :loading="loading">
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
          <draggable
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
                      size="small"
                      :disabled="index === 0"
                      @click.stop="moveTaskUp(index)"
                    >
                      <UpOutlined />
                    </a-button>
                    <a-button
                      type="text"
                      size="small"
                      :disabled="index === localTaskQueue.length - 1"
                      @click.stop="moveTaskDown(index)"
                    >
                      <DownOutlined />
                    </a-button>
                    <a-button
                      type="text"
                      size="small"
                      danger
                      @click.stop="deleteTask(index)"
                    >
                      <DeleteOutlined />
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
          
          <a-button
            type="primary"
            danger
            block
            style="margin-top: 24px"
            @click="deleteSelectedTask"
          >
            删除此任务
          </a-button>
        </div>
        
        <div class="no-selection" v-else>
          <Empty description="请从左侧选择一个任务进行配置" />
        </div>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { PlusOutlined, UpOutlined, DownOutlined, DeleteOutlined } from '@ant-design/icons-vue'
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
      
      response.data.forEach((task: any) => {
        if (!task.group || !task.group.includes('standalone')) {
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
  emit('update:taskQueue', localTaskQueue.value)
}

watch(
  () => props.taskQueue,
  (newQueue) => {
    localTaskQueue.value = [...newQueue]
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
  border-radius: 8px;
}

.draggable-task-item {
  padding: 12px 16px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  transition: background-color 0.2s;
}

.draggable-task-item:hover {
  background-color: var(--ant-color-primary-bg-hover);
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
}

.task-actions {
  display: flex;
  gap: 4px;
}

.selected-item {
  background-color: var(--ant-color-primary-bg);
}

.task-config {
  padding: 16px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
}

.selected-task-name {
  font-size: 18px;
  font-weight: 600;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border);
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
</style>

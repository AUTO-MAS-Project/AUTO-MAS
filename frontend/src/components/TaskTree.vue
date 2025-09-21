<template>
  <div class="task-tree-container">
    <div v-if="taskData.length === 0" class="empty-state">
      <a-empty description="暂无任务数据" />
    </div>
    <div v-else class="task-tree">
      <div 
        v-for="script in taskData" 
        :key="script.script_id"
        class="script-card"
      >
        <!-- 脚本级别 -->
        <div 
          class="script-header"
          @click="toggleScript(script.script_id)"
        >
          <div class="script-content">
            <div class="script-info">
              <CaretDownOutlined 
                v-if="expandedScripts.has(script.script_id)"
                class="expand-icon"
              />
              <CaretRightOutlined 
                v-else
                class="expand-icon"
              />
              <span class="script-name">{{ script.name }}</span>
              <span class="user-count" v-if="script.user_list && script.user_list.length > 0">
                ({{ script.user_list.length }}个用户)
              </span>
            </div>
            <a-tag 
              :color="getStatusColor(script.status)" 
              size="small"
              class="status-tag"
            >
              {{ script.status }}
            </a-tag>
          </div>
        </div>
        
        <!-- 用户列表 -->
        <div 
          v-show="expandedScripts.has(script.script_id)"
          class="user-list"
        >
          <div v-if="!script.user_list || script.user_list.length === 0" class="no-users">
            <div class="no-users-content">
              <span class="no-users-text">暂无用户</span>
            </div>
          </div>
          <div 
            v-for="(user, index) in script.user_list" 
            :key="user.user_id"
            class="user-item"
            :class="{ 'last-item': index === script.user_list.length - 1 }"
          >
            <div class="user-content">
              <span class="user-name">{{ user.name }}</span>
              <a-tag 
                :color="getStatusColor(user.status)" 
                size="small"
                class="status-tag"
              >
                {{ user.status }}
              </a-tag>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { CaretDownOutlined, CaretRightOutlined } from '@ant-design/icons-vue'

interface User {
  user_id: string
  status: string
  name: string
}

interface Script {
  script_id: string
  status: string
  name: string
  user_list: User[]
}

interface Props {
  taskData: Script[]
}

const props = defineProps<Props>()

// 展开的脚本集合
const expandedScripts = ref<Set<string>>(new Set())

// 切换脚本展开状态
const toggleScript = (scriptId: string) => {
  if (expandedScripts.value.has(scriptId)) {
    expandedScripts.value.delete(scriptId)
  } else {
    expandedScripts.value.add(scriptId)
  }
}

// 获取状态颜色 - 使用更全面的映射和后备逻辑
const getStatusColor = (status: string) => {
  // 精确匹配优先
  const exactStatusColorMap: Record<string, string> = {
    '等待': 'orange',
    '排队': 'orange',
    '挂起': 'orange',
    '运行中': 'blue',
    '运行': 'blue',
    '进行中': 'blue',
    '执行中': 'blue',
    '已完成': 'green',
    '完成': 'green',
    '成功': 'green',
    '失败': 'red',
    '异常': 'red',
    '错误': 'red',
    '暂停': 'gray',
    '取消': 'default',
    '停止': 'default'
  }
  
  // 先尝试精确匹配
  if (exactStatusColorMap[status]) {
    return exactStatusColorMap[status]
  }
  
  // 使用正则表达式进行模糊匹配（作为后备）
  if (/成功|完成|已完成/.test(status)) return 'green'
  if (/失败|错误|异常/.test(status)) return 'red'
  if (/等待|排队|挂起/.test(status)) return 'orange'
  if (/进行|执行|运行/.test(status)) return 'blue'
  if (/暂停|停止/.test(status)) return 'gray'
  
  return 'default'
}

// 初始化时展开所有脚本
const initExpandedScripts = () => {
  console.log('初始化展开脚本，数据:', props.taskData)
  props.taskData.forEach(script => {
    console.log('添加展开脚本:', script.script_id, script.name)
    expandedScripts.value.add(script.script_id)
  })
  console.log('展开的脚本集合:', Array.from(expandedScripts.value))
}

// 监听数据变化，自动展开新的脚本
const updateExpandedScripts = () => {
  console.log('更新展开脚本，当前数据:', props.taskData)
  props.taskData.forEach(script => {
    if (!expandedScripts.value.has(script.script_id)) {
      console.log('添加新脚本到展开列表:', script.script_id, script.name)
      expandedScripts.value.add(script.script_id)
    }
  })
  console.log('更新后展开的脚本集合:', Array.from(expandedScripts.value))
}

// 监听 taskData 变化
watch(() => props.taskData, (newData) => {
  console.log('TaskData 发生变化:', newData)
  if (newData && newData.length > 0) {
    updateExpandedScripts()
  }
}, { immediate: true, deep: true })

// 暴露方法供父组件调用
defineExpose({
  expandAll: () => {
    props.taskData.forEach(script => {
      expandedScripts.value.add(script.script_id)
    })
  },
  collapseAll: () => {
    expandedScripts.value.clear()
  },
  updateExpandedScripts
})
</script>

<style scoped>
.task-tree-container {
  width: 100%;
  height: 100%;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 200px;
}

.task-tree {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.script-card {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
  transition: all 0.3s ease;
}

.script-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: var(--ant-color-primary-border);
}

.script-header {
  cursor: pointer;
  padding: 12px 16px;
  background: linear-gradient(135deg, var(--ant-color-fill-quaternary) 0%, var(--ant-color-fill-tertiary) 100%);
  transition: all 0.2s ease;
}

.script-header:hover {
  background: linear-gradient(135deg, var(--ant-color-fill-tertiary) 0%, var(--ant-color-fill-secondary) 100%);
}

.script-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.script-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.expand-icon {
  font-size: 14px;
  color: var(--ant-color-primary);
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.expand-icon:hover {
  color: var(--ant-color-primary-hover);
}

.script-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
  word-break: break-word;
}

.user-count {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  font-weight: normal;
}

.status-tag {
  flex-shrink: 0;
}

.user-list {
  background: var(--ant-color-bg-layout);
}

.no-users {
  padding: 16px;
}

.no-users-content {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 12px;
  background: var(--ant-color-fill-quaternary);
  border-radius: 6px;
  border: 1px dashed var(--ant-color-border);
}

.no-users-text {
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
  font-style: italic;
}

.user-item {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.user-item.last-item {
  border-bottom: none;
}

.user-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  transition: all 0.2s ease;
}

.user-content:hover {
  background: var(--ant-color-fill-quaternary);
}

.user-name {
  flex: 1;
  font-size: 14px;
  color: var(--ant-color-text);
  word-break: break-word;
  font-weight: 500;
}

/* 深色模式适配 */
[data-theme="dark"] .script-card,
.dark .script-card {
  background: #1f1f1f;
  border-color: #424242;
}

[data-theme="dark"] .script-card:hover,
.dark .script-card:hover {
  box-shadow: 0 2px 8px rgba(255, 255, 255, 0.1);
  border-color: #1890ff;
}

[data-theme="dark"] .script-header,
.dark .script-header {
  background: linear-gradient(135deg, #262626 0%, #303030 100%);
}

[data-theme="dark"] .script-header:hover,
.dark .script-header:hover {
  background: linear-gradient(135deg, #303030 0%, #383838 100%);
}

[data-theme="dark"] .script-name,
.dark .script-name {
  color: #ffffff;
}

[data-theme="dark"] .user-count,
.dark .user-count {
  color: #8c8c8c;
}

[data-theme="dark"] .user-list,
.dark .user-list {
  background: #141414;
}

[data-theme="dark"] .no-users-content,
.dark .no-users-content {
  background: #262626;
  border-color: #424242;
}

[data-theme="dark"] .no-users-text,
.dark .no-users-text {
  color: #8c8c8c;
}

[data-theme="dark"] .user-item,
.dark .user-item {
  border-bottom-color: #424242;
}

[data-theme="dark"] .user-content:hover,
.dark .user-content:hover {
  background: #262626;
}

[data-theme="dark"] .user-name,
.dark .user-name {
  color: #ffffff;
}

[data-theme="dark"] .expand-icon,
.dark .expand-icon {
  color: #1890ff;
}

[data-theme="dark"] .expand-icon:hover,
.dark .expand-icon:hover {
  color: #40a9ff;
}

/* 浅色模式适配 */
[data-theme="light"] .script-card,
.light .script-card,
.script-card {
  background: #ffffff;
  border-color: #d9d9d9;
}

[data-theme="light"] .script-card:hover,
.light .script-card:hover,
.script-card:hover {
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: #1890ff;
}

[data-theme="light"] .script-header,
.light .script-header,
.script-header {
  background: linear-gradient(135deg, #fafafa 0%, #f5f5f5 100%);
}

[data-theme="light"] .script-header:hover,
.light .script-header:hover,
.script-header:hover {
  background: linear-gradient(135deg, #f5f5f5 0%, #f0f0f0 100%);
}

[data-theme="light"] .script-name,
.light .script-name,
.script-name {
  color: #262626;
}

[data-theme="light"] .user-count,
.light .user-count,
.user-count {
  color: #8c8c8c;
}

[data-theme="light"] .user-list,
.light .user-list,
.user-list {
  background: #fafafa;
}

[data-theme="light"] .no-users-content,
.light .no-users-content,
.no-users-content {
  background: #f5f5f5;
  border-color: #d9d9d9;
}

[data-theme="light"] .no-users-text,
.light .no-users-text,
.no-users-text {
  color: #8c8c8c;
}

[data-theme="light"] .user-item,
.light .user-item,
.user-item {
  border-bottom-color: #f0f0f0;
}

[data-theme="light"] .user-content:hover,
.light .user-content:hover,
.user-content:hover {
  background: #f5f5f5;
}

[data-theme="light"] .user-name,
.light .user-name,
.user-name {
  color: #262626;
}

[data-theme="light"] .expand-icon,
.light .expand-icon,
.expand-icon {
  color: #1890ff;
}

[data-theme="light"] .expand-icon:hover,
.light .expand-icon:hover,
.expand-icon:hover {
  color: #40a9ff;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .task-tree {
    gap: 8px;
  }
  
  .script-header {
    padding: 10px 12px;
  }
  
  .script-name {
    font-size: 14px;
  }
  
  .user-count {
    font-size: 11px;
  }
  
  .user-content {
    padding: 8px 12px;
  }
  
  .user-name {
    font-size: 13px;
  }
  
  .no-users {
    padding: 12px;
  }
}

/* 动画效果 */
.user-list {
  animation: slideDown 0.3s ease-out;
}

@keyframes slideDown {
  from {
    opacity: 0;
    transform: translateY(-10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.script-card {
  animation: fadeIn 0.3s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
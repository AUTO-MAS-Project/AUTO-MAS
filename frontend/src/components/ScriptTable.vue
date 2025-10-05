<template>
  <div class="scripts-grid">
    <!-- 使用vuedraggable包装脚本列表 -->
    <draggable
      v-model="localScripts"
      item-key="id"
      :animation="200"
      ghost-class="script-ghost"
      chosen-class="script-chosen"
      drag-class="script-drag"
      class="draggable-scripts"
      @end="onScriptDragEnd"
    >
      <template #item="{ element: script }">
        <div :key="script.id" class="script-wrapper">
          <a-card :hoverable="true" class="script-card" :body-style="{ padding: '0' }">
            <!-- 脚本头部信息 -->
            <div class="script-header">
              <div class="script-info">
                <div class="script-logo-container">
                  <img
                    v-if="script.type === 'MAA'"
                    src="@/assets/MAA.png"
                    alt="MAA"
                    class="script-logo"
                  />
                  <img v-else src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="script-logo" />
                </div>
                <div class="script-details">
                  <h3 class="script-name">{{ script.name }}</h3>
                  <a-tag :color="script.type === 'MAA' ? 'blue' : 'green'" class="script-type">
                    {{ script.type }}
                  </a-tag>
                </div>
              </div>
              <div class="header-actions">
                <a-button
                  v-if="script.type === 'MAA' && !props.activeConnections.has(script.id)"
                  type="primary"
                  ghost
                  size="middle"
                  @click="handleStartMAAConfig(script)"
                >
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置MAA
                </a-button>
                <a-button
                  v-if="script.type === 'MAA' && props.activeConnections.has(script.id)"
                  type="primary"
                  size="middle"
                  style="background: #52c41a; border-color: #52c41a"
                  @click="handleSaveMAAConfig(script)"
                >
                  <template #icon>
                    <SaveOutlined />
                  </template>
                  保存配置
                </a-button>
                <a-button type="default" size="middle" @click="handleEdit(script)">
                  <template #icon>
                    <EditOutlined />
                  </template>
                  编辑脚本
                </a-button>
                <a-button
                  type="default"
                  size="middle"
                  class="action-button add-button"
                  @click="handleAddUser(script)"
                >
                  <template #icon>
                    <UserAddOutlined />
                  </template>
                  添加用户
                </a-button>
                <a-popconfirm
                  title="确定要删除这个脚本吗？"
                  description="删除后将无法恢复，请谨慎操作"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="handleDelete(script)"
                >
                  <a-button danger size="middle" class="action-button delete-button">
                    <template #icon>
                      <DeleteOutlined />
                    </template>
                    删除脚本
                  </a-button>
                </a-popconfirm>
              </div>
            </div>

            <!-- 用户列表 -->
            <div v-if="script.users && script.users.length > 0" class="users-section">
              <!-- 使用vuedraggable包装用户列表 -->
              <draggable
                v-model="script.users"
                item-key="id"
                :animation="200"
                ghost-class="user-ghost"
                chosen-class="user-chosen"
                drag-class="user-drag"
                class="users-list"
                @end="(evt: any) => onUserDragEnd(evt, script)"
              >
                <template #item="{ element: user }">
                  <div :key="user.id" class="user-item">
                    <div class="user-info">
                      <div class="user-details-row">
                        <div class="user-name-section">
                          <span class="user-name">{{ user.Info.Name }}</span>
                          <!-- 只有MAA脚本才显示服务器标签 -->
                          <a-tag
                            v-if="script.type === 'MAA'"
                            :color="user.Info.Server === 'Official' ? 'blue' : 'purple'"
                            class="server-tag"
                          >
                            {{ user.Info.Server === 'Official' ? '官服' : 'B服' }}
                          </a-tag>
                        </div>

                        <!-- 用户详细信息 - MAA脚本用户 -->
                        <div v-if="script.type === 'MAA'" class="user-info-tags">
                          <!-- 剿灭模式 -->
                          <a-tag
                            v-if="
                              user.Info.Annihilation &&
                              user.Info.Annihilation !== '-' &&
                              user.Info.Annihilation !== ''
                            "
                            class="info-tag"
                            color="cyan"
                          >
                            剿灭：{{
                              ANNIHILATION_MAP[user.Info.Annihilation] ?? user.Info.Annihilation
                            }}
                          </a-tag>

                          <!-- 森空岛签到 -->
                          <a-tag
                            v-if="user.Info.IfSkland !== undefined && user.Info.IfSkland !== null"
                            class="info-tag"
                            :color="user.Info.IfSkland ? 'green' : 'blue'"
                          >
                            森空岛: {{ user.Info.IfSkland ? '开启' : '关闭' }}
                          </a-tag>

                          <!-- 剩余天数 -->
                          <a-tag
                            v-if="
                              user.Info.RemainedDay !== undefined && user.Info.RemainedDay !== null
                            "
                            class="info-tag"
                            :color="getRemainingDayColor(user.Info.RemainedDay)"
                          >
                            {{ getRemainingDayText(user.Info.RemainedDay) }}
                          </a-tag>

                          <!-- 基建模式 -->
                          <a-tag
                            v-if="
                              user.Info.InfrastMode &&
                              user.Info.InfrastMode !== '-' &&
                              user.Info.InfrastMode !== ''
                            "
                            class="info-tag"
                            color="purple"
                          >
                            基建: {{ user.Info.InfrastMode === 'Normal' ? '普通' : '自定义' }}
                          </a-tag>

                          <!-- 关卡信息 - 根据是否使用计划表配置显示不同内容 -->
                          <template v-if="user.Info.Stage === '1-7' && props.currentPlanData">
                            <!-- 计划表模式信息 -->
                            <a-tag
                              v-if="props.currentPlanData.Info?.Mode"
                              class="info-tag"
                              color="purple"
                            >
                              模式:
                              {{ props.currentPlanData.Info.Mode === 'ALL' ? '全局' : '周计划' }}
                            </a-tag>

                            <!-- 显示计划表中的所有关卡 -->
                            <template v-for="(stageInfo, index) in getAllPlanStages()" :key="index">
                              <a-tag class="info-tag" color="green">
                                {{ stageInfo.label }}: {{ stageInfo.value }}
                              </a-tag>
                            </template>

                            <!-- 如果没有配置任何关卡，显示提示 -->
                            <a-tag
                              v-if="getAllPlanStages().length === 0"
                              class="info-tag"
                              color="orange"
                            >
                              关卡: 计划表未配置
                            </a-tag>
                          </template>

                          <!-- 用户自定义关卡 -->
                          <template v-else>
                            <a-tag
                              v-if="user.Info.Stage"
                              class="info-tag"
                              :color="getStageTagColor(user.Info.Stage)"
                            >
                              关卡: {{ getDisplayStage(user.Info.Stage) }}
                            </a-tag>
                          </template>

                          <!-- 额外关卡 - 只有不为-或空时才显示 -->
                          <a-tag
                            v-if="
                              user.Info.Stage_1 &&
                              user.Info.Stage_1 !== '-' &&
                              user.Info.Stage_1 !== ''
                            "
                            class="info-tag"
                            color="geekblue"
                          >
                            关卡1: {{ user.Info.Stage_1 }}
                          </a-tag>

                          <a-tag
                            v-if="
                              user.Info.Stage_2 &&
                              user.Info.Stage_2 !== '-' &&
                              user.Info.Stage_2 !== ''
                            "
                            class="info-tag"
                            color="geekblue"
                          >
                            关卡2: {{ user.Info.Stage_2 }}
                          </a-tag>

                          <a-tag
                            v-if="
                              user.Info.Stage_3 &&
                              user.Info.Stage_3 !== '-' &&
                              user.Info.Stage_3 !== ''
                            "
                            class="info-tag"
                            color="geekblue"
                          >
                            关卡3: {{ user.Info.Stage_3 }}
                          </a-tag>

                          <a-tag
                            v-if="
                              user.Info.Stage_Remain &&
                              user.Info.Stage_Remain !== '-' &&
                              user.Info.Stage_Remain !== ''
                            "
                            class="info-tag"
                            color="geekblue"
                          >
                            剩余关卡: {{ user.Info.Stage_Remain }}
                          </a-tag>

                          <a-tag class="info-tag" color="magenta">
                            备注: {{ truncateText(user.Info.Notes) }}
                          </a-tag>
                        </div>
                        <!-- 用户详细信息 - 通用脚本用户 -->
                        <div v-if="script.type === 'General'" class="user-info-tags">
                          <!-- 剩余天数 -->
                          <a-tag
                            v-if="
                              user.Info.RemainedDay !== undefined && user.Info.RemainedDay !== null
                            "
                            class="info-tag"
                            :color="getRemainingDayColor(user.Info.RemainedDay)"
                          >
                            {{ getRemainingDayText(user.Info.RemainedDay) }}
                          </a-tag>

                          <a-tag class="info-tag" color="magenta">
                            备注: {{ truncateText(user.Info.Notes) }}
                          </a-tag>
                        </div>
                      </div>
                    </div>

                    <div class="user-controls">
                      <div class="user-status">
                        <a-switch
                          :checked="user.Info.Status"
                          :checked-children="'启用'"
                          :un-checked-children="'禁用'"
                          class="status-switch"
                          @click="handleToggleUserStatus(user)"
                        />
                      </div>

                      <div class="user-actions">
                        <a-tooltip title="编辑用户配置">
                          <a-button
                            type="default"
                            size="middle"
                            class="user-action-btn"
                            @click="handleEditUser(user)"
                          >
                            <template #icon>
                              <EditOutlined />
                            </template>
                            编辑
                          </a-button>
                        </a-tooltip>
                        <a-popconfirm
                          title="确定要删除这个用户吗？"
                          description="删除后将无法恢复"
                          ok-text="确定"
                          cancel-text="取消"
                          @confirm="handleDeleteUser(user)"
                        >
                          <a-tooltip title="删除用户">
                            <a-button type="default" size="middle" danger class="user-action-btn">
                              <template #icon>
                                <DeleteOutlined />
                              </template>
                              删除
                            </a-button>
                          </a-tooltip>
                        </a-popconfirm>
                      </div>
                    </div>
                  </div>
                </template>
              </draggable>
            </div>

            <!-- 空状态 -->
            <div v-else class="empty-users">
              <div class="empty-content">
                <img src="@/assets/NoData.png" alt="无数据" class="empty-image" />
              </div>
            </div>
          </a-card>
        </div>
      </template>
    </draggable>
  </div>
</template>

<script setup lang="ts">
import type { Script, User } from '../types/script'
import {
  DeleteOutlined,
  EditOutlined,
  SaveOutlined,
  SettingOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { ref, watch } from 'vue'
import { Service } from '@/api'
import { message } from 'ant-design-vue'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  currentPlanData?: Record<string, any> | null
}

interface Emits {
  (e: 'edit', script: Script): void

  (e: 'delete', script: Script): void

  (e: 'addUser', script: Script): void

  (e: 'editUser', user: User): void

  (e: 'deleteUser', user: User): void

  (e: 'startMaaConfig', script: Script): void

  (e: 'saveMaaConfig', script: Script): void

  (e: 'toggleUserStatus', user: User): void

  (e: 'scriptsReordered', scripts: Script[]): void
}

const ANNIHILATION_MAP: Record<string, string> = {
  Annihilation: '当期剿灭',
  'Chernobog@Annihilation': '切尔诺伯格',
  'LungmenOutskirts@Annihilation': '龙门外环',
  'LungmenDowntown@Annihilation': '龙门市区',
  Close: '关闭',
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 本地脚本列表状态
const localScripts = ref<Script[]>([])

// 监听props变化，更新本地状态
watch(
  () => props.scripts,
  newScripts => {
    localScripts.value = [...newScripts]
  },
  { immediate: true, deep: true }
)

const handleEdit = (script: Script) => {
  emit('edit', script)
}

const handleDelete = (script: Script) => {
  emit('delete', script)
}

const handleAddUser = (script: Script) => {
  emit('addUser', script)
}

const handleEditUser = (user: User) => {
  emit('editUser', user)
}

const handleDeleteUser = (user: User) => {
  emit('deleteUser', user)
}

const handleStartMAAConfig = (script: Script) => {
  emit('startMaaConfig', script)
}

const handleSaveMAAConfig = (script: Script) => {
  emit('saveMaaConfig', script)
}

const handleToggleUserStatus = (user: User) => {
  emit('toggleUserStatus', user)
}

const truncateText = (text: string, maxLength: number = 10): string => {
  if (!text || text.length === 0) return '无'
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}

// 获取剩余天数的颜色
const getRemainingDayColor = (remainedDay: number): string => {
  if (remainedDay === -1) return 'gold'
  if (remainedDay === 0) return 'red'
  if (remainedDay <= 3) return 'orange'
  if (remainedDay <= 7) return 'yellow'
  if (remainedDay <= 30) return 'blue'
  return 'green'
}

// 获取关卡标签颜色
const getStageTagColor = (stage: string): string => {
  if (stage === '1-7') return 'green' // 使用计划表配置用绿色
  return 'blue' // 自定义关卡用蓝色
}

// 获取剩余天数的显示文本
const getRemainingDayText = (remainedDay: number): string => {
  if (remainedDay === -1) return '剩余天数: 长期有效'
  if (remainedDay === 0) return '剩余天数: 已到期'
  return `剩余天数: ${remainedDay}天`
}

// 获取关卡的显示文本
const getDisplayStage = (stage: string): string => {
  if (stage === '-') return '未选择'

  // 如果是默认值且有计划表数据，显示计划表中的实际关卡
  if (stage === '1-7' && props.currentPlanData) {
    const planStage = getCurrentPlanStage()
    if (planStage && planStage !== '-') {
      return planStage
    }
    return '使用计划表配置'
  }

  return stage
}

// 从计划表获取当前关卡
const getCurrentPlanStage = (): string => {
  if (!props.currentPlanData) return ''

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = props.currentPlanData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    // 如果是周模式，根据当前星期几获取对应配置
    const today = new Date().getDay() // 0=Sunday, 1=Monday, ...
    const dayMap = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    timeKey = dayMap[today]
  }

  // 从计划表获取关卡配置
  const timeConfig = props.currentPlanData[timeKey]
  if (!timeConfig) return ''

  // 获取主要关卡
  if (timeConfig.Stage && timeConfig.Stage !== '-') {
    return timeConfig.Stage
  }

  // 如果主要关卡为空，尝试获取第一个备选关卡
  const backupStages = [timeConfig.Stage_1, timeConfig.Stage_2, timeConfig.Stage_3]
  for (const stage of backupStages) {
    if (stage && stage !== '-') {
      return stage
    }
  }

  return ''
}

// 从计划表获取所有配置的关卡
const getAllPlanStages = (): Array<{ label: string; value: string }> => {
  if (!props.currentPlanData) return []

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = props.currentPlanData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    // 如果是周模式，根据当前星期几获取对应配置
    const today = new Date().getDay() // 0=Sunday, 1=Monday, ...
    const dayMap = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    timeKey = dayMap[today]
  }

  // 从计划表获取关卡配置
  const timeConfig = props.currentPlanData[timeKey]
  if (!timeConfig) return []

  const stages: Array<{ label: string; value: string }> = []

  // 主关卡
  if (timeConfig.Stage && timeConfig.Stage !== '-') {
    stages.push({ label: '关卡', value: timeConfig.Stage })
  }

  // 备选关卡
  if (timeConfig.Stage_1 && timeConfig.Stage_1 !== '-') {
    stages.push({ label: '关卡1', value: timeConfig.Stage_1 })
  }
  if (timeConfig.Stage_2 && timeConfig.Stage_2 !== '-') {
    stages.push({ label: '关卡2', value: timeConfig.Stage_2 })
  }
  if (timeConfig.Stage_3 && timeConfig.Stage_3 !== '-') {
    stages.push({ label: '关卡3', value: timeConfig.Stage_3 })
  }

  // 剩余关卡
  if (timeConfig.Stage_Remain && timeConfig.Stage_Remain !== '-') {
    stages.push({ label: '剩余关卡', value: timeConfig.Stage_Remain })
  }

  return stages
}

// 处理脚本拖拽结束
const onScriptDragEnd = async () => {
  try {
    // 获取当前脚本ID顺序
    const currentScriptIds = localScripts.value.map(script => script.id)
    // 获取原始脚本ID顺序
    const originalScriptIds = props.scripts.map(script => script.id)

    // 检查顺序是否发生变化
    const hasOrderChanged =
      currentScriptIds.length !== originalScriptIds.length ||
      currentScriptIds.some((id, index) => id !== originalScriptIds[index])

    // 如果顺序没有变化，则不触发后端更新
    if (!hasOrderChanged) {
      console.log('脚本顺序未发生变化，跳过后端更新')
      return
    }

    // 顺序发生变化，调用后端API更新
    await Service.reorderScriptApiScriptsOrderPost({
      indexList: currentScriptIds,
    })

    // 通知父组件脚本顺序已更改
    emit('scriptsReordered', localScripts.value)

    message.success('脚本排序已保存')
  } catch (error) {
    console.error('保存脚本排序失败:', error)
    message.error('保存脚本排序失败')

    // 恢复原始顺序
    localScripts.value = [...props.scripts]
  }
}

// 处理用户拖拽结束
const onUserDragEnd = async (_evt: any, script: Script) => {
  try {
    const userIds = script.users?.map(user => user.id) || []
    await Service.reorderUserApiScriptsUserOrderPost({
      scriptId: script.id,
      indexList: userIds,
    })

    message.success('用户排序已保存')
  } catch (error) {
    console.error('保存用户排序失败:', error)
    message.error('保存用户排序失败')

    // 恢复原始顺序 - 找到原始脚本并恢复用户顺序
    const originalScript = props.scripts.find(s => s.id === script.id)
    if (originalScript && originalScript.users) {
      script.users = [...originalScript.users]
    }
  }
}
</script>

<style scoped>
.scripts-grid {
  width: 100%;
}

/* 拖拽样式 */
.draggable-scripts {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.script-wrapper {
  width: 100%;
}

.script-ghost {
  opacity: 0.5;
  transform: rotate(2deg);
}

.script-chosen {
  cursor: grabbing !important;
}

.script-drag {
  transform: rotate(2deg);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
  z-index: 1000;
}

.users-list {
  width: 100%;
}

.user-ghost {
  opacity: 0.5;
  background: var(--ant-color-primary-bg) !important;
  border: 2px dashed var(--ant-color-primary) !important;
}

.user-chosen {
  cursor: grabbing !important;
  background: var(--ant-color-primary-bg) !important;
}

.user-drag {
  transform: rotate(1deg);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  z-index: 999;
  background: var(--ant-color-bg-container) !important;
}

/* 拖拽时禁用某些交互 */
.script-ghost .script-card:hover,
.script-drag .script-card:hover {
  transform: none !important;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2) !important;
}

.user-ghost:hover,
.user-drag:hover {
  background: var(--ant-color-primary-bg) !important;
}

/* 脚本卡片 */
.script-card {
  border-radius: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-container);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.script-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  transform: translateY(-2px);
}

/* 脚本头部 */
.script-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.script-info {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
}

.script-logo-container {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-layout);
  border: 1px solid var(--ant-color-border);
  overflow: hidden;
  flex-shrink: 0;
}

.script-logo {
  width: 36px;
  height: 36px;
  object-fit: contain;
  transition: all 0.3s ease;
}

.script-details {
  flex: 1;
  min-width: 0;
}

.script-name {
  margin: 0 0 6px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
  line-height: 1.3;
  word-break: break-word;
}

.script-type {
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.action-button {
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
}

.action-button:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

.add-button {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.add-button:hover {
  background: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
  color: var(--ant-color-primary-hover);
}

.delete-button:hover {
  background: linear-gradient(135deg, var(--ant-color-error), var(--ant-color-error-hover));
}

/* 用户区域 */
.users-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  transition: all 0.2s ease;
  min-height: 80px;
}

.user-item:last-child {
  border-bottom: none;
}

.user-item:hover {
  background: var(--ant-color-bg-layout);
}

.user-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-details-row {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.user-name-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-name {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.user-info-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

.info-tag {
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  margin: 0;
}

.server-tag {
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
}

.user-controls {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
  height: 100%;
  justify-content: center;
}

.user-status {
  display: flex;
  align-items: center;
}

.status-switch {
  font-size: 12px;
}

.status-switch :deep(.ant-switch-inner) {
  font-size: 11px;
  font-weight: 500;
}

.user-actions {
  display: flex;
  flex-direction: row;
  gap: 8px;
  align-items: center;
}

.user-action-btn {
  border-radius: 6px;
  font-weight: 500;
  transition: all 0.3s ease;
  min-width: 60px;
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.user-action-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-color: var(--ant-color-primary);
}

.user-action-btn.ant-btn-dangerous {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
}

.user-action-btn.ant-btn-dangerous:hover {
  border-color: var(--ant-color-error-hover);
  background: var(--ant-color-error-bg);
}

/* 空状态 */
.empty-users {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .script-header {
    padding: 16px 16px 12px;
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }

  .script-name {
    font-size: 16px;
  }

  .header-actions {
    gap: 8px;
  }

  .action-button {
    font-size: 12px;
    height: 28px;
    padding: 0 8px;
  }

  .user-item {
    padding-left: 16px;
    padding-right: 16px;
  }

  .user-controls {
    flex-direction: column;
    gap: 8px;
    align-items: flex-start;
  }

  .user-actions {
    flex-direction: column;
    gap: 4px;
  }

  .empty-users {
    padding: 30px 16px;
  }
}

@media (max-width: 576px) {
  .script-info {
    gap: 8px;
  }

  .script-logo-container {
    width: 40px;
    height: 40px;
  }

  .script-logo {
    width: 28px;
    height: 28px;
  }

  .script-name {
    font-size: 15px;
  }

  .header-actions {
    gap: 6px;
  }

  .action-button {
    font-size: 11px;
    height: 26px;
    padding: 0 6px;
  }

  .user-item {
    padding-left: 12px;
    padding-right: 12px;
    padding-top: 12px;
    padding-bottom: 12px;
  }

  .user-details-row {
    gap: 6px;
  }

  .user-name-section {
    flex-direction: column;
    align-items: flex-start;
    gap: 4px;
  }

  .user-name {
    font-size: 16px;
  }

  .user-info-tags {
    gap: 4px;
  }

  .info-tag {
    font-size: 10px;
  }
}
</style>

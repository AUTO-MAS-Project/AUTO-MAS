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
                  type="default"
                  size="middle"
                  disabled
                  style="color: #52c41a; border-color: #52c41a"
                >
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  正在配置
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
                            :color="getServerTagColor(user.Info.Server)"
                            class="server-tag"
                          >
                            {{ getServerDisplayName(user.Info.Server) }}
                          </a-tag>
                          
                          <!-- 账号标签 -->
                          <a-tag
                            v-if="script.type === 'MAA'"
                            :color="getServerTagColor(user.Info.Server)"
                            class="clickable-tag"
                            @click="handleUserIdClick(user)"
                          >
                            {{ getUserIdDisplayText(user) }}
                          </a-tag>
                          
                          <!-- 密码标签 -->
                          <a-tag
                            v-if="script.type === 'MAA'"
                            :color="getServerTagColor(user.Info.Server)"
                            class="clickable-tag"
                            @click="handlePasswordClick(user)"
                          >
                            {{ getPasswordDisplayText(user) }}
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
                            :color="getAnnihilationTagColor(user.Info.Annihilation, user.Data?.LastAnnihilationDate)"
                          >
                            剿灭：{{ getAnnihilationDisplayText(user.Info.Annihilation, user.Data?.LastAnnihilationDate) }}
                          </a-tag>

                          <!-- 日常代理 -->
                          <a-tag
                            class="info-tag"
                            :color="getRoutineTagColor(user.Data?.LastProxyDate)"
                          >
                            日常：{{ getRoutineDisplayText(user.Data?.LastProxyDate, user.Data?.ProxyTimes) }}
                          </a-tag>

                          <!-- 森空岛签到 -->
                          <a-tag
                            v-if="user.Info.IfSkland !== undefined && user.Info.IfSkland !== null"
                            class="info-tag"
                            :color="getSklandTagColor(user.Info.IfSkland, user.Data?.LastSklandDate)"
                          >
                            森空岛: {{ getSklandDisplayText(user.Info.IfSkland, user.Data?.LastSklandDate) }}
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
                            基建: {{ getInfrastModeDisplayName(user.Info.InfrastMode) }}
                          </a-tag>

                          <!-- 关卡信息 - 根据是否使用计划表配置显示不同内容 -->
                          <template v-if="user.Info.StageMode && user.Info.StageMode !== 'Fixed'">
                            <!-- 主关卡 -->
                            <a-tag
                              v-if="getUserPlanMainStageDisplay(user)"
                              class="info-tag"
                              color="green"
                            >
                              主关卡: {{ getUserPlanMainStageDisplay(user) }}
                            </a-tag>

                            <!-- 备选关卡（合并显示） -->
                            <a-tag
                              v-if="getUserPlanBackupStages(user).length > 0"
                              class="info-tag"
                              color="green"
                            >
                              备选: {{ getUserPlanBackupStages(user).join(', ') }}
                            </a-tag>

                            <!-- 剩余关卡 -->
                            <a-tag
                              v-if="getUserPlanRemainStageDisplay(user)"
                              class="info-tag"
                              color="green"
                            >
                              剩余: {{ getUserPlanRemainStageDisplay(user) }}
                            </a-tag>

                            <!-- 如果没有配置任何关卡，显示提示 -->
                            <a-tag
                              v-if="!getUserPlanMainStageDisplay(user) && getUserPlanBackupStages(user).length === 0 && !getUserPlanRemainStageDisplay(user)"
                              class="info-tag"
                              color="green"
                            >
                              主关卡: 计划表未配置
                            </a-tag>
                          </template>

                          <!-- 固定模式的关卡显示 -->
                          <template v-else>
                            <!-- 主关卡 -->
                            <a-tag
                              v-if="getMainStageDisplay(user)"
                              class="info-tag"
                              color="blue"
                            >
                              主关卡: {{ getMainStageDisplay(user) }}
                            </a-tag>

                            <!-- 备选关卡（合并显示） -->
                            <a-tag
                              v-if="getBackupStages(user).length > 0"
                              class="info-tag"
                              color="blue"
                            >
                              备选: {{ getBackupStages(user).join(', ') }}
                            </a-tag>

                            <!-- 剩余关卡 -->
                            <a-tag
                              v-if="getRemainStageDisplay(user)"
                              class="info-tag"
                              color="blue"
                            >
                              剩余: {{ getRemainStageDisplay(user) }}
                            </a-tag>
                          </template>

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
import { 
  getWeekStartInTimezone, 
  getTodayInTimezone, 
  isDateInRange, 
  isDateEqual,
  getWeekdayInTimezone
} from '@/utils/dateUtils'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  allPlansData?: Record<string, Record<string, any>>
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

// 账号信息展开状态管理 - 使用用户ID作为key
const expandedUserIds = ref<Set<string>>(new Set())
const expandedUserPasswords = ref<Set<string>>(new Set())

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

// 处理账号ID点击
const handleUserIdClick = async (user: any) => {
  const userId = user.id
  const userIdValue = user.Info.Id || ''
  
  // 切换展开状态
  if (expandedUserIds.value.has(userId)) {
    expandedUserIds.value.delete(userId)
  } else {
    expandedUserIds.value.add(userId)
  }
  
  // 只有在有值的情况下才复制到剪贴板
  if (userIdValue) {
    try {
      await navigator.clipboard.writeText(userIdValue)
      message.success('账号已复制到剪贴板')
    } catch (error) {
      message.error('复制失败')
    }
  }
}

// 处理密码点击
const handlePasswordClick = async (user: any) => {
  const userId = user.id
  const passwordValue = user.Info.Password || ''
  
  // 切换展开状态
  if (expandedUserPasswords.value.has(userId)) {
    expandedUserPasswords.value.delete(userId)
  } else {
    expandedUserPasswords.value.add(userId)
  }
  
  // 只有在有值的情况下才复制到剪贴板
  if (passwordValue) {
    try {
      await navigator.clipboard.writeText(passwordValue)
      message.success('密码已复制到剪贴板')
    } catch (error) {
      message.error('复制失败')
    }
  }
}

// 获取账号ID显示文本
const getUserIdDisplayText = (user: any): string => {
  const userId = user.id
  const userIdValue = user.Info.Id || ''
  
  if (expandedUserIds.value.has(userId)) {
    // 展开状态：显示完整内容或未设置
    return userIdValue ? `账号: ${userIdValue}` : '账号: 未设置'
  } else {
    // 隐藏状态：只显示标题
    return '账号'
  }
}

// 获取密码显示文本
const getPasswordDisplayText = (user: any): string => {
  const userId = user.id
  const passwordValue = user.Info.Password || ''
  
  if (expandedUserPasswords.value.has(userId)) {
    // 展开状态：显示完整内容或未设置
    return passwordValue ? `密码: ${passwordValue}` : '密码: 未设置'
  } else {
    // 隐藏状态：只显示标题
    return '密码'
  }
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
const getStageTagColor = (stage: string, stageMode?: string): string => {
  // 如果使用计划表模式（stageMode不是'Fixed'），用绿色
  if (stageMode && stageMode !== 'Fixed') return 'green'
  return 'blue' // 自定义关卡用蓝色
}

// 获取服务器标签颜色
const getServerTagColor = (server: string): string => {
  switch (server) {
    case 'Official':
      return 'blue'
    case 'Bilibili':
      return 'purple'
    case 'YoStarEN':
      return 'green'
    case 'YoStarJP':
      return 'red'
    case 'YoStarKR':
      return 'orange'
    case 'txwy':
      return 'gold'
    default:
      return 'gray'
  }
}

// 获取服务器显示名称
const getServerDisplayName = (server: string): string => {
  switch (server) {
    case 'Official':
      return '官服'
    case 'Bilibili':
      return 'B服'
    case 'YoStarEN':
      return '国际服'
    case 'YoStarJP':
      return '日服'
    case 'YoStarKR':
      return '韩服'
    case 'txwy':
      return '繁中服'
    default:
      return server || '未知'
  }
}

// 获取基建模式显示名称
const getInfrastModeDisplayName = (mode: string): string => {
  switch (mode) {
    case 'Normal':
      return '普通'
    case 'Rotation':
      return '轮班'
    case 'Custom':
      return '自定义'
    default:
      return mode || '未知'
  }
}

// 检查是否完成了本周剿灭
const isAnnihilationCompletedThisWeek = (lastAnnihilationDate: string): boolean => {
  if (!lastAnnihilationDate) return false
  
  // 使用东4区时区获取本周一的Date对象
  const mondayDate = getWeekStartInTimezone(4)
  
  // 检查最后剿灭日期是否 >= 本周一（基于Date对象比较）
  return isDateInRange(lastAnnihilationDate, mondayDate, new Date(), 4)
}

// 获取剿灭标签颜色
const getAnnihilationTagColor = (annihilation: string, lastAnnihilationDate?: string): string => {
  if (annihilation === 'Close') return 'red'
  return isAnnihilationCompletedThisWeek(lastAnnihilationDate || '') ? 'green' : 'orange'
}

// 获取剿灭显示文本
const getAnnihilationDisplayText = (annihilation: string, lastAnnihilationDate?: string): string => {
  if (annihilation === 'Close') return '关闭'
  return isAnnihilationCompletedThisWeek(lastAnnihilationDate || '') ? '已完成' : '未完成'
}

// 检查是否完成了今日日常代理
const isSklandCompletedToday = (lastSklandDate: string): boolean => {
  if (!lastSklandDate) return false
  
  // 森空岛使用东8区时间（UTC+8）
  const todayUTC8 = getTodayInTimezone(8)
  
  // 基于Date对象比较
  return isDateEqual(lastSklandDate, todayUTC8, 8)
}

// 获取森空岛标签颜色
const getSklandTagColor = (ifSkland: boolean, lastSklandDate?: string): string => {
  if (!ifSkland) return 'red'
  return isSklandCompletedToday(lastSklandDate || '') ? 'green' : 'orange'
}

// 获取森空岛显示文本
const getSklandDisplayText = (ifSkland: boolean, lastSklandDate?: string): string => {
  if (!ifSkland) return '关闭'
  return isSklandCompletedToday(lastSklandDate || '') ? '已签到' : '未签到'
}

// 检查是否完成了今日日常代理
const isRoutineCompletedToday = (lastProxyDate: string): boolean => {
  if (!lastProxyDate) return false
  
  // 使用东4区时区获取今日的Date对象
  const todayEast4 = getTodayInTimezone(4)
  
  // 基于Date对象比较
  return isDateEqual(lastProxyDate, todayEast4, 4)
}

// 获取日常代理标签颜色
const getRoutineTagColor = (lastProxyDate?: string): string => {
  return isRoutineCompletedToday(lastProxyDate || '') ? 'green' : 'orange'
}

// 获取日常代理显示文本
const getRoutineDisplayText = (lastProxyDate?: string, proxyTimes?: number): string => {
  if (isRoutineCompletedToday(lastProxyDate || '')) {
    const times = proxyTimes || 0
    return `已代理${times}次`
  } else {
    return '未代理'
  }
}

// 获取主关卡显示文本
const getMainStageDisplay = (user: any): string => {
  // 如果使用计划表模式
  if (user.Info.StageMode && user.Info.StageMode !== 'Fixed' && props.currentPlanData) {
    const planStage = getCurrentPlanStage()
    if (planStage && planStage !== '-') {
      return planStage
    }
    return '计划表配置'
  }
  
  // 固定模式，显示用户自定义关卡
  if (user.Info.Stage && user.Info.Stage !== '-' && user.Info.Stage !== '') {
    return user.Info.Stage
  }
  
  return ''
}

// 获取备选关卡列表（过滤掉无效值）
const getBackupStages = (user: any): string[] => {
  const stages = [user.Info.Stage_1, user.Info.Stage_2, user.Info.Stage_3]
  return stages.filter(stage => 
    stage && 
    stage !== '-' && 
    stage !== '' && 
    stage !== '当前' && 
    stage !== '上次' && 
    stage !== '未选择'
  )
}

// 获取剩余关卡显示文本
const getRemainStageDisplay = (user: any): string => {
  if (
    user.Info.Stage_Remain && 
    user.Info.Stage_Remain !== '-' && 
    user.Info.Stage_Remain !== '' &&
    user.Info.Stage_Remain !== '当前' && 
    user.Info.Stage_Remain !== '上次' && 
    user.Info.Stage_Remain !== '未选择'
  ) {
    return user.Info.Stage_Remain
  }
  return ''
}

// 获取统一的关卡显示标签
const getStageDisplayLabel = (originalLabel: string): string => {
  switch (originalLabel) {
    case '关卡':
      return '主关卡'
    case '关卡1':
    case '关卡2':
    case '关卡3':
      return '备选'
    case '剩余关卡':
      return '剩余'
    default:
      return originalLabel
  }
}

// 获取剩余天数的显示文本
const getRemainingDayText = (remainedDay: number): string => {
  if (remainedDay === -1) return '剩余天数: 长期有效'
  if (remainedDay === 0) return '剩余天数: 已到期'
  return `剩余天数: ${remainedDay}天`
}

// 获取关卡的显示文本
const getDisplayStage = (stage: string, stageMode?: string): string => {
  if (stage === '-') return '未选择'

  // 如果使用计划表模式且有计划表数据，显示计划表中的实际关卡
  if (stageMode && stageMode !== 'Fixed' && props.currentPlanData) {
    const planStage = getCurrentPlanStage()
    if (planStage && planStage !== '-') {
      return planStage
    }
    return '使用计划表配置'
  }

  return stage
}

// 获取用户对应的计划表数据
const getUserPlanData = (user: any): Record<string, any> | null => {
  if (!user.Info.StageMode || user.Info.StageMode === 'Fixed') {
    return null
  }

  // StageMode 存储的就是计划表的ID
  const planId = user.Info.StageMode

  // 从 allPlansData 中获取对应的计划表数据
  if (props.allPlansData && props.allPlansData[planId]) {
    return props.allPlansData[planId]
  }

  return null
}

// 从计划表获取当前关卡
const getCurrentPlanStage = (): string => {
  if (!props.currentPlanData) return ''

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = props.currentPlanData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    // 如果是周模式，根据东4区时区的当前星期几获取对应配置
    const today = getWeekdayInTimezone(4) // 0=Sunday, 1=Monday, ...
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

// 从用户的计划表获取主关卡显示文本
const getUserPlanMainStageDisplay = (user: any): string => {
  const planData = getUserPlanData(user)
  if (!planData) return ''

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = planData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    const today = getWeekdayInTimezone(4)
    const dayMap = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    timeKey = dayMap[today]
  }

  const timeConfig = planData[timeKey]
  if (!timeConfig) return ''

  if (timeConfig.Stage && timeConfig.Stage !== '-') {
    return timeConfig.Stage
  }
  return ''
}

// 从用户的计划表获取备选关卡列表
const getUserPlanBackupStages = (user: any): string[] => {
  const planData = getUserPlanData(user)
  if (!planData) return []

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = planData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    const today = getWeekdayInTimezone(4)
    const dayMap = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    timeKey = dayMap[today]
  }

  const timeConfig = planData[timeKey]
  if (!timeConfig) return []

  const backupStages: string[] = []
  
  if (timeConfig.Stage_1 && timeConfig.Stage_1 !== '-') {
    backupStages.push(timeConfig.Stage_1)
  }
  if (timeConfig.Stage_2 && timeConfig.Stage_2 !== '-') {
    backupStages.push(timeConfig.Stage_2)
  }
  if (timeConfig.Stage_3 && timeConfig.Stage_3 !== '-') {
    backupStages.push(timeConfig.Stage_3)
  }

  return backupStages
}

// 从用户的计划表获取剩余关卡显示文本
const getUserPlanRemainStageDisplay = (user: any): string => {
  const planData = getUserPlanData(user)
  if (!planData) return ''

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = planData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    const today = getWeekdayInTimezone(4)
    const dayMap = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    timeKey = dayMap[today]
  }

  const timeConfig = planData[timeKey]
  if (!timeConfig) return ''

  if (timeConfig.Stage_Remain && timeConfig.Stage_Remain !== '-') {
    return timeConfig.Stage_Remain
  }
  return ''
}

// 从计划表获取当前关卡
const getCurrentPlanStageOld = (): string => {
  if (!props.currentPlanData) return ''

  // 根据当前时间确定使用哪个时间段的配置
  const planMode = props.currentPlanData.Info?.Mode || 'ALL'
  let timeKey = 'ALL'

  if (planMode === 'Weekly') {
    // 如果是周模式，根据东4区时区的当前星期几获取对应配置
    const today = getWeekdayInTimezone(4) // 0=Sunday, 1=Monday, ...
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

  .clickable-tag {
    cursor: pointer;
    user-select: none;
    transition: all 0.2s ease;
  }

  .clickable-tag:hover {
    transform: scale(1.05);
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
  }

  .clickable-tag:active {
    transform: scale(0.95);
  }
}
</style>

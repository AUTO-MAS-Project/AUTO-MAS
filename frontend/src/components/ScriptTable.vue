<template>
  <div class="scripts-grid">
    <!-- 使用vuedraggable包装脚本列表 -->
    <draggable v-model="localScripts" item-key="id" :animation="200" ghost-class="script-ghost"
      chosen-class="script-chosen" drag-class="script-drag" handle=".script-drag-handle" class="draggable-scripts"
      @end="onScriptDragEnd">
      <template #item="{ element: script }">
        <div :key="script.id" class="script-wrapper">
          <a-card :hoverable="false" class="script-card" :body-style="{ padding: '0' }">
            <!-- 脚本头部信息 -->
            <div class="script-header">
              <div class="script-info">
                <span class="script-drag-handle" title="拖拽排序" aria-label="拖拽排序">
                  <span class="script-drag-dots" aria-hidden="true"></span>
                </span>
                <div class="script-logo-container">
                  <img v-if="script.type === 'MAA'" src="@/assets/MAA.png" alt="MAA" class="script-logo" />
                  <img v-else-if="script.type === 'SRC'" src="@/assets/SRC.png" alt="SRC" class="script-logo" />
                  <img v-else-if="script.type === 'MaaEnd'" src="@/assets/MaaEnd.png" alt="MaaEnd"
                    class="script-logo" />
                  <img v-else src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="script-logo" />
                </div>
                <div class="script-details">
                  <h3 class="script-name">{{ script.name }}</h3>
                  <a-tag :color="script.type === 'MAA'
                    ? 'blue'
                    : script.type === 'SRC'
                      ? 'purple'
                      : script.type === 'MaaEnd'
                        ? 'blue'
                        : 'green'
                    " class="script-type">
                    {{ script.type }}
                  </a-tag>
                </div>
              </div>
              <div class="header-actions">
                <a-button v-if="script.type === 'MAA' && !props.activeConnections.has(script.id)" type="primary" ghost
                  size="middle" @click="handleStartMAAConfig(script)">
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置MAA
                </a-button>
                <a-button v-if="script.type === 'MAA' && props.activeConnections.has(script.id)" type="default"
                  size="middle" disabled style="color: #52c41a; border-color: #52c41a">
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  正在配置
                </a-button>
                <a-button v-if="script.type === 'SRC' && !props.activeConnections.has(script.id)" type="primary" ghost
                  size="middle" @click="handleStartSRCConfig(script)">
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置SRC
                </a-button>
                <a-button v-if="script.type === 'SRC' && props.activeConnections.has(script.id)" type="default"
                  size="middle" disabled style="color: #52c41a; border-color: #52c41a">
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  正在配置
                </a-button>
                <a-button v-if="script.type === 'MaaEnd' && !props.activeConnections.has(script.id)" type="primary"
                  ghost size="middle" @click="handleStartMaaEndConfig(script)">
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置MaaEnd
                </a-button>
                <a-button v-if="script.type === 'MaaEnd' && props.activeConnections.has(script.id)" type="default"
                  size="middle" disabled style="color: #52c41a; border-color: #52c41a">
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
                <a-button type="default" size="middle" class="action-button add-button" @click="handleAddUser(script)">
                  <template #icon>
                    <UserAddOutlined />
                  </template>
                  添加用户
                </a-button>
                <a-popconfirm title="确定要删除这个脚本吗？" description="删除后将无法恢复，请谨慎操作" ok-text="确定" cancel-text="取消"
                  @confirm="handleDelete(script)">
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
              <draggable v-model="script.users" item-key="id" :animation="200" ghost-class="user-ghost"
                chosen-class="user-chosen" drag-class="user-drag" handle=".user-drag-handle" class="users-list"
                @end="(evt: any) => onUserDragEnd(evt, script)">
                <template #item="{ element: user }">
                  <div :key="user.id" class="user-item">
                    <span class="user-drag-handle" title="拖拽排序" aria-label="拖拽排序">
                      <span class="script-drag-dots" aria-hidden="true"></span>
                    </span>
                    <div class="user-info">
                      <div class="user-details-row">
                        <div class="user-name-section">
                          <span class="user-name">{{ user.Info.Name }}</span>
                          <!-- MAA、SRC 和 MaaEnd 脚本显示服务器标签 -->
                          <a-tag v-if="
                            script.type === 'MAA' ||
                            script.type === 'SRC' ||
                            script.type === 'MaaEnd'
                          " :color="script.type === 'MaaEnd'
                            ? getMaaEndResourceTagColor(user)
                            : getServerTagColor(user.Info.Server)
                            " class="server-tag">
                            {{ script.type === 'MaaEnd' ? getMaaEndResourceLabel(user) :
                              getServerDisplayName(user.Info.Server) }}
                          </a-tag>

                          <!-- 账号标签 -->
                          <a-tag v-if="
                            script.type === 'MAA' ||
                            script.type === 'SRC' ||
                            script.type === 'MaaEnd'
                          " :color="script.type === 'MaaEnd'
                            ? 'blue'
                            : getServerTagColor(user.Info.Server)
                            " class="clickable-tag" @click="handleUserIdClick(user)">
                            {{ getUserIdDisplayText(user) }}
                          </a-tag>

                          <!-- 密码标签 -->
                          <a-tag v-if="
                            script.type === 'MAA' ||
                            script.type === 'SRC' ||
                            script.type === 'MaaEnd'
                          " :color="script.type === 'MaaEnd'
                            ? 'blue'
                            : getServerTagColor(user.Info.Server)
                            " class="clickable-tag" @click="handlePasswordClick(user)">
                            {{ getPasswordDisplayText(user) }}
                          </a-tag>
                        </div>

                        <!-- 用户详细信息 - MAA和SRC脚本用户 -->
                        <div v-if="
                          script.type === 'MAA' ||
                          script.type === 'SRC' ||
                          script.type === 'MaaEnd'
                        " class="user-info-tags">
                          <!-- 直接使用后端提供的Tag字段 -->
                          <a-tag v-for="(tag, index) in parseStatusTagList(user.Info.Tag)" :key="index"
                            :title="tag.text" :class="['info-tag', { 'clickable-tag': tag.text === '人工排查未通过' }]"
                            :color="tag.color" @click="tag.text === '人工排查未通过' ? handlePassCheck(user) : undefined">
                            {{ tag.text }}
                          </a-tag>
                        </div>
                        <!-- 用户详细信息 - 通用脚本用户 -->
                        <div v-if="script.type === 'General'" class="user-info-tags">
                          <!-- 直接使用后端提供的Tag字段 -->
                          <a-tag v-for="(tag, index) in parseStatusTagList(user.Info.Tag)" :key="index"
                            :title="tag.text" class="info-tag" :color="tag.color">
                            {{ tag.text }}
                          </a-tag>
                        </div>
                      </div>
                    </div>

                    <div class="user-controls">
                      <div class="user-status">
                        <a-switch :checked="user.Info.Status" :checked-children="'启用'" :un-checked-children="'禁用'"
                          class="status-switch" @click="handleToggleUserStatus(user)" />
                      </div>

                      <div class="user-actions">
                        <a-tooltip title="编辑用户配置">
                          <a-button type="default" size="middle" class="user-action-btn" @click="handleEditUser(user)">
                            <template #icon>
                              <EditOutlined />
                            </template>
                            编辑
                          </a-button>
                        </a-tooltip>
                        <a-popconfirm title="确定要删除这个用户吗？" description="删除后将无法恢复" ok-text="确定" cancel-text="取消"
                          @confirm="handleDeleteUser(user)">
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
  SettingOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { ref, watch } from 'vue'
import { Service } from '@/api'
import { message, Modal } from 'ant-design-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { parseStatusTagList } from '@/composables/useStatusTag'
import { getTodayInTimezone, isDateEqual, getWeekdayInTimezone } from '@/utils/dateUtils'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  allPlansData?: Record<string, Record<string, any>>
  currentPlanData?: Record<string, any>
}

interface Emits {
  (e: 'edit', script: Script): void

  (e: 'delete', script: Script): void

  (e: 'addUser', script: Script): void

  (e: 'editUser', user: User): void

  (e: 'deleteUser', user: User): void

  (e: 'startMaaConfig', script: Script): void

  (e: 'saveMaaConfig', script: Script): void

  (e: 'startSrcConfig', script: Script): void

  (e: 'saveSrcConfig', script: Script): void

  (e: 'startMaaEndConfig', script: Script): void

  (e: 'saveMaaEndConfig', script: Script): void

  (e: 'toggleUserStatus', user: User): void

  (e: 'passCheckUser', user: User): void

  (e: 'scriptsReordered', scripts: Script[]): void
}

const ANNIHILATION_MAP: Record<string, string> = {
  Annihilation: '当期剿灭',
  'Chernobog@Annihilation': '切尔诺伯格',
  'LungmenOutskirts@Annihilation': '龙门外环',
  'LungmenDowntown@Annihilation': '龙门市区',
  Close: '关闭',
}

// 常见资源关卡映射
const STAGE_NAME_MAP: Record<string, string> = {
  'LS-6': '经验',
  'CE-6': '龙门币',
  'AP-5': '红票',
  'CA-5': '技能',
  'SK-5': '碳',
  'PR-A-1': '奶/盾芯片',
  'PR-A-2': '奶/盾芯片组',
  'PR-B-1': '术/狙芯片',
  'PR-B-2': '术/狙芯片组',
  'PR-C-1': '先/辅芯片',
  'PR-C-2': '先/辅芯片组',
  'PR-D-1': '近/特芯片',
  'PR-D-2': '近/特芯片组',
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

const handleStartSRCConfig = (script: Script) => {
  emit('startSrcConfig', script)
}

const handleSaveSRCConfig = (script: Script) => {
  emit('saveSrcConfig', script)
}

const handleStartMaaEndConfig = (script: Script) => {
  emit('startMaaEndConfig', script)
}

const handleSaveMaaEndConfig = (script: Script) => {
  emit('saveMaaEndConfig', script)
}

const handleToggleUserStatus = (user: User) => {
  emit('toggleUserStatus', user)
}

const handlePassCheck = (user: User) => {
  Modal.confirm({
    title: '确认操作',
    content: `确定要将用户 ${user.Info.Name} 标记为「已通过人工排查」吗？`,
    okText: '确定',
    cancelText: '取消',
    onOk: () => {
      emit('passCheckUser', user)
    },
  })
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

const getMaaEndResourceLabel = (user: any): string => {
  return user.Info?.Resource || '官服'
}

const getMaaEndResourceTagColor = (user: any): string => {
  switch (getMaaEndResourceLabel(user)) {
    case '官服':
    default:
      return 'blue'
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

// 将关卡代码转换为中文名称（如果有映射的话）
const convertStageNameToChinese = (stageName: string): string => {
  if (!stageName) return stageName
  return STAGE_NAME_MAP[stageName] || stageName
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
    // MAA服务器
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
    // SRC服务器
    case 'CN-Official':
      return 'blue'
    case 'CN-Bilibili':
      return 'purple'
    case 'VN-Official':
      return 'cyan'
    case 'OVERSEA-America':
      return 'green'
    case 'OVERSEA-Asia':
      return 'orange'
    case 'OVERSEA-Europe':
      return 'geekblue'
    case 'OVERSEA-TWHKMO':
      return 'gold'
    default:
      return 'gray'
  }
}

// 获取服务器显示名称
const getServerDisplayName = (server: string): string => {
  switch (server) {
    // MAA服务器
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
    // SRC服务器
    case 'CN-Official':
      return '官服'
    case 'CN-Bilibili':
      return 'B服'
    case 'VN-Official':
      return '越南服'
    case 'OVERSEA-America':
      return '美服'
    case 'OVERSEA-Asia':
      return '亚服'
    case 'OVERSEA-Europe':
      return '欧服'
    case 'OVERSEA-TWHKMO':
      return '港澳台服'
    default:
      return server || '未知'
  }
}

// 获取基建模式显示名称
const getInfrastModeDisplayName = (mode: string): string => {
  switch (mode) {
    case 'Normal':
      return '常规'
    case 'Rotation':
      return '轮休'
    case 'Custom':
      return '自定义'
    default:
      return mode || '未知'
  }
}

// 获取基建显示文本
const getInfrastDisplayText = (user: User): string => {
  const mode = user.Info.InfrastMode

  // 如果是自定义模式，只显示当前排班号
  if (mode === 'Custom') {
    // 显示排班索引
    if (user.Info.InfrastIndex && user.Info.InfrastIndex !== '') {
      return `排班 ${user.Info.InfrastIndex}`
    }

    // 没有排班信息时返回'自定义'
    return '自定义'
  }

  // 非自定义模式，返回标准显示名称
  return getInfrastModeDisplayName(mode)
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
      return convertStageNameToChinese(planStage)
    }
    return '计划表配置'
  }

  // 固定模式，显示用户自定义关卡
  if (user.Info.Stage && user.Info.Stage !== '-' && user.Info.Stage !== '') {
    return convertStageNameToChinese(user.Info.Stage)
  }

  return ''
}

// 获取备选关卡列表（过滤掉无效值）
const getBackupStages = (user: any): string[] => {
  const stages = [user.Info.Stage_1, user.Info.Stage_2, user.Info.Stage_3]
  return stages
    .filter(
      stage =>
        stage &&
        stage !== '-' &&
        stage !== '' &&
        stage !== '当前' &&
        stage !== '上次' &&
        stage !== '未选择'
    )
    .map(stage => convertStageNameToChinese(stage))
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
    return convertStageNameToChinese(user.Info.Stage_Remain)
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
    return convertStageNameToChinese(timeConfig.Stage)
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
    backupStages.push(convertStageNameToChinese(timeConfig.Stage_1))
  }
  if (timeConfig.Stage_2 && timeConfig.Stage_2 !== '-') {
    backupStages.push(convertStageNameToChinese(timeConfig.Stage_2))
  }
  if (timeConfig.Stage_3 && timeConfig.Stage_3 !== '-') {
    backupStages.push(convertStageNameToChinese(timeConfig.Stage_3))
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
    return convertStageNameToChinese(timeConfig.Stage_Remain)
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
const { reorderScript } = useScriptApi()
const { reorderUser } = useUserApi()

const onScriptDragEnd = async () => {
  const scriptIds = localScripts.value.map(s => s.id)
  const success = await reorderScript(scriptIds)
  if (success) {
    emit('scriptsReordered', localScripts.value)
  }
}

const onUserDragEnd = async (evt: any, script: Script) => {
  const userIds = script.users.map(u => u.id)
  const success = await reorderUser(script.id, userIds)
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
  cursor: auto;
}

.script-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.script-chosen {
  cursor: move !important;
}

.script-drag {
  transform: rotate(2deg);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
  z-index: 1000;
  opacity: 1 !important;
  cursor: all-scroll !important;
}

.script-drag * {
  cursor: all-scroll !important;
}

.script-drag .script-card {
  opacity: 1 !important;
  transition: none !important;
}

.users-list {
  width: 100%;
}

.user-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.user-chosen {
  cursor: move !important;
  background: var(--ant-color-primary-bg) !important;
}

.user-drag {
  transform: rotate(1deg);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  z-index: 999;
  background: var(--ant-color-bg-container) !important;
  opacity: 1 !important;
  cursor: all-scroll !important;
}

.user-drag * {
  cursor: all-scroll !important;
}

.script-drag .script-drag-handle {
  cursor: grabbing !important;
}

.script-drag .script-drag-handle * {
  cursor: grabbing !important;
}

.user-drag .user-drag-handle {
  cursor: grabbing !important;
}

.user-drag .user-drag-handle * {
  cursor: grabbing !important;
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
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.script-card:hover {
  border-color: var(--ant-color-primary);
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

.script-drag-handle {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  background: transparent;
  border: none;
  cursor: move;
  flex-shrink: 0;
  user-select: none;
}

.script-drag-handle:active {
  cursor: move;
}

.script-drag-dots {
  width: 10px;
  height: 16px;
  display: block;
  background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
  background-size: 5px 5px;
  background-position: 0 0;
  opacity: 0.65;
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
  border: 1px solid rgba(0, 0, 0, 0.15);
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
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
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
  min-height: 80px;
}

.user-drag-handle {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  background: transparent;
  border: none;
  cursor: move;
  flex-shrink: 0;
  user-select: none;
}

.user-drag-handle:active {
  cursor: move;
}

.user-drag-handle:hover .script-drag-dots {
  opacity: 0.85;
}

.user-item:last-child {
  border-bottom: none;
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
  display: inline-block;
  max-width: 120px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  margin: 0;
  border: 1px solid rgba(0, 0, 0, 0.15);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.server-tag {
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  border: 1px solid rgba(0, 0, 0, 0.15);
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
  min-width: 60px;
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
}

.user-action-btn.ant-btn-dangerous {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
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
    max-width: 100px;
  }

  .clickable-tag {
    cursor: pointer;
    user-select: none;
    border: 1px solid rgba(0, 0, 0, 0.15);
  }
}
</style>

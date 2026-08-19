<template>
  <div class="scripts-grid">
    <!-- 使用vuedraggable包装脚本列表 -->
    <draggable
      v-model="localScripts"
      item-key="id"
      :animation="200"
      :disabled="props.searching"
      ghost-class="script-ghost"
      chosen-class="script-chosen"
      drag-class="script-drag"
      handle=".script-drag-handle"
      class="draggable-scripts"
      @end="onScriptDragEnd"
    >
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
                  <img
                    v-if="script.type === 'MAA'"
                    src="@/assets/MAA.png"
                    alt="MAA"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'SRC'"
                    src="@/assets/SRC.png"
                    alt="SRC"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'MaaEnd'"
                    src="@/assets/MaaEnd.png"
                    alt="MaaEnd"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'M9A'"
                    src="@/assets/M9A.png"
                    alt="M9A"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'Okww'"
                    src="@/assets/ok-ww.ico"
                    alt="ok-ww"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'OkNte'"
                    src="@/assets/ok-nte.ico"
                    alt="ok-nte"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'HSR'"
                    src="@/assets/hsr.png"
                    alt="HSR"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'BetterGI'"
                    src="@/assets/bettergi.ico"
                    alt="BetterGI"
                    class="script-logo"
                  />
                  <img v-else src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="script-logo" />
                </div>
                <div class="script-details">
                  <h3 class="script-name">{{ script.name }}</h3>
                  <a-tag
                    :color="
                      script.type === 'MAA'
                        ? 'blue'
                        : script.type === 'SRC'
                          ? 'purple'
                          : script.type === 'MaaEnd'
                            ? 'blue'
                            : script.type === 'M9A'
                              ? 'cyan'
                              : script.type === 'Okww'
                                ? 'blue'
                                : script.type === 'OkNte'
                                  ? 'blue'
                                  : script.type === 'HSR'
                                    ? 'purple'
                                    : 'green'
                    "
                    class="script-type"
                  >
                    {{ getScriptTypeLabel(script.type) }}
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
                <a-button
                  v-if="script.type === 'SRC' && !props.activeConnections.has(script.id)"
                  type="primary"
                  ghost
                  size="middle"
                  @click="handleStartSRCConfig(script)"
                >
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置SRC
                </a-button>
                <a-button
                  v-if="script.type === 'SRC' && props.activeConnections.has(script.id)"
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
                <a-button
                  v-if="isMaaEndPresetSupported(script) && !props.activeConnections.has(script.id)"
                  type="primary"
                  ghost
                  size="middle"
                  @click="handleStartMaaEndConfig(script)"
                >
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置MaaEnd
                </a-button>
                <a-button
                  v-if="isMaaEndPresetSupported(script) && props.activeConnections.has(script.id)"
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
                <a-button
                  v-if="script.type === 'Okww' && !props.activeConnections.has(script.id)"
                  type="primary"
                  ghost
                  size="middle"
                  @click="handleStartOkwwConfig(script)"
                >
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  配置ok-ww
                </a-button>
                <a-button
                  v-if="script.type === 'Okww' && props.activeConnections.has(script.id)"
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
                <a-dropdown :trigger="['click']">
                  <a-button
                    size="middle"
                    class="action-button"
                    :loading="props.copyingScriptId === script.id"
                    :disabled="Boolean(props.copyingScriptId)"
                  >
                    <template #icon>
                      <EllipsisOutlined />
                    </template>
                    更多
                  </a-button>
                  <template #overlay>
                    <a-menu>
                      <a-menu-item key="copy" @click="handleCopy(script)">
                        <CopyOutlined />
                        复制脚本
                      </a-menu-item>
                      <a-menu-divider />
                      <a-menu-item key="delete" danger @click="handleDeleteConfirm(script)">
                        <DeleteOutlined />
                        删除脚本
                      </a-menu-item>
                    </a-menu>
                  </template>
                </a-dropdown>
                <a-tooltip
                  :title="
                    props.searching
                      ? '搜索时自动展开用户'
                      : isUsersCollapsed(script.id)
                        ? '展开用户'
                        : '收起用户'
                  "
                >
                  <a-button
                    size="middle"
                    class="action-button"
                    :disabled="props.searching"
                    :aria-label="isUsersCollapsed(script.id) ? '展开用户' : '收起用户'"
                    @click="toggleUsersCollapsed(script.id)"
                  >
                    <template #icon>
                      <DownOutlined v-if="isUsersCollapsed(script.id)" />
                      <UpOutlined v-else />
                    </template>
                  </a-button>
                </a-tooltip>
              </div>
            </div>

            <!-- 用户列表 -->
            <div
              v-if="!isUsersCollapsed(script.id) && script.users && script.users.length > 0"
              class="users-section"
            >
              <!-- 使用vuedraggable包装用户列表 -->
              <draggable
                v-model="script.users"
                item-key="id"
                :animation="200"
                :disabled="props.searching"
                ghost-class="user-ghost"
                chosen-class="user-chosen"
                drag-class="user-drag"
                handle=".user-drag-handle"
                class="users-list"
                @end="onUserDragEnd(script)"
              >
                <template #item="{ element: user }">
                  <div :key="user.id" class="user-item">
                    <span class="user-drag-handle" title="拖拽排序" aria-label="拖拽排序">
                      <span class="script-drag-dots" aria-hidden="true"></span>
                    </span>
                    <div class="user-info">
                      <div class="user-details-row">
                        <div class="user-name-section">
                          <span class="user-name">{{ user.Info.Name }}</span>
                          <!-- MAA、SRC、MaaEnd 和 HSR 脚本显示服务器标签 -->
                          <a-tag
                            v-if="
                              script.type === 'MAA' ||
                              script.type === 'SRC' ||
                              script.type === 'MaaEnd'
                            "
                            :color="
                              script.type === 'MaaEnd'
                                ? getMaaEndResourceTagColor(user)
                                : getServerTagColor(user.Info.Server)
                            "
                            class="server-tag"
                          >
                            {{
                              script.type === 'MaaEnd'
                                ? getMaaEndResourceLabel(user)
                                : getServerDisplayName(user.Info.Server)
                            }}
                          </a-tag>

                          <!-- M9A 脚本显示服务器标签 -->
                          <a-tag
                            v-if="script.type === 'M9A'"
                            :color="getM9AServerTagColor(user.Info.Resource)"
                            class="server-tag"
                          >
                            {{ user.Info.Resource || '官服' }}
                          </a-tag>

                          <!-- 账号标签 (HSR 不显示账号/密码) -->
                          <a-tag
                            v-if="
                              script.type === 'MAA' ||
                              script.type === 'SRC' ||
                              script.type === 'MaaEnd'
                            "
                            :color="
                              script.type === 'MaaEnd'
                                ? 'blue'
                                : getServerTagColor(user.Info.Server)
                            "
                            class="clickable-tag"
                            @click="handleUserIdClick(user)"
                          >
                            {{ getUserIdDisplayText(user) }}
                          </a-tag>

                          <!-- 密码标签 (HSR 不显示账号/密码) -->
                          <a-tag
                            v-if="
                              script.type === 'MAA' ||
                              script.type === 'SRC' ||
                              script.type === 'MaaEnd'
                            "
                            :color="
                              script.type === 'MaaEnd'
                                ? 'blue'
                                : getServerTagColor(user.Info.Server)
                            "
                            class="clickable-tag"
                            @click="handlePasswordClick(user)"
                          >
                            {{ getPasswordDisplayText(user) }}
                          </a-tag>
                        </div>

                        <!-- 用户详细信息 - MAA和SRC脚本用户 -->
                        <div
                          v-if="
                            script.type === 'MAA' ||
                            script.type === 'SRC' ||
                            script.type === 'MaaEnd'
                          "
                          class="user-info-tags"
                        >
                          <!-- 直接使用后端提供的Tag字段 -->
                          <a-tag
                            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
                            :key="index"
                            :title="tag.text"
                            :class="['info-tag']"
                            :color="tag.color"
                          >
                            {{ tag.text }}
                          </a-tag>
                        </div>
                        <!-- 用户详细信息 - 后端提供 Tag 的脚本用户 -->
                        <div
                          v-if="
                            script.type === 'General' ||
                            script.type === 'Okww' ||
                            script.type === 'OkNte' ||
                            script.type === 'BetterGI'
                          "
                          class="user-info-tags"
                        >
                          <!-- 直接使用后端提供的Tag字段 -->
                          <a-tag
                            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
                            :key="index"
                            :title="tag.text"
                            class="info-tag"
                            :color="tag.color"
                          >
                            {{ tag.text }}
                          </a-tag>
                        </div>
                        <!-- 用户详细信息 - M9A脚本用户 -->
                        <div v-if="script.type === 'M9A'" class="user-info-tags">
                          <!-- 显示备注（仅当有值时）-->
                          <a-tag
                            v-if="
                              user.Info.Notes &&
                              user.Info.Notes !== '无' &&
                              user.Info.Notes.trim() !== ''
                            "
                            color="geekblue"
                            class="info-tag"
                            :title="user.Info.Notes"
                          >
                            {{ truncateText(user.Info.Notes, 10) }}
                          </a-tag>

                          <a-tag
                            v-for="(tag, index) in getM9AOnceStatusTags(script, user)"
                            :key="`m9a-once-${index}`"
                            :title="tag.text"
                            class="info-tag"
                            :color="tag.color"
                          >
                            {{ tag.text }}
                          </a-tag>

                          <!-- 后端提供的Tag字段 -->
                          <a-tag
                            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
                            :key="index"
                            :title="tag.text"
                            class="info-tag"
                            :color="tag.color"
                          >
                            {{ tag.text }}
                          </a-tag>
                        </div>
                        <!-- 用户详细信息 - HSR脚本用户 -->
                        <div v-if="script.type === 'HSR'" class="user-info-tags">
                          <a-tag
                            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
                            :key="index"
                            :title="tag.text"
                            class="info-tag"
                            :color="tag.color"
                          >
                            {{ tag.text }}
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
                        <a-tooltip
                          v-if="shouldShowMaaEndUserConfigButton(script, user)"
                          title="配置用户级 MaaEnd"
                        >
                          <a-button
                            v-if="!props.activeConnections.has(user.id)"
                            type="default"
                            size="middle"
                            class="user-action-btn"
                            @click="handleStartMaaEndUserConfig(script, user)"
                          >
                            <template #icon>
                              <SettingOutlined />
                            </template>
                            配置MaaEnd
                          </a-button>
                          <a-button
                            v-else
                            type="default"
                            size="middle"
                            class="user-action-btn"
                            disabled
                            style="color: #52c41a; border-color: #52c41a"
                          >
                            <template #icon>
                              <SettingOutlined />
                            </template>
                            正在配置
                          </a-button>
                        </a-tooltip>
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
            <div v-else-if="!isUsersCollapsed(script.id)" class="empty-users">
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
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  EditOutlined,
  EllipsisOutlined,
  SettingOutlined,
  UpOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import { ref, watch } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { parseStatusTagList } from '@/composables/useStatusTag'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  copyingScriptId?: string | null
  allPlansData?: Record<string, Record<string, any>>
  currentPlanData?: Record<string, any>
  searching?: boolean
}

interface Emits {
  (e: 'edit', script: Script): void

  (e: 'delete', script: Script): void

  (e: 'copy', script: Script): void

  (e: 'addUser', script: Script): void

  (e: 'editUser', user: User): void

  (e: 'deleteUser', user: User): void

  (e: 'startMaaConfig', script: Script): void

  (e: 'saveMaaConfig', script: Script): void

  (e: 'startSrcConfig', script: Script): void

  (e: 'saveSrcConfig', script: Script): void

  (e: 'startMaaEndConfig', script: Script): void

  (e: 'startMaaEndUserConfig', script: Script, user: User): void

  (e: 'saveMaaEndConfig', script: Script): void

  (e: 'startOkwwConfig', script: Script): void

  (e: 'toggleUserStatus', user: User): void

  (e: 'scriptsReordered', scripts: Script[]): void
}

const M9A_PSYCHUBE_NAMES = ['每日心相（意志解析）', '每日心相']
const M9A_LIMBO_NAMES = ['自动深眠']
const M9A_LUCIDSCAPE_NAMES = ['自动醒梦']

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

// 本地脚本列表状态
const localScripts = ref<Script[]>([])
// 脚本用户列表收起状态 - 持久化到 localStorage，切换页面后仍保持
const COLLAPSED_SCRIPTS_STORAGE_KEY = 'scripts.collapsedScriptIds'

const loadCollapsedScriptIds = (): Set<string> => {
  try {
    const raw = localStorage.getItem(COLLAPSED_SCRIPTS_STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw)
    return new Set(Array.isArray(parsed) ? parsed.filter(id => typeof id === 'string') : [])
  } catch {
    return new Set()
  }
}

const collapsedScriptIds = ref<Set<string>>(loadCollapsedScriptIds())

const saveCollapsedScriptIds = () => {
  try {
    localStorage.setItem(
      COLLAPSED_SCRIPTS_STORAGE_KEY,
      JSON.stringify([...collapsedScriptIds.value])
    )
  } catch {
    // 存储不可用时（如隐私模式）忽略，仅本次会话内生效
  }
}

const isUsersCollapsed = (scriptId: string) =>
  !props.searching && collapsedScriptIds.value.has(scriptId)

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

const handleCopy = (script: Script) => {
  emit('copy', script)
}

const handleDeleteConfirm = (script: Script) => {
  Modal.confirm({
    title: '确定要删除这个脚本吗？',
    content: '删除后将无法恢复，请谨慎操作',
    okText: '确定',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => handleDelete(script),
  })
}

const toggleUsersCollapsed = (scriptId: string) => {
  const next = new Set(collapsedScriptIds.value)
  if (next.has(scriptId)) {
    next.delete(scriptId)
  } else {
    next.add(scriptId)
  }
  collapsedScriptIds.value = next
  saveCollapsedScriptIds()
}

const collapseAllUsers = () => {
  collapsedScriptIds.value = new Set(localScripts.value.map(script => script.id))
  saveCollapsedScriptIds()
}

const expandAllUsers = () => {
  collapsedScriptIds.value = new Set()
  saveCollapsedScriptIds()
}

defineExpose({ collapseAllUsers, expandAllUsers })

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

const handleStartSRCConfig = (script: Script) => {
  emit('startSrcConfig', script)
}

const handleStartMaaEndConfig = (script: Script) => {
  emit('startMaaEndConfig', script)
}

const handleStartMaaEndUserConfig = (script: Script, user: User) => {
  emit('startMaaEndUserConfig', script, user)
}

const isMaaEndPresetSupported = (script: Script) => {
  const controllerType = (script.config as any).Game?.ControllerType
  return script.type === 'MaaEnd' && controllerType === 'Win32-Front'
}

const shouldShowMaaEndUserConfigButton = (script: Script, user: User) => {
  return script.type === 'MaaEnd' && user.Info?.Mode === '详细'
}

const handleStartOkwwConfig = (script: Script) => {
  emit('startOkwwConfig', script)
}

const handleToggleUserStatus = (user: User) => {
  emit('toggleUserStatus', user)
}

const getScriptTypeLabel = (type: Script['type']) => {
  if (type === 'Okww') return 'ok-ww'
  if (type === 'OkNte') return 'ok-nte'
  return type
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
    } catch {
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
    } catch {
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

// M9A服务器标签颜色映射
const getM9AServerTagColor = (_resource: string): string => {
  return 'blue'
}

const getM9ATodayString = (): string => {
  return new Date(Date.now() + 4 * 60 * 60 * 1000).toISOString().slice(0, 10)
}

const getM9ACurrentMonthString = (): string => {
  return getM9ATodayString().slice(0, 7)
}

const parseM9ATaskQueue = (queue: unknown): Array<{ name?: string }> => {
  if (Array.isArray(queue)) return queue as Array<{ name?: string }>
  if (typeof queue !== 'string') return []

  try {
    const parsed = JSON.parse(queue)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

const hasM9ATaskInQueue = (queue: Array<{ name?: string }>, names: string[]): boolean => {
  return queue.some(item => item.name && names.includes(item.name))
}

const getM9AOnceStatusTags = (script: Script, user: User) => {
  const runConfig = (script.config as any)?.Run || {}
  const queue = parseM9ATaskQueue((user as any).Task?.Queue)
  const data = (user as any).Data || {}
  const tags: Array<{ text: string; color: string }> = []

  if (runConfig.IfPsychubeDailyOnce && hasM9ATaskInQueue(queue, M9A_PSYCHUBE_NAMES)) {
    const completed = data.LastPsychubeDate === getM9ATodayString()
    tags.push({
      text: `每日心相：${completed ? '已完成' : '未完成'}`,
      color: completed ? 'green' : 'orange',
    })
  }

  if (runConfig.IfSleepDreamMonthlyOnce) {
    const hasLimbo = hasM9ATaskInQueue(queue, M9A_LIMBO_NAMES)
    const hasLucidscape = hasM9ATaskInQueue(queue, M9A_LUCIDSCAPE_NAMES)
    if (hasLimbo || hasLucidscape) {
      const currentMonth = getM9ACurrentMonthString()
      const completed =
        (!hasLimbo || data.LastLimboMonth === currentMonth) &&
        (!hasLucidscape || data.LastLucidscapeMonth === currentMonth)

      tags.push({
        text: `深眠浅梦：${completed ? '已完成' : '未完成'}`,
        color: completed ? 'green' : 'orange',
      })
    }
  }

  return tags
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

const onUserDragEnd = async (script: Script) => {
  const userIds = script.users.map(u => u.id)
  await reorderUser(script.id, userIds)
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

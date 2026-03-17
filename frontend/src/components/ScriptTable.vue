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
                  <img
                    v-else-if="script.type === 'SRC'"
                    src="@/assets/SRC.png"
                    alt="SRC"
                    class="script-logo"
                  />
                  <img
                    v-else-if="script.type === 'MaaEnd'"
                    src="@/assets/MAA.png"
                    alt="MaaEnd"
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
                            ? 'geekblue'
                            : 'green'
                    "
                    class="script-type"
                  >
                    {{
                      script.type === 'MAA'
                        ? 'MAA'
                        : script.type === 'SRC'
                          ? 'SRC'
                          : script.type === 'MaaEnd'
                            ? 'MAAEND'
                            : 'GENERAL'
                    }}
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
                  v-if="script.type === 'MaaEnd' && !props.activeConnections.has(script.id)"
                  type="primary"
                  ghost
                  size="middle"
                  @click="handleStartMaaEndConfig(script)"
                >
                  <template #icon>
                    <SettingOutlined />
                  </template>
                  {{ getMaaEndConfigActionText(script) }}
                </a-button>
                <a-button
                  v-if="script.type === 'MaaEnd' && props.activeConnections.has(script.id)"
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
                @end="() => onUserDragEnd(script)"
              >
                <template #item="{ element: user }">
                  <div :key="user.id" class="user-item">
                    <div class="user-info">
                      <div class="user-details-row">
                        <div class="user-name-section">
                          <span class="user-name">{{ user.Info.Name }}</span>
                          <!-- 只有MAA和SRC脚本才显示服务器标签 -->
                          <a-tag
                            v-if="script.type === 'MAA' || script.type === 'SRC'"
                            :color="getServerTagColor(user.Info.Server)"
                            class="server-tag"
                          >
                            {{ getServerDisplayName(user.Info.Server) }}
                          </a-tag>

                          <!-- 账号标签 -->
                          <a-tag
                            v-if="
                              script.type === 'MAA' ||
                              script.type === 'SRC' ||
                              script.type === 'MaaEnd'
                            "
                            color="blue"
                            class="clickable-tag"
                            @click="handleUserIdClick(user)"
                          >
                            {{ getUserIdDisplayText(user, script.type) }}
                          </a-tag>

                          <!-- 密码标签 -->
                          <a-tag
                            v-if="
                              script.type === 'MAA' ||
                              script.type === 'SRC' ||
                              script.type === 'MaaEnd'
                            "
                            color="blue"
                            class="clickable-tag"
                            @click="handlePasswordClick(user)"
                          >
                            {{ getPasswordDisplayText(user) }}
                          </a-tag>
                        </div>

                        <!-- 用户详细信息 - MAA和SRC脚本用户 -->
                        <div
                          v-if="script.type === 'MAA' || script.type === 'SRC'"
                          class="user-info-tags"
                        >
                          <!-- 直接使用后端提供的Tag字段 -->
                          <a-tag
                            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
                            :key="index"
                            :class="[
                              'info-tag',
                              { 'clickable-tag': tag.text === '人工排查未通过' },
                            ]"
                            :color="tag.color"
                            @click="
                              tag.text === '人工排查未通过' ? handlePassCheck(user) : undefined
                            "
                          >
                            {{ tag.text }}
                          </a-tag>
                        </div>
                        <!-- 用户详细信息 - 通用脚本用户 -->
                        <div
                          v-if="script.type === 'General' || script.type === 'MaaEnd'"
                          class="user-info-tags"
                        >
                          <!-- 直接使用后端提供的Tag字段 -->
                          <a-tag
                            v-for="(tag, index) in parseStatusTagList(user.Info.Tag)"
                            :key="index"
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
  SettingOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'
import { message, Modal } from 'ant-design-vue'
import { ref, watch } from 'vue'
import draggable from 'vuedraggable'
import { useScriptApi } from '@/composables/useScriptApi'
import { parseStatusTagList } from '@/composables/useStatusTag'
import { useUserApi } from '@/composables/useUserApi'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
}

const props = defineProps<Props>()
const emit = defineEmits([
  'edit',
  'delete',
  'addUser',
  'editUser',
  'deleteUser',
  'startMaaConfig',
  'startSrcConfig',
  'startMaaEndConfig',
  'toggleUserStatus',
  'passCheckUser',
  'scriptsReordered',
])

const localScripts = ref<Script[]>([])
const expandedUserIds = ref<Set<string>>(new Set())
const expandedUserPasswords = ref<Set<string>>(new Set())

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

const handleStartSRCConfig = (script: Script) => {
  emit('startSrcConfig', script)
}

const handleStartMaaEndConfig = (script: Script) => {
  emit('startMaaEndConfig', script)
}

const getMaaEndConfigActionText = (script: Script): string => {
  if (script.type !== 'MaaEnd') {
    return '配置MaaEnd'
  }

  return '配置MAAEND'
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

const handleUserIdClick = async (user: User) => {
  const userId = user.id
  const userIdValue = user.Info.Id || ''

  if (expandedUserIds.value.has(userId)) {
    expandedUserIds.value.delete(userId)
  } else {
    expandedUserIds.value.add(userId)
  }

  if (!userIdValue) {
    return
  }

  try {
    await navigator.clipboard.writeText(userIdValue)
    message.success('账号已复制到剪贴板')
  } catch {
    message.error('复制失败')
  }
}

const handlePasswordClick = async (user: User) => {
  const userId = user.id
  const passwordValue = user.Info.Password || ''

  if (expandedUserPasswords.value.has(userId)) {
    expandedUserPasswords.value.delete(userId)
  } else {
    expandedUserPasswords.value.add(userId)
  }

  if (!passwordValue) {
    return
  }

  try {
    await navigator.clipboard.writeText(passwordValue)
    message.success('密码已复制到剪贴板')
  } catch {
    message.error('复制失败')
  }
}

const getUserIdDisplayText = (user: User, scriptType?: ScriptType): string => {
  const accountText =
    scriptType === 'MaaEnd' ? ((user as any)?.Info?.Account ?? '') : ((user as any)?.Info?.Id ?? '')

  if (expandedUserIds.value.has(user.id)) {
    return accountText ? `账号: ${accountText}` : '账号: 未设置'
  }

  return '账号'
}

const getPasswordDisplayText = (user: User): string => {
  if (expandedUserPasswords.value.has(user.id)) {
    return user.Info.Password ? `密码: ${user.Info.Password}` : '密码: 未设置'
  }

  return '密码'
}

const getServerTagColor = (server: string): string => {
  switch (server) {
    case 'Official':
    case 'CN-Official':
      return 'blue'
    case 'Bilibili':
    case 'CN-Bilibili':
      return 'purple'
    case 'YoStarEN':
    case 'OVERSEA-America':
      return 'green'
    case 'YoStarJP':
      return 'red'
    case 'YoStarKR':
    case 'OVERSEA-Asia':
      return 'orange'
    case 'txwy':
    case 'OVERSEA-TWHKMO':
      return 'gold'
    case 'VN-Official':
      return 'cyan'
    case 'OVERSEA-Europe':
      return 'geekblue'
    default:
      return 'gray'
  }
}

const getServerDisplayName = (server: string): string => {
  switch (server) {
    case 'Official':
    case 'CN-Official':
      return '官服'
    case 'Bilibili':
    case 'CN-Bilibili':
      return 'B服'
    case 'YoStarEN':
      return '国际服'
    case 'YoStarJP':
      return '日服'
    case 'YoStarKR':
      return '韩服'
    case 'txwy':
      return '繁中服'
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

const { reorderScript } = useScriptApi()
const { reorderUser } = useUserApi()

const onScriptDragEnd = async () => {
  const scriptIds = localScripts.value.map(script => script.id)
  const success = await reorderScript(scriptIds)
  if (success) {
    emit('scriptsReordered', localScripts.value)
  }
}

const onUserDragEnd = async (script: Script) => {
  const userIds = script.users.map(user => user.id)
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
  border: 1px solid rgba(0, 0, 0, 0.15);
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
    border: 1px solid rgba(0, 0, 0, 0.15);
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

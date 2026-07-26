<template>
  <div
    :ref="element => registerMatchElement(scriptMatchKey, element)"
    :class="['script-wrapper', { 'search-match-active': scriptMatchActive }]"
    :aria-current="scriptMatchActive ? 'true' : undefined"
  >
    <a-card :hoverable="false" class="script-card" :body-style="{ padding: '0' }">
      <!-- 脚本头部信息 -->
      <div class="script-header">
        <div class="script-info">
          <span
            class="script-drag-handle"
            :class="{ 'drag-handle-disabled': searchActive }"
            :title="searchActive ? '搜索期间暂停拖拽排序' : '拖拽排序'"
            aria-label="拖拽排序"
            :aria-disabled="searchActive"
          >
            <span class="script-drag-dots" aria-hidden="true"></span>
          </span>
          <div class="script-logo-container">
            <img
              :src="getScriptIcon(script.type, script.iconUrl)"
              :alt="script.type"
              class="script-logo"
              @error="event => handleScriptIconError(event, script.type)"
            />
          </div>
          <div class="script-details">
            <h3 class="script-name">{{ script.name }}</h3>
            <a-tag
              :color="getScriptTypeTagColor(script.type, script.themeColor)"
              class="script-type"
            >
              {{ getScriptTypeLabel(script) }}
            </a-tag>
            <a-tag v-if="script.available === false" color="orange" class="script-type">
              未启用
            </a-tag>
          </div>
        </div>
        <div class="header-actions">
          <a-button
            v-if="script.type === 'SRC' && !isActiveConfig"
            type="primary"
            ghost
            size="middle"
            :disabled="!isOperable"
            @click="emit('startSrcConfig', script)"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            配置SRC
          </a-button>
          <a-button
            v-if="script.type === 'SRC' && isActiveConfig"
            type="default"
            size="middle"
            disabled
            class="config-active-btn"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            正在配置
          </a-button>
          <a-button
            v-if="script.type === 'MaaEnd' && !isActiveConfig"
            type="primary"
            ghost
            size="middle"
            :disabled="!isOperable"
            @click="emit('startMaaEndConfig', script)"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            配置MaaEnd
          </a-button>
          <a-button
            v-if="script.type === 'MaaEnd' && isActiveConfig"
            type="default"
            size="middle"
            disabled
            class="config-active-btn"
          >
            <template #icon>
              <SettingOutlined />
            </template>
            正在配置
          </a-button>
          <a-button type="default" size="middle" :disabled="!canEdit" @click="emit('edit', script)">
            <template #icon>
              <EditOutlined />
            </template>
            编辑脚本
          </a-button>
          <a-button
            type="default"
            size="middle"
            class="action-button add-button"
            :disabled="!isOperable"
            @click="emit('addUser', script)"
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
              :loading="copyingScriptId === script.id"
              :disabled="Boolean(copyingScriptId) || !isOperable"
            >
              <template #icon>
                <EllipsisOutlined />
              </template>
              更多
            </a-button>
            <template #overlay>
              <a-menu>
                <a-menu-item key="copy" @click="emit('copy', script)">
                  <CopyOutlined />
                  复制脚本
                </a-menu-item>
                <a-menu-divider />
                <a-menu-item key="delete" danger @click="handleDeleteConfirm">
                  <DeleteOutlined />
                  删除脚本
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>
          <a-tooltip :title="collapsed ? '展开用户' : '收起用户'">
            <a-button
              size="middle"
              class="action-button"
              :disabled="searchActive"
              :aria-label="collapsed ? '展开用户' : '收起用户'"
              @click="emit('toggleCollapsed')"
            >
              <template #icon>
                <DownOutlined v-if="collapsed" />
                <UpOutlined v-else />
              </template>
            </a-button>
          </a-tooltip>
        </div>
      </div>

      <!-- 用户列表 -->
      <div v-if="showUsersSection" class="users-section">
        <draggable
          v-model="localUsers"
          item-key="id"
          :animation="200"
          :disabled="searchActive || isReorderingUsers"
          ghost-class="user-ghost"
          chosen-class="user-chosen"
          drag-class="user-drag"
          handle=".user-drag-handle"
          class="users-list"
          @start="onUserDragStart"
          @end="onUserDragEnd"
        >
          <template #item="{ element: user }">
            <ScriptUserRow
              :user="user"
              :operable="isOperable"
              :drag-disabled="searchActive"
              :should-show="shouldShowUserInSearch(user)"
              :match-key="getUserSearchMatchKey(script.id, user.id)"
              :active-match="activeSearchMatchKey === getUserSearchMatchKey(script.id, user.id)"
              :register-match-element="registerMatchElement"
              @edit-user="emit('editUser', $event)"
              @delete-user="emit('deleteUser', $event)"
              @toggle-user-status="emit('toggleUserStatus', $event)"
              @pass-check="emit('passCheckUser', $event)"
            />
          </template>
        </draggable>
      </div>

      <!-- 空状态 -->
      <div v-else-if="!collapsed || searchActive" class="empty-users">
        <EmptyState title="暂无用户" description="为此脚本添加首个用户" :icon="UserAddOutlined">
          <template #actions>
            <a-button
              type="primary"
              class="empty-users-action"
              :disabled="!isOperable"
              @click="emit('addUser', script)"
            >
              <template #icon>
                <UserAddOutlined />
              </template>
              添加用户
            </a-button>
          </template>
        </EmptyState>
      </div>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Modal } from 'ant-design-vue'
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
import type { MaaFWScriptConfig, Script, User } from '@/types/script'
import { getScriptIcon, getScriptTypeTagColor, handleScriptIconError } from '@/utils/scriptRegistry'
import {
  getScriptSearchMatchKey,
  getUserSearchMatchKey,
  matchesScriptOwnSearch,
  matchesUserSearch,
} from '@/views/scripts/scriptPageSearch'
import { isSameOrder, restoreItemOrder } from '@/views/scripts/reorderHelpers'
import EmptyState from '@/components/v6/EmptyState.vue'
import ScriptUserRow from './ScriptUserRow.vue'

interface Props {
  script: Script
  activeConnections: Map<string, { subscriptionId: string; websocketId: string }>
  copyingScriptId?: string | null
  searchActive: boolean
  normalizedSearchKeyword: string
  activeSearchMatchKey: string
  collapsed: boolean
  registerMatchElement: (key: string, element: unknown) => void
}

interface Emits {
  (e: 'edit', script: Script): void
  (e: 'delete', script: Script): void
  (e: 'copy', script: Script): void
  (e: 'addUser', script: Script): void
  (e: 'editUser', user: User): void
  (e: 'deleteUser', user: User): void
  (e: 'startSrcConfig', script: Script): void
  (e: 'startMaaEndConfig', script: Script): void
  (e: 'toggleUserStatus', user: User): void
  (e: 'passCheckUser', user: User): void
  (e: 'toggleCollapsed'): void
  (e: 'userReorder', scriptId: string, userIds: string[], previousUserIds: string[]): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const localUsers = ref<User[]>([...props.script.users])
const isReorderingUsers = ref(false)
const userOrderBeforeDrag = ref<string[]>([])

// 仅在外部引用变化时同步；用户排序 pending 期间跳过，避免刷新覆盖新状态
watch(
  () => props.script.users,
  newUsers => {
    if (isReorderingUsers.value) return
    localUsers.value = [...newUsers]
  }
)

const isOperable = computed(() => props.script.available !== false)
const canEdit = computed(() => props.script.providerAvailable ?? isOperable.value)
const isActiveConfig = computed(() => props.activeConnections.has(props.script.id))
const scriptMatchKey = computed(() => getScriptSearchMatchKey(props.script.id))
const scriptMatchActive = computed(() => props.activeSearchMatchKey === scriptMatchKey.value)

const showUsersSection = computed(() => {
  if (props.collapsed && !props.searchActive) return false
  return Boolean(props.script.users && props.script.users.length > 0)
})

const getMaaFWProjectLabel = (script: Script) => {
  const config = script.config as Partial<MaaFWScriptConfig> | undefined
  return config?.Info?.ProjectLabel?.trim() || 'MaaFW'
}

const getScriptTypeLabel = (script: Script) => {
  if (script.type === 'MaaFW') return getMaaFWProjectLabel(script)
  return script.displayName || script.type
}

const shouldShowUserInSearch = (user: User): boolean =>
  !props.searchActive ||
  matchesScriptOwnSearch(props.script, props.normalizedSearchKeyword) ||
  matchesUserSearch(user, props.normalizedSearchKeyword)

const handleDeleteConfirm = () => {
  Modal.confirm({
    title: '确定要删除这个脚本吗？',
    content: '删除后将无法恢复，请谨慎操作',
    okText: '确定',
    okType: 'danger',
    cancelText: '取消',
    onOk: () => emit('delete', props.script),
  })
}

const onUserDragStart = () => {
  userOrderBeforeDrag.value = localUsers.value.map(u => u.id)
  isReorderingUsers.value = true
}

const restoreLocalUserOrder = () => {
  localUsers.value = restoreItemOrder(userOrderBeforeDrag.value, props.script.users)
}

const onUserDragEnd = () => {
  const userIds = localUsers.value.map(u => u.id)
  const previousIds = userOrderBeforeDrag.value
  if (isSameOrder(userIds, previousIds)) {
    isReorderingUsers.value = false
    userOrderBeforeDrag.value = []
    return
  }
  emit('userReorder', props.script.id, userIds, previousIds)
}

const finishUserReorder = (success: boolean) => {
  if (!success) restoreLocalUserOrder()
  isReorderingUsers.value = false
  userOrderBeforeDrag.value = []
}

defineExpose({ finishUserReorder })
</script>

<style scoped>
.script-wrapper {
  width: 100%;
  height: 100%;
  min-height: 0;
  cursor: auto;
}

.script-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
}

.script-chosen {
  cursor: grabbing !important;
}

.script-drag {
  transform: rotate(2deg);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2);
  z-index: 1000;
  opacity: 1 !important;
  cursor: grabbing !important;
}

.script-drag * {
  cursor: grabbing !important;
}

.script-drag .script-card {
  opacity: 1 !important;
  transition: none !important;
}

.users-list {
  flex: 1;
  min-height: 0;
  overflow: auto;
  width: 100%;
}

.user-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
  box-shadow: none !important;
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
  opacity: 1 !important;
  cursor: grabbing !important;
}

.user-drag * {
  cursor: grabbing !important;
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
  border-radius: var(--v6-radius-card);
  border: 1px solid var(--v6-color-border-subtle);
  background: var(--app-background-panel-bg, var(--v6-color-surface));
  overflow: hidden;
  height: 100%;
  display: flex;
  flex-direction: column;
  box-shadow: var(--v6-shadow-card);
  transition:
    border-color var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out);
}

.script-card :deep(.ant-card-body) {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
}

.script-card:hover {
  border-color: color-mix(in srgb, var(--ant-color-primary) 54%, var(--v6-color-border));
}

.script-wrapper.search-match-active .script-card {
  border-color: var(--ant-color-primary);
  box-shadow:
    0 0 0 2px color-mix(in srgb, var(--ant-color-primary) 22%, transparent),
    var(--v6-shadow-card);
}

.config-active-btn {
  color: var(--v6-color-success);
  border-color: var(--v6-color-success);
}

/* 脚本头部 */
.script-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--v6-space-4) var(--v6-space-4) var(--v6-space-3);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  flex-shrink: 0;
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
  cursor: grab;
  flex-shrink: 0;
  user-select: none;
}

.script-drag-handle:active {
  cursor: grabbing;
}

.drag-handle-disabled,
.drag-handle-disabled:active {
  cursor: default;
  opacity: 0.45;
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
  border-radius: var(--v6-radius-card);
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--v6-color-window);
  border: 1px solid var(--v6-color-border);
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
  border-radius: var(--v6-radius-control);
  font-weight: 500;
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
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* 空状态 */
.empty-users {
  flex: 1;
  display: flex;
  min-height: 0;
  align-items: center;
  justify-content: center;
  overflow: auto;
}

.empty-users :deep(.v6-empty-state) {
  width: 100%;
  min-height: 100%;
}

/* 响应式设计:按脚本页容器宽度响应(侧栏挤压时同样生效),不用视口 @media */
@container scripts-page (max-width: 768px) {
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

  .empty-users {
    padding: 30px 16px;
  }
}

@container scripts-page (max-width: 576px) {
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
}
</style>

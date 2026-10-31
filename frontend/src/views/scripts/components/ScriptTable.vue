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
            <ScriptCardHeader
              :script="script"
              :configuring="props.activeConnections.has(script.id)"
              :collapsed="isUsersCollapsed(script.id)"
              :searching="props.searching"
              :copying-script-id="props.copyingScriptId"
              @action="handleCardAction"
              @toggle-users="toggleUsersCollapsed"
            />

            <a-alert
              v-if="script.usersLoadError"
              class="users-load-error"
              type="error"
              show-icon
              :message="t('core.apiErrors.userLoadRetry', { reason: script.usersLoadError })"
            >
              <template #action>
                <a-button
                  size="small"
                  :loading="props.retryingUsers?.has(script.id)"
                  @click="emit('retryUsers', script.id)"
                >
                  {{ t('core.apiErrors.retry') }}
                </a-button>
              </template>
            </a-alert>

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
                  <ScriptUserRow
                    :user="user"
                    :script="script"
                    :account-expanded="expandedUserIds.has(user.id)"
                    :password-expanded="expandedUserPasswords.has(user.id)"
                    @toggle-disclosure="toggleDisclosure"
                    @edit="emit('editUser', $event)"
                    @delete="emit('deleteUser', $event)"
                    @toggle-status="emit('toggleUserStatus', $event)"
                  />
                </template>
              </draggable>
            </div>

            <!-- 空状态 -->
            <div
              v-else-if="!script.usersLoadError && !isUsersCollapsed(script.id)"
              class="empty-users"
            >
              <NoData :image-style="{ height: '120px' }" :description="false" />
            </div>
          </a-card>
        </div>
      </template>
    </draggable>
  </div>
</template>
<script setup lang="ts">
import ScriptCardHeader, {
  type ScriptCardAction,
} from '@/views/scripts/components/ScriptCardHeader.vue'
import ScriptUserRow from '@/views/scripts/components/ScriptUserRow.vue'
import { ref, watch } from 'vue'
import { useStorage } from '@vueuse/core'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import draggable from 'vuedraggable'
import type { ScriptListItem, ScriptListUser } from '@/views/scripts/scriptListModel'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
const { t } = useI18n()
const { reorderScript } = useScriptApi()
const { reorderUser } = useUserApi()
interface Props {
  scripts: ScriptListItem[]
  activeConnections: Map<string, { subscriptionIds: string[]; taskId: string }>
  copyingScriptId?: string | null
  searching?: boolean
  retryingUsers?: ReadonlySet<string>
}

interface Emits {
  (e: 'retryUsers', scriptId: string): void
  (e: 'edit', script: ScriptListItem): void

  (e: 'delete', script: ScriptListItem): void

  (e: 'copy', script: ScriptListItem): void

  (e: 'addUser', script: ScriptListItem): void

  (e: 'editUser', user: ScriptListUser): void

  (e: 'deleteUser', user: ScriptListUser): void

  (e: 'startMaaConfig', script: ScriptListItem): void

  (e: 'startSrcConfig', script: ScriptListItem): void

  (e: 'startMaaEndConfig', script: ScriptListItem): void

  (e: 'startOkwwConfig', script: ScriptListItem): void

  (e: 'startWhimboxConfig', script: ScriptListItem): void

  (e: 'toggleUserStatus', user: ScriptListUser): void

  (e: 'scriptsReordered', scripts: ScriptListItem[]): void
}

const props = defineProps<Props>()

const emit = defineEmits<Emits>()

// 本地脚本列表状态
const localScripts = ref<ScriptListItem[]>([])

// 脚本用户列表收起状态 - 持久化到 localStorage，切换页面后仍保持
const COLLAPSED_SCRIPTS_STORAGE_KEY = 'scripts.collapsedScriptIds'

const collapsedScriptIds = useStorage<Set<string>>(
  COLLAPSED_SCRIPTS_STORAGE_KEY,
  new Set(),
  undefined,
  {
    serializer: {
      read: raw => {
        const parsed: unknown = JSON.parse(raw)
        return new Set(
          Array.isArray(parsed) ? parsed.filter((id): id is string => typeof id === 'string') : []
        )
      },
      write: ids => JSON.stringify([...ids]),
    },
    writeDefaults: false,
    listenToStorageChanges: false,
    flush: 'sync',
    // 存储不可用时仍保持当前会话内的展开/折叠。
    onError: () => {},
  }
)

const isUsersCollapsed = (scriptId: string) =>
  !props.searching && collapsedScriptIds.value.has(scriptId)

// 账号信息展开状态管理 - 使用用户ID作为key
const expandedUserIds = ref<Set<string>>(new Set())

const expandedUserPasswords = ref<Set<string>>(new Set())

const handleDelete = (script: ScriptListItem) => {
  emit('delete', script)
}

const handleDeleteConfirm = (script: ScriptListItem) => {
  Modal.confirm({
    title: t('core.comp.deleteThisScript'),
    content: t('core.comp.thisCannotBeUndone2'),
    okText: t('core.comp.ok'),
    okType: 'danger',
    cancelText: t('core.comp.cancel'),
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
}

const collapseAllUsers = () => {
  collapsedScriptIds.value = new Set(localScripts.value.map(script => script.id))
}

const expandAllUsers = () => {
  collapsedScriptIds.value = new Set()
}

const onScriptDragEnd = async () => {
  if (props.searching) return
  const scriptIds = localScripts.value.map(s => s.id)
  const success = await reorderScript(scriptIds)
  if (success) {
    emit('scriptsReordered', localScripts.value)
  }
}

const onUserDragEnd = async (script: ScriptListItem) => {
  if (props.searching) return
  const userIds = script.users.map(u => u.id)
  await reorderUser(script.id, userIds)
}
// 监听 props 变化，更新本地状态。只关心数组引用（增删、父级回写的新顺序），
// 不能 deep：父级改共享对象（启停用户、删用户）时会用未重排的父数组把拖拽顺序覆盖回去
watch(
  () => props.scripts,
  newScripts => {
    localScripts.value = [...newScripts]
  },
  { immediate: true }
)
defineExpose({ collapseAllUsers, expandAllUsers })
const toggleDisclosure = (userId: string, kind: 'account' | 'password') => {
  const set = kind === 'account' ? expandedUserIds.value : expandedUserPasswords.value
  if (set.has(userId)) set.delete(userId)
  else set.add(userId)
}
const handleCardAction = (action: ScriptCardAction, script: ScriptListItem) => {
  switch (action) {
    case 'startMaaConfig':
      emit('startMaaConfig', script)
      break
    case 'startSrcConfig':
      emit('startSrcConfig', script)
      break
    case 'startMaaEndConfig':
      emit('startMaaEndConfig', script)
      break
    case 'startOkwwConfig':
      emit('startOkwwConfig', script)
      break
    case 'startWhimboxConfig':
      emit('startWhimboxConfig', script)
      break
    case 'edit':
      emit('edit', script)
      break
    case 'addUser':
      emit('addUser', script)
      break
    case 'copy':
      emit('copy', script)
      break
    case 'delete':
      handleDeleteConfirm(script)
      break
  }
}
</script>
<style scoped src="@/views/scripts/components/scriptListDrag.css"></style>
<style scoped>
.users-load-error {
  margin: 16px 24px;
}

.scripts-grid {
  width: 100%;
}
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
.script-ghost .script-card:hover,
.script-drag .script-card:hover {
  transform: none !important;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.2) !important;
}

.user-ghost:hover,
.user-drag:hover {
  background: var(--ant-color-primary-bg) !important;
}
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
.users-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}
.empty-users {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 20px;
}
@media (max-width: 768px) {
  .empty-users {
    padding: 30px 16px;
  }
}
</style>

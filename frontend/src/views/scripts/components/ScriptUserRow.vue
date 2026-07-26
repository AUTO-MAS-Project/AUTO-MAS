<template>
  <div
    v-show="shouldShow"
    :ref="element => registerMatchElement(matchKey, element)"
    :class="['user-item', { 'search-match-active': activeMatch }]"
    :aria-current="activeMatch ? 'true' : undefined"
  >
    <span
      class="user-drag-handle"
      :class="{ 'drag-handle-disabled': dragDisabled }"
      :title="dragDisabled ? '搜索期间暂停拖拽排序' : '拖拽排序'"
      aria-label="拖拽排序"
      :aria-disabled="dragDisabled"
    >
      <span class="script-drag-dots" aria-hidden="true"></span>
    </span>
    <div class="user-info">
      <div class="user-details-row">
        <div class="user-name-section">
          <span class="user-name">{{ user.Info.Name }}</span>
          <a-tag
            v-if="shouldShowServerTag(user)"
            :color="getUserServerTagColor(user)"
            class="server-tag"
          >
            {{ getUserServerDisplayName(user) }}
          </a-tag>
          <a-tag
            v-if="shouldShowUserIdTag(user)"
            :color="getUserIdentityTagColor(user)"
            class="clickable-tag"
            @click="userDisplay.handleUserIdClick(user)"
          >
            {{ userDisplay.getUserIdDisplayText(user) }}
          </a-tag>
          <a-tag
            v-if="shouldShowPasswordTag(user)"
            :color="getUserIdentityTagColor(user)"
            class="clickable-tag"
            @click="userDisplay.handlePasswordClick(user)"
          >
            {{ userDisplay.getPasswordDisplayText(user) }}
          </a-tag>
        </div>
        <div v-if="shouldShowStatusTags(user)" class="user-info-tags">
          <a-tag
            v-for="(tag, index) in getUserStatusTags(user)"
            :key="index"
            :title="tag.text"
            :class="['info-tag', { 'clickable-tag': isPassCheckTag(tag) }]"
            :color="tag.color || 'default'"
            @click="isPassCheckTag(tag) ? emit('passCheck', user) : undefined"
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
          class="status-switch"
          :disabled="!operable"
          @click="emit('toggleUserStatus', user)"
        />
      </div>
      <div class="user-actions">
        <a-tooltip title="编辑用户配置">
          <a-button
            type="default"
            size="middle"
            class="user-action-btn"
            :disabled="!operable"
            @click="emit('editUser', user)"
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
          @confirm="emit('deleteUser', user)"
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

<script setup lang="ts">
import { DeleteOutlined, EditOutlined } from '@ant-design/icons-vue'
import type { User } from '@/types/script'
import { useUserDisplay } from '@/views/scripts/composables/useUserDisplay'
import {
  getUserServerTagColor,
  getUserServerDisplayName,
  getUserIdentityTagColor,
  getUserStatusTags,
  isPassCheckTag,
  shouldShowServerTag,
  shouldShowUserIdTag,
  shouldShowPasswordTag,
  shouldShowStatusTags,
} from '@/views/scripts/composables/useUserDisplay'

interface Props {
  user: User
  operable: boolean
  dragDisabled: boolean
  shouldShow: boolean
  matchKey: string
  activeMatch: boolean
  registerMatchElement: (key: string, element: unknown) => void
}

interface Emits {
  (e: 'editUser', user: User): void
  (e: 'deleteUser', user: User): void
  (e: 'toggleUserStatus', user: User): void
  (e: 'passCheck', user: User): void
}

defineProps<Props>()
const emit = defineEmits<Emits>()

const userDisplay = useUserDisplay()
</script>

<style scoped>
.user-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: var(--v6-space-4);
  border-bottom: 1px solid var(--v6-color-border-subtle);
  min-height: 80px;
  transition:
    background var(--v6-motion-fast) var(--v6-ease-out),
    box-shadow var(--v6-motion-fast) var(--v6-ease-out);
}

.user-item.search-match-active {
  background: color-mix(in srgb, var(--ant-color-primary) 10%, transparent);
  box-shadow: inset 3px 0 0 var(--ant-color-primary);
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
  cursor: grab;
  flex-shrink: 0;
  user-select: none;
}

.user-drag-handle:active {
  cursor: grabbing;
}

.user-drag-handle:hover .script-drag-dots {
  opacity: 0.85;
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

.clickable-tag {
  cursor: pointer;
  user-select: none;
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
  border-radius: var(--v6-radius-control);
  font-weight: 500;
  min-width: 60px;
  border: 1px solid var(--v6-color-border);
  background: var(--v6-color-surface);
}

.user-action-btn.ant-btn-dangerous {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
}

/* 按脚本页容器宽度响应(侧栏挤压时同样生效),不用视口 @media */
@container scripts-page (max-width: 768px) {
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
}

@container scripts-page (max-width: 576px) {
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
}
</style>

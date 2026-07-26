<script setup lang="ts">
/**
 * Lane 8：游戏签到 - 用户列表表格。
 *
 * 从 TabGameSign.vue 拆分。负责：
 * - 渲染账号列表（含拖拽排序 handle）
 * - 每行展示社区签到标签云（来自 useSignResultTags）
 * - 行内启用/禁用切换
 * - 编辑/删除操作
 *
 * 拖拽排序由 vuedraggable 完成；排序变更通过 @reorder 事件上传父组件保存。
 */
import { EditOutlined, DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import type { AccountLike, PlatformTag, AccountGroup } from '../composables/useSignResultTags'
import { getTagText, getTagClass } from '../composables/useSignResultTags'

export interface AccountInstance extends AccountLike {
  type: string
  Name: string
  Enabled: boolean
}

defineProps<{
  accounts: AccountInstance[]
  addLoading: boolean
  disabled: boolean
  isDragging: boolean
  getTagsForAccount: (account: AccountLike) => PlatformTag[]
  getGroupsForPlatform: (account: AccountLike, platform: string) => AccountGroup[]
}>()

const emit = defineEmits<{
  add: []
  delete: [account: AccountInstance]
  edit: [account: AccountInstance]
  'field-save': [account: AccountInstance]
  reorder: [evt: any]
  'select-visible-change': [visible: boolean]
}>()
</script>

<template>
  <div class="form-section">
    <div class="section-header">
      <h3>用户列表</h3>
      <a-button
        type="primary"
        ghost
        size="middle"
        :loading="addLoading"
        :disabled="disabled"
        @click="emit('add')"
      >
        <template #icon><PlusOutlined /></template>
        添加用户
      </a-button>
    </div>

    <div class="user-table-container">
      <!-- 表头 -->
      <div class="user-table-header">
        <div class="header-cell drag-cell"></div>
        <div class="header-cell name-cell">用户名</div>
        <div class="header-cell status-cell">状态</div>
        <div class="header-cell tags-cell">各社区签到情况</div>
        <div class="header-cell actions-cell">操作</div>
      </div>

      <!-- 拖拽内容 -->
      <draggable
        :list="accounts"
        item-key="uid"
        :animation="200"
        :disabled="disabled || isDragging"
        ghost-class="user-ghost"
        chosen-class="user-chosen"
        drag-class="user-drag"
        handle=".drag-handle"
        class="user-draggable"
        @end="emit('reorder', $event)"
      >
        <template #item="{ element: account }">
          <div class="user-row">
            <!-- 拖拽手柄 -->
            <div class="row-cell drag-cell">
              <span class="drag-handle" title="拖拽排序">
                <span class="drag-dots"></span>
              </span>
            </div>
            <!-- 用户名 -->
            <div class="row-cell name-cell">
              <span class="user-name-text">{{ account.Name }}</span>
            </div>
            <!-- 状态 -->
            <div class="row-cell status-cell">
              <a-select
                v-model:value="account.Enabled"
                size="middle"
                style="width: 100px"
                :disabled="disabled"
                :class="{ 'select-enabled': account.Enabled }"
                @change="emit('field-save', account)"
                @dropdown-visible-change="emit('select-visible-change', $event)"
              >
                <a-select-option :value="true">启用</a-select-option>
                <a-select-option :value="false">禁用</a-select-option>
              </a-select>
            </div>
            <!-- 社区签到情况（标签云） -->
            <div class="row-cell tags-cell">
              <a-space :size="6" wrap>
                <a-tooltip v-for="tag in getTagsForAccount(account)" :key="tag.platform">
                  <template #title>
                    <div class="sign-tooltip">
                      <div class="sign-tooltip-title">{{ tag.platform }} - 签到详情</div>
                      <template
                        v-for="(group, gIdx) in getGroupsForPlatform(account, tag.platform)"
                        :key="gIdx"
                      >
                        <div class="sign-tooltip-alias">{{ group.account_alias }}</div>
                        <div v-for="game in group.games" :key="game.game" class="sign-tooltip-row">
                          <span>{{ game.game }}</span>
                          <span
                            :class="
                              game.status === '成功' || game.status === '已签到'
                                ? 'tt-signed'
                                : game.status === '风控'
                                  ? 'tt-risk'
                                  : game.status === '失败'
                                    ? 'tt-failed'
                                    : 'tt-unsigned'
                            "
                          >
                            ●
                            {{
                              game.status === '成功' || game.status === '已签到'
                                ? '已签'
                                : game.status === '风控'
                                  ? '风控'
                                  : game.status === '失败'
                                    ? '失败'
                                    : '未签'
                            }}
                          </span>
                          <span v-if="game.reward" class="tt-reward">{{ game.reward }}</span>
                        </div>
                      </template>
                      <div v-if="tag.games.length === 0" class="sign-tooltip-empty">
                        暂无签到数据
                      </div>
                    </div>
                  </template>
                  <span :class="['platform-tag', getTagClass(tag.status)]">
                    {{ getTagText(tag) }}
                  </span>
                </a-tooltip>
              </a-space>
            </div>
            <!-- 操作 -->
            <div class="row-cell actions-cell">
              <a-space :size="8">
                <a-button size="middle" class="action-btn edit-btn" @click="emit('edit', account)">
                  <template #icon><EditOutlined /></template>
                  编辑
                </a-button>
                <a-popconfirm
                  title="确定要删除此用户吗？"
                  ok-text="确定"
                  cancel-text="取消"
                  @confirm="emit('delete', account)"
                >
                  <a-button size="middle" class="action-btn delete-btn">
                    <template #icon><DeleteOutlined /></template>
                    删除
                  </a-button>
                </a-popconfirm>
              </a-space>
            </div>
          </div>
        </template>
      </draggable>

      <!-- 空状态 -->
      <div v-if="accounts.length === 0" class="empty-state">
        <div class="empty-hint">暂无用户</div>
        <div class="empty-guide">点击右上角「添加用户」创建</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 选中启用时边框变绿 */
.select-enabled :deep(.ant-select-selector) {
  border-color: var(--ant-color-success) !important;
}

/* 用户列表表格 */
.user-table-container {
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  overflow: hidden;
  background: var(--ant-color-bg-container);
}

.user-table-header {
  display: flex;
  align-items: center;
  background-color: var(--ant-color-fill-quaternary);
  border-bottom: 1px solid var(--ant-color-border);
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
  min-height: 48px;
}

.user-table-header .header-cell {
  padding: 12px 16px;
  border-right: 1px solid var(--ant-color-border);
}

.user-table-header .header-cell:last-child {
  border-right: none;
}

.drag-cell {
  width: 36px;
  min-width: 36px;
  max-width: 36px;
  text-align: center;
}
.name-cell {
  width: 140px;
  min-width: 140px;
  text-align: center;
}
.status-cell {
  width: 120px;
  min-width: 120px;
}
.tags-cell {
  flex: 1;
  min-width: 0;
}
.actions-cell {
  width: 200px;
  min-width: 200px;
  text-align: center;
}

.user-draggable {
  min-height: 60px;
}

.user-row {
  display: flex;
  align-items: center;
  min-height: 64px;
  border-bottom: 1px solid var(--ant-color-border);
  padding: 0;
  transition: background 0.2s ease;
  cursor: default;
  background: var(--ant-color-bg-container);
}

.user-row:last-child {
  border-bottom: none;
}
.user-row:hover {
  background-color: var(--ant-color-fill-quaternary);
}

.row-cell {
  padding: 14px 16px;
  text-align: center;
  border-right: 1px solid var(--ant-color-border);
  display: flex;
  align-items: center;
  justify-content: center;
}

.row-cell:last-child {
  border-right: none;
}

.row-cell.name-cell {
  justify-content: center;
}
.row-cell.tags-cell {
  justify-content: flex-start;
  padding-right: 20px;
}
.row-cell.actions-cell {
  justify-content: center;
  padding: 14px 24px;
}

/* 拖拽手柄 */
.drag-handle {
  width: 16px;
  height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--ant-color-text-tertiary);
  background: transparent;
  border: none;
  cursor: grab;
  user-select: none;
}

.drag-handle:active {
  cursor: grabbing;
}

.drag-dots {
  width: 10px;
  height: 16px;
  display: block;
  background-image: radial-gradient(currentColor 1.2px, transparent 1.2px);
  background-size: 5px 5px;
  opacity: 0.65;
}

.drag-handle:hover .drag-dots {
  opacity: 0.85;
}

/* 拖拽视觉反馈 */
.user-ghost {
  opacity: 0 !important;
  background: transparent !important;
  border-color: transparent !important;
}
.user-chosen {
  cursor: grabbing !important;
}
.user-drag {
  transform: rotate(3deg);
  opacity: 1 !important;
}

/* 用户名 */
.user-name-text {
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

/* 社区标签云 */
.platform-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  line-height: 1.5;
  border: 1px solid transparent;
  cursor: default;
  white-space: nowrap;
}

.tag-signed {
  background: #f6ffed;
  border-color: #b7eb8f;
  color: #52c41a;
}
.tag-unsigned {
  background: #f5f5f5;
  border-color: #e8e8e8;
  color: #999;
}
.tag-failed {
  background: #fff1f0;
  border-color: #ffa39e;
  color: #f5222d;
}
.tag-risk {
  background: #fff2e8;
  border-color: #ffbb96;
  color: #e8590c;
}
.tag-partial {
  background: #fff7e6;
  border-color: #ffd591;
  color: #fa8c16;
}

/* Tooltip 签到详情 */
.sign-tooltip {
  min-width: 220px;
  color: rgba(255, 255, 255, 0.85);
}
.sign-tooltip-title {
  font-size: 13px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  padding-bottom: 8px;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.18);
}
.sign-tooltip-alias {
  font-size: 12px;
  font-weight: 600;
  color: rgba(255, 255, 255, 0.95);
  padding: 4px 0 2px;
  margin-top: 4px;
}
.sign-tooltip-alias:first-of-type {
  margin-top: 0;
}
.sign-tooltip-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 2px 0;
  font-size: 13px;
  gap: 12px;
}
.tt-signed {
  color: #52c41a;
}
.tt-unsigned {
  color: #d4b106;
}
.tt-risk {
  color: #e8590c;
}
.tt-failed {
  color: #f5222d;
}
.tt-reward {
  color: rgba(255, 255, 255, 0.55);
  font-size: 12px;
}
.sign-tooltip-empty {
  color: rgba(255, 255, 255, 0.55);
  font-size: 13px;
  text-align: center;
  padding: 8px 0;
}

/* 操作按钮 */
.action-btn {
  padding: 4px 12px;
  border-radius: 4px;
  font-size: 13px;
  border: 1px solid;
  background: transparent;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.edit-btn {
  border-color: var(--ant-color-border);
  color: var(--ant-color-text-secondary);
}

.edit-btn:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
}

.delete-btn {
  border-color: var(--ant-color-error);
  color: var(--ant-color-error);
}

.delete-btn:hover {
  border-color: #ff7875;
  color: #ff7875;
}

/* 空状态 */
.empty-state {
  text-align: center;
  padding: 48px 0;
}
.empty-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 15px;
  margin-bottom: 6px;
}
.empty-guide {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}
</style>

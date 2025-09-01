<template>
  <div class="scripts-grid">
    <a-row :gutter="[24, 24]">
      <a-col
        v-for="script in props.scripts"
        :key="script.id"
        :xs="24"
        :sm="24"
        :md="24"
        :lg="24"
        :xl="24"
        :xxl="24"
      >
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
                <img v-else src="@/assets/AUTO_MAA.png" alt="AUTO_MAA" class="script-logo" />
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
                @click="handleMAAConfig(script)"
              >
                <template #icon>
                  <SettingOutlined />
                </template>
                设置MAA全局配置
              </a-button>
              <a-button
                v-if="script.type === 'MAA' && props.activeConnections.has(script.id)"
                type="primary"
                danger
                size="middle"
                @click="handleDisconnectMAA(script)"
              >
                <template #icon>
                  <StopOutlined />
                </template>
                断开配置连接
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
                @confirm="handleDelete(script)"
                ok-text="确定"
                cancel-text="取消"
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
          <div class="users-section" v-if="script.users && script.users.length > 0">
            <div class="users-list">
              <div v-for="user in script.users" :key="user.id" class="user-item">
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

                    <!-- 用户详细信息 - 只有MAA脚本才显示 -->
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
                        v-if="user.Info.RemainedDay !== undefined && user.Info.RemainedDay !== null"
                        class="info-tag"
                        :color="
                          user.Info.RemainedDay < 1
                            ? 'gold'
                            : user.Info.RemainedDay > 30
                              ? 'green'
                              : 'orange'
                        "
                      >
                        剩余天数:
                        {{ user.Info.RemainedDay < 1 ? '长期有效' : user.Info.RemainedDay + '天' }}
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

                      <!-- 关卡信息 - Stage固定展示 -->
                      <a-tag v-if="user.Info.Stage" class="info-tag" color="blue">
                        关卡: {{ user.Info.Stage === '-' ? '未选择' : user.Info.Stage }}
                      </a-tag>

                      <!-- 额外关卡 - 只有不为-或空时才显示 -->
                      <a-tag
                        v-if="
                          user.Info.Stage_1 && user.Info.Stage_1 !== '-' && user.Info.Stage_1 !== ''
                        "
                        class="info-tag"
                        color="geekblue"
                      >
                        关卡1: {{ user.Info.Stage_1 }}
                      </a-tag>

                      <a-tag
                        v-if="
                          user.Info.Stage_2 && user.Info.Stage_2 !== '-' && user.Info.Stage_2 !== ''
                        "
                        class="info-tag"
                        color="geekblue"
                      >
                        关卡2: {{ user.Info.Stage_2 }}
                      </a-tag>

                      <a-tag
                        v-if="
                          user.Info.Stage_3 && user.Info.Stage_3 !== '-' && user.Info.Stage_3 !== ''
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

                      <a-tag
                        class="info-tag"
                        color="magenta"
                      >
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
                      @click="handleToggleUserStatus(user)"
                      class="status-switch"
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
                      @confirm="handleDeleteUser(user)"
                      ok-text="确定"
                      cancel-text="取消"
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
            </div>
          </div>

          <!-- 空状态 -->
          <div v-else class="empty-users">
            <a-empty
              description="暂无用户"
              class="compact-empty"
            >
              <a-button type="primary" size="small" @click="handleAddUser(script)">
                <template #icon>
                  <PlusOutlined />
                </template>
                添加用户
              </a-button>
            </a-empty>
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import type { Script, User } from '../types/script'
import {
  DeleteOutlined,
  EditOutlined,
  PlusOutlined,
  SettingOutlined,
  StopOutlined,
  UserAddOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'

interface Props {
  scripts: Script[]
  activeConnections: Map<string, string>
}

interface Emits {
  (e: 'edit', script: Script): void

  (e: 'delete', script: Script): void

  (e: 'addUser', script: Script): void

  (e: 'editUser', user: User): void

  (e: 'deleteUser', user: User): void

  (e: 'maaConfig', script: Script): void

  (e: 'disconnectMaa', script: Script): void

  (e: 'toggleUserStatus', user: User): void
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

const handleMAAConfig = (script: Script) => {
  emit('maaConfig', script)
}

const handleDisconnectMAA = (script: Script) => {
  emit('disconnectMaa', script)
}

const handleToggleUserStatus = (user: User) => {
  emit('toggleUserStatus', user)
}

function get_annihilation_name(annihilation_name) {
  if (annihilation_name == 'Annihilation') {
    return '当期剿灭'
  }
  if (annihilation_name == 'Chernobog@Annihilation') {
    return '切尔诺伯格'
  }
  if (annihilation_name == 'LungmenOutskirts@Annihilation') {
    return '龙门外环'
  }
  if (annihilation_name == 'LungmenDowntown@Annihilation') {
    return '龙门市区'
  }
  return '未开启'
}

const truncateText = (text: string, maxLength: number = 20): string => {
  if (!text) return ''
  return text.length > maxLength ? text.substring(0, maxLength) + '...' : text
}
</script>

<style scoped>
.scripts-grid {
  width: 100%;
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

.config-button {
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-color: var(--ant-color-primary);
}

.config-button:hover {
  background: linear-gradient(
    135deg,
    var(--ant-color-primary-hover),
    var(--ant-color-primary-active)
  );
  border-color: var(--ant-color-primary-hover);
}

.edit-button {
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
}

.edit-button:hover {
  background: linear-gradient(
    135deg,
    var(--ant-color-primary-hover),
    var(--ant-color-primary-active)
  );
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

.more-actions {
  color: var(--ant-color-text-secondary);
  border: none;
  box-shadow: none;
}

.more-actions:hover {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

/* 脚本操作按钮 */
.script-actions {
  display: flex;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  background: var(--ant-color-bg-layout);
}

.script-actions .ant-btn {
  border-radius: 6px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.script-actions .ant-btn:hover {
  transform: translateY(-1px);
}

/* 用户区域 */
.users-section {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* 用户列表 */
.users-list {
  max-height: 280px; /* 增加高度以完整展示3个用户 */
  overflow-y: auto;
}

.user-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  transition: all 0.2s ease;
  min-height: 80px; /* 确保每个用户项有足够高度 */
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

.compact-empty :deep(.ant-empty-description) {
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
}

.empty-icon {
  font-size: 32px;
  color: var(--ant-color-text-quaternary);
  margin-bottom: 8px;
}

/* 折叠动画 */
.ant-collapse-transition {
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

/* 滚动条样式 */
.users-list::-webkit-scrollbar {
  width: 4px;
}

.users-list::-webkit-scrollbar-track {
  background: var(--ant-color-bg-layout);
}

.users-list::-webkit-scrollbar-thumb {
  background: var(--ant-color-border);
  border-radius: 2px;
}

.users-list::-webkit-scrollbar-thumb:hover {
  background: var(--ant-color-border-secondary);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .script-card:hover {
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  }
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

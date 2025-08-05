<template>
  <a-table
    :columns="columns"
    :data-source="scripts"
    :pagination="false"
    :expandable="expandableConfig"
    row-key="id"
    class="modern-table"
  >
    <template #bodyCell="{ column, record }">
      <template v-if="column.key === 'name'">
        <div class="script-name-cell">
          <div class="script-type-logo">
            <img
              v-if="record.type === 'MAA'"
              src="@/assets/MAA.png"
              alt="MAA"
              class="script-logo"
            />
            <img v-else src="@/assets/AUTO_MAA.png" alt="AUTO MAA" class="script-logo" />
          </div>
          <div class="script-info">
            <div class="script-title">{{ record.name }}</div>
            <a-tag :color="record.type === 'MAA' ? 'blue' : 'green'" class="script-type-tag">
              {{ record.type }}
            </a-tag>
          </div>
        </div>
      </template>

      <template v-if="column.key === 'userCount'">
        <a-badge
          :count="record.users && record.users.length ? record.users.length : 0"
          :number-style="{
            backgroundColor: record.users.length > 0 ? '#52c41a' : '#d9d9d9',
            color: record.users.length > 0 ? '#fff' : '#666',
          }"
          class="user-count-badge"
        />
      </template>

      <template v-if="column.key === 'action'">
        <a-space size="middle">
          <a-button type="primary" size="middle" @click="handleEdit(record)" shape="round">
            <template #icon>
              <EditOutlined />
            </template>
            编辑
          </a-button>

          <a-button type="primary" size="middle" @click="handleAddUser(record)" shape="round">
            <template #icon>
              <UserAddOutlined />
            </template>
            添加用户
          </a-button>

          <a-popconfirm
            title="确定要删除这个脚本吗？"
            description="删除后将无法恢复，请谨慎操作"
            @confirm="handleDelete(record)"
            ok-text="确定"
            cancel-text="取消"
          >
            <a-button danger size="middle" type="primary" shape="round">
              <template #icon>
                <DeleteOutlined />
              </template>
              删除
            </a-button>
          </a-popconfirm>
        </a-space>
      </template>
    </template>

    <template #expandedRowRender="{ record }">
      <div class="expanded-content">
        <a-table
          :columns="userColumns"
          :data-source="record.users"
          :pagination="false"
          size="small"
          row-key="id"
          class="user-table"
        >

          <template #bodyCell="{ column, record: user }">
            <template v-if="column.key === 'server'">
              <div class="server-cell">
                <a-tag color="green">{{ user.Info.Server === 'Official' ? '官服' : 'B服' }}</a-tag>
              </div>
            </template>
            <template v-if="column.key === 'status'">
              <div class="status-cell">
                <PlayCircleOutlined v-if="user.Info.Status" class="status-icon active" />
                <PauseCircleOutlined v-else class="status-icon inactive" />
                <a-tag :color="user.Info.Status ? 'success' : 'error'">
                  {{ user.Info.Status ? '启用' : '禁用' }}
                </a-tag>
              </div>
            </template>

            <template v-if="column.key === 'lastRun'">
              <div class="last-run-cell">
                <div v-if="!user.Data.LastAnnihilationDate && !user.Data.LastProxyDate" class="no-run-text">
                  尚未运行
                </div>
                <template v-else>
                  <div class="run-item" v-if="user.Data.LastAnnihilationDate">
                    <span class="run-label">剿灭:</span>
                    <span class="run-date">{{ user.Data.LastAnnihilationDate }}</span>
                  </div>
                  <div class="run-item" v-if="user.Data.LastProxyDate">
                    <span class="run-label">代理:</span>
                    <span class="run-date">{{ user.Data.LastProxyDate }}</span>
                  </div>
                </template>
              </div>
            </template>


            <template v-if="column.key === 'userAction'">
              <a-space size="small">
                <a-tooltip title="编辑用户配置">
                  <a-button
                    type="link"
                    size="small"
                    @click="handleEditUser(user)"
                    class="user-action-button"
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
                    <a-button type="link" danger size="small" class="user-action-button">
                      <template #icon>
                        <DeleteOutlined />
                      </template>
                      删除
                    </a-button>
                  </a-tooltip>
                </a-popconfirm>
              </a-space>
            </template>
          </template>
        </a-table>
      </div>
    </template>
  </a-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TableColumnsType } from 'ant-design-vue'
import type { Script, User } from '../types/script'
import {
  DeleteOutlined,
  EditOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  UserAddOutlined,
} from '@ant-design/icons-vue'

interface Props {
  scripts: Script[]
}

interface Emits {
  (e: 'edit', script: Script): void

  (e: 'delete', script: Script): void

  (e: 'addUser', script: Script): void

  (e: 'editUser', user: User): void

  (e: 'deleteUser', user: User): void
}

const props = defineProps<Props>()
const emit = defineEmits<Emits>()

const columns: TableColumnsType = [
  {
    title: '脚本名称',
    dataIndex: 'name',
    key: 'name',
    width: 300,
  },
  {
    title: '用户数量',
    dataIndex: 'userCount',
    key: 'userCount',
    width: 120,
    align: 'center',
  },
  // {
  //   title: '创建时间',
  //   dataIndex: 'createTime',
  //   key: 'createTime',
  //   width: 180,
  // },
  {
    title: '操作',
    key: 'action',
    width: 250,
    align: 'center',
  },
]

const userColumns: TableColumnsType = [
  {
    title: '用户名',
    dataIndex: ['Info', 'Name'],
    key: 'name',
    width: 150,
  },
  {
    title: 'ID',
    dataIndex: ['Info', 'Id'],
    key: 'id',
    width: 100,
  },
  {
    title: '服务器',
    dataIndex: ['Info', 'Server'],
    key: 'server',
    width: 100,
  },
  {
    title: '状态',
    key: 'status',
    width: 80,
    align: 'center',
  },
  {
    title: '最后运行',
    key: 'lastRun',
    width: 200,
  },
  {
    title: '备注',
    dataIndex: ['Info', 'Notes'],
    key: 'notes',
    width: 250,
  },
  {
    title: '操作',
    key: 'userAction',
    width: 120,
    align: 'center',
  },
]

const expandableConfig = computed(() => ({
  expandedRowRender: true,
  rowExpandable: (record: Script) => record.users && record.users.length > 0,
}))

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
</script>

<style scoped>
.modern-table :deep(.ant-table) {
  background: var(--ant-color-bg-container);
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.modern-table :deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-bg-container);
  border-bottom: 2px solid var(--ant-color-border-secondary);
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
  padding: 16px 24px;
}

.modern-table :deep(.ant-table-tbody > tr > td) {
  padding: 20px 24px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
  transition: all 0.3s ease;
}

.modern-table :deep(.ant-table-tbody > tr:hover > td) {
  background: var(--ant-color-bg-layout);
}

.modern-table :deep(.ant-table-expanded-row > td) {
  padding: 0;
  background: var(--ant-color-bg-layout);
}

/* 脚本名称单元格 */
.script-name-cell {
  display: flex;
  align-items: center;
  gap: 12px;
}

.script-type-logo {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--ant-color-bg-elevated);
  border: 1px solid var(--ant-color-border-secondary);
  overflow: hidden;
}

.script-logo {
  width: 32px;
  height: 32px;
  object-fit: contain;
  transition: all 0.3s ease;
}

.script-info {
  flex: 1;
}

.script-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 4px;
}

.script-type-tag {
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
}

/* 用户数量徽章 */
.user-count-badge :deep(.ant-badge-count) {
  font-weight: 600;
  border-radius: 8px;
  min-width: 24px;
  height: 24px;
  line-height: 24px;
  font-size: 12px;
}

/* 操作按钮 */
.action-button {
  border-radius: 8px;
  font-weight: 500;
  transition: all 0.3s ease;
}

.edit-button {
  background: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.edit-button:hover {
  background: var(--ant-color-primary-hover);
  border-color: var(--ant-color-primary-hover);
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(24, 144, 255, 0.3);
}

.add-user-button {
  border: 1px solid var(--ant-color-border);
  background: var(--ant-color-bg-container);
  color: var(--ant-color-text);
}

.add-user-button:hover {
  border-color: var(--ant-color-primary);
  color: var(--ant-color-primary);
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
}

.delete-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 8px rgba(255, 77, 79, 0.3);
}

/* 展开内容 */
.expanded-content {
  padding: 24px;
  background: var(--ant-color-bg-layout);
  border-radius: 0 0 12px 12px;
}

.user-table :deep(.ant-table) {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border-secondary);
}

.user-table :deep(.ant-table-thead > tr > th) {
  background: var(--ant-color-bg-layout);
  font-size: 13px;
  padding: 12px 16px;
}

.user-table :deep(.ant-table-tbody > tr > td) {
  padding: 16px;
  font-size: 13px;
}

/* 状态单元格 */
.status-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-icon {
  font-size: 16px;
}

.status-icon.active {
  color: #52c41a;
}

.status-icon.inactive {
  color: #ff4d4f;
}

/* 最后运行单元格 */
.last-run-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.run-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.run-label {
  color: var(--ant-color-text-secondary);
  font-weight: 500;
  min-width: 32px;
}

.run-date {
  color: var(--ant-color-text);
  font-family: 'Consolas', 'Monaco', monospace;
}

.no-run-text {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  font-style: italic;
  text-align: center;
  padding: 8px 0;
}

/* 任务标签 */
.task-tags {
  max-width: 300px;
}

.task-tag {
  font-size: 11px;
  font-weight: 500;
  border-radius: 4px;
  margin: 2px;
}

/* 用户操作按钮 */
.user-action-button {
  font-size: 12px;
  padding: 4px 8px;
  height: auto;
  border-radius: 6px;
}

.user-action-button:hover {
  transform: translateY(-1px);
}

/* 深色模式适配 */
@media (prefers-color-scheme: dark) {
  .modern-table :deep(.ant-table) {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
  }

  .edit-button:hover {
    box-shadow: 0 4px 8px rgba(24, 144, 255, 0.4);
  }

  .add-user-button:hover {
    box-shadow: 0 4px 8px rgba(255, 255, 255, 0.1);
  }

  .delete-button:hover {
    box-shadow: 0 4px 8px rgba(255, 77, 79, 0.4);
  }
}

/* 响应式设计 */
@media (max-width: 768px) {
  .modern-table :deep(.ant-table-tbody > tr > td) {
    padding: 12px 16px;
  }

  .script-name-cell {
    gap: 8px;
  }

  .script-type-icon {
    width: 32px;
    height: 32px;
    font-size: 14px;
  }

  .script-title {
    font-size: 14px;
  }

  .expanded-content {
    padding: 16px;
  }

  .action-button {
    font-size: 12px;
    padding: 4px 8px;
  }
}
</style>

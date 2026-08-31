<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { HolderOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import draggable from 'vuedraggable'
import {
  useCommunityActivityApi,
  type ActivitySnapshot,
  type ActivityStatus,
} from './useCommunityActivityApi'

const snapshots = ref<ActivitySnapshot[]>([])
const loading = ref(false)
const hasLoaded = ref(false)
const errorMessage = ref('')
const lastUpdated = ref('')
let requestId = 0

const { queryActivity } = useCommunityActivityApi()

const statusMeta = (status: ActivityStatus) => {
  switch (status) {
    case 'success':
      return { label: '已获取', color: 'success' }
    case 'empty':
      return { label: '暂无角色', color: 'default' }
    case 'limited':
      return { label: '受限', color: 'warning' }
    case 'unavailable':
      return { label: '不可用', color: 'orange' }
    case 'failed':
      return { label: '失败', color: 'error' }
    default:
      return { label: '未知', color: 'default' }
  }
}

const progressPercent = (snapshot: ActivitySnapshot) => {
  if (
    typeof snapshot.completed !== 'number' ||
    typeof snapshot.target !== 'number' ||
    snapshot.target <= 0
  ) {
    return 0
  }
  return Math.min(100, Math.max(0, Math.round((snapshot.completed / snapshot.target) * 100)))
}

const hasProgress = (snapshot: ActivitySnapshot) =>
  typeof snapshot.completed === 'number' &&
  typeof snapshot.target === 'number' &&
  snapshot.target > 0

const formatTime = (value: string) => {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString('zh-CN', {
    hour: '2-digit',
    minute: '2-digit',
  })
}

const snapshotKey = (snapshot: ActivitySnapshot) =>
  [snapshot.accountUid, snapshot.platform, snapshot.game, snapshot.roleUid, snapshot.roleName]
    .map(value => value || '-')
    .join(':')

const loadActivity = async () => {
  const currentRequestId = ++requestId
  loading.value = true
  errorMessage.value = ''
  try {
    const data = await queryActivity()
    if (currentRequestId !== requestId) return

    snapshots.value = data
    const updatedValues = data
      .map(snapshot => snapshot.updatedAt)
      .filter(Boolean)
      .sort()
    lastUpdated.value = updatedValues.at(-1) || new Date().toISOString()
  } catch (error) {
    if (currentRequestId !== requestId) return
    errorMessage.value = error instanceof Error ? error.message : '日常便笺查询失败'
  } finally {
    if (currentRequestId === requestId) {
      hasLoaded.value = true
      loading.value = false
    }
  }
}

const isEmpty = computed(() => hasLoaded.value && snapshots.value.length === 0)

onMounted(() => {
  void loadActivity()
})
</script>

<template>
  <section class="activity-view" aria-label="日常便笺">
    <header class="activity-toolbar">
      <div class="activity-heading">
        <h2 class="activity-title">日常便笺</h2>
        <span v-if="lastUpdated" class="activity-updated">
          查询于 {{ formatTime(lastUpdated) }}
        </span>
      </div>
      <a-tooltip title="刷新日常便笺">
        <a-button
          type="text"
          shape="circle"
          :loading="loading"
          aria-label="刷新日常便笺"
          @click="loadActivity"
        >
          <ReloadOutlined />
        </a-button>
      </a-tooltip>
    </header>

    <a-alert
      v-if="errorMessage"
      type="error"
      show-icon
      :message="errorMessage"
      class="activity-alert"
    />

    <div v-if="loading && !hasLoaded" class="activity-state">
      <a-spin size="large" />
    </div>

    <a-empty v-else-if="isEmpty" description="暂无可展示的日常便笺" class="activity-state" />

    <a-spin v-else-if="snapshots.length" :spinning="loading" class="activity-spin">
      <draggable
        v-model="snapshots"
        :item-key="snapshotKey"
        :animation="180"
        handle=".activity-drag-handle"
        ghost-class="activity-card-ghost"
        chosen-class="activity-card-chosen"
        class="activity-grid"
      >
        <template #item="{ element }">
          <article class="activity-card-wrap">
            <a-card :bordered="false" class="activity-card">
              <div class="activity-card-header">
                <span class="activity-drag-handle" title="拖拽排序" aria-label="拖拽排序">
                  <HolderOutlined />
                </span>
                <div class="activity-card-title">
                  <strong>{{ element.game }}</strong>
                  <span>{{ element.platform }}</span>
                </div>
                <a-tag :color="statusMeta(element.status).color">
                  {{ statusMeta(element.status).label }}
                </a-tag>
              </div>

              <div class="activity-identity">
                <span>{{ element.account }}</span>
                <span v-if="element.roleName">{{ element.roleName }}</span>
                <span v-if="element.server">{{ element.server }}</span>
              </div>

              <div class="activity-details">
                <div class="activity-progress-heading">
                  <span>日常完成</span>
                  <strong v-if="hasProgress(element)">
                    {{ element.completed }} / {{ element.target }}
                  </strong>
                  <span v-else class="activity-muted">暂无进度</span>
                </div>
                <a-progress
                  v-if="hasProgress(element)"
                  :percent="progressPercent(element)"
                  :show-info="false"
                  size="small"
                />

                <div class="activity-section-label">每日任务</div>
                <div v-if="element.tasks.length" class="activity-task-list">
                  <div
                    v-for="task in element.tasks"
                    :key="`${task.name}-${task.period}`"
                    class="activity-row"
                  >
                    <span class="activity-row-name">{{ task.name }}</span>
                    <span>{{ task.completed }} / {{ task.target }}</span>
                  </div>
                </div>
                <span v-else class="activity-muted">暂无可识别任务</span>

                <template v-if="element.resources.length">
                  <div class="activity-section-label">可用资源</div>
                  <div class="activity-resource-list">
                    <div
                      v-for="resource in element.resources"
                      :key="resource.name"
                      class="activity-row"
                    >
                      <span class="activity-row-name">{{ resource.name }}</span>
                      <span>{{ resource.current }} / {{ resource.target }}</span>
                    </div>
                  </div>
                </template>

                <div v-if="element.reason" class="activity-reason">
                  {{ element.reason }}
                </div>
              </div>

              <div class="activity-card-footer">
                <span v-if="element.roleUid">UID {{ element.roleUid }}</span>
                <span v-else>未绑定角色</span>
                <span v-if="formatTime(element.updatedAt)">
                  {{ formatTime(element.updatedAt) }}
                </span>
              </div>
            </a-card>
          </article>
        </template>
      </draggable>
    </a-spin>
  </section>
</template>

<style scoped>
.activity-view {
  min-height: 100%;
  box-sizing: border-box;
  padding: 24px;
  color: var(--ant-color-text);
}

.activity-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.activity-heading {
  display: flex;
  align-items: baseline;
  gap: 12px;
  min-width: 0;
}

.activity-title {
  margin: 0;
  font-size: 22px;
  font-weight: 600;
  line-height: 1.35;
}

.activity-updated,
.activity-muted {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
}

.activity-alert {
  margin-bottom: 16px;
}

.activity-state {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 220px;
}

.activity-spin {
  display: block;
}

.activity-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  grid-auto-rows: 280px;
  gap: 12px;
  min-width: 0;
}

.activity-card-wrap {
  min-width: 0;
  min-height: 0;
}

.activity-card {
  height: 100%;
  overflow: hidden;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-bg-container);
}

.activity-card :deep(.ant-card-body) {
  display: flex;
  flex-direction: column;
  height: 100%;
  box-sizing: border-box;
  padding: 16px;
  min-height: 0;
}

.activity-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.activity-drag-handle {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 20px;
  color: var(--ant-color-text-tertiary);
  cursor: grab;
}

.activity-drag-handle:active {
  cursor: grabbing;
}

.activity-card-title {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  line-height: 1.35;
}

.activity-card-title strong,
.activity-card-title span,
.activity-identity span,
.activity-row-name,
.activity-reason {
  overflow-wrap: anywhere;
}

.activity-card-title span {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.activity-identity {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
  margin: 10px 0;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.activity-details {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding-right: 3px;
}

.activity-progress-heading,
.activity-row,
.activity-card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.activity-progress-heading {
  margin-bottom: 4px;
  font-size: 13px;
}

.activity-section-label {
  margin: 12px 0 6px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.activity-task-list,
.activity-resource-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.activity-row {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.activity-row-name {
  min-width: 0;
}

.activity-reason {
  margin-top: 12px;
  padding: 8px 10px;
  border-left: 3px solid var(--ant-color-warning);
  background: var(--ant-color-warning-bg);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.activity-card-footer {
  flex: 0 0 auto;
  margin-top: 10px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
}

.activity-card-ghost {
  opacity: 0.45;
}

.activity-card-chosen {
  box-shadow: 0 0 0 2px var(--ant-color-primary-bg);
}

@media (max-width: 760px) {
  .activity-view {
    padding: 16px;
  }

  .activity-heading {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }

  .activity-grid {
    grid-template-columns: minmax(0, 1fr);
    grid-auto-rows: 280px;
  }
}
</style>

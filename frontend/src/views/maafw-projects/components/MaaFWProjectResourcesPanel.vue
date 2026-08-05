<template>
  <div class="maafw-project-resources-panel">
    <a-alert
      v-if="!binding.managed"
      type="info"
      show-icon
      message="当前仍是普通 MaaFW 项目"
      description="转换为托管项目后，项目版本、共享运行时和引用关系会在这里统一展示。"
    />

    <template v-else>
      <section class="manager-section">
        <div class="section-heading">
          <div>
            <h3>当前绑定</h3>
            <p>脚本 ID 与全部用户保持不变，运行时从当前项目版本的私有 manifest 解析。</p>
          </div>
          <a-space>
            <a-button
              v-if="features.runtimeManagement && !readOnly"
              :disabled="busy || !binding.projectId || !binding.version"
              @click="emit('install-runtime')"
            >
              更新运行环境
            </a-button>
            <a-button :loading="loading" :disabled="busy" @click="emit('refresh')">
              <template #icon><ReloadOutlined /></template>
              刷新
            </a-button>
          </a-space>
        </div>

        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="项目">
            <a-typography-text copyable>{{ binding.projectId || '未绑定' }}</a-typography-text>
          </a-descriptions-item>
          <a-descriptions-item label="版本">
            {{ binding.version || '未绑定' }}
          </a-descriptions-item>
          <a-descriptions-item label="共享运行时">
            <a-typography-text v-if="binding.runtimeId" copyable>
              {{ binding.runtimeId }}
            </a-typography-text>
            <span v-else>尚未准备</span>
          </a-descriptions-item>
          <a-descriptions-item label="依赖约束">
            {{ binding.runtimeConstraint || '由项目 manifest 决定' }}
          </a-descriptions-item>
          <a-descriptions-item label="状态" :span="2">
            {{ binding.status || '托管资源已绑定' }}
          </a-descriptions-item>
        </a-descriptions>
      </section>

      <section class="manager-section">
        <div class="section-heading">
          <div>
            <h3>项目资源</h3>
            <p>
              每个版本的内容受保护；升级会导入新版本。仍被脚本引用或已固定的旧版本可用于切换和回退。
            </p>
          </div>
        </div>

        <a-table
          size="small"
          :columns="projectColumns"
          :data-source="projects"
          :loading="loading"
          :pagination="false"
          row-key="projectId"
          :custom-row="projectRowProps"
        >
          <template #emptyText>
            <a-empty description="尚未导入托管项目资源" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'projectId'">
              <a-button
                type="link"
                class="project-link"
                :disabled="busy || versionsLoading"
                @click.stop="selectProject(record.projectId)"
              >
                {{ record.projectId }}
              </a-button>
            </template>
            <template v-else-if="column.key === 'currentVersion'">
              {{ displayProjectVersion(record) }}
            </template>
            <template v-else-if="column.key === 'size'">
              {{ formatBytes(projectSizeBytes(record.summary)) }}
            </template>
          </template>
        </a-table>
      </section>

      <section v-if="selectedProjectId" class="manager-section">
        <div class="section-heading">
          <div>
            <h3>{{ selectedProjectId }} 的版本</h3>
            <p>有引用、固定标记或活动 lease 的版本会由后端拒绝删除。</p>
          </div>
        </div>

        <a-table
          size="small"
          :columns="versionColumns"
          :data-source="versions"
          :loading="versionsLoading"
          :pagination="false"
          row-key="version"
        >
          <template #emptyText>
            <a-empty description="当前项目没有可用版本" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'version'">
              <a-space>
                <span>{{ record.version }}</span>
                <a-tag v-if="isBoundVersion(record)" color="green">脚本绑定</a-tag>
                <a-tag v-if="record.current" color="cyan">Store 当前</a-tag>
                <a-tag v-if="record.pinned" color="blue">已固定</a-tag>
              </a-space>
            </template>
            <template v-else-if="column.key === 'references'">
              <div v-if="record.references?.length" class="reference-list">
                <a-typography-text
                  v-for="reference in record.references"
                  :key="reference"
                  code
                  copyable
                >
                  {{ reference }}
                </a-typography-text>
              </div>
              <span v-else>无</span>
            </template>
            <template v-else-if="column.key === 'lastUsedAt'">
              {{ formatTime(record.lastUsedAt) }}
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space v-if="!readOnly" wrap>
                <a-button
                  v-if="features.upgradePlans"
                  size="small"
                  :disabled="
                    busy || isBoundVersion(record) || record.projectId !== binding.projectId
                  "
                  @click="emit('switch-version', record)"
                >
                  生成切换计划
                </a-button>
                <a-button
                  v-if="features.pinning !== false"
                  size="small"
                  :disabled="busy"
                  @click="emit('pin-version', record, !record.pinned)"
                >
                  {{ record.pinned ? '取消固定' : '固定' }}
                </a-button>
                <a-button
                  danger
                  size="small"
                  :disabled="busy || record.current || isBoundVersion(record)"
                  @click="emit('delete-version', record)"
                >
                  删除
                </a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </section>

      <section v-if="features.runtimeManagement" class="manager-section">
        <div class="section-heading">
          <div>
            <h3>共享运行时</h3>
            <p>
              相同完整依赖选择器复用同一环境；不同 MaaFW 版本保持隔离。各环境中的相同依赖会通过共享
              uv 缓存和 hardlink 复用，页面占用是目录逻辑大小；引用、固定标记和活动 lease
              会阻止回收。
            </p>
          </div>
        </div>

        <a-table
          size="small"
          :columns="runtimeColumns"
          :data-source="runtimes"
          :loading="loading"
          :pagination="false"
          row-key="runtimeId"
        >
          <template #emptyText>
            <a-empty description="尚未建立共享 MaaFW 运行时" />
          </template>
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'runtimeId'">
              <div class="runtime-identity">
                <a-typography-text code copyable>{{ record.runtimeId }}</a-typography-text>
                <a-tag v-if="record.pinned" color="blue">已固定</a-tag>
              </div>
            </template>
            <template v-else-if="column.key === 'projects'">
              <div v-if="runtimeProjects(record).length" class="runtime-project-list">
                <a-tag v-for="project in runtimeProjects(record)" :key="project" color="blue">
                  {{ project }}
                </a-tag>
              </div>
              <span v-else class="secondary-text">未绑定项目</span>
            </template>
            <template v-else-if="column.key === 'requirements'">
              <span>{{ formatRequirements(record) }}</span>
            </template>
            <template v-else-if="column.key === 'usage'">
              <span>{{ formatBytes(record.sizeBytes) }}</span>
              <span class="secondary-text"> · {{ formatTime(record.lastUsedAt) }}</span>
            </template>
            <template v-else-if="column.key === 'protection'">
              引用 {{ record.references?.length || 0 }} · Lease
              {{ record.activeLeaseIds?.length || 0 }}
            </template>
            <template v-else-if="column.key === 'action'">
              <a-space v-if="!readOnly" wrap>
                <a-button
                  v-if="features.pinning !== false"
                  size="small"
                  :disabled="busy"
                  @click="emit('pin-runtime', record, !record.pinned)"
                >
                  {{ record.pinned ? '取消固定' : '固定' }}
                </a-button>
                <a-button
                  danger
                  size="small"
                  :disabled="busy"
                  @click="emit('delete-runtime', record)"
                >
                  删除
                </a-button>
              </a-space>
            </template>
          </template>
        </a-table>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { TableColumnsType } from 'ant-design-vue'
import { ReloadOutlined } from '@ant-design/icons-vue'
import type {
  MaaFWManagedBinding,
  MaaFWManagedFeatures,
  MaaFWManagedInventorySummary,
  MaaFWManagedProjectSummary,
  MaaFWManagedProjectVersion,
  MaaFWManagedRuntime,
} from '@/composables/useMaaFWManagedApi'

defineOptions({ name: 'MaaFWProjectResourcesPanel' })

const props = defineProps<{
  binding: MaaFWManagedBinding
  features: MaaFWManagedFeatures
  projects: MaaFWManagedProjectSummary[]
  versions: MaaFWManagedProjectVersion[]
  runtimes: MaaFWManagedRuntime[]
  selectedProjectId: string
  loading: boolean
  versionsLoading: boolean
  busy: boolean
  readOnly: boolean
}>()

const emit = defineEmits<{
  refresh: []
  'select-project': [projectId: string]
  'switch-version': [version: MaaFWManagedProjectVersion]
  'delete-version': [version: MaaFWManagedProjectVersion]
  'pin-version': [version: MaaFWManagedProjectVersion, pinned: boolean]
  'install-runtime': []
  'delete-runtime': [runtime: MaaFWManagedRuntime]
  'pin-runtime': [runtime: MaaFWManagedRuntime, pinned: boolean]
}>()

const projectColumns: TableColumnsType<MaaFWManagedProjectSummary> = [
  { title: '项目 ID', key: 'projectId', dataIndex: 'projectId', width: 240 },
  { title: '当前 / 绑定版本', key: 'currentVersion', dataIndex: 'currentVersion', width: 160 },
  { title: '版本数', key: 'versionCount', dataIndex: 'versionCount', width: 90 },
  { title: '占用', key: 'size', width: 120 },
]

const versionColumns = computed<TableColumnsType<MaaFWManagedProjectVersion>>(() => [
  { title: '版本', key: 'version', dataIndex: 'version', width: 190 },
  { title: '引用', key: 'references', width: 280 },
  { title: '最近使用', key: 'lastUsedAt', width: 180 },
  ...(!props.readOnly ? [{ title: '操作', key: 'action', width: 300 }] : []),
])

const runtimeColumns = computed<TableColumnsType<MaaFWManagedRuntime>>(() => [
  { title: '运行时', key: 'runtimeId', dataIndex: 'runtimeId', width: 265 },
  { title: '项目', key: 'projects', width: 180 },
  { title: '依赖', key: 'requirements', width: 235 },
  { title: '占用 / 最近使用', key: 'usage', width: 190 },
  { title: '保护', key: 'protection', width: 130 },
  ...(!props.readOnly ? [{ title: '操作', key: 'action', width: 180 }] : []),
])

const selectProject = (projectId: string) => {
  if (projectId === props.selectedProjectId && props.versions.length) return
  emit('select-project', projectId)
}

const projectRowProps = (record: MaaFWManagedProjectSummary) => ({
  class:
    record.projectId === props.selectedProjectId
      ? 'project-row-clickable project-row-selected'
      : 'project-row-clickable',
  onClick: () => selectProject(record.projectId),
})

const isBoundVersion = (version: MaaFWManagedProjectVersion) =>
  version.projectId === props.binding.projectId && version.version === props.binding.version

const displayProjectVersion = (project: MaaFWManagedProjectSummary) => {
  if (project.currentVersion) return project.currentVersion
  if (project.projectId === props.binding.projectId && props.binding.version) {
    return props.binding.version
  }
  return project.versions.length === 1 ? project.versions[0] : '—'
}

const formatBytes = (value?: number | null) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—'
  if (value < 1024) return `${value} B`
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(1)} KB`
  if (value < 1024 ** 3) return `${(value / 1024 ** 2).toFixed(1)} MB`
  return `${(value / 1024 ** 3).toFixed(2)} GB`
}

const projectSizeBytes = (summary?: MaaFWManagedInventorySummary | null) =>
  summary?.size?.projectedBytes ?? summary?.sizeBytes

const formatTime = (value?: string | null) => {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

const formatRequirements = (runtime: MaaFWManagedRuntime) => {
  const requirements = runtime.selectorRequirements?.length
    ? runtime.selectorRequirements
    : runtime.packages || []
  return requirements.length ? requirements.join('、') : runtime.maafwVersion || '未记录'
}

const runtimeProjects = (runtime: MaaFWManagedRuntime) => {
  const projectIds = new Set<string>()
  for (const reference of runtime.references || []) {
    const value = String(reference || '').trim()
    if (!value.startsWith('maafw-project:')) continue
    const identity = value.slice('maafw-project:'.length)
    const at = identity.lastIndexOf('@')
    const projectId = (at > 0 ? identity.slice(0, at) : identity).trim()
    if (projectId) projectIds.add(projectId)
  }
  return [...projectIds].sort((left, right) => left.localeCompare(right, 'zh-CN'))
}
</script>

<style scoped>
.maafw-project-resources-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.manager-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.section-heading h3 {
  margin: 0 0 4px;
  color: var(--ant-color-text);
  font-size: 16px;
}

.section-heading p {
  margin: 0;
  color: var(--ant-color-text-secondary);
}

.project-link {
  height: auto;
  padding: 0;
  text-align: left;
}

:deep(.project-row-clickable) {
  cursor: pointer;
}

:deep(.project-row-clickable:hover > td) {
  background: var(--ant-color-fill-quaternary);
}

:deep(.project-row-selected > td) {
  background: var(--ant-color-primary-bg);
}

.reference-list,
.runtime-identity {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
}

.runtime-identity {
  flex-direction: row;
  align-items: center;
  flex-wrap: wrap;
}

.secondary-text {
  color: var(--ant-color-text-secondary);
}
</style>

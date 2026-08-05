<template>
  <a-card class="inventory-panel" :bordered="false">
    <template #title>
      <div class="panel-title">
        <div>
          <span>全局资源盘点</span>
          <small>不依赖脚本绑定的只读视图</small>
        </div>
        <a-tag color="blue">只读</a-tag>
      </div>
    </template>
    <template #extra>
      <a-space>
        <a-button @click="goToPluginSettings">配置资源目录</a-button>
        <a-button :loading="loading" @click="emit('refresh')">
          <template #icon><ReloadOutlined /></template>
          刷新盘点
        </a-button>
      </a-space>
    </template>

    <a-alert v-if="error" type="error" show-icon message="全局资源盘点失败" :description="error" />

    <div v-if="loading && !inventory" class="inventory-loading">
      <a-spin tip="正在对账并读取 Project Store 与 Runtime Pool" />
    </div>

    <template v-else-if="inventory">
      <a-alert
        v-if="!inventory.complete"
        type="warning"
        show-icon
        message="本次盘点不完整"
        description="部分存储或引用未能读取，下列结果不能作为删除依据。"
      />
      <a-alert
        v-for="(item, index) in inventory.errors"
        :key="`${index}-${item.scope || ''}-${item.path || ''}`"
        type="warning"
        show-icon
        :message="formatInventoryError(item)"
      />

      <div class="inventory-meta">
        <a-typography-text type="secondary">
          生成时间：{{ formatDate(inventory.generatedAt) }}；盘点会先对账 MAS
          管理的脚本与运行时引用。
        </a-typography-text>
        <a-spin v-if="loading" size="small" tip="正在刷新" />
      </div>

      <a-row :gutter="[16, 16]">
        <a-col :xs="24" :sm="12" :xl="6">
          <a-statistic title="托管项目" :value="inventory.projects.length" />
        </a-col>
        <a-col :xs="24" :sm="12" :xl="6">
          <a-statistic title="已安装项目版本" :value="inventory.versions.length" />
        </a-col>
        <a-col :xs="24" :sm="12" :xl="6">
          <a-statistic title="共享运行时" :value="inventory.runtimes.length" />
        </a-col>
        <a-col :xs="24" :sm="12" :xl="6">
          <a-statistic title="无引用、待 GC 评估" :value="unreferencedCandidateCount" />
        </a-col>
      </a-row>

      <section class="inventory-section">
        <h3>存储位置</h3>
        <a-alert
          type="info"
          show-icon
          message="目录配置由对应插件实例管理"
          description="Project Store、脱壳运行目录与 Runtime Pool 可分别设置绝对路径；保存并重载插件后生效，不会自动搬迁旧资源。"
        />
        <div class="storage-grid storage-grid-three">
          <div class="storage-card">
            <div class="storage-heading">
              <strong>Project Store</strong>
              <a-tag :color="storageColor(inventory.storage.projectStore)">
                {{ storageLabel(inventory.storage.projectStore) }}
              </a-tag>
            </div>
            <a-typography-paragraph
              v-if="inventory.storage.projectStore.root"
              class="path-value"
              :copyable="{ text: inventory.storage.projectStore.root }"
            >
              {{ inventory.storage.projectStore.root }}
            </a-typography-paragraph>
            <a-typography-text v-else type="secondary">
              {{ inventory.storage.projectStore.reason || '未返回存储根目录' }}
            </a-typography-text>
            <small v-if="inventory.storage.projectStore.storeId">
              Store ID：{{ inventory.storage.projectStore.storeId }}
            </small>
          </div>
          <div class="storage-card">
            <div class="storage-heading">
              <strong>脱壳运行目录</strong>
              <a-tag
                :color="
                  inventory.storage.projectStore.available
                    ? inventory.storage.projectStore.isDefaultRunRoot
                      ? 'blue'
                      : 'green'
                    : 'red'
                "
              >
                {{
                  inventory.storage.projectStore.available
                    ? inventory.storage.projectStore.isDefaultRunRoot
                      ? '默认位置'
                      : '自定义位置'
                    : '不可用'
                }}
              </a-tag>
            </div>
            <a-typography-paragraph
              v-if="inventory.storage.projectStore.runRoot"
              class="path-value"
              :copyable="{ text: inventory.storage.projectStore.runRoot }"
            >
              {{ inventory.storage.projectStore.runRoot }}
            </a-typography-paragraph>
            <a-typography-text v-else type="secondary">未返回脱壳运行目录</a-typography-text>
            <small v-if="inventory.storage.projectStore.runRootId">
              Run Root ID：{{ inventory.storage.projectStore.runRootId }}
            </small>
          </div>
          <div class="storage-card">
            <div class="storage-heading">
              <strong>Runtime Pool</strong>
              <a-tag :color="storageColor(inventory.storage.runtimePool)">
                {{ storageLabel(inventory.storage.runtimePool) }}
              </a-tag>
            </div>
            <a-typography-paragraph
              v-if="inventory.storage.runtimePool.root"
              class="path-value"
              :copyable="{ text: inventory.storage.runtimePool.root }"
            >
              {{ inventory.storage.runtimePool.root }}
            </a-typography-paragraph>
            <a-typography-text v-else type="secondary">
              {{ inventory.storage.runtimePool.reason || '未返回存储根目录' }}
            </a-typography-text>
            <small v-if="inventory.storage.runtimePool.poolId">
              Pool ID：{{ inventory.storage.runtimePool.poolId }}
            </small>
          </div>
        </div>
      </section>

      <section class="inventory-section">
        <div class="section-heading">
          <h3>项目</h3>
          <a-typography-text type="secondary">
            已对账 {{ inventory.references.scripts.scriptCount || 0 }} 条脚本记录
          </a-typography-text>
        </div>
        <a-table
          size="small"
          :columns="projectColumns"
          :data-source="inventory.projects"
          :pagination="inventory.projects.length > 8 ? { pageSize: 8 } : false"
          row-key="projectId"
          :scroll="{ x: 760 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'projectId'">
              <a-typography-text code copyable>{{ record.projectId }}</a-typography-text>
            </template>
            <template v-else-if="column.key === 'currentVersion'">
              <a-tag v-if="record.currentVersion" color="green">
                {{ record.currentVersion }}
              </a-tag>
              <a-typography-text v-else type="secondary">未设置</a-typography-text>
            </template>
            <template v-else-if="column.key === 'versions'">
              <div class="compact-values">
                <a-tag v-for="version in record.versions" :key="version">{{ version }}</a-tag>
                <span v-if="record.versions.length === 0">无版本</span>
              </div>
            </template>
          </template>
        </a-table>
      </section>

      <section class="inventory-section">
        <h3>项目版本与引用</h3>
        <a-table
          size="small"
          :columns="versionColumns"
          :data-source="versionRows"
          :pagination="versionRows.length > 8 ? { pageSize: 8 } : false"
          row-key="key"
          :scroll="{ x: 1760 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'identity'">
              <div class="identity-cell">
                <a-typography-text code>{{ record.projectId }}</a-typography-text>
                <strong>{{ record.version }}</strong>
              </div>
            </template>
            <template v-else-if="column.key === 'state'">
              <div class="compact-values">
                <a-tag v-if="record.current" color="green">当前版本</a-tag>
                <a-tag v-if="record.pinned" color="purple">已固定</a-tag>
                <a-tag v-if="record.references.length === 0" color="orange">无引用</a-tag>
                <a-tag v-if="record.activeLeaseIds.length > 0" color="blue">
                  {{ record.activeLeaseIds.length }} 个活跃租约
                </a-tag>
                <a-tag v-if="isVersionCandidate(record)" color="orange"> 无引用，待 GC 评估 </a-tag>
              </div>
            </template>
            <template v-else-if="column.key === 'references'">
              <ReferenceList :items="record.references" empty-label="没有记录到引用" />
            </template>
            <template v-else-if="column.key === 'leases'">
              <ReferenceList :items="record.activeLeaseIds" empty-label="没有活跃租约" />
            </template>
            <template v-else-if="column.key === 'runtimeDependency'">
              <div class="identity-cell">
                <span>{{ record.runtimeConstraint || '未声明 MaaFW 约束' }}</span>
                <a-typography-text
                  v-if="getVersionRuntimeId(record)"
                  code
                  :copyable="{ text: getVersionRuntimeId(record) }"
                >
                  {{ getVersionRuntimeId(record) }}
                </a-typography-text>
                <small v-else>尚未绑定共享运行时</small>
              </div>
            </template>
            <template v-else-if="column.key === 'path'">
              <a-typography-paragraph
                v-if="record.dataPath"
                class="path-value table-path"
                :copyable="{ text: record.dataPath }"
              >
                {{ record.dataPath }}
              </a-typography-paragraph>
              <span v-else>—</span>
            </template>
            <template v-else-if="column.key === 'lastUsedAt'">
              {{ formatDate(record.lastUsedAt) }}
            </template>
          </template>
        </a-table>
      </section>

      <section class="inventory-section">
        <h3>按脚本隔离的脱壳目录</h3>
        <a-table
          size="small"
          :columns="checkoutColumns"
          :data-source="checkoutRows"
          :pagination="checkoutRows.length > 8 ? { pageSize: 8 } : false"
          row-key="checkoutId"
          :scroll="{ x: 1220 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'project'">
              <div class="identity-cell">
                <a-typography-text code
                  >{{ record.projectId }}@{{ record.version }}</a-typography-text
                >
                <small>脚本：{{ record.scriptId }}</small>
              </div>
            </template>
            <template v-else-if="column.key === 'state'">
              <div class="compact-values">
                <a-tag v-if="record.bindingCurrent" color="green">当前脚本绑定</a-tag>
                <a-tag v-if="record.orphanReason" color="orange">
                  {{ checkoutOrphanLabel(record.orphanReason) }}
                </a-tag>
                <a-tag v-if="record.activeLeaseIds?.length" color="blue">
                  {{ record.activeLeaseIds.length }} 个活跃租约
                </a-tag>
                <a-tag v-if="record.leaseProtectionAvailable === false" color="orange">
                  无 checkout 租约能力，保守保留
                </a-tag>
              </div>
            </template>
            <template v-else-if="column.key === 'path'">
              <a-typography-paragraph
                class="path-value table-path"
                :copyable="{ text: record.dataPath }"
              >
                {{ record.dataPath }}
              </a-typography-paragraph>
            </template>
            <template v-else-if="column.key === 'createdAt'">
              <div class="identity-cell">
                <span>最近使用：{{ formatDate(record.lastUsedAt) }}</span>
                <small>创建：{{ formatDate(record.createdAt) }}</small>
              </div>
            </template>
          </template>
        </a-table>
      </section>

      <section class="inventory-section">
        <div class="section-heading">
          <h3>共享运行时、引用与租约</h3>
          <a-typography-text type="secondary">
            已对账 {{ inventory.references.runtimes.runtimeCount || 0 }} 个运行时
          </a-typography-text>
        </div>
        <a-table
          size="small"
          :columns="runtimeColumns"
          :data-source="runtimeRows"
          :pagination="runtimeRows.length > 8 ? { pageSize: 8 } : false"
          row-key="runtimeId"
          :scroll="{ x: 1420 }"
        >
          <template #bodyCell="{ column, record }">
            <template v-if="column.key === 'runtimeId'">
              <a-typography-text code copyable>{{ record.runtimeId }}</a-typography-text>
            </template>
            <template v-else-if="column.key === 'state'">
              <div class="compact-values">
                <a-tag v-if="record.pinned" color="purple">已固定</a-tag>
                <a-tag v-if="record.references.length === 0" color="orange">无引用</a-tag>
                <a-tag v-if="record.activeLeaseIds.length > 0" color="blue">
                  {{ record.activeLeaseIds.length }} 个活跃租约
                </a-tag>
                <a-tag v-if="isRuntimeCandidate(record)" color="orange"> 无引用，待 GC 评估 </a-tag>
              </div>
            </template>
            <template v-else-if="column.key === 'runtime'">
              <div class="identity-cell">
                <span>MaaFW {{ record.maafwVersion || record.maafwRequirement || '未知' }}</span>
                <small>Python {{ record.pythonPatchVersion || '未知' }}</small>
                <small v-if="record.sizeBytes !== null">{{ formatBytes(record.sizeBytes) }}</small>
              </div>
            </template>
            <template v-else-if="column.key === 'references'">
              <ReferenceList :items="record.references" empty-label="没有记录到引用" />
            </template>
            <template v-else-if="column.key === 'leases'">
              <ReferenceList :items="record.activeLeaseIds" empty-label="没有活跃租约" />
            </template>
            <template v-else-if="column.key === 'path'">
              <a-typography-paragraph
                v-if="record.environmentPath || record.path"
                class="path-value table-path"
                :copyable="{ text: record.environmentPath || record.path }"
              >
                {{ record.environmentPath || record.path }}
              </a-typography-paragraph>
              <span v-else>—</span>
            </template>
            <template v-else-if="column.key === 'lastUsedAt'">
              {{ formatDate(record.lastUsedAt) }}
            </template>
          </template>
        </a-table>
      </section>

      <a-alert
        type="info"
        show-icon
        message="全局盘点不提供删除操作"
        description="删除、切换、升级和回收仍需选择脚本上下文，由后端按绑定、引用、固定状态和租约再次校验。"
      />
    </template>
  </a-card>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, type PropType } from 'vue'
import { useRouter } from 'vue-router'
import { ReloadOutlined } from '@ant-design/icons-vue'
import { Typography } from 'ant-design-vue'
import type {
  MaaFWManagedGlobalInventory,
  MaaFWManagedCheckout,
  MaaFWManagedInventoryError,
  MaaFWManagedProjectVersion,
  MaaFWManagedRuntime,
  MaaFWManagedStorageInfo,
} from '@/composables/useMaaFWManagedApi'

defineOptions({ name: 'MaaFWGlobalInventoryPanel' })

const props = defineProps<{
  inventory: MaaFWManagedGlobalInventory | null
  loading: boolean
  error: string
}>()
const router = useRouter()

const emit = defineEmits<{
  refresh: []
}>()

const ReferenceList = defineComponent({
  name: 'MaaFWInventoryReferenceList',
  props: {
    items: { type: Array as PropType<string[]>, required: true },
    emptyLabel: { type: String, required: true },
  },
  setup(componentProps) {
    return () =>
      componentProps.items.length
        ? h(
            'div',
            { class: 'reference-list' },
            componentProps.items.map(item =>
              h(
                Typography.Text,
                { key: item, code: true, copyable: { text: item } },
                { default: () => item }
              )
            )
          )
        : h(Typography.Text, { type: 'secondary' }, { default: () => componentProps.emptyLabel })
  },
})

interface ProjectVersionRow extends MaaFWManagedProjectVersion {
  key: string
  references: string[]
  activeLeaseIds: string[]
}

interface RuntimeRow extends Omit<MaaFWManagedRuntime, 'sizeBytes'> {
  references: string[]
  activeLeaseIds: string[]
  sizeBytes: number | null
}

interface CheckoutRow extends MaaFWManagedCheckout {
  activeLeaseIds: string[]
}

const projectColumns = [
  { title: 'Project ID', key: 'projectId', dataIndex: 'projectId', width: 260 },
  { title: '当前版本', key: 'currentVersion', dataIndex: 'currentVersion', width: 160 },
  { title: '版本数', key: 'versionCount', dataIndex: 'versionCount', width: 100 },
  { title: '全部版本', key: 'versions', dataIndex: 'versions' },
]

const versionColumns = [
  { title: '项目 / 版本', key: 'identity', width: 260 },
  { title: '状态', key: 'state', width: 240 },
  { title: '引用', key: 'references', width: 300 },
  { title: '活跃租约', key: 'leases', width: 260 },
  { title: '运行时依赖', key: 'runtimeDependency', width: 280 },
  { title: '数据目录', key: 'path', width: 320 },
  { title: '最后使用', key: 'lastUsedAt', width: 180 },
]

const runtimeColumns = [
  { title: 'Runtime ID', key: 'runtimeId', width: 300 },
  { title: '状态', key: 'state', width: 250 },
  { title: '环境', key: 'runtime', width: 190 },
  { title: '引用', key: 'references', width: 300 },
  { title: '活跃租约', key: 'leases', width: 260 },
  { title: '环境目录', key: 'path', width: 320 },
  { title: '最后使用', key: 'lastUsedAt', width: 180 },
]

const checkoutColumns = [
  { title: '项目 / 脚本', key: 'project', width: 300 },
  { title: '状态', key: 'state', width: 280 },
  { title: '脱壳数据目录', key: 'path', width: 440 },
  { title: '使用时间', key: 'createdAt', width: 220 },
]

const versionRows = computed<ProjectVersionRow[]>(() =>
  (props.inventory?.versions || []).map(item => ({
    ...item,
    key: `${item.projectId}@${item.version}`,
    references: Array.isArray(item.references) ? item.references : [],
    activeLeaseIds: Array.isArray(item.activeLeaseIds) ? item.activeLeaseIds : [],
  }))
)

const runtimeRows = computed<RuntimeRow[]>(() =>
  (props.inventory?.runtimes || []).map(item => ({
    ...item,
    references: Array.isArray(item.references) ? item.references : [],
    activeLeaseIds: Array.isArray(item.activeLeaseIds) ? item.activeLeaseIds : [],
    sizeBytes: typeof item.sizeBytes === 'number' ? item.sizeBytes : null,
  }))
)

const checkoutRows = computed<CheckoutRow[]>(() =>
  (props.inventory?.checkouts || []).map(item => ({
    ...item,
    activeLeaseIds: Array.isArray(item.activeLeaseIds) ? item.activeLeaseIds : [],
  }))
)

const checkoutOrphanLabel = (reason: string) => {
  if (reason === 'managed-script-missing') return '脚本已删除，待 GC 评估'
  if (reason === 'script-binding-moved') return '脚本已切换绑定，待 GC 评估'
  if (reason === 'store-version-missing') return 'Store 版本缺失，保守检查'
  return '状态无法确认，保守保留'
}

const isVersionCandidate = (record: ProjectVersionRow) =>
  record.references.length === 0 &&
  !record.current &&
  !record.pinned &&
  record.activeLeaseIds.length === 0

const isRuntimeCandidate = (record: RuntimeRow) =>
  record.references.length === 0 && record.activeLeaseIds.length === 0 && !record.pinned

const isCheckoutCandidate = (record: CheckoutRow) =>
  Boolean(record.orphanReason) &&
  !record.bindingCurrent &&
  record.leaseProtectionAvailable === true &&
  record.activeLeaseIds.length === 0

const getVersionRuntime = (record: ProjectVersionRow) => {
  const manifest = record.manifest
  return manifest?.runtime &&
    typeof manifest.runtime === 'object' &&
    !Array.isArray(manifest.runtime)
    ? (manifest.runtime as Record<string, unknown>)
    : {}
}

const getVersionRuntimeId = (record: ProjectVersionRow) => {
  const runtime = getVersionRuntime(record)
  const binding =
    runtime.binding && typeof runtime.binding === 'object' && !Array.isArray(runtime.binding)
      ? (runtime.binding as Record<string, unknown>)
      : {}
  return typeof binding.runtimeId === 'string' ? binding.runtimeId : ''
}

const unreferencedCandidateCount = computed(
  () =>
    versionRows.value.filter(isVersionCandidate).length +
    runtimeRows.value.filter(isRuntimeCandidate).length +
    checkoutRows.value.filter(isCheckoutCandidate).length
)

const storageColor = (storage: MaaFWManagedStorageInfo) =>
  storage.available ? (storage.isDefault ? 'blue' : 'green') : 'red'

const storageLabel = (storage: MaaFWManagedStorageInfo) =>
  storage.available ? (storage.isDefault ? '默认位置' : '自定义位置') : '不可用'

const formatInventoryError = (item: MaaFWManagedInventoryError) => {
  const location = item.path || item.scriptId || item.runtimeId || item.scope || '未知位置'
  return `${location}：${item.error || '未知盘点错误'}`
}

const goToPluginSettings = () => router.push('/plugins')

const formatDate = (value?: string | null) => {
  if (!value) return '—'
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp) ? new Date(timestamp).toLocaleString() : value
}

const formatBytes = (value: number) => {
  if (value < 1024) return `${value} B`
  const units = ['KB', 'MB', 'GB', 'TB']
  let amount = value / 1024
  let index = 0
  while (amount >= 1024 && index < units.length - 1) {
    amount /= 1024
    index += 1
  }
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[index]}`
}
</script>

<style scoped>
.inventory-panel {
  background: var(--ant-color-bg-container);
}

.panel-title,
.panel-title > div,
.storage-card,
.identity-cell {
  display: flex;
}

.panel-title {
  align-items: center;
  gap: 12px;
}

.panel-title > div,
.storage-card,
.identity-cell {
  min-width: 0;
  flex-direction: column;
}

.panel-title small,
.storage-card small,
.identity-cell small {
  color: var(--ant-color-text-secondary);
  font-weight: 400;
}

.inventory-loading {
  display: flex;
  min-height: 180px;
  align-items: center;
  justify-content: center;
}

.inventory-meta,
.section-heading,
.storage-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.inventory-meta {
  margin-bottom: 20px;
}

.inventory-section {
  margin-top: 24px;
}

.inventory-section h3 {
  margin: 0 0 12px;
  font-size: 16px;
}

.section-heading h3 {
  margin-bottom: 12px;
}

.storage-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.storage-grid-three {
  margin-top: 12px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.storage-card {
  gap: 8px;
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.path-value {
  margin: 0;
  overflow-wrap: anywhere;
}

.table-path {
  max-width: 300px;
}

.compact-values,
:deep(.reference-list) {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

:deep(.reference-list) {
  flex-direction: column;
  align-items: flex-start;
}

.identity-cell {
  gap: 4px;
}

.inventory-panel :deep(.ant-alert + .ant-alert) {
  margin-top: 8px;
}

.inventory-panel :deep(.ant-statistic) {
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

@media (max-width: 860px) {
  .storage-grid,
  .storage-grid-three {
    grid-template-columns: 1fr;
  }

  .inventory-meta,
  .section-heading {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>

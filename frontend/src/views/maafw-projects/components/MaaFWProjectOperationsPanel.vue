<template>
  <div class="maafw-project-operations-panel">
    <section v-if="!binding.managed" class="operation-section">
      <div class="section-heading">
        <div>
          <h3>转换为托管项目</h3>
          <p>转换沿用当前脚本 ID、用户、任务和日志关联，项目路径由后端从脚本读取。</p>
        </div>
      </div>

      <a-alert
        v-if="!features.inPlaceConversion"
        type="warning"
        show-icon
        message="当前插件暂不支持原位转换"
        description="普通 MaaFW 项目仍可继续使用；升级 Managed 插件且能力探测通过后才会显示转换操作。"
      />

      <a-form v-else layout="vertical" class="operation-form">
        <a-row :gutter="16">
          <a-col :span="8">
            <a-form-item label="项目 ID（可选）">
              <a-input
                v-model:value="convertForm.projectId"
                :disabled="busy"
                placeholder="留空时从 ProjectInterface 推导"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="版本（可选）">
              <a-input
                v-model:value="convertForm.version"
                :disabled="busy"
                placeholder="留空时使用项目声明版本"
              />
            </a-form-item>
          </a-col>
          <a-col :span="8">
            <a-form-item label="运行时约束（可选）">
              <a-input
                v-model:value="convertForm.runtimeConstraint"
                :disabled="busy"
                placeholder="例如 maafw==5.12.4"
              />
            </a-form-item>
          </a-col>
        </a-row>
        <a-button type="primary" :loading="busy" @click="submitConvert">
          转换并导入当前项目
        </a-button>
      </a-form>
    </section>

    <template v-else>
      <section v-if="binding.pendingPlan" class="operation-section pending-plan-section">
        <div class="section-heading">
          <div>
            <h3>待确认升级计划</h3>
            <p>计划应用前会再次校验资源 hash、脚本配置、用户配置和用户集合。</p>
          </div>
          <a-tag :color="planStatusColor">{{ planStatusLabel }}</a-tag>
        </div>

        <a-descriptions bordered size="small" :column="2">
          <a-descriptions-item label="计划 ID">
            <a-typography-text copyable>{{ binding.pendingPlan.planId }}</a-typography-text>
          </a-descriptions-item>
          <a-descriptions-item label="配置记录">
            {{ binding.pendingPlan.planCount ?? '—' }}
          </a-descriptions-item>
          <a-descriptions-item label="版本">
            {{ binding.pendingPlan.project?.fromVersion || '—' }} →
            {{ binding.pendingPlan.project?.toVersion || '—' }}
          </a-descriptions-item>
          <a-descriptions-item label="无损计划">
            {{ binding.pendingPlan.lossless ? '是' : '否' }}
          </a-descriptions-item>
        </a-descriptions>

        <a-alert
          v-if="planBlockingMessages.length"
          type="warning"
          show-icon
          message="计划尚不能应用"
        >
          <template #description>
            <ul class="message-list">
              <li v-for="item in planBlockingMessages" :key="item">{{ item }}</li>
            </ul>
          </template>
        </a-alert>

        <a-space>
          <a-button type="primary" :disabled="busy || !planCanApply" @click="emit('apply-plan')">
            确认并应用计划
          </a-button>
          <a-button danger :disabled="busy" @click="emit('cancel-plan')"> 取消待确认升级 </a-button>
        </a-space>
      </section>

      <section class="operation-section">
        <div class="section-heading">
          <div>
            <h3>导入与升级</h3>
            <p>本地目录或 ZIP 会先导入不可变版本；已有绑定只生成计划，不会直接切换。</p>
          </div>
        </div>

        <a-alert
          v-if="!features.localImport && !features.remoteImport"
          type="info"
          show-icon
          message="当前 Managed 服务未开放资源导入能力"
        />

        <a-tabs v-else v-model:active-key="sourceTab">
          <a-tab-pane v-if="features.localImport" key="local" tab="本地目录 / ZIP">
            <a-form layout="vertical" class="operation-form">
              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="项目 ID" required>
                    <a-input
                      v-model:value="localForm.projectId"
                      :disabled="busy || Boolean(binding.projectId)"
                      placeholder="稳定项目标识"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="目标版本（可选）">
                    <a-input
                      v-model:value="localForm.version"
                      :disabled="busy"
                      placeholder="留空时读取 manifest / interface"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="运行时约束（可选）">
                    <a-input
                      v-model:value="localForm.runtimeConstraint"
                      :disabled="busy"
                      placeholder="沿用当前绑定或由 manifest 决定"
                    />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-form-item label="资源来源" required>
                <a-input-group compact>
                  <a-select v-model:value="localSourceKind" :disabled="busy" style="width: 150px">
                    <a-select-option value="directory">项目目录</a-select-option>
                    <a-select-option value="archive">ZIP 文件</a-select-option>
                  </a-select>
                  <a-input
                    v-model:value="localForm.source"
                    readonly
                    :disabled="busy"
                    placeholder="选择包含 ProjectInterface 的目录或发行 ZIP"
                    style="width: calc(100% - 250px)"
                  />
                  <a-button :disabled="busy" style="width: 100px" @click="selectLocalSource">
                    选择
                  </a-button>
                </a-input-group>
              </a-form-item>

              <a-button type="primary" :loading="busy" @click="submitLocal">
                {{ binding.projectId ? '导入并生成升级计划' : '导入首个资源版本' }}
              </a-button>
            </a-form>
          </a-tab-pane>

          <a-tab-pane v-if="features.remoteImport" key="remote" tab="远程来源">
            <a-form layout="vertical" class="operation-form">
              <a-row :gutter="16">
                <a-col :span="8">
                  <a-form-item label="项目 ID" required>
                    <a-input
                      v-model:value="remoteForm.projectId"
                      :disabled="busy || Boolean(binding.projectId)"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="来源">
                    <a-select v-model:value="remoteForm.source" :disabled="busy">
                      <a-select-option value="MirrorChyan">MirrorChyan</a-select-option>
                      <a-select-option value="GitHub">GitHub Release</a-select-option>
                    </a-select>
                  </a-form-item>
                </a-col>
                <a-col :span="8">
                  <a-form-item label="通道（可选）">
                    <a-input v-model:value="remoteForm.channel" :disabled="busy" />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row v-if="remoteForm.source === 'MirrorChyan'" :gutter="16">
                <a-col :span="12">
                  <a-form-item label="MirrorChyan RID" required>
                    <a-input v-model:value="remoteForm.mirrorChyanRid" :disabled="busy" />
                  </a-form-item>
                </a-col>
                <a-col :span="12">
                  <a-form-item label="MirrorChyan CDK" required>
                    <a-input-password v-model:value="remoteForm.mirrorChyanCDK" :disabled="busy" />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-row v-else :gutter="16">
                <a-col :span="10">
                  <a-form-item label="GitHub 仓库" required>
                    <a-input
                      v-model:value="remoteForm.githubRepo"
                      :disabled="busy"
                      placeholder="owner/repository"
                    />
                  </a-form-item>
                </a-col>
                <a-col :span="7">
                  <a-form-item label="Tag（可选）">
                    <a-input v-model:value="remoteForm.githubTag" :disabled="busy" />
                  </a-form-item>
                </a-col>
                <a-col :span="7">
                  <a-form-item label="资源匹配（可选）">
                    <a-input v-model:value="remoteForm.githubAssetPattern" :disabled="busy" />
                  </a-form-item>
                </a-col>
              </a-row>

              <a-alert
                v-if="currentRemoteDiscovery"
                :type="currentRemoteDiscovery.installable ? 'success' : 'warning'"
                show-icon
                :message="currentRemoteDiscovery.message || '远程资源检查完成'"
                :description="remoteDiscoveryDescription"
              />

              <a-space>
                <a-button :loading="busy" @click="submitRemoteCheck">检查远程资源</a-button>
                <a-button
                  type="primary"
                  :loading="busy"
                  :disabled="!currentRemoteDiscovery?.installable"
                  @click="submitRemote"
                >
                  {{ binding.projectId ? '下载并生成升级计划' : '下载并导入' }}
                </a-button>
              </a-space>
            </a-form>
          </a-tab-pane>
        </a-tabs>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import type {
  MaaFWManagedBinding,
  MaaFWManagedFeatures,
  MaaFWManagedLocalSourceInput,
  MaaFWManagedRemoteDiscovery,
  MaaFWManagedRemoteSourceInput,
} from '@/composables/useMaaFWManagedApi'

defineOptions({ name: 'MaaFWProjectOperationsPanel' })

const props = defineProps<{
  scriptId: string
  binding: MaaFWManagedBinding
  features: MaaFWManagedFeatures
  busy: boolean
  remoteDiscovery: MaaFWManagedRemoteDiscovery | null
}>()

const emit = defineEmits<{
  convert: [input: { projectId?: string; version?: string; runtimeConstraint?: string }]
  'local-submit': [mode: 'import' | 'upgrade', input: MaaFWManagedLocalSourceInput]
  'remote-check': [input: MaaFWManagedRemoteSourceInput]
  'remote-submit': [mode: 'import' | 'upgrade', input: MaaFWManagedRemoteSourceInput]
  'apply-plan': []
  'cancel-plan': []
}>()

const sourceTab = ref<'local' | 'remote'>('local')
const localSourceKind = ref<'directory' | 'archive'>('directory')
const convertForm = reactive({
  projectId: '',
  version: '',
  runtimeConstraint: '',
})
const localForm = reactive({
  projectId: '',
  version: '',
  runtimeConstraint: '',
  source: '',
})
const remoteForm = reactive({
  projectId: '',
  runtimeConstraint: '',
  source: 'MirrorChyan' as 'MirrorChyan' | 'GitHub',
  channel: '',
  mirrorChyanRid: '',
  mirrorChyanCDK: '',
  githubRepo: '',
  githubTag: '',
  githubAssetPattern: '',
})
const remoteFormRevision = ref(0)
const lastCheckedRemoteRevision = ref(-1)

watch(
  remoteForm,
  () => {
    remoteFormRevision.value += 1
  },
  { deep: true }
)

watch(
  () => props.binding,
  binding => {
    localForm.projectId = binding.projectId || localForm.projectId
    localForm.runtimeConstraint = binding.runtimeConstraint || localForm.runtimeConstraint
    remoteForm.projectId = binding.projectId || remoteForm.projectId
    remoteForm.runtimeConstraint = binding.runtimeConstraint || remoteForm.runtimeConstraint
  },
  { immediate: true }
)

watch(
  () => props.features,
  features => {
    if (sourceTab.value === 'local' && !features.localImport && features.remoteImport) {
      sourceTab.value = 'remote'
    } else if (sourceTab.value === 'remote' && !features.remoteImport && features.localImport) {
      sourceTab.value = 'local'
    }
  },
  { immediate: true }
)

const planStatusLabel = computed(() => {
  const plan = props.binding.pendingPlan
  if (!plan) return ''
  if (plan.state === 'ready' && plan.readyToApply) return '可以应用'
  if (plan.state === 'plan_error') return '规划失败'
  if (['applying', 'committing', 'recovery_required'].includes(plan.state)) return '正在恢复事务'
  if (plan.state === 'rollback_failed') return '回滚失败'
  return '需要处理'
})

const planStatusColor = computed(() => {
  const plan = props.binding.pendingPlan
  if (plan?.state === 'ready' && plan.readyToApply) return 'green'
  if (plan?.state === 'plan_error' || plan?.state === 'rollback_failed') return 'red'
  return 'orange'
})

const planCanApply = computed(
  () =>
    props.binding.pendingPlan?.state === 'ready' &&
    props.binding.pendingPlan.readyToApply &&
    Boolean(props.binding.pendingPlan.confirmationToken)
)

const planBlockingMessages = computed(() => {
  const plan = props.binding.pendingPlan
  if (!plan) return []
  const messages = [...(plan.errors || []), ...(plan.manualActions || [])]
    .map(item => item.message || String(item.action?.message || ''))
    .filter(Boolean)
  return [...new Set(messages)]
})

const currentRemoteDiscovery = computed(() =>
  lastCheckedRemoteRevision.value === remoteFormRevision.value ? props.remoteDiscovery : null
)

const remoteDiscoveryDescription = computed(() => {
  if (!currentRemoteDiscovery.value) return ''
  const current = currentRemoteDiscovery.value.currentVersion || '未绑定'
  const latest = currentRemoteDiscovery.value.latestVersion || '未发现'
  return `当前 ${current} · 远程 ${latest}${
    currentRemoteDiscovery.value.installable ? ' · 可下载安装' : ' · 无可安装候选'
  }`
})

const submitConvert = () => {
  emit('convert', {
    projectId: convertForm.projectId.trim() || undefined,
    version: convertForm.version.trim() || undefined,
    runtimeConstraint: convertForm.runtimeConstraint.trim() || undefined,
  })
}

const selectLocalSource = async () => {
  if (localSourceKind.value === 'directory') {
    const selected = await window.electronAPI?.selectFolder()
    if (selected) localForm.source = selected
    return
  }
  const selected = await window.electronAPI?.selectFile([
    { name: 'ZIP 发行包', extensions: ['zip'] },
  ])
  if (selected?.[0]) localForm.source = selected[0]
}

const submitLocal = () => {
  const projectId = localForm.projectId.trim()
  const source = localForm.source.trim()
  if (!projectId || !source) {
    message.warning('请选择资源来源并填写项目 ID')
    return
  }
  emit('local-submit', props.binding.projectId ? 'upgrade' : 'import', {
    scriptId: props.scriptId,
    projectId,
    version: localForm.version.trim() || undefined,
    runtimeConstraint: localForm.runtimeConstraint.trim() || undefined,
    sourcePath: localSourceKind.value === 'directory' ? source : undefined,
    sourceArchive: localSourceKind.value === 'archive' ? source : undefined,
  })
}

const buildRemoteInput = (): MaaFWManagedRemoteSourceInput | null => {
  const projectId = remoteForm.projectId.trim()
  if (!projectId) {
    message.warning('请填写项目 ID')
    return null
  }
  if (
    remoteForm.source === 'MirrorChyan' &&
    (!remoteForm.mirrorChyanRid.trim() || !remoteForm.mirrorChyanCDK.trim())
  ) {
    message.warning('MirrorChyan 来源需要 RID 和 CDK')
    return null
  }
  if (remoteForm.source === 'GitHub' && !remoteForm.githubRepo.trim()) {
    message.warning('GitHub 来源需要 owner/repository')
    return null
  }
  return {
    scriptId: props.scriptId,
    projectId,
    runtimeConstraint: remoteForm.runtimeConstraint.trim() || undefined,
    source: remoteForm.source,
    channel: remoteForm.channel.trim() || undefined,
    mirrorChyanRid: remoteForm.mirrorChyanRid.trim() || undefined,
    mirrorChyanCDK: remoteForm.mirrorChyanCDK.trim() || undefined,
    githubRepo: remoteForm.githubRepo.trim() || undefined,
    githubTag: remoteForm.githubTag.trim() || undefined,
    githubAssetPattern: remoteForm.githubAssetPattern.trim() || undefined,
  }
}

const submitRemoteCheck = () => {
  const input = buildRemoteInput()
  if (input) {
    lastCheckedRemoteRevision.value = remoteFormRevision.value
    emit('remote-check', input)
  }
}

const submitRemote = () => {
  if (!currentRemoteDiscovery.value?.installable) {
    message.warning('远程来源已变化，请先重新检查可安装候选')
    return
  }
  const input = buildRemoteInput()
  if (input) emit('remote-submit', props.binding.projectId ? 'upgrade' : 'import', input)
}
</script>

<style scoped>
.maafw-project-operations-panel {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.operation-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.operation-section + .operation-section {
  padding-top: 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
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

.operation-form {
  padding: 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
}

.pending-plan-section {
  padding: 16px;
  border: 1px solid var(--ant-color-warning-border);
  border-radius: 8px;
  background: var(--ant-color-warning-bg);
}

.message-list {
  margin: 0;
  padding-left: 20px;
}
</style>

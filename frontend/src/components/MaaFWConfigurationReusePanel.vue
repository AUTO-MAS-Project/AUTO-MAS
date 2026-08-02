<template>
  <section class="reuse-panel">
    <a-alert
      :message="mode === 'first-user' ? '复用已有 MaaFW 配置' : '选择新用户的配置来源'"
      :description="panelDescription"
      type="info"
      show-icon
      class="reuse-intro"
    />

    <div class="source-mode-grid">
      <button
        type="button"
        :class="['source-mode-card', { selected: selectedMode === 'blank' }]"
        @click="selectMode('blank')"
      >
        <PlusOutlined />
        <span class="mode-title">{{ mode === 'first-user' ? '暂不导入' : '空白用户' }}</span>
        <span class="mode-description">
          {{
            mode === 'first-user'
              ? '保留当前默认配置，继续完成项目引导。'
              : '使用当前项目 schema 的默认值。'
          }}
        </span>
      </button>
      <button
        type="button"
        :class="['source-mode-card', { selected: selectedMode === 'external' }]"
        @click="selectMode('external')"
      >
        <FolderOpenOutlined />
        <span class="mode-title">外部 MaaFW 配置</span>
        <span class="mode-description">
          从 MFAAvalonia、MFW/CFA 或 MXU 的配置文件中生成预览。
        </span>
      </button>
      <button
        v-if="mode === 'new-user'"
        type="button"
        :disabled="existingUsers.length === 0"
        :class="['source-mode-card', { selected: selectedMode === 'copy' }]"
        @click="selectMode('copy')"
      >
        <CopyOutlined />
        <span class="mode-title">复制已有用户</span>
        <span class="mode-description">
          {{
            existingUsers.length ? '深复制业务配置并重置运行状态。' : '当前脚本还没有可复制的用户。'
          }}
        </span>
      </button>
    </div>

    <div v-if="selectedMode === 'blank'" class="action-surface">
      <a-result
        status="success"
        :title="mode === 'first-user' ? '继续使用默认配置' : '创建空白用户'"
        :sub-title="
          mode === 'first-user' ? '不会扫描或修改任何外部目录。' : '创建后会进入 MaaFW 用户编辑页。'
        "
      >
        <template #extra>
          <a-button type="primary" size="large" :loading="loading" @click="handleBlank">
            {{ mode === 'first-user' ? '确认并继续' : '创建空白用户' }}
          </a-button>
        </template>
      </a-result>
    </div>

    <div v-else-if="selectedMode === 'external'" class="action-surface">
      <div class="surface-heading">
        <div>
          <h3>选择配置文件或目录</h3>
          <p>只读发现候选配置；不会改写外部 MaaFW 文件。</p>
        </div>
        <a-space wrap>
          <a-button
            v-if="defaultSourcePath"
            :loading="loading"
            @click="scanSource(defaultSourcePath)"
          >
            扫描当前项目
          </a-button>
          <a-button :loading="loading" @click="chooseFolder">选择目录</a-button>
          <a-button :loading="loading" @click="chooseFile">选择 JSON</a-button>
        </a-space>
      </div>

      <a-input
        v-model:value="sourcePath"
        readonly
        placeholder="请选择包含 config 的 MaaFW 目录或具体 JSON 文件"
        class="source-path"
      />

      <a-spin :spinning="loading">
        <a-empty
          v-if="sourceScanned && sources.length === 0"
          description="该位置没有发现可识别的 MFAAvalonia/MFW/CFA/MXU 配置"
          class="source-empty"
        />
        <a-radio-group
          v-else-if="sources.length"
          v-model:value="selectedSourceId"
          class="source-list"
        >
          <label v-for="source in sources" :key="source.sourceId" class="source-row">
            <a-radio :value="source.sourceId" />
            <span class="source-main">
              <span class="source-title">{{ source.label }}</span>
              <span class="source-meta">
                <a-tag>{{ source.kind }}</a-tag>
                <span>{{ source.summary?.taskCount || 0 }} 个任务</span>
                <span v-if="source.summary?.controller"
                  >Controller: {{ source.summary.controller }}</span
                >
                <span v-if="source.summary?.resource">Resource: {{ source.summary.resource }}</span>
              </span>
            </span>
          </label>
        </a-radio-group>
      </a-spin>

      <div v-if="sources.length" class="surface-actions">
        <a-button
          type="primary"
          :loading="loading"
          :disabled="!selectedSource"
          @click="previewExternal"
        >
          预览导入内容
        </a-button>
      </div>
    </div>

    <div v-else-if="selectedMode === 'copy'" class="action-surface">
      <div class="surface-heading">
        <div>
          <h3>复制已有用户</h3>
          <p>任务、通知和业务字段会被复制；运行状态、journal、lease 和引用会重置。</p>
        </div>
      </div>
      <a-form layout="vertical">
        <a-form-item label="来源用户">
          <a-select
            v-model:value="sourceUserId"
            placeholder="请选择一个已有用户"
            :options="userOptions"
          />
        </a-form-item>
        <a-form-item label="新用户名称（可选）">
          <a-input v-model:value="targetUserName" placeholder="默认：原名称 - 副本" />
        </a-form-item>
      </a-form>
      <div class="surface-actions">
        <a-button type="primary" :loading="loading" :disabled="!sourceUserId" @click="previewCopy">
          预览复制内容
        </a-button>
      </div>
    </div>

    <a-alert v-if="error" type="error" show-icon :message="error" class="reuse-error" />

    <a-card v-if="plan" title="配置复用预览" class="preview-card">
      <a-descriptions :column="2" bordered size="small">
        <a-descriptions-item label="来源">{{ plan.preview.sourceLabel }}</a-descriptions-item>
        <a-descriptions-item label="格式">{{ plan.preview.format }}</a-descriptions-item>
        <a-descriptions-item label="新用户">{{ plan.preview.userName }}</a-descriptions-item>
        <a-descriptions-item label="任务 / Option">
          {{ plan.preview.taskCount }} / {{ plan.preview.optionCount }}
        </a-descriptions-item>
        <a-descriptions-item label="脚本级字段" :span="2">
          <a-space v-if="plan.preview.scriptFields.length" wrap>
            <a-tag v-for="field in plan.preview.scriptFields" :key="field" color="blue">
              {{ field }}
            </a-tag>
          </a-space>
          <span v-else class="muted-text">不修改当前脚本绑定</span>
        </a-descriptions-item>
      </a-descriptions>

      <div v-if="plan.manualActions.length" class="preview-section">
        <h4>需要确认</h4>
        <a-alert
          v-for="item in plan.manualActions"
          :key="`${item.kind}:${item.message}`"
          :type="item.blocking ? 'error' : 'warning'"
          show-icon
          :message="item.message"
          class="preview-alert"
        />
      </div>

      <div v-if="plan.warnings.length" class="preview-section">
        <h4>提示</h4>
        <a-alert
          v-for="warning in plan.warnings"
          :key="warning"
          type="warning"
          show-icon
          :message="warning"
          class="preview-alert"
        />
      </div>

      <div v-if="orphanKeys.length" class="preview-section">
        <h4>未映射内容</h4>
        <a-space wrap>
          <a-tag v-for="key in orphanKeys" :key="key" color="orange">{{ key }}</a-tag>
        </a-space>
        <p class="muted-text">未映射内容不会静默写入运行配置，可返回外部 MaaFW 人工核对。</p>
      </div>

      <template #actions>
        <a-button
          type="primary"
          size="large"
          :loading="loading"
          :disabled="!plan.readyToApply"
          @click="confirmApply"
        >
          {{ mode === 'first-user' ? '确认导入并创建第一个用户' : '确认并创建用户' }}
        </a-button>
      </template>
    </a-card>
  </section>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { CopyOutlined, FolderOpenOutlined, PlusOutlined } from '@ant-design/icons-vue'
import {
  useMaaFWConfigurationReuse,
  type MaaFWConfigurationApplyResult,
  type MaaFWConfigurationPlan,
  type MaaFWConfigurationSource,
} from '@/composables/useMaaFWConfigurationReuse'
import type { ScriptUserRecord } from '@/types/scriptRegistry'

type ReuseMode = 'blank' | 'external' | 'copy'

const props = withDefaults(
  defineProps<{
    scriptId: string
    mode: 'first-user' | 'new-user'
    defaultSourcePath?: string
    existingUsers?: ScriptUserRecord[]
  }>(),
  {
    defaultSourcePath: '',
    existingUsers: () => [],
  }
)

const emit = defineEmits<{
  blank: []
  skipped: []
  applied: [result: MaaFWConfigurationApplyResult]
}>()

const { loading, error, discoverSources, planExternal, planCopy, applyPlan } =
  useMaaFWConfigurationReuse()

const selectedMode = ref<ReuseMode | null>(null)
const sourcePath = ref('')
const sourceScanned = ref(false)
const sources = ref<MaaFWConfigurationSource[]>([])
const selectedSourceId = ref('')
const sourceUserId = ref('')
const targetUserName = ref('')
const plan = ref<MaaFWConfigurationPlan | null>(null)

const panelDescription = computed(() =>
  props.mode === 'first-user'
    ? '可把游戏、控制、资源和具体任务配置导入当前项目；具体任务会创建为第一个用户。'
    : '创建记录前先选择空白配置、外部 MaaFW 配置，或复制当前脚本中的已有用户。'
)

const selectedSource = computed(
  () => sources.value.find(item => item.sourceId === selectedSourceId.value) || null
)
const userOptions = computed(() =>
  props.existingUsers.map(user => ({
    label: user.name,
    value: user.id,
  }))
)
const orphanKeys = computed(() => Object.keys(plan.value?.orphans || {}))

watch(selectedMode, () => {
  plan.value = null
  error.value = null
})

const selectMode = (mode: ReuseMode) => {
  if (mode === 'copy' && props.existingUsers.length === 0) return
  selectedMode.value = mode
}

const scanSource = async (path: string) => {
  const normalizedPath = path.trim()
  if (!normalizedPath) {
    message.warning('请选择配置文件或目录')
    return
  }
  sourcePath.value = normalizedPath
  plan.value = null
  try {
    sources.value = await discoverSources(props.scriptId, normalizedPath)
    selectedSourceId.value = sources.value[0]?.sourceId || ''
    sourceScanned.value = true
    if (sources.value.length === 0) {
      message.info('没有发现可识别的 MaaFW 配置')
    }
  } catch {
    sources.value = []
    selectedSourceId.value = ''
    sourceScanned.value = true
  }
}

const chooseFolder = async () => {
  const selected = await window.electronAPI?.selectFolder()
  if (selected) await scanSource(selected)
}

const chooseFile = async () => {
  const selected = await window.electronAPI?.selectFile([
    { name: 'MaaFW JSON 配置', extensions: ['json'] },
  ])
  if (selected?.[0]) await scanSource(selected[0])
}

const previewExternal = async () => {
  if (!selectedSource.value) return
  try {
    plan.value = await planExternal(
      props.scriptId,
      selectedSource.value,
      props.mode === 'first-user' ? 'project-and-first-user' : 'new-user'
    )
  } catch {
    plan.value = null
  }
}

const previewCopy = async () => {
  if (!sourceUserId.value) return
  try {
    plan.value = await planCopy(props.scriptId, sourceUserId.value, targetUserName.value)
  } catch {
    plan.value = null
  }
}

const handleBlank = () => {
  if (props.mode === 'first-user') {
    emit('skipped')
    return
  }
  emit('blank')
}

const confirmApply = async () => {
  if (!plan.value?.readyToApply) return
  try {
    const result = await applyPlan(props.scriptId, plan.value.planId)
    message.success(props.mode === 'first-user' ? '外部配置已导入' : '用户已创建')
    emit('applied', result)
  } catch {
    // The composable exposes the exact server-side CAS/transaction error above.
  }
}
</script>

<style scoped>
.reuse-panel {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.reuse-intro,
.reuse-error {
  border-radius: 10px;
}

.source-mode-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.source-mode-card {
  display: flex;
  min-height: 132px;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  padding: 20px;
  color: var(--ant-color-text);
  text-align: left;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    box-shadow 0.2s ease,
    transform 0.2s ease;
}

.source-mode-card > :deep(.anticon) {
  color: var(--ant-color-primary);
  font-size: 24px;
}

.source-mode-card:hover:not(:disabled),
.source-mode-card.selected {
  border-color: var(--ant-color-primary);
  box-shadow: 0 6px 20px color-mix(in srgb, var(--ant-color-primary) 14%, transparent);
  transform: translateY(-1px);
}

.source-mode-card:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.mode-title {
  font-size: 16px;
  font-weight: 600;
}

.mode-description,
.surface-heading p,
.muted-text {
  color: var(--ant-color-text-secondary);
}

.mode-description {
  line-height: 1.6;
}

.action-surface {
  padding: 20px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 12px;
}

.surface-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.surface-heading h3,
.surface-heading p,
.preview-section h4,
.preview-section p {
  margin: 0;
}

.surface-heading p {
  margin-top: 6px;
}

.source-path {
  margin-bottom: 16px;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
}

.source-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 14px;
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  cursor: pointer;
}

.source-main {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 8px;
}

.source-title {
  font-weight: 600;
}

.source-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

.source-empty {
  padding: 24px 0;
}

.surface-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 18px;
}

.preview-card {
  border-radius: 12px;
}

.preview-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 20px;
}

.preview-alert {
  border-radius: 8px;
}

@media (max-width: 900px) {
  .source-mode-grid {
    grid-template-columns: 1fr;
  }

  .surface-heading {
    flex-direction: column;
  }
}
</style>

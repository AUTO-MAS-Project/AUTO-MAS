<template>
  <a-modal
    :open="open"
    :width="960"
    :closable="!submitting"
    :keyboard="!submitting"
    :mask-closable="!submitting"
    :confirm-loading="submitting"
    :z-index="900"
    :footer="null"
    class="script-create-dialog"
    title="新建脚本"
    @cancel="handleCancel"
  >
    <div class="create-layout">
      <section class="step-content">
        <template v-if="currentStep === 'type'">
          <StepHeading title="选择脚本类型" description="按名称、游戏或脚本框架快速查找。" />
          <div class="list-toolbar single">
            <a-input v-model:value="typeKeyword" allow-clear placeholder="搜索脚本类型">
              <template #prefix><SearchOutlined /></template>
            </a-input>
          </div>
          <a-radio-group
            v-if="filteredTypes.length"
            v-model:value="selectedType"
            class="type-sections"
          >
            <section v-if="typeSections.general.length" class="type-section">
              <div class="type-section-heading">
                <span class="type-section-title">通用脚本</span>
              </div>
              <label
                v-for="option in typeSections.general"
                :key="option.value"
                :class="['type-row general-type-row', { selected: selectedType === option.value }]"
              >
                <img :src="option.icon" :alt="option.title" class="type-icon" />
                <span class="choice-copy">
                  <span class="choice-title">{{ option.title }}</span>
                  <span class="choice-description">{{ option.description }}</span>
                </span>
                <a-radio :value="option.value" />
              </label>
            </section>
            <section
              v-if="typeSections.specialized.length"
              class="type-section specialized-section"
            >
              <div class="type-section-heading">
                <span class="type-section-title">专项适配</span>
              </div>
              <div class="type-grid">
                <label
                  v-for="option in typeSections.specialized"
                  :key="option.value"
                  :class="['type-row', { selected: selectedType === option.value }]"
                >
                  <img :src="option.icon" :alt="option.title" class="type-icon" />
                  <span class="choice-copy">
                    <span class="choice-title">{{ option.title }}</span>
                    <span class="choice-description">{{ option.description }}</span>
                  </span>
                  <a-radio :value="option.value" />
                </label>
              </div>
            </section>
          </a-radio-group>
          <a-empty v-else description="未找到匹配的脚本类型">
            <a-button @click="clearTypeFilters">清空搜索</a-button>
          </a-empty>
        </template>

        <template v-else-if="currentStep === 'config'">
          <template v-if="configView === 'choice'">
            <StepHeading
              title="选择配置来源"
              description="通用脚本可以从模板开始，也可以完全自定义。"
            />
            <a-radio-group v-model:value="selectedConfigMode" class="choice-list">
              <label :class="['choice-row', { selected: selectedConfigMode === 'template' }]">
                <a-radio value="template" />
                <span class="choice-icon"><DatabaseOutlined /></span>
                <span class="choice-copy">
                  <span class="choice-title">从模板创建</span>
                  <span class="choice-description">选择社区模板，快速获得一套基础配置</span>
                </span>
              </label>
              <label :class="['choice-row', { selected: selectedConfigMode === 'custom' }]">
                <a-radio value="custom" />
                <span class="choice-icon"><SettingOutlined /></span>
                <span class="choice-copy">
                  <span class="choice-title">自定义配置</span>
                  <span class="choice-description">创建空白通用脚本，在编辑页逐项配置</span>
                </span>
              </label>
            </a-radio-group>
          </template>

          <template v-else>
            <StepHeading title="选择配置模板" description="搜索并选择一个模板作为初始配置。" />
            <div class="list-toolbar single">
              <a-input
                v-model:value="templateKeyword"
                allow-clear
                placeholder="搜索模板名称、作者或描述"
              >
                <template #prefix><SearchOutlined /></template>
              </a-input>
              <a-button :loading="templateLoading" @click="emit('request-templates')"
                >重新加载</a-button
              >
            </div>
            <a-alert
              v-if="templateError"
              type="error"
              show-icon
              :message="templateError"
              class="template-alert"
            >
              <template #action>
                <a-button size="small" @click="emit('request-templates')">重试</a-button>
              </template>
            </a-alert>
            <div v-if="templateLoading" class="template-loading-state">
              <a-spin size="large" tip="正在加载配置模板..." />
            </div>
            <a-radio-group
              v-else-if="filteredTemplates.length"
              v-model:value="selectedTemplateUrl"
              class="entity-list template-list"
            >
              <label
                v-for="template in filteredTemplates"
                :key="template.downloadUrl"
                :class="[
                  'entity-row template-row',
                  { selected: selectedTemplateUrl === template.downloadUrl },
                ]"
              >
                <span class="choice-copy">
                  <span class="choice-title">{{ template.configName }}</span>
                  <span class="template-meta">
                    <span><UserOutlined /> {{ template.author || '未知作者' }}</span>
                    <span><ClockCircleOutlined /> {{ template.createTime || '未知时间' }}</span>
                  </span>
                  <!-- eslint-disable vue/no-v-html -- MarkdownIt has raw HTML disabled, so template descriptions are escaped. -->
                  <span
                    class="template-description"
                    @click="handleTemplateDescriptionClick"
                    v-html="parseMarkdown(template.description)"
                  ></span>
                  <!-- eslint-enable vue/no-v-html -->
                </span>
                <a-radio :value="template.downloadUrl" />
              </label>
            </a-radio-group>
            <a-empty v-else :description="templateKeyword ? '未找到匹配的模板' : '暂无可用模板'">
              <a-button v-if="templateKeyword" @click="templateKeyword = ''">清空搜索</a-button>
              <a-button v-else @click="chooseCustomConfig">改为自定义配置</a-button>
            </a-empty>
          </template>
        </template>

        <template v-else>
          <StepHeading
            title="确认创建脚本"
            description="确认以下信息后再创建，避免产生错误实例。"
          />
          <a-descriptions bordered :column="1" class="confirm-summary">
            <a-descriptions-item label="创建方式"> 创建全新脚本 </a-descriptions-item>
            <a-descriptions-item label="脚本类型">
              {{ getTypeOption(selectedType).title }}
            </a-descriptions-item>
            <a-descriptions-item v-if="selectedType === 'General'" label="配置来源">
              {{
                selectedConfigMode === 'custom'
                  ? '自定义配置'
                  : `模板：${selectedTemplate?.configName}`
              }}
            </a-descriptions-item>
          </a-descriptions>
        </template>
      </section>
    </div>

    <div class="dialog-footer">
      <a-button :disabled="!canGoBack || submitting" @click="handleBack">
        <template #icon><ArrowLeftOutlined /></template>
        返回
      </a-button>
      <a-space>
        <a-button :disabled="submitting" @click="handleCancel">取消</a-button>
        <a-button type="primary" :loading="submitting" :disabled="nextDisabled" @click="handleNext">
          {{ primaryButtonText }}
        </a-button>
      </a-space>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, ref, watch } from 'vue'
import {
  ArrowLeftOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import MarkdownIt from 'markdown-it'
import type { ScriptType } from '@/types/script'
import type { WebConfigTemplate } from '@/composables/useTemplateApi'
import { openExternalUrl } from '@/utils/openExternal'
import {
  buildCreateRequest,
  buildCreateSteps,
  filterScriptTypeOptions,
  SCRIPT_TYPE_OPTIONS,
  splitScriptTypeOptions,
  type ConfigMode,
  type CreateStepKey,
  type ScriptCreateRequest,
} from './scriptCreateFlow'

const StepHeading = defineComponent({
  props: { title: { type: String, required: true }, description: { type: String, required: true } },
  setup(props) {
    return () =>
      h('div', { class: 'step-heading' }, [h('h3', props.title), h('p', props.description)])
  },
})

const props = defineProps<{
  open: boolean
  templates: WebConfigTemplate[]
  submitting: boolean
  templateLoading: boolean
  templateError: string | null
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  'request-templates': []
  submit: [request: ScriptCreateRequest]
}>()

const md = new MarkdownIt({ html: false, linkify: true, typographer: true })
const currentStep = ref<CreateStepKey>('type')
const selectedType = ref<ScriptType>('MAA')
const selectedConfigMode = ref<ConfigMode>('template')
const selectedTemplateUrl = ref<string | null>(null)
const configView = ref<'choice' | 'templates'>('choice')
const typeKeyword = ref('')
const templateKeyword = ref('')

const steps = computed(() => buildCreateSteps({ type: selectedType.value }))
const currentStepIndex = computed(() =>
  Math.max(
    0,
    steps.value.findIndex(step => step.key === currentStep.value)
  )
)
const canGoBack = computed(
  () =>
    currentStepIndex.value > 0 ||
    (currentStep.value === 'config' && configView.value === 'templates')
)
const filteredTypes = computed(() =>
  filterScriptTypeOptions(SCRIPT_TYPE_OPTIONS, typeKeyword.value)
)
const typeSections = computed(() => splitScriptTypeOptions(filteredTypes.value))
const filteredTemplates = computed(() => {
  const keyword = templateKeyword.value.trim().toLowerCase()
  return props.templates.filter(template =>
    [template.configName, template.author, template.description]
      .join(' ')
      .toLowerCase()
      .includes(keyword)
  )
})
const selectedTemplate = computed(() =>
  props.templates.find(template => template.downloadUrl === selectedTemplateUrl.value)
)
const nextDisabled = computed(() => {
  if (props.submitting) return true
  if (currentStep.value === 'config' && configView.value === 'templates') {
    return !selectedTemplateUrl.value
  }
  return false
})
const primaryButtonText = computed(() => {
  if (currentStep.value === 'type' && selectedType.value !== 'General') return '创建并配置'
  if (currentStep.value === 'config' && selectedConfigMode.value === 'custom') {
    return '创建并配置'
  }
  if (currentStep.value === 'config' && configView.value === 'templates') {
    return '使用模板创建'
  }
  return '下一步'
})

watch(
  () => props.open,
  open => {
    if (open) resetDialog()
  }
)

const resetDialog = () => {
  currentStep.value = 'type'
  selectedType.value = 'MAA'
  selectedConfigMode.value = 'template'
  selectedTemplateUrl.value = null
  configView.value = 'choice'
  typeKeyword.value = ''
  templateKeyword.value = ''
}

const getTypeOption = (type: ScriptType) =>
  SCRIPT_TYPE_OPTIONS.find(option => option.value === type) ?? SCRIPT_TYPE_OPTIONS[0]

const handleBack = () => {
  if (props.submitting) return
  if (currentStep.value === 'config' && configView.value === 'templates') {
    configView.value = 'choice'
    return
  }
  const previousStep = steps.value[currentStepIndex.value - 1]
  if (previousStep) currentStep.value = previousStep.key
}

const handleNext = () => {
  if (currentStep.value === 'type') {
    if (selectedType.value === 'General') {
      currentStep.value = 'config'
    } else {
      submitCurrentSelection()
    }
    return
  }
  if (currentStep.value === 'config') {
    if (configView.value === 'choice' && selectedConfigMode.value === 'template') {
      configView.value = 'templates'
      emit('request-templates')
      return
    }
    if (selectedConfigMode.value === 'custom' || selectedTemplateUrl.value) submitCurrentSelection()
    return
  }
}

const submitCurrentSelection = () => {
  const request = buildCreateRequest({
    type: selectedType.value,
    configMode: selectedConfigMode.value,
    template: selectedTemplate.value ?? null,
  })
  if (request) emit('submit', request)
}

const handleCancel = () => {
  if (!props.submitting) emit('update:open', false)
}

const clearTypeFilters = () => {
  typeKeyword.value = ''
}

const chooseCustomConfig = () => {
  selectedConfigMode.value = 'custom'
  configView.value = 'choice'
}

const parseMarkdown = (text: string) => md.render(text || '暂无描述信息')

const handleTemplateDescriptionClick = (event: MouseEvent) => {
  const link = (event.target as HTMLElement | null)?.closest('a')
  if (!link) return
  event.preventDefault()
  const url = link.getAttribute('href')
  if (url) openExternalUrl(url)
}
</script>

<style scoped>
:global(.script-create-dialog) {
  top: 64px;
  padding-bottom: 16px;
}

:global(.script-create-dialog .ant-modal-content) {
  max-height: calc(100vh - 128px);
  overflow: hidden;
}

.create-layout {
  height: min(500px, calc(100vh - 192px));
  min-height: 0;
  margin: -8px -24px 0;
  overflow: hidden;
}

.choice-copy {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.step-content {
  height: 100%;
  min-width: 0;
  padding: 24px 28px;
  overflow-y: auto;
  background: var(--ant-color-bg-elevated);
}

:deep(.step-heading h3) {
  margin: 0;
  color: var(--ant-color-text);
  font-size: 18px;
}

:deep(.step-heading p) {
  margin: 6px 0 20px;
  color: var(--ant-color-text-secondary);
}

.choice-list,
.entity-list {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 10px;
}

.choice-row,
.entity-row,
.type-row {
  display: flex;
  min-width: 0;
  gap: 12px;
  align-items: center;
  padding: 14px;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text);
  background: var(--ant-color-bg-container);
  cursor: pointer;
}

.choice-row:hover,
.entity-row:hover,
.type-row:hover,
.choice-row.selected,
.entity-row.selected,
.type-row.selected {
  border-color: var(--ant-color-primary);
}

.choice-row.selected,
.entity-row.selected,
.type-row.selected {
  background: var(--ant-color-primary-bg);
}

.choice-row.disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.choice-icon {
  display: inline-flex;
  width: 38px;
  height: 38px;
  flex: 0 0 38px;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  font-size: 19px;
}

.choice-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.choice-description {
  margin-top: 3px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.list-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 10px;
  margin-bottom: 16px;
}

.list-toolbar.single {
  grid-template-columns: minmax(0, 1fr) auto;
}

.type-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.type-sections {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 18px;
}

.type-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.type-section-title {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
}

.type-section-count,
.type-section-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
}

.specialized-section {
  padding-top: 14px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.general-type-row {
  background: var(--ant-color-bg-container);
}

.type-icon {
  width: 34px;
  height: 34px;
  flex: 0 0 34px;
  border-radius: 6px;
  object-fit: contain;
}

.entity-list,
.template-list {
  width: 100%;
}

.ellipsis {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.template-row {
  align-items: flex-start;
}

.template-meta {
  display: flex;
  gap: 16px;
  margin-top: 4px;
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
}

.template-description {
  margin-top: 7px;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 1.5;
}

.template-description :deep(p) {
  margin: 0;
}

.template-alert {
  margin-bottom: 12px;
}

.template-loading-state {
  display: flex;
  min-height: 240px;
  align-items: center;
  justify-content: center;
}

.confirm-summary {
  margin-top: 20px;
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  margin: 0 -24px -20px;
  padding: 14px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

@media (max-width: 760px) {
  .type-grid {
    grid-template-columns: 1fr;
  }

  .list-toolbar {
    grid-template-columns: 1fr;
  }
}
</style>

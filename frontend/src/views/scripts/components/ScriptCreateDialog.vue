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
    :title="t('scripts.create.title')"
    @cancel="handleCancel"
  >
    <div class="create-layout">
      <section class="step-content">
        <template v-if="currentStep === 'type'">
          <StepHeading
            :title="t('scripts.create.typeHeading')"
            :description="t('scripts.create.typeHeadingDesc')"
          />
          <div class="list-toolbar single">
            <a-input
              v-model:value="typeKeyword"
              allow-clear
              :placeholder="t('scripts.create.typeSearch')"
            >
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
                <span class="type-section-title">{{ t('scripts.create.groupGeneral') }}</span>
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
                <span class="type-section-title">{{ t('scripts.create.groupSpecialized') }}</span>
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
          <a-empty v-else :description="t('scripts.create.noTypeMatch')">
            <a-button @click="clearTypeFilters">{{ t('scripts.clearSearch') }}</a-button>
          </a-empty>
        </template>

        <template v-else-if="currentStep === 'config'">
          <template v-if="configView === 'choice'">
            <StepHeading
              :title="t('scripts.create.sourceHeading')"
              :description="t('scripts.create.sourceHeadingDesc')"
            />
            <a-radio-group v-model:value="selectedConfigMode" class="choice-list">
              <label :class="['choice-row', { selected: selectedConfigMode === 'template' }]">
                <a-radio value="template" />
                <span class="choice-icon"><DatabaseOutlined /></span>
                <span class="choice-copy">
                  <span class="choice-title">{{ t('scripts.create.fromTemplate') }}</span>
                  <span class="choice-description">{{ t('scripts.create.fromTemplateDesc') }}</span>
                </span>
              </label>
              <label :class="['choice-row', { selected: selectedConfigMode === 'custom' }]">
                <a-radio value="custom" />
                <span class="choice-icon"><SettingOutlined /></span>
                <span class="choice-copy">
                  <span class="choice-title">{{ t('scripts.create.custom') }}</span>
                  <span class="choice-description">{{ t('scripts.create.customDesc') }}</span>
                </span>
              </label>
            </a-radio-group>
          </template>

          <template v-else>
            <StepHeading
              :title="t('scripts.create.templateHeading')"
              :description="t('scripts.create.templateHeadingDesc')"
            />
            <div class="list-toolbar single">
              <a-input
                v-model:value="templateKeyword"
                allow-clear
                :placeholder="t('scripts.create.templateSearch')"
                @update:value="scheduleTemplateSearch"
                @press-enter="requestTemplates(1)"
              >
                <template #prefix><SearchOutlined /></template>
              </a-input>
              <a-button :loading="templateLoading" @click="requestTemplates(templatePage)">{{
                t('scripts.create.reload')
              }}</a-button>
            </div>
            <a-alert
              v-if="templateError"
              type="error"
              show-icon
              :message="templateError"
              class="template-alert"
            >
              <template #action>
                <a-button size="small" @click="requestTemplates(templatePage)">{{
                  t('scripts.create.retry')
                }}</a-button>
              </template>
            </a-alert>
            <div v-if="templateLoading" class="template-loading-state">
              <a-spin size="large" :tip="t('scripts.create.templateLoading')" />
            </div>
            <template v-else-if="templates.length">
              <a-radio-group v-model:value="selectedTemplateKey" class="entity-list template-list">
                <label
                  v-for="template in templates"
                  :key="template.configKey"
                  :class="[
                    'entity-row template-row',
                    { selected: selectedTemplateKey === template.configKey },
                  ]"
                >
                  <span class="choice-copy">
                    <span class="choice-title">{{ template.displayName }}</span>
                    <span class="template-meta">
                      <span
                        ><UserOutlined />
                        {{ template.ownerUsername || t('scripts.template.unknownAuthor') }}</span
                      >
                      <span
                        ><ClockCircleOutlined /> {{ formatPublishedAt(template.publishedAt) }}</span
                      >
                    </span>
                    <span class="template-description">{{
                      template.description || t('scripts.noDescription')
                    }}</span>
                  </span>
                  <a-radio :value="template.configKey" />
                </label>
              </a-radio-group>
              <div v-if="templateTotal > templatePageSize" class="template-pagination">
                <a-pagination
                  size="small"
                  :current="templatePage"
                  :page-size="templatePageSize"
                  :total="templateTotal"
                  :show-size-changer="false"
                  :disabled="templateLoading"
                  @change="requestTemplates"
                />
              </div>
            </template>
            <a-empty
              v-else
              :description="
                templateKeyword
                  ? t('scripts.create.noTemplateMatch')
                  : t('scripts.create.noTemplates')
              "
            >
              <a-button v-if="templateKeyword" @click="clearTemplateKeyword">{{
                t('scripts.clearSearch')
              }}</a-button>
              <a-button v-else @click="chooseCustomConfig">{{
                t('scripts.create.switchToCustom')
              }}</a-button>
            </a-empty>
          </template>
        </template>

        <template v-else>
          <StepHeading
            :title="t('scripts.create.confirmHeading')"
            :description="t('scripts.create.confirmHeadingDesc')"
          />
          <a-descriptions bordered :column="1" class="confirm-summary">
            <a-descriptions-item :label="t('scripts.create.labelMode')">
              {{ t('scripts.create.modeNew') }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('scripts.create.labelType')">
              {{ t(getTypeOption(selectedType).titleKey) }}
            </a-descriptions-item>
            <a-descriptions-item
              v-if="selectedType === 'General'"
              :label="t('scripts.create.labelSource')"
            >
              {{
                selectedConfigMode === 'custom'
                  ? t('scripts.create.custom')
                  : t('scripts.create.sourceTemplate', { name: selectedTemplate?.displayName })
              }}
            </a-descriptions-item>
          </a-descriptions>
        </template>
      </section>
    </div>

    <div class="dialog-footer">
      <a-button :disabled="!canGoBack || submitting" @click="handleBack">
        <template #icon><ArrowLeftOutlined /></template>
        {{ t('scripts.create.back') }}
      </a-button>
      <a-space>
        <a-button :disabled="submitting" @click="handleCancel">{{ t('common.cancel') }}</a-button>
        <a-button type="primary" :loading="submitting" :disabled="nextDisabled" @click="handleNext">
          {{ primaryButtonText }}
        </a-button>
      </a-space>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, defineComponent, h, onBeforeUnmount, ref, watch } from 'vue'
import {
  ArrowLeftOutlined,
  ClockCircleOutlined,
  DatabaseOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import type { ScriptType } from '@/types/script'
import type { ShareTemplateItem } from '@/composables/useTemplateApi'
import { formatBackendDateTime } from '@/utils/dateDisplay'
import {
  buildCreateRequest,
  buildCreateSteps,
  filterScriptTypeOptions,
  SCRIPT_TYPE_OPTIONS,
  splitScriptTypeOptions,
  type ConfigMode,
  type CreateStepKey,
  type ScriptCreateRequest,
  type TemplateRequest,
} from './scriptCreateFlow'

const { t } = useI18n()

const StepHeading = defineComponent({
  props: { title: { type: String, required: true }, description: { type: String, required: true } },
  setup(props) {
    return () =>
      h('div', { class: 'step-heading' }, [h('h3', props.title), h('p', props.description)])
  },
})

const props = defineProps<{
  open: boolean
  templates: ShareTemplateItem[]
  submitting: boolean
  templateLoading: boolean
  templateError: string | null
  templatePage: number
  templatePageSize: number
  templateTotal: number
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  'request-templates': [query: TemplateRequest]
  submit: [request: ScriptCreateRequest]
}>()

// 关键字输入后的静默期，避免每敲一个字就打一次配置中心
const TEMPLATE_SEARCH_DEBOUNCE = 400

const currentStep = ref<CreateStepKey>('type')
const selectedType = ref<ScriptType>('MAA')
const selectedConfigMode = ref<ConfigMode>('template')
const selectedTemplateKey = ref<string | null>(null)
const configView = ref<'choice' | 'templates'>('choice')
const typeKeyword = ref('')
const templateKeyword = ref('')
let searchTimer: ReturnType<typeof setTimeout> | null = null

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
// title/description 随语言变，先解析再过滤，别名匹配仍走 keywords
const typeOptions = computed(() =>
  SCRIPT_TYPE_OPTIONS.map(option => ({
    ...option,
    title: t(option.titleKey),
    description: t(option.descriptionKey),
  }))
)
const filteredTypes = computed(() =>
  filterScriptTypeOptions(typeOptions.value, typeKeyword.value, t)
)
const typeSections = computed(() => splitScriptTypeOptions(filteredTypes.value))
const selectedTemplate = computed(() =>
  props.templates.find(template => template.configKey === selectedTemplateKey.value)
)
const nextDisabled = computed(() => {
  if (props.submitting) return true
  if (currentStep.value === 'config' && configView.value === 'templates') {
    return !selectedTemplateKey.value
  }
  return false
})
const primaryButtonText = computed(() => {
  if (currentStep.value === 'type' && selectedType.value !== 'General') {
    return t('scripts.create.createAndConfigure')
  }
  if (currentStep.value === 'config' && selectedConfigMode.value === 'custom') {
    return t('scripts.create.createAndConfigure')
  }
  if (currentStep.value === 'config' && configView.value === 'templates') {
    return t('scripts.create.createFromTemplate')
  }
  return t('scripts.create.next')
})

watch(
  () => props.open,
  open => {
    if (open) resetDialog()
  }
)

const resetDialog = () => {
  cancelScheduledSearch()
  currentStep.value = 'type'
  selectedType.value = 'MAA'
  selectedConfigMode.value = 'template'
  selectedTemplateKey.value = null
  configView.value = 'choice'
  typeKeyword.value = ''
  templateKeyword.value = ''
}

const cancelScheduledSearch = () => {
  if (searchTimer !== null) {
    clearTimeout(searchTimer)
    searchTimer = null
  }
}

const requestTemplates = (page: number) => {
  cancelScheduledSearch()
  selectedTemplateKey.value = null
  emit('request-templates', { page, keyword: templateKeyword.value.trim() })
}

const scheduleTemplateSearch = () => {
  cancelScheduledSearch()
  searchTimer = setTimeout(() => requestTemplates(1), TEMPLATE_SEARCH_DEBOUNCE)
}

const clearTemplateKeyword = () => {
  templateKeyword.value = ''
  requestTemplates(1)
}

// 发布时间来自配置中心，按本机时区展示
const formatPublishedAt = (publishedAt: string | undefined) =>
  publishedAt ? formatBackendDateTime(publishedAt) : t('scripts.template.unknownTime')

onBeforeUnmount(cancelScheduledSearch)

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
      requestTemplates(1)
      return
    }
    if (selectedConfigMode.value === 'custom' || selectedTemplateKey.value) submitCurrentSelection()
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

.template-pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}

.template-description {
  white-space: pre-line;
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

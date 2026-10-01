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
              <div class="type-grid">
                <label
                  v-for="option in typeSections.general"
                  :key="option.value"
                  :class="[
                    'type-row general-type-row',
                    { selected: selectedType === option.value },
                  ]"
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

        <!-- MFW 家族第二步：项目从哪来（新建一个别的项目 / 复用已导入的同类型项目）。
             选项列表是可由特调替换的分节 create.source，选中状态留在这里；
             之后是特调的插入点 create.afterSourceStep -->
        <template v-else-if="currentStep === 'config' && isMfwFamily(selectedType)">
          <StepHeading
            :title="t('scripts.create.mfwSourceHeading')"
            :description="t('scripts.create.mfwSourceHeadingDesc')"
          />
          <component
            :is="createSections.source"
            v-model:value="selectedMfwChoice"
            :type="createFlavor.type"
            :choices="mfwReuseChoices"
            :loading="mfwSourcesLoading"
            :error="mfwSourcesError"
            @retry="emit('request-mfw-sources')"
          />
          <MaaFWFlavorSlot
            part="create"
            name="afterSourceStep"
            :flavor="createFlavor"
            :context="createSlotContext"
          />
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
              >
                <template #prefix><SearchOutlined /></template>
              </a-input>
              <a-button :loading="templateLoading" @click="emit('request-templates')">{{
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
                <a-button size="small" @click="emit('request-templates')">{{
                  t('scripts.create.retry')
                }}</a-button>
              </template>
            </a-alert>
            <div v-if="templateLoading" class="template-loading-state">
              <a-spin size="large" :tip="t('scripts.create.templateLoading')" />
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
                    <span
                      ><UserOutlined />
                      {{ template.author || t('scripts.template.unknownAuthor') }}</span
                    >
                    <span
                      ><ClockCircleOutlined />
                      {{ template.createTime || t('scripts.template.unknownTime') }}</span
                    >
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
            <a-empty
              v-else
              :description="
                templateKeyword
                  ? t('scripts.create.noTemplateMatch')
                  : t('scripts.create.noTemplates')
              "
            >
              <a-button v-if="templateKeyword" @click="templateKeyword = ''">{{
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
                  : t('scripts.create.sourceTemplate', { name: selectedTemplate?.configName })
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
import type { MaaFWEmbeddedSourceItem } from '@/api'
import {
  prepareMaaFWFlavorPage,
  resolveMaaFWFlavor,
  useMaaFWSections,
  type MaaFWCreateSlotContext,
} from '@/composables/useMaaFWFlavor'
import MaaFWFlavorSlot from '@/views/EditView/MaaFWFlavor/MaaFWFlavorSlot.vue'
import { openExternalUrl } from '@/utils/openExternal'
import MaaFWSourceStep from './MaaFWSourceStep.vue'
import {
  buildCreateRequest,
  buildCreateSteps,
  filterScriptTypeOptions,
  isMfwFamily,
  SCRIPT_TYPE_OPTIONS,
  splitScriptTypeOptions,
  type ConfigMode,
  type CreateStepKey,
  buildMfwReuseChoices,
  type ScriptCreateRequest,
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
  templates: WebConfigTemplate[]
  submitting: boolean
  templateLoading: boolean
  templateError: string | null
  /** 有健康副本的 MFW 家族脚本：MFW 家族第二步「复用已有脚本的项目」的候选（按类型筛在这里做） */
  mfwSources: MaaFWEmbeddedSourceItem[]
  mfwSourcesLoading: boolean
  /** 候选列表没读出来时的原因；有值就显示错误条 + 重试，而不是把它当成「没有可复用的脚本」 */
  mfwSourcesError: string | null
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  'request-templates': []
  'request-mfw-sources': []
  submit: [request: ScriptCreateRequest]
}>()

const md = new MarkdownIt({ html: false, linkify: true, typographer: true })
const currentStep = ref<CreateStepKey>('type')
const selectedType = ref<ScriptType>('MAA')
const selectedConfigMode = ref<ConfigMode>('template')
const selectedTemplateUrl = ref<string | null>(null)
const configView = ref<'choice' | 'templates'>('choice')
/** 'new' = 新建一个别的项目（进引导页选目录）；否则是要复用的项目所属脚本的 id */
const selectedMfwChoice = ref<string>('new')
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
const isMfwStep = computed(() => currentStep.value === 'config' && isMfwFamily(selectedType.value))
// MFW 家族第二步按选中的类型卡片取特调：分节可被它替换（默认是 MaaFWSourceStep），后面跟它的插入点
const createFlavor = computed(() => resolveMaaFWFlavor(selectedType.value))
const createSections = useMaaFWSections(createFlavor, 'create', { source: MaaFWSourceStep })
const createSlotContext = computed<MaaFWCreateSlotContext>(() => ({
  type: createFlavor.value.type,
  selection: selectedMfwChoice.value,
}))
// 可复用的项目只列与入口同类型的，同一项目多个脚本并成一行
const mfwReuseChoices = computed(() => buildMfwReuseChoices(props.mfwSources, selectedType.value))
// 选中的源以当前列表为准：返回再进来时列表会重新拉，源可能已在运行（busy）或已被删，
// 残留的 id 不能直接拿去提交——那会先建出脚本再被后端拒绝，留下一个没项目的空脚本。
const selectedMfwReuse = computed(
  () =>
    mfwReuseChoices.value.find(
      choice => choice.scriptId === selectedMfwChoice.value && !choice.busy
    ) ?? null
)
watch(mfwReuseChoices, () => {
  if (selectedMfwChoice.value !== 'new' && !selectedMfwReuse.value) {
    selectedMfwChoice.value = 'new'
  }
})
const nextDisabled = computed(() => {
  if (props.submitting) return true
  if (isMfwStep.value) {
    return selectedMfwChoice.value !== 'new' && (props.mfwSourcesLoading || !selectedMfwReuse.value)
  }
  if (currentStep.value === 'config' && configView.value === 'templates') {
    return !selectedTemplateUrl.value
  }
  return false
})
const primaryButtonText = computed(() => {
  if (currentStep.value === 'type') {
    return steps.value.length > 1
      ? t('scripts.create.next')
      : t('scripts.create.createAndConfigure')
  }
  if (isMfwStep.value) {
    return selectedMfwChoice.value !== 'new'
      ? t('scripts.create.createAndReuse')
      : t('scripts.create.createAndConfigure')
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
  currentStep.value = 'type'
  selectedType.value = 'MAA'
  selectedConfigMode.value = 'template'
  selectedTemplateUrl.value = null
  configView.value = 'choice'
  selectedMfwChoice.value = 'new'
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
    if (steps.value.length > 1) {
      currentStep.value = 'config'
      if (isMfwFamily(selectedType.value)) {
        emit('request-mfw-sources')
        // 特调替换的分节与插入点按需加载：进这一步时预取（从不往外抛）
        void prepareMaaFWFlavorPage(createFlavor.value, 'create')
      }
    } else {
      submitCurrentSelection()
    }
    return
  }
  if (isMfwStep.value) {
    submitCurrentSelection()
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
    mfwSourceMode: selectedMfwChoice.value === 'new' ? 'new' : 'reuse',
    mfwSourceScriptId: selectedMfwReuse.value?.scriptId ?? null,
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

const parseMarkdown = (text: string) => md.render(text || t('scripts.noDescription'))

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

.entity-row.disabled {
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

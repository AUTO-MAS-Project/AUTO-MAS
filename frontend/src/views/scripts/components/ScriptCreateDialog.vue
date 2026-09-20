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

        <!-- MFW 家族第二步：项目从哪来。已导入过的项目直接列出来复用（从那个脚本的副本克隆，
             运行时与模型共用、不另占空间，来源目录删了也能建）；只列与入口同类型的项目——
             选了 M9A 入口就只能复用 M9A 项目。第一行永远是「新建一个别的项目」 -->
        <template v-else-if="currentStep === 'config' && isMfwFamily(selectedType)">
          <StepHeading
            :title="t('scripts.create.mfwSourceHeading')"
            :description="t('scripts.create.mfwSourceHeadingDesc')"
          />
          <a-radio-group v-model:value="selectedMfwChoice" class="choice-list">
            <label :class="['choice-row', { selected: selectedMfwChoice === 'new' }]">
              <a-radio value="new" />
              <span class="choice-icon"><FolderOpenOutlined /></span>
              <span class="choice-copy">
                <span class="choice-title">{{ t('scripts.create.mfwNewProject') }}</span>
                <span class="choice-description">{{ t('scripts.create.mfwNewProjectDesc') }}</span>
              </span>
            </label>
            <div class="choice-group-heading">
              <span class="choice-group-title">{{ t('scripts.create.mfwReuse') }}</span>
              <span class="choice-group-description">{{ t('scripts.create.mfwReuseDesc') }}</span>
            </div>
            <a-alert
              v-if="mfwSourcesError"
              type="error"
              show-icon
              :message="mfwSourcesError"
              class="template-alert"
            >
              <template #action>
                <a-button size="small" @click="emit('request-mfw-sources')">{{
                  t('scripts.create.retry')
                }}</a-button>
              </template>
            </a-alert>
            <div v-if="mfwSourcesLoading" class="choice-placeholder">
              <a-spin size="small" />
              <span>{{ t('scripts.create.mfwReuseLoading') }}</span>
            </div>
            <template v-else-if="mfwReuseChoices.length">
              <label
                v-for="choice in mfwReuseChoices"
                :key="choice.scriptId"
                :class="[
                  'choice-row',
                  { selected: selectedMfwChoice === choice.scriptId, disabled: choice.busy },
                ]"
              >
                <a-radio :value="choice.scriptId" :disabled="choice.busy" />
                <span class="choice-icon"><CopyOutlined /></span>
                <span class="choice-copy">
                  <span class="choice-title">{{ mfwReuseTitle(choice) }}</span>
                  <span class="choice-description">{{ mfwReuseMeta(choice) }}</span>
                </span>
              </label>
            </template>
            <div v-else-if="!mfwSourcesError" class="choice-placeholder">
              {{ t('scripts.create.mfwReuseEmpty', { type: selectedType }) }}
            </div>
          </a-radio-group>
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
  CopyOutlined,
  DatabaseOutlined,
  FolderOpenOutlined,
  SearchOutlined,
  SettingOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import MarkdownIt from 'markdown-it'
import type { ScriptType } from '@/types/script'
import type { WebConfigTemplate } from '@/composables/useTemplateApi'
import type { MaaFWEmbeddedSourceItem } from '@/api'
import { openExternalUrl } from '@/utils/openExternal'
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
  type MfwReuseChoice,
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
  /** 有健康副本的 MFW / M9A 脚本：MFW 家族第二步「复用已有脚本的项目」的候选 */
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

// 标题是项目名（interface 读不出就用脚本名）；副标题「来自脚本「x」 · 版本」，
// 持有该项目的脚本都在跑时标一句「运行中」，那一行本身已禁用
const mfwReuseTitle = (choice: MfwReuseChoice) =>
  choice.projectName || choice.scriptName || choice.scriptId.slice(0, 8)
const mfwReuseMeta = (choice: MfwReuseChoice) => {
  const name = choice.scriptName || choice.scriptId.slice(0, 8)
  const from =
    choice.scriptCount > 1
      ? t('scripts.create.mfwReuseFromMany', { name, count: choice.scriptCount })
      : t('scripts.create.mfwReuseFrom', { name })
  const parts = [from, choice.version]
  if (choice.busy) parts.push(t('scripts.create.mfwReuseBusy'))
  return parts.filter(Boolean).join(' · ')
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
      if (isMfwFamily(selectedType.value)) emit('request-mfw-sources')
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

.choice-row.disabled,
.entity-row.disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.choice-group-heading {
  display: flex;
  flex-direction: column;
  gap: 2px;
  margin-top: 10px;
  padding: 0 2px;
}

.choice-group-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
}

.choice-group-description {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
}

.choice-placeholder {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 14px;
  border: 1px dashed var(--ant-color-border);
  border-radius: 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
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

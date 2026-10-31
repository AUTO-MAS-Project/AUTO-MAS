<template>
  <a-modal
    :open="open"
    :width="960"
    :closable="!submitting"
    :keyboard="!submitting"
    :mask-closable="!submitting"
    :confirm-loading="submitting"
    :z-index="900"
    :body-style="{ height: '500px', minHeight: 0, overflowY: 'auto' }"
    class="script-create-dialog"
    :title="t('core.scripts.create.title')"
    @cancel="handleCancel"
  >
    <div class="create-layout">
      <section class="step-content">
        <template v-if="currentStep === 'type'">
          <StepHeading
            :title="t('core.scripts.create.typeHeading')"
            :description="t('core.scripts.create.typeHeadingDesc')"
          />
          <div class="list-toolbar single">
            <a-input
              v-model:value="typeKeyword"
              allow-clear
              :placeholder="t('core.scripts.create.typeSearch')"
            >
              <template #prefix><SearchOutlined /></template>
            </a-input>
          </div>
          <SelectableOptionList v-if="filteredTypes.length" v-model="selectedType">
            <section v-if="typeSections.general.length" class="type-section">
              <div class="type-section-heading">
                <span class="type-section-title">{{ t('core.scripts.create.groupGeneral') }}</span>
              </div>
              <div class="type-grid">
                <SelectableOptionCard
                  v-for="option in typeSections.general"
                  :key="option.value"
                  :value="option.value"
                  :title="option.title"
                  :description="option.description"
                  :selected="selectedType === option.value"
                  radio-position="end"
                >
                  <template #icon>
                    <img :src="option.icon" :alt="option.title" class="selectable-option-image" />
                  </template>
                </SelectableOptionCard>
              </div>
            </section>
            <section
              v-if="typeSections.specialized.length"
              class="type-section specialized-section"
            >
              <div class="type-section-heading">
                <span class="type-section-title">{{
                  t('core.scripts.create.groupSpecialized')
                }}</span>
              </div>
              <div class="type-grid">
                <SelectableOptionCard
                  v-for="option in typeSections.specialized"
                  :key="option.value"
                  :value="option.value"
                  :title="option.title"
                  :description="option.description"
                  :selected="selectedType === option.value"
                  radio-position="end"
                >
                  <template #icon>
                    <img :src="option.icon" :alt="option.title" class="selectable-option-image" />
                  </template>
                </SelectableOptionCard>
              </div>
            </section>
          </SelectableOptionList>
          <NoData v-else :description="t('core.scripts.create.noTypeMatch')">
            <a-button @click="clearTypeFilters">{{ t('core.scripts.clearSearch') }}</a-button>
          </NoData>
        </template>

        <!-- MFW 家族第二步：项目从哪来（新建一个别的项目 / 复用已导入的同类型项目）。
             选项列表是可由特调替换的分节 create.source，选中状态留在这里；
             之后是特调的插入点 create.afterSourceStep -->
        <template v-else-if="currentStep === 'config' && isMfwFamily(selectedType)">
          <StepHeading
            :title="t('core.scripts.create.mfwSourceHeading')"
            :description="t('core.scripts.create.mfwSourceHeadingDesc')"
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
              :title="t('core.scripts.create.sourceHeading')"
              :description="t('core.scripts.create.sourceHeadingDesc')"
            />
            <SelectableOptionList v-model="selectedConfigMode">
              <SelectableOptionCard
                value="template"
                :title="t('core.scripts.create.fromTemplate')"
                :description="t('core.scripts.create.fromTemplateDesc')"
                :selected="selectedConfigMode === 'template'"
              >
                <template #icon>
                  <span class="selectable-option-icon"><DatabaseOutlined /></span>
                </template>
              </SelectableOptionCard>
              <SelectableOptionCard
                value="custom"
                :title="t('core.scripts.create.custom')"
                :description="t('core.scripts.create.customDesc')"
                :selected="selectedConfigMode === 'custom'"
              >
                <template #icon>
                  <span class="selectable-option-icon"><SettingOutlined /></span>
                </template>
              </SelectableOptionCard>
            </SelectableOptionList>
          </template>

          <template v-else>
            <StepHeading
              :title="t('core.scripts.create.templateHeading')"
              :description="t('core.scripts.create.templateHeadingDesc')"
            />
            <div class="list-toolbar single">
              <a-input
                v-model:value="templateKeyword"
                allow-clear
                :placeholder="t('core.scripts.create.templateSearch')"
                @update:value="scheduleTemplateSearch"
                @press-enter="requestTemplates(1)"
              >
                <template #prefix><SearchOutlined /></template>
              </a-input>
              <a-button :loading="templateLoading" @click="requestTemplates(templatePage)">{{
                t('core.scripts.create.reload')
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
                  t('core.scripts.create.retry')
                }}</a-button>
              </template>
            </a-alert>
            <div v-if="templateLoading" class="template-loading-state">
              <a-spin size="large" :tip="t('core.scripts.create.templateLoading')" />
            </div>
            <template v-else-if="templates.length">
              <SelectableOptionList v-model="selectedTemplateKey">
                <SelectableOptionCard
                  v-for="template in templates"
                  :key="template.configKey"
                  :value="template.configKey"
                  :title="template.displayName"
                  :selected="selectedTemplateKey === template.configKey"
                  align="start"
                  radio-position="end"
                >
                  <template #meta>
                    <span class="template-meta">
                      <span
                        ><UserOutlined />
                        {{
                          template.ownerUsername || t('core.scripts.template.unknownAuthor')
                        }}</span
                      >
                      <span
                        ><ClockCircleOutlined /> {{ formatPublishedAt(template.publishedAt) }}</span
                      >
                    </span>
                  </template>
                  <template #description>
                    <span class="template-description">{{
                      template.description || t('core.scripts.noDescription')
                    }}</span>
                  </template>
                </SelectableOptionCard>
              </SelectableOptionList>
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
            <NoData
              v-else
              :description="
                templateKeyword
                  ? t('core.scripts.create.noTemplateMatch')
                  : t('core.scripts.create.noTemplates')
              "
            >
              <a-button v-if="templateKeyword" @click="clearTemplateKeyword">{{
                t('core.scripts.clearSearch')
              }}</a-button>
              <a-button v-else @click="chooseCustomConfig">{{
                t('core.scripts.create.switchToCustom')
              }}</a-button>
            </NoData>
          </template>
        </template>

        <template v-else>
          <StepHeading
            :title="t('core.scripts.create.confirmHeading')"
            :description="t('core.scripts.create.confirmHeadingDesc')"
          />
          <a-descriptions bordered :column="1" class="confirm-summary">
            <a-descriptions-item :label="t('core.scripts.create.labelMode')">
              {{ t('core.scripts.create.modeNew') }}
            </a-descriptions-item>
            <a-descriptions-item :label="t('core.scripts.create.labelType')">
              {{ t(getTypeOption(selectedType).titleKey) }}
            </a-descriptions-item>
            <a-descriptions-item
              v-if="selectedType === 'General'"
              :label="t('core.scripts.create.labelSource')"
            >
              {{
                selectedConfigMode === 'custom'
                  ? t('core.scripts.create.custom')
                  : t('core.scripts.create.sourceTemplate', { name: selectedTemplate?.displayName })
              }}
            </a-descriptions-item>
          </a-descriptions>
        </template>
      </section>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <a-button :disabled="!canGoBack || submitting" @click="handleBack">
          <template #icon><ArrowLeftOutlined /></template>
          {{ t('core.scripts.create.back') }}
        </a-button>
        <a-space>
          <a-button :disabled="submitting" @click="handleCancel">{{
            t('core.common.cancel')
          }}</a-button>
          <a-button
            type="primary"
            :loading="submitting"
            :disabled="nextDisabled"
            @click="handleNext"
          >
            {{ primaryButtonText }}
          </a-button>
        </a-space>
      </div>
    </template>
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
import type { MaaFWEmbeddedSourceItem } from '@/api'
import {
  prepareMaaFWFlavorPage,
  resolveMaaFWFlavor,
  useMaaFWSections,
  type MaaFWCreateSlotContext,
} from '@/composables/useMaaFWFlavor'
import MaaFWFlavorSlot from '@/views/EditView/MaaFWFlavor/MaaFWFlavorSlot.vue'
import { openExternalUrl } from '@/utils/openExternal'
import SelectableOptionCard from '@/components/SelectableOptionCard.vue'
import SelectableOptionList from '@/components/SelectableOptionList.vue'
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
  /** 有健康副本的 MFW 家族脚本：MFW 家族第二步「复用已有脚本的项目」的候选（按类型筛在这里做） */
  mfwSources: MaaFWEmbeddedSourceItem[]
  mfwSourcesLoading: boolean
  /** 候选列表没读出来时的原因；有值就显示错误条 + 重试，而不是把它当成「没有可复用的脚本」 */
  mfwSourcesError: string | null
}>()

const emit = defineEmits<{
  'update:open': [open: boolean]
  'request-templates': [query: TemplateRequest]
  'request-mfw-sources': []
  submit: [request: ScriptCreateRequest]
}>()

// 关键字输入后的静默期，避免每敲一个字就打一次配置中心
const TEMPLATE_SEARCH_DEBOUNCE = 400

const currentStep = ref<CreateStepKey>('type')
const selectedType = ref<ScriptType>('MAA')
const selectedConfigMode = ref<ConfigMode>('template')
const selectedTemplateKey = ref<string | null>(null)
const configView = ref<'choice' | 'templates'>('choice')
/** 'new' = 新建一个别的项目（进引导页选目录）；否则是要复用的项目所属脚本的 id */
const selectedMfwChoice = ref<string>('new')
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
    return !selectedTemplateKey.value
  }
  return false
})
const primaryButtonText = computed(() => {
  if (currentStep.value === 'type') {
    return steps.value.length > 1
      ? t('core.scripts.create.next')
      : t('core.scripts.create.createAndConfigure')
  }
  if (isMfwStep.value) {
    return selectedMfwChoice.value !== 'new'
      ? t('core.scripts.create.createAndReuse')
      : t('core.scripts.create.createAndConfigure')
  }
  if (currentStep.value === 'config' && selectedConfigMode.value === 'custom') {
    return t('core.scripts.create.createAndConfigure')
  }
  if (currentStep.value === 'config' && configView.value === 'templates') {
    return t('core.scripts.create.createFromTemplate')
  }
  return t('core.scripts.create.next')
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
  selectedMfwChoice.value = 'new'
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
  publishedAt ? formatBackendDateTime(publishedAt) : t('core.scripts.template.unknownTime')

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
</script>

<style scoped>
:global(.script-create-dialog) {
  top: 64px;
  padding-bottom: 16px;
}

:global(.script-create-dialog .ant-modal-content) {
  display: flex;
  flex-direction: column;
  max-height: calc(100vh - 128px);
  overflow: hidden;
}

.step-content {
  min-width: 0;
  padding: 16px 4px;
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

.ellipsis {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
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

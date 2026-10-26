<template>
  <div class="copilot-planner">
    <a-alert v-if="!bound" :message="t('maaCopilot.bindHint')" type="warning" show-icon />
    <section class="planner-setup" :aria-label="t('maaCopilot.scope')">
      <div v-if="result" class="result-context">
        <span>{{
          t('maaCopilot.analysisContext', {
            scope: scopeOptions.find(option => option.value === source)?.label,
            coverage,
          })
        }}</span>
        <a-button type="text" size="small" @click="showAnalysisSettings = !showAnalysisSettings">
          <template #icon><SettingOutlined aria-hidden="true" /></template>
          {{
            t(showAnalysisSettings ? 'maaCopilot.collapseSettings' : 'maaCopilot.adjustSettings')
          }}
        </a-button>
      </div>
      <div v-show="!result || showAnalysisSettings" class="scope-heading">
        <div>
          <h3>{{ t('maaCopilot.scope') }}</h3>
          <p>{{ t('maaCopilot.hint') }}</p>
        </div>
        <a-segmented v-model:value="source" :options="scopeOptions" :disabled="busy || disabled" />
      </div>
      <div v-if="source === 'author' && (!result || showAnalysisSettings)" class="source-query">
        <!-- 回车解析作者名 → 唯一命中直接定位（query 置为作者 ID，下方自动加载其作业）；
             多命中列在下面点选，零命中就地提示 -->
        <a-input-search
          v-model:value="authorKeyword"
          :placeholder="t('maaCopilot.authorHint')"
          :aria-label="t('maaCopilot.authorHint')"
          :loading="searching"
          :disabled="busy || disabled"
          @search="searchAuthors"
        />
      </div>
      <!-- 作业集/单个作业的链接输入：必须紧跟上面的 v-if 成链，避免漏进作者模式 -->
      <div v-else-if="source !== 'all' && (!result || showAnalysisSettings)" class="source-query">
        <a-input
          v-model:value="query"
          :placeholder="t('maaCopilot.linkHint')"
          :aria-label="t(source === 'set' ? 'maaCopilot.set' : 'maaCopilot.copilot')"
          :disabled="busy || disabled"
        />
      </div>
      <div
        v-if="source === 'author' && (!result || showAnalysisSettings) && authorCandidates.length"
        class="author-candidates"
      >
        <span class="author-candidates-label">
          {{ t('maaCopilot.authorCandidates', { count: authorCandidates.length }) }}
        </span>
        <a-button
          v-for="author in authorCandidates"
          :key="author.value"
          size="small"
          :disabled="busy || disabled"
          @click="selectAuthor(author)"
        >
          {{ author.label }}
        </a-button>
      </div>
      <div
        v-if="source === 'author' && (!result || showAnalysisSettings) && authorNone"
        class="author-none"
      >
        {{ t('maaCopilot.noAuthors') }}
      </div>
      <CopilotSourceStatus
        :state="sourceState"
        :source="source"
        :compact="!!result && !showAnalysisSettings"
        :disabled="busy || disabled || !validSource"
        @sync="syncSource"
      />
      <div v-show="!result || showAnalysisSettings" class="analyze-actions">
        <a-space wrap>
          <span>{{ t('maaCopilot.coverage') }}</span>
          <a-select
            v-model:value="coverage"
            :options="coverageOptions"
            :aria-label="t('maaCopilot.coverage')"
            :disabled="busy || disabled"
          />
          <a-checkbox v-model:checked="requireModules" :disabled="busy || disabled">{{
            t('maaCopilot.modules')
          }}</a-checkbox>
        </a-space>
        <a-button
          :type="result ? 'default' : 'primary'"
          :loading="busy"
          :disabled="disabled || !bound || !sourceState?.available || sourceState?.running"
          @click="analyze"
        >
          <template #icon><SearchOutlined aria-hidden="true" /></template>
          {{ t('maaCopilot.analyze') }}
        </a-button>
      </div>
    </section>
    <a-alert v-if="error" :message="error" type="error" show-icon />
    <div v-if="busy" class="analysis-loading">
      <a-spin /><span>{{ t('maaCopilot.analyzing') }}</span>
    </div>
    <CopilotAnalysisResults
      v-if="result"
      :result="result"
      :catalog="catalog"
      :coverage="coverage"
      :disabled="disabled || busy"
      :importing="importing"
      @import="importPlans"
    />
    <div v-else-if="!busy" class="analysis-placeholder">
      <SolutionOutlined aria-hidden="true" />
      <h3>{{ t('maaCopilot.emptyTitle') }}</h3>
      <p>{{ t('maaCopilot.empty') }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, shallowRef, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { SearchOutlined, SettingOutlined, SolutionOutlined } from '@ant-design/icons-vue'
import type { MaaCopilotAnalyzeOut, MaaCopilotOperator, MaaCopilotSourceOut } from '@/api'
import { useMaaCopilotApi } from '@/composables/useMaaCopilotApi'
import CopilotAnalysisResults from './CopilotAnalysisResults.vue'
import CopilotSourceStatus from './CopilotSourceStatus.vue'
import { MaaCopilotSourceIn } from '@/api'
import type { CultivateImportResult, CultivateOperatorCatalogEntry } from './cultivateTargets'

const props = defineProps<{
  disabled: boolean
  bound: boolean
  bindingKey: string
  catalog: CultivateOperatorCatalogEntry[]
  prepareAnalysis: () => Promise<void>
  importTargets: (
    content: string,
    format?: 'clipboard' | 'targets'
  ) => Promise<CultivateImportResult>
}>()
const emit = defineEmits<{ imported: [operatorIds: string[]]; busy: [value: boolean] }>()
const route = useRoute()
const { t } = useI18n()
const api = useMaaCopilotApi()
const source = ref<NonNullable<MaaCopilotSourceIn['source']>>(MaaCopilotSourceIn.source.ALL)
const query = ref('')
// 作者搜索：输入框只持有关键词；query 承载解析后的作者 ID（后端按 uploaderId 取作业）
const authorKeyword = ref('')
const authorCandidates = ref<Array<{ label: string; value: string }>>([])
const authorNone = ref(false)
const searching = ref(false)
const sourceState = shallowRef<MaaCopilotSourceOut | null>(null)
const result = shallowRef<MaaCopilotAnalyzeOut | null>(null)
const showAnalysisSettings = ref(false)
const coverage = ref(90)
const requireModules = ref(true)
const busy = ref(false)
const importing = ref(false)
const error = ref('')
let generation = 0
let searchGeneration = 0
let pollTimer: ReturnType<typeof setTimeout> | undefined
const scopeOptions = computed(() =>
  ['all', 'author', 'set', 'copilot'].map(value => ({
    value,
    label: t(`maaCopilot.scopes.${value}`),
  }))
)
const coverageOptions = [50, 75, 90, 95, 100].map(value => ({ value, label: `${value}%` }))
const validSource = computed(() => source.value === 'all' || !!query.value.trim())
const invalidate = () => {
  generation++
  clearTimeout(pollTimer)
  sourceState.value = null
  result.value = null
  busy.value = false
  error.value = ''
}
// 作者 query 只在点选/唯一命中时离散赋值，变更即自动加载其作业；
// set/copilot 是逐字符输入的 query，不自动加载，仍由下方按钮触发
watch([source, query], () => {
  invalidate()
  if (source.value === 'author' && validSource.value) void syncSource(false)
})
watch(
  () => props.bindingKey,
  () => {
    invalidate()
    if (validSource.value) void syncSource(false)
  }
)
watch([coverage, requireModules], () => {
  result.value = null
})
// 范围或关键词变化后，旧搜索响应不再有权更新作者或作业查询。
watch(
  [source, authorKeyword],
  () => {
    searchGeneration++
    searching.value = false
    authorCandidates.value = []
    authorNone.value = false
  },
  { flush: 'sync' }
)
onScopeDispose(() => {
  generation++
  searchGeneration++
  clearTimeout(pollTimer)
})

const syncSource = async (refresh: boolean) => {
  const version = ++generation
  clearTimeout(pollTimer)
  error.value = ''
  result.value = null
  if (sourceState.value) sourceState.value = { ...sourceState.value, running: true }
  const request = { source: source.value, query: query.value }
  const poll = async (action: NonNullable<MaaCopilotSourceIn['action']>) => {
    try {
      const state = await api.loadSource({ ...request, action })
      if (version !== generation) return
      sourceState.value = state
      if (state.running)
        pollTimer = setTimeout(() => void poll(MaaCopilotSourceIn.action.STATUS), 1500)
    } catch (e) {
      if (version === generation) {
        if (sourceState.value) sourceState.value = { ...sourceState.value, running: false }
        error.value = e instanceof Error ? e.message : t('maaCopilot.failed')
      }
    }
  }
  await poll(refresh ? MaaCopilotSourceIn.action.REFRESH : MaaCopilotSourceIn.action.LOAD)
}
// 回车/按钮触发解析（接口慢，不做输入防抖）；代次守卫防连续回车的乱序覆盖
const searchAuthors = async () => {
  const keyword = authorKeyword.value.trim()
  if (!keyword) return
  authorCandidates.value = []
  authorNone.value = false
  const version = ++searchGeneration
  const isCurrentSearch = () =>
    version === searchGeneration &&
    source.value === 'author' &&
    authorKeyword.value.trim() === keyword
  searching.value = true
  try {
    const response = await api.searchAuthors(keyword)
    if (!isCurrentSearch()) return
    const matched = (response.data ?? []).flatMap(item =>
      item.value ? [{ label: item.label, value: item.value }] : []
    )
    // 唯一命中直接定位：query 置为作者 ID 触发下方自动加载其作业
    if (matched.length === 1) selectAuthor(matched[0])
    else if (matched.length > 1) authorCandidates.value = matched
    else authorNone.value = true
  } catch (e) {
    if (isCurrentSearch()) error.value = e instanceof Error ? e.message : t('maaCopilot.failed')
  } finally {
    if (version === searchGeneration) searching.value = false
  }
}
const selectAuthor = (author: { label: string; value: string }) => {
  authorKeyword.value = author.label
  query.value = author.value
  authorCandidates.value = []
}
const analyze = async () => {
  if (
    busy.value ||
    props.disabled ||
    !props.bound ||
    !sourceState.value?.available ||
    sourceState.value.running
  )
    return
  const version = generation
  const bindingKey = props.bindingKey
  busy.value = true
  error.value = ''
  result.value = null
  try {
    // 绑定先在表单回显，须等原有保存队列完成后再读取该角色。
    await props.prepareAnalysis()
    if (version !== generation) return
    const response = await api.analyze({
      scriptId: String(route.params.scriptId),
      userId: String(route.params.userId),
      bindingKey,
      source: source.value,
      query: query.value,
      coverage: coverage.value,
      requireModules: requireModules.value,
    })
    if (version !== generation) return
    if (response.bindingKey !== bindingKey || bindingKey !== props.bindingKey)
      throw new Error(t('maaCopilot.roleChanged'))
    if (sourceState.value?.running || response.updatedAt !== sourceState.value?.updatedAt)
      throw new Error(t('maaCopilot.sourceChanged'))
    result.value = response
    showAnalysisSettings.value = false
  } catch (e) {
    if (version === generation)
      error.value = e instanceof Error ? e.message : t('maaCopilot.failed')
  } finally {
    if (version === generation) busy.value = false
  }
}
const importPlans = async (plans: MaaCopilotOperator[] = []) => {
  if (
    importing.value ||
    busy.value ||
    props.disabled ||
    !plans.length ||
    result.value?.bindingKey !== props.bindingKey ||
    sourceState.value?.running ||
    result.value?.updatedAt !== sourceState.value?.updatedAt
  )
    return
  importing.value = true
  emit('busy', true)
  try {
    const content = JSON.stringify(
      plans.map(op => ({ operator_id: op.operatorId, goals: op.goals }))
    )
    const imported = await props.importTargets(content, 'targets')
    message.success(
      t('edit.maaCultivateImportSuccess', { added: imported.added, updated: imported.updated })
    )
    emit('imported', imported.operatorIds)
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('maaCopilot.failed'))
  } finally {
    importing.value = false
    emit('busy', false)
  }
}
onMounted(() => void syncSource(false))
</script>

<style scoped>
.copilot-planner {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.scope-heading,
.analyze-actions,
.result-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
}
.result-context {
  margin-bottom: 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
.scope-heading {
  margin: 4px 0 20px;
}
.scope-heading h3 {
  margin: 0 0 4px;
  font-size: 16px;
  font-weight: 600;
}
.scope-heading p,
.analysis-placeholder p {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}
.source-query {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}
.source-query > * {
  flex: 1;
  min-width: 200px;
}
/* 多命中候选/零命中提示：上提贴近输入框，视觉上同属一次搜索 */
.author-candidates {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin: -8px 0 16px;
}

.author-candidates-label {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.author-none {
  margin: -8px 0 16px;
  font-size: 13px;
  color: var(--ant-color-text-tertiary);
}
.analyze-actions {
  padding: 20px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}
.analysis-loading {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 12px;
  min-height: 160px;
}
.analysis-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 180px;
  gap: 8px;
  text-align: center;
}
.analysis-placeholder > .anticon {
  color: var(--ant-color-text-quaternary);
  font-size: 28px;
}
.analysis-placeholder h3 {
  margin: 0;
  color: var(--ant-color-text-secondary);
  font-size: 14px;
  font-weight: 500;
}
</style>

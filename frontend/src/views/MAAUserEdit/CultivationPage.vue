<template>
  <div class="cultivation-page">
    <!-- 页头：面包屑 + 标题 -->
    <header class="cultivation-header">
      <div class="cultivation-header-main">
        <a-breadcrumb class="cultivation-breadcrumb">
          <a-breadcrumb-item>
            <router-link to="/scripts">{{ t('edit.scripts') }}</router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>
            <router-link :to="{ name: 'MAAUserEdit', params: { scriptId, userId } }">
              {{ formData?.Info?.Name || scriptName }}
            </router-link>
          </a-breadcrumb-item>
          <a-breadcrumb-item>{{ t('maaCopilot.pageTitle') }}</a-breadcrumb-item>
        </a-breadcrumb>
        <h1 class="page-title">{{ t('maaCopilot.pageTitle') }}</h1>
        <p class="cultivation-desc">{{ t('maaCopilot.saveHint') }}</p>
      </div>
      <a-button class="cultivation-back" size="large" :loading="leavingPage" @click="emit('back')">
        <template #icon><ArrowLeftOutlined aria-hidden="true" /></template>
        {{ t('edit.back') }}
      </a-button>
    </header>

    <ConfigLockPanel :script-id="scriptId" content-class="cultivation-body">
      <!-- 后端运行提示（养成暂停/降级等原因说明） -->
      <a-alert
        v-if="formData?.Data?.CultivateNotice"
        class="cultivation-notice"
        :message="formData.Data.CultivateNotice"
        type="warning"
        show-icon
      />

      <!-- 总览：启停/绑定/执行设置 + 关键数字 -->
      <CultivationOverview
        :form-data="formData"
        :loading="loading"
        :editor-busy="editorBusy"
        :enabled="cultivationEnabled"
        :skland-bound="sklandBound"
        :skland-bound-composite="sklandBoundComposite"
        :skland-role-options="sklandRoleOptions"
        :skland-role-loading="sklandRoleLoading"
        :skland-role-error="sklandRoleError"
        :load-skland-role-options="loadSklandRoleOptions"
        :cultivate-preview="cultivatePreview"
        @save="(key, value) => emit('save', key, value)"
      />

      <!-- 内容卡：培养目标 / 作业规划 -->
      <section class="cultivation-content" :inert="editorBusy">
        <a-tabs v-model:active-key="activeTab" type="card" class="cultivation-tabs">
          <a-tab-pane key="targets" :tab="t('maaCopilot.targetsTab')">
            <!-- tab-content 类承接页面的标签页内容内边距（与游戏社区/设置页同款） -->
            <CultivateTargetEditor
              ref="editorRef"
              class="tab-content"
              :form-data="formData"
              :loading="loading || copilotImporting"
              :operator-catalog="operatorCatalog"
              :operator-options-loading="operatorOptionsLoading"
              :operator-options-error="operatorOptionsError"
              :skland-bound="sklandBound"
              :item-options="itemOptions"
              :cultivate-preview="cultivatePreview"
              :cultivate-preview-loading="cultivatePreviewLoading"
              :cultivate-preview-error="cultivatePreviewError"
              :load-cultivate-preview="loadCultivatePreview"
              :import-cultivate-targets="importCultivateTargets"
              @save="(key, value) => emit('save', key, value)"
              @busy="clipboardImporting = $event"
            />
          </a-tab-pane>
          <a-tab-pane key="copilot" :tab="t('maaCopilot.analysisTab')">
            <CopilotCultivatePlanner
              class="tab-content"
              :disabled="loading || clipboardImporting"
              :bound="sklandBound"
              :binding-key="sklandBoundComposite ?? ''"
              :catalog="operatorCatalog"
              :import-targets="importCultivateTargets"
              :prepare-analysis="prepareCopilotAnalysis"
              @imported="handleCopilotImported"
              @busy="copilotImporting = $event"
            />
          </a-tab-pane>
        </a-tabs>
      </section>
    </ConfigLockPanel>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowLeftOutlined } from '@ant-design/icons-vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import type { CultivatePreviewOut } from '@/api'
import CultivationOverview from './CultivationOverview.vue'
import CultivateTargetEditor from './CultivateTargetEditor.vue'
import CopilotCultivatePlanner from './CopilotCultivatePlanner.vue'
import type { CultivateImportResult, CultivateOperatorCatalogEntry } from './cultivateTargets'

type SelectOption = { label: string; value: string }

const props = defineProps<{
  scriptId: string
  userId: string
  scriptName: string
  formData: any
  loading: boolean
  leavingPage: boolean
  editorBusy: boolean
  /** 干员目录（一图流全量表，含技能/模组名称目录；[] 表示已加载但为空） */
  operatorCatalog: CultivateOperatorCatalogEntry[]
  operatorOptionsLoading: boolean
  operatorOptionsError: string
  /** 森空岛绑定下拉：合并所有已配置凭据账号组的角色（决策 37/38） */
  sklandRoleOptions: SelectOption[]
  sklandRoleLoading: boolean
  sklandRoleError: string
  /** 按需加载角色列表（下拉首次展开时触发） */
  loadSklandRoleOptions: () => Promise<void>
  /** 物品目录（MAA item_index，供预览材料名显示） */
  itemOptions: SelectOption[]
  /** 养成需求预览（后端纯计算结果） */
  cultivatePreview: CultivatePreviewOut | null
  cultivatePreviewLoading: boolean
  cultivatePreviewError: string
  loadCultivatePreview: (targetsJson: string) => Promise<void>
  importCultivateTargets: (
    content: string,
    format?: 'clipboard' | 'targets'
  ) => Promise<CultivateImportResult>
  prepareCopilotAnalysis: () => Promise<void>
}>()

const emit = defineEmits<{
  save: [key: string, value: unknown]
  back: []
}>()

const { t } = useI18n()

const cultivationEnabled = computed(() => props.formData?.Task?.IfCultivate ?? false)

// ── 标签页与导入联动 ──
const activeTab = ref('targets')
const editorRef = ref<InstanceType<typeof CultivateTargetEditor>>()
// 两类导入互斥共用 busy：剪贴板导入在编辑器内、作业导入在规划器内，
// 任一进行中都要冻结另一侧（保存队列串行，避免并发导入互相覆盖）
const clipboardImporting = ref(false)
const copilotImporting = ref(false)
const handleCopilotImported = (operatorIds: string[]) => {
  activeTab.value = 'targets'
  editorRef.value?.reveal(operatorIds)
}

// ── 森空岛绑定状态（编辑器与规划器按绑定口径只读/分析） ──
const sklandBound = computed(
  () => !!props.formData?.Task?.CultivateSklandAccount && !!props.formData?.Task?.CultivateSklandUid
)
// 选项 value 为 "账号组UUID|游戏uid" 复合值：选中即拆回两个字段保存
const sklandBoundComposite = computed(() => {
  const account = String(props.formData?.Task?.CultivateSklandAccount ?? '')
  const uid = String(props.formData?.Task?.CultivateSklandUid ?? '')
  return account && uid ? `${account}|${uid}` : undefined
})
</script>

<style scoped>
/* 页面骨架与游戏社区/设置页一致：页头 + 圆角内容卡 */
.cultivation-page {
  display: flex;
  flex-direction: column;
  width: 100%;
  min-height: 100%;
}

.cultivation-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-height: 0;
}

.cultivation-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  margin-bottom: 16px;
}

.cultivation-header-main {
  min-width: 0;
}

.cultivation-breadcrumb {
  margin-bottom: 8px;
}

.page-title {
  margin: 0;
  font-size: 28px;
  font-weight: 700;
  line-height: 1.3;
  color: var(--app-page-title-color, var(--ant-color-text));
}

.cultivation-desc {
  margin: 4px 0 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.cultivation-back {
  flex-shrink: 0;
}

.cultivation-notice {
  margin-bottom: 16px;
}

/* ── 内容卡与 card 标签页（与游戏社区/设置页同款） ── */
.cultivation-content {
  background: var(--ant-color-bg-container);
  border-radius: 8px;
  flex: 1;
}

.cultivation-tabs {
  margin: 0;
  padding: 12px;
}

/* 只作用于外层 card 标签栏（> 直接子），避免殃及面板内嵌套的小标签页 */
.cultivation-tabs > :deep(.ant-tabs-nav) {
  margin: 0;
  padding: 0;
}

/* sticky 侧栏依赖各层不裁剪溢出 */
.cultivation-tabs > :deep(.ant-tabs-content-holder) {
  overflow: visible;
}

/* card 样式自带 .ant-tabs-card > 限定，内嵌 line 型标签页不会命中 */
.cultivation-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
  margin-right: 8px;
  background: transparent;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
}

.cultivation-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

/* 标签页内容内边距（tab-content 挂在子组件根上，与游戏社区/设置页同款） */
.cultivation-tabs :deep(.tab-content) {
  padding: 24px;
  width: 100%;
}

@media (max-width: 768px) {
  .cultivation-header {
    flex-direction: column;
  }

  .cultivation-tabs {
    padding: 8px;
  }

  .cultivation-tabs :deep(.tab-content) {
    padding: 16px;
  }
}
</style>

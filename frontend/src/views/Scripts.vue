<template>
  <!-- MAA配置遮罩层 -->
  <div v-if="showMAAConfigMask" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: '#1890ff' }" />
      </div>
      <h2 class="mask-title">{{ t('scripts.mask.maaTitle') }}</h2>
      <p class="mask-description">
        {{ t('scripts.mask.maaDesc') }}
        <br />
        {{ t('scripts.mask.unlockTip') }}
      </p>
      <div class="mask-actions">
        <a-button
          v-if="currentConfigScript"
          type="primary"
          size="large"
          @click="handleSaveMAAConfig(currentConfigScript)"
        >
          {{ t('scripts.mask.saveConfig') }}
        </a-button>
      </div>
    </div>
  </div>

  <!-- SRC配置遮罩层 -->
  <div v-if="showSRCConfigMask" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: '#722ed1' }" />
      </div>
      <h2 class="mask-title">{{ t('scripts.mask.srcTitle') }}</h2>
      <p class="mask-description">
        {{ t('scripts.mask.srcDesc') }}
        <br />
        {{ t('scripts.mask.unlockTip') }}
      </p>
      <div class="mask-actions">
        <a-button
          v-if="currentConfigScript"
          type="primary"
          size="large"
          @click="handleSaveSRCConfig(currentConfigScript)"
        >
          {{ t('scripts.mask.saveConfig') }}
        </a-button>
      </div>
    </div>
  </div>

  <div v-if="showMaaEndConfigMask" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
      </div>
      <h2 class="mask-title">
        {{
          currentMaaEndConfigUser
            ? t('scripts.mask.maaEndUserTitle')
            : t('scripts.mask.maaEndScriptTitle')
        }}
      </h2>
      <p class="mask-description">
        {{
          currentMaaEndConfigUser
            ? t('scripts.mask.maaEndUserDesc', { name: currentMaaEndConfigUser.Info.Name })
            : t('scripts.mask.maaEndScriptDesc')
        }}
        <br />
        {{ t('scripts.mask.maaEndUnlockTip') }}
      </p>
      <div class="mask-actions">
        <a-button
          v-if="currentConfigScript"
          type="primary"
          size="large"
          @click="handleSaveMaaEndConfig(currentConfigScript)"
        >
          {{ t('scripts.mask.saveConfig') }}
        </a-button>
      </div>
    </div>
  </div>

  <div v-if="showOkwwConfigMask" class="maa-config-mask">
    <div class="mask-content">
      <div class="mask-icon">
        <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
      </div>
      <h2 class="mask-title">{{ t('scripts.mask.okwwTitle') }}</h2>
      <p class="mask-description">
        {{ t('scripts.mask.okwwDesc') }}
        <br />
        {{ t('scripts.mask.okwwUnlockTip') }}
      </p>
      <div class="mask-actions">
        <a-button
          v-if="currentConfigScript"
          type="primary"
          size="large"
          @click="handleSaveOkwwConfig(currentConfigScript)"
        >
          {{ t('scripts.mask.saveSettings') }}
        </a-button>
      </div>
    </div>
  </div>

  <!-- 主要内容 -->
  <div class="scripts-header">
    <div class="header-left">
      <h1 class="page-title">{{ t('scripts.title') }}</h1>
      <a
        class="doc-link"
        :href="MAS_DOC_URLS.scripts"
        target="_blank"
        rel="noreferrer"
        :aria-label="t('common.viewPageDocs')"
        @click="handleExternalLink"
      >
        <BookOutlined />
        {{ t('common.viewPageDocs') }}
        <ExportOutlined />
      </a>
      <a-input
        v-model:value="scriptSearchKeyword"
        allow-clear
        class="script-search"
        :placeholder="t('scripts.searchPlaceholder')"
        :aria-label="t('scripts.searchAria')"
      >
        <template #prefix><SearchOutlined /></template>
      </a-input>
    </div>
    <div class="header-actions">
      <a-space size="middle">
        <a-tooltip :title="t('scripts.collapseAllTip')">
          <a-button
            size="large"
            :disabled="scripts.length === 0 || isSearching"
            @click="handleCollapseAll"
          >
            <template #icon><UpOutlined /></template>
            {{ t('scripts.collapseAll') }}
          </a-button>
        </a-tooltip>
        <a-tooltip :title="t('scripts.expandAllTip')">
          <a-button
            size="large"
            :disabled="scripts.length === 0 || isSearching"
            @click="handleExpandAll"
          >
            <template #icon><DownOutlined /></template>
            {{ t('scripts.expandAll') }}
          </a-button>
        </a-tooltip>
        <a-button type="primary" size="large" class="link" @click="handleAddScript">
          <template #icon>
            <PlusOutlined />
          </template>
          {{ t('scripts.create.title') }}
        </a-button>
      </a-space>
    </div>
  </div>

  <!-- 空状态 -->
  <!-- 增加 loadedOnce 条件，避免初始渲染时闪烁 -->
  <div v-if="!addLoading && loadedOnce && scripts.length === 0" class="empty-state">
    <div class="empty-content">
      <div class="empty-image-container">
        <img src="@/assets/NoData.png" :alt="t('scripts.empty.alt')" class="empty-image" />
      </div>
      <div class="empty-text-content">
        <h3 class="empty-title">{{ t('scripts.empty.title') }}</h3>
        <p class="empty-description">{{ t('scripts.empty.desc') }}</p>
      </div>
    </div>
  </div>

  <div v-else-if="!addLoading && loadedOnce && filteredScripts.length === 0" class="empty-state">
    <a-empty :description="t('scripts.empty.noMatch')">
      <a-button @click="scriptSearchKeyword = ''">{{ t('scripts.clearSearch') }}</a-button>
    </a-empty>
  </div>

  <ScriptTable
    v-else
    ref="scriptTableRef"
    :scripts="filteredScripts"
    :searching="isSearching"
    :active-connections="activeConnections"
    :copying-script-id="copyingScriptId"
    :all-plans-data="allPlansData"
    @edit="handleEditScript"
    @copy="handleCopyScript"
    @delete="handleDeleteScript"
    @add-user="handleAddUser"
    @edit-user="handleEditUser"
    @delete-user="handleDeleteUser"
    @start-maa-config="handleStartMAAConfig"
    @save-maa-config="handleSaveMAAConfig"
    @start-src-config="handleStartSRCConfig"
    @save-src-config="handleSaveSRCConfig"
    @start-maa-end-config="handleStartMaaEndConfig"
    @start-maa-end-user-config="handleStartMaaEndUserConfig"
    @save-maa-end-config="handleSaveMaaEndConfig"
    @start-okww-config="handleStartOkwwConfig"
    @toggle-user-status="handleToggleUserStatus"
  />

  <ScriptCreateDialog
    v-model:open="scriptCreateVisible"
    :templates="templates"
    :submitting="addLoading || templateLoading"
    :template-loading="templateLoading"
    :template-error="templateError"
    @request-templates="loadTemplates"
    @submit="handleSubmitScriptCreate"
  />

  <!-- 创建方式选择弹窗 -->
  <a-modal
    v-model:open="createModeSelectVisible"
    :title="t('scripts.createMode.title')"
    :confirm-loading="addLoading"
    class="create-mode-modal"
    width="600px"
    :ok-text="t('common.confirm')"
    :cancel-text="t('common.cancel')"
    @ok="handleConfirmCreateMode"
    @cancel="createModeSelectVisible = false"
  >
    <div class="mode-selection">
      <a-radio-group v-model:value="selectedCreateMode" class="mode-radio-group">
        <a-radio-button value="copy" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <FileTextOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">{{ t('scripts.createMode.copyTitle') }}</div>
              <div class="mode-description">{{ t('scripts.createMode.copyDesc') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="new" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <PlusOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">{{ t('scripts.createMode.newTitle') }}</div>
              <div class="mode-description">{{ t('scripts.createMode.newDesc') }}</div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>

  <!-- 脚本选择弹窗 -->
  <a-modal
    v-model:open="scriptSelectVisible"
    :title="t('scripts.copy.title')"
    :confirm-loading="addLoading"
    class="script-select-modal"
    width="800px"
    :ok-text="t('scripts.copy.ok')"
    :cancel-text="t('common.back')"
    :ok-button-props="{ disabled: !selectedScriptId }"
    @ok="handleConfirmScriptSelect"
    @cancel="
      () => {
        scriptSelectVisible = false
        createModeSelectVisible = true
      }
    "
  >
    <div class="script-selection">
      <div v-if="scripts.length === 0" class="no-scripts">
        <p>{{ t('scripts.copy.empty') }}</p>
      </div>
      <div v-else class="scripts-list">
        <div
          v-for="script in scripts"
          :key="script.id"
          :class="['script-item', { selected: selectedScriptId === script.id }]"
          @click="selectedScriptId = script.id"
        >
          <div class="script-item-content">
            <div class="script-icon">
              <img
                v-if="script.type === 'MAA'"
                src="@/assets/MAA.png"
                alt="MAA"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'SRC'"
                src="@/assets/SRC.png"
                alt="SRC"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'MaaEnd'"
                src="@/assets/MaaEnd.png"
                alt="MaaEnd"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'M9A'"
                src="@/assets/M9A.png"
                alt="M9A"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'Okww'"
                src="@/assets/ok-ww.ico"
                alt="ok-ww"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'OkNte'"
                src="@/assets/ok-nte.ico"
                alt="ok-nte"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'HSR'"
                src="@/assets/hsr.png"
                alt="HSR"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'MaaFW'"
                src="@/assets/maafw.png"
                alt="MFW"
                class="type-icon"
              />
              <img
                v-else-if="script.type === 'BetterGI'"
                src="@/assets/bettergi.ico"
                alt="BetterGI"
                class="type-icon"
              />
              <img v-else src="@/assets/AUTO-MAS.ico" alt="General" class="type-icon" />
            </div>
            <div class="script-info">
              <div class="script-name">{{ script.name }}</div>
              <div class="script-meta">
                <span
                  class="script-type"
                  :class="{
                    'script-type-okww': script.type === 'Okww',
                    'script-type-oknte': script.type === 'OkNte',
                  }"
                >
                  {{ getScriptTypeDisplayLabel(script.type) }}
                </span>
                <span class="script-users">
                  <UserOutlined />
                  {{
                    t(
                      'scripts.userCount',
                      { count: script.users?.length || 0 },
                      script.users?.length || 0
                    )
                  }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </a-modal>

  <!-- 脚本类型选择弹窗 -->
  <a-modal
    v-model:open="typeSelectVisible"
    :title="t('scripts.typeSelect.title')"
    :confirm-loading="addLoading"
    class="type-select-modal"
    width="500px"
    :ok-text="t('common.confirm')"
    :cancel-text="t('common.cancel')"
    @ok="handleConfirmAddScript"
    @cancel="typeSelectVisible = false"
  >
    <div class="type-selection">
      <a-radio-group v-model:value="selectedType" class="type-radio-group">
        <a-radio-button value="MAA" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/MAA.png" alt="MAA" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.MAA') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.MAA') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="SRC" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/SRC.png" alt="SRC" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.SRC') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.SRC') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="MaaEnd" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/MaaEnd.png" alt="MaaEnd" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.MaaEnd') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.MaaEnd') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="M9A" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/M9A.png" alt="M9A" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.M9A') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.M9A') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="Okww" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/ok-ww.ico" alt="ok-ww" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.Okww') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.Okww') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="OkNte" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/ok-nte.ico" alt="ok-nte" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.OkNte') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.OkNte') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="HSR" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/hsr.png" alt="HSR" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.HSR') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.HSR') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="BetterGI" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/bettergi.ico" alt="BetterGI" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.BetterGI') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.BetterGI') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="General" class="type-option">
          <div class="type-content">
            <div class="type-logo-container">
              <img src="@/assets/AUTO-MAS.ico" alt="AUTO-MAS" class="type-logo" />
            </div>
            <div class="type-info">
              <div class="type-title">{{ t('scripts.type.General') }}</div>
              <div class="type-description">{{ t('scripts.typeDesc.General') }}</div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>

  <!-- 通用脚本创建方式选择弹窗 -->
  <a-modal
    v-model:open="generalModeSelectVisible"
    :title="t('scripts.generalMode.title')"
    :confirm-loading="addLoading"
    class="general-mode-modal"
    width="600px"
    :ok-text="t('common.confirm')"
    :cancel-text="t('common.back')"
    @ok="handleConfirmGeneralMode"
    @cancel="generalModeSelectVisible = false"
  >
    <div class="mode-selection">
      <a-radio-group v-model:value="selectedGeneralMode" class="mode-radio-group">
        <a-radio-button value="template" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <FileTextOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">{{ t('scripts.generalMode.templateTitle') }}</div>
              <div class="mode-description">{{ t('scripts.generalMode.templateDesc') }}</div>
            </div>
          </div>
        </a-radio-button>
        <a-radio-button value="custom" class="mode-option">
          <div class="mode-content">
            <div class="mode-icon">
              <SettingOutlined />
            </div>
            <div class="mode-info">
              <div class="mode-title">{{ t('scripts.generalMode.customTitle') }}</div>
              <div class="mode-description">{{ t('scripts.generalMode.customDesc') }}</div>
            </div>
          </div>
        </a-radio-button>
      </a-radio-group>
    </div>
  </a-modal>

  <!-- 模板选择弹窗 -->
  <a-modal
    v-model:open="templateSelectVisible"
    :title="t('scripts.template.title')"
    :confirm-loading="templateLoading"
    class="template-select-modal"
    width="1000px"
    :ok-text="t('scripts.template.ok')"
    :cancel-text="t('common.back')"
    :ok-button-props="{ disabled: !selectedTemplate }"
    @ok="handleConfirmTemplate"
    @cancel="handleCancelTemplate"
  >
    <div class="template-selection">
      <a-spin :spinning="templateLoading">
        <div v-if="templates.length === 0 && !templateLoading" class="no-templates">
          <div class="no-templates-content">
            <FileSearchOutlined class="no-templates-icon" />
            <h3>{{ t('scripts.template.emptyTitle') }}</h3>
            <p>{{ t('scripts.template.emptyDesc') }}</p>
          </div>
        </div>
        <div v-else class="templates-container">
          <div class="templates-header">
            <div class="templates-count">
              <span class="count-badge">{{ filteredTemplates.length }}</span>
              <span class="count-text">{{ t('scripts.template.count') }}</span>
            </div>
            <div class="search-container">
              <a-input
                v-model:value="pendingSearchKeyword"
                :placeholder="t('scripts.template.searchPlaceholder')"
                allow-clear
                size="large"
                class="template-search"
                @press-enter="handleSearchTemplates"
                @change="handleSearchInputChange"
              >
                <template #prefix>
                  <FileSearchOutlined />
                </template>
              </a-input>
              <a-button type="primary" @click="handleSearchTemplates">{{
                t('scripts.template.search')
              }}</a-button>
            </div>
          </div>
          <div class="templates-list">
            <div v-if="filteredTemplates.length === 0" class="no-search-results">
              <FileSearchOutlined class="no-results-icon" />
              <p>{{ t('scripts.template.noMatch') }}</p>
              <p class="no-results-tip">{{ t('scripts.template.noMatchTip') }}</p>
            </div>
            <template v-else>
              <div
                v-for="(template, index) in filteredTemplates"
                :key="getTemplateKey(template, index)"
                :class="['template-item', { selected: isSelectedTemplate(template) }]"
                @click="selectedTemplate = template"
              >
                <div class="template-content">
                  <div class="template-header">
                    <div class="template-info">
                      <h3 class="template-name">{{ template.configName }}</h3>
                      <div class="template-meta">
                        <span class="template-author">
                          <UserOutlined />
                          {{ template.author || t('scripts.template.unknownAuthor') }}
                        </span>
                        <span class="template-time">
                          <ClockCircleOutlined />
                          {{ template.createTime || t('scripts.template.unknownTime') }}
                        </span>
                      </div>
                    </div>
                  </div>

                  <!-- eslint-disable vue/no-v-html 模板描述来自 MAS 后端 markdown，属可信内容 -->
                  <div
                    class="template-description"
                    @click="handleTemplateDescriptionClick"
                    v-html="parseMarkdown(template.description)"
                  ></div>
                  <!-- eslint-enable vue/no-v-html -->
                </div>
              </div>
            </template>
          </div>
        </div>
      </a-spin>
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import {
  BookOutlined,
  ClockCircleOutlined,
  DownOutlined,
  ExportOutlined,
  FileSearchOutlined,
  FileTextOutlined,
  PlusOutlined,
  SearchOutlined,
  SettingOutlined,
  UpOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import ScriptTable from '@/components/ScriptTable.vue'
import ScriptCreateDialog from '@/views/scripts/components/ScriptCreateDialog.vue'
import type { Script, ScriptType, User } from '@/types/script'
import {
  getScriptEditSegment,
  type ScriptCreateRequest,
} from '@/views/scripts/components/scriptCreateFlow'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useWebSocket } from '@/composables/useWebSocket'
import {
  WS_TASK_COMPLETED,
  WS_TASK_NOTICE,
  type WSTaskCompletedData,
  type WSTaskNoticeData,
} from '@/services/websocket/types'
import { useTemplateApi, type WebConfigTemplate } from '@/composables/useTemplateApi'
import { usePlanApi } from '@/composables/usePlanApi'
import { PLAN_CONFIG_TYPES } from '@/utils/planTypeRegistry'
import { Service } from '@/api/services/Service'
import { TaskCreateIn } from '@/api/models/TaskCreateIn'
import { MAS_DOC_URLS, handleExternalLink, openExternalUrl } from '@/utils/openExternal'
import MarkdownIt from 'markdown-it'
import { filterScriptsByKeyword } from '@/views/scripts/scriptSearch'

const { t } = useI18n()

defineOptions({ name: 'ScriptsPage' })

const logger = window.electronAPI.getLogger('脚本管理')

const router = useRouter()
const { addScript, deleteScript, getScriptsWithUsers } = useScriptApi()
const { updateUser, deleteUser } = useUserApi()
const { subscribe, unsubscribe } = useWebSocket()
const { getWebConfigTemplates, importScriptFromWeb, error: templateError } = useTemplateApi()
const { getPlans } = usePlanApi()

// 初始化markdown解析器
const md = new MarkdownIt({
  html: false,
  linkify: true,
  typographer: true,
})

const scripts = ref<Script[]>([])
const scriptSearchKeyword = ref('')
const isSearching = computed(() => Boolean(scriptSearchKeyword.value.trim()))
const filteredScripts = computed(() =>
  filterScriptsByKeyword(scripts.value, scriptSearchKeyword.value)
)
const scriptTableRef = ref<InstanceType<typeof ScriptTable> | null>(null)
// 增加：标记是否已经完成过一次脚本列表加载（成功或失败都算一次）
const loadedOnce = ref(false)
// 所有计划表数据 (planId -> planData)
const allPlansData = ref<Record<string, Record<string, any>>>({})
const scriptCreateVisible = ref(false)
const createModeSelectVisible = ref(false) // 创建方式选择弹窗（复制已有 vs 创建新脚本）
const scriptSelectVisible = ref(false) // 脚本列表选择弹窗
const typeSelectVisible = ref(false)
const generalModeSelectVisible = ref(false)
const templateSelectVisible = ref(false)
const selectedCreateMode = ref('new') // 'copy' or 'new'
const selectedScriptId = ref<string | null>(null) // 选中要复制的脚本ID
const selectedType = ref<ScriptType>('MAA')
const selectedGeneralMode = ref('template')
const selectedTemplate = ref<WebConfigTemplate | null>(null)
const templates = ref<WebConfigTemplate[]>([])
const addLoading = ref(false)
const copyingScriptId = ref<string | null>(null)
const templateLoading = ref(false)
const pendingSearchKeyword = ref('')
const appliedSearchKeyword = ref('')
const showMAAConfigMask = ref(false) // 控制MAA配置遮罩层的显示
const showSRCConfigMask = ref(false) // 控制SRC配置遮罩层的显示
const showMaaEndConfigMask = ref(false) // 控制MaaEnd配置遮罩层的显示
const showOkwwConfigMask = ref(false) // 控制ok-ww配置遮罩层的显示
const currentConfigScript = ref<Script | null>(null) // 当前正在配置的脚本
const currentMaaEndConfigUser = ref<User | null>(null)

const scriptEditPathMap: Record<ScriptType, string> = {
  MAA: 'maa',
  General: 'general',
  Okww: 'okww',
  OkNte: 'oknte',
  SRC: 'src',
  MaaEnd: 'maaend',
  M9A: 'm9a',
  MaaFW: 'maafw',
  HSR: 'hsr',
  BetterGI: 'bettergi',
}

const getScriptEditPath = (type: ScriptType) => scriptEditPathMap[type]

// 新建脚本后的落地页。MFW 走分步引导（项目路径、控制、更新、运行四步都要配
// 才跑得起来），其余类型仍直接进编辑页。
const getScriptCreateRoute = (type: ScriptType, scriptId: string) =>
  type === 'MaaFW'
    ? `/scripts/${scriptId}/setup/maafw`
    : `/scripts/${scriptId}/edit/${getScriptEditPath(type)}`

// 复制脚本弹窗列表里的类型文案
const getScriptTypeDisplayLabel = (type: ScriptType) =>
  t(`scripts.type.${type}`) || t('scripts.type.General')

// WebSocket连接管理
const activeConnections = ref<Map<string, { subscriptionIds: string[]; taskId: string }>>(new Map()) // scriptId -> { subscriptionIds, taskId }

// 解析模板描述的markdown
const parseMarkdown = (text: string) => {
  if (!text) return t('scripts.noDescription')
  return md.render(text)
}

const getTemplateKey = (template: WebConfigTemplate, index: number) =>
  [template.downloadUrl, template.configName, template.author, template.createTime, index]
    .filter(value => value !== undefined && value !== '')
    .join('::')

const isSelectedTemplate = (template: WebConfigTemplate) => selectedTemplate.value === template

const handleTemplateDescriptionClick = (event: MouseEvent) => {
  const link = (event.target as HTMLElement | null)?.closest('a')
  if (!link) return

  event.preventDefault()
  const url = link.getAttribute('href')
  if (url) {
    openExternalUrl(url)
  }
}

// 过滤模板
const filteredTemplates = computed(() => {
  if (!appliedSearchKeyword.value.trim()) {
    return templates.value
  }

  const keyword = appliedSearchKeyword.value.toLowerCase()
  return templates.value.filter(
    template =>
      template.configName.toLowerCase().includes(keyword) ||
      (template.author && template.author.toLowerCase().includes(keyword)) ||
      (template.description && template.description.toLowerCase().includes(keyword))
  )
})

const handleSearchTemplates = () => {
  appliedSearchKeyword.value = pendingSearchKeyword.value.trim()
}

const handleSearchInputChange = () => {
  if (!pendingSearchKeyword.value.trim()) {
    appliedSearchKeyword.value = ''
  }
}

watch(filteredTemplates, filtered => {
  if (selectedTemplate.value && !filtered.includes(selectedTemplate.value)) {
    selectedTemplate.value = null
  }
})

onMounted(() => {
  loadScripts()
  loadCurrentPlan()
})

// 离开页面时释放全部配置会话订阅；清空 map 同时使 30 分钟超时回调的
// has() 守卫失效，不会在其他页面弹出提示。
onUnmounted(() => {
  for (const connection of activeConnections.value.values()) {
    for (const subscriptionId of connection.subscriptionIds) {
      unsubscribe(subscriptionId)
    }
  }
  activeConnections.value.clear()
})

const loadScripts = async () => {
  try {
    const scriptDetails = await getScriptsWithUsers()

    // 将 ScriptDetail 转换为 Script 格式（为了兼容现有的表格组件）
    scripts.value = scriptDetails.map(detail => ({
      id: detail.uid,
      type: detail.type as ScriptType,
      name: detail.name,
      config: detail.config,
      users: (detail.users || []).filter((user): user is NonNullable<typeof user> => user !== null),
      createTime: new Date().toLocaleString(),
    }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载脚本列表失败: ${errorMsg}`)
    message.error(t('scripts.toast.loadListFailed', { error: errorMsg }))
  } finally {
    // 首次加载结束（不论成功失败）后置位，避免初始闪烁
    loadedOnce.value = true
  }
}

// 加载所有计划表数据
const loadCurrentPlan = async () => {
  try {
    const response = await getPlans()
    if (response.data && response.index) {
      const maaPlanIds = response.index
        .filter(plan => plan.type === PLAN_CONFIG_TYPES.MAA)
        .map(plan => plan.uid)

      allPlansData.value = Object.fromEntries(
        maaPlanIds
          .filter(planId => response.data[planId])
          .map(planId => [planId, response.data[planId]])
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载计划表数据失败: ${errorMsg}`)
    // 不显示错误消息，因为计划表数据是可选的
  }
}

const handleAddScript = () => {
  scriptCreateVisible.value = true
}

const handleCollapseAll = () => {
  scriptTableRef.value?.collapseAllUsers()
}

const handleExpandAll = () => {
  scriptTableRef.value?.expandAllUsers()
}

const navigateToCreatedScript = (
  scriptId: string,
  type: ScriptType,
  data?: Record<string, unknown>
) => {
  const route = {
    // MFW 新建后进分步引导；其余类型直接进编辑页
    path:
      type === 'MaaFW'
        ? `/scripts/${scriptId}/setup/maafw`
        : `/scripts/${scriptId}/edit/${getScriptEditSegment(type)}`,
    ...(data
      ? {
          state: {
            scriptData: {
              id: scriptId,
              type,
              config: JSON.parse(JSON.stringify(data)),
            },
          },
        }
      : {}),
  }
  router.push(route)
}

const handleSubmitScriptCreate = async (request: ScriptCreateRequest) => {
  addLoading.value = true
  try {
    const type = request.kind === 'new' ? request.type : 'General'
    const result = await addScript(type)
    if (!result) return

    if (request.kind === 'general-template') {
      const imported = await importScriptFromWeb(result.scriptId, request.template.downloadUrl)
      if (!imported) return
      message.success(t('scripts.toast.createdFromTemplate', { name: request.template.configName }))
      await loadScripts()
      scriptCreateVisible.value = false
      navigateToCreatedScript(result.scriptId, 'General')
      return
    }

    scriptCreateVisible.value = false
    navigateToCreatedScript(result.scriptId, type, result.data)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`创建脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleConfirmCreateMode = () => {
  if (selectedCreateMode.value === 'copy') {
    // 复制已有脚本 - 打开脚本选择弹窗
    createModeSelectVisible.value = false
    selectedScriptId.value = null
    scriptSelectVisible.value = true
  } else {
    // 创建新脚本 - 进入类型选择
    createModeSelectVisible.value = false
    selectedType.value = 'MAA'
    typeSelectVisible.value = true
  }
}

const handleConfirmScriptSelect = async () => {
  if (!selectedScriptId.value) {
    message.warning(t('scripts.toast.selectScript'))
    return
  }

  // 获取选中的脚本信息
  const selectedScript = scripts.value.find(s => s.id === selectedScriptId.value)
  if (!selectedScript) {
    message.error(t('scripts.toast.scriptMissing'))
    return
  }

  addLoading.value = true
  try {
    // 使用选中的脚本ID调用addScript，传入scriptId进行复制创建
    const result = await addScript(selectedScript.type, selectedScriptId.value)
    if (result) {
      scriptSelectVisible.value = false
      // 跳转到编辑页面
      router.push({
        path: getScriptCreateRoute(selectedScript.type, result.scriptId),
        state: {
          scriptData: {
            id: result.scriptId,
            type: selectedScript.type,
            config: result.data,
          },
        },
      })
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`复制脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleConfirmAddScript = async () => {
  if (selectedType.value === 'General') {
    // 如果选择通用脚本，进入创建方式选择
    typeSelectVisible.value = false
    generalModeSelectVisible.value = true
    return
  }

  // MAA和SRC脚本直接创建
  addLoading.value = true
  try {
    const result = await addScript(selectedType.value)
    if (result) {
      typeSelectVisible.value = false
      // 跳转到编辑页面，传递API返回的数据
      router.push({
        path: getScriptCreateRoute(selectedType.value, result.scriptId),
        state: {
          scriptData: {
            id: result.scriptId,
            type: selectedType.value,
            config: result.data,
          },
        },
      })
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`添加脚本失败: ${errorMsg}`)
  } finally {
    addLoading.value = false
  }
}

const handleConfirmGeneralMode = async () => {
  if (selectedGeneralMode.value === 'template') {
    // 加载模板列表并打开模板选择弹窗
    await loadTemplates()
    generalModeSelectVisible.value = false
    templateSelectVisible.value = true
  } else {
    // 自定义配置 - 直接创建通用脚本
    generalModeSelectVisible.value = false
    addLoading.value = true
    try {
      const result = await addScript('General')
      if (result) {
        router.push({
          path: `/scripts/${result.scriptId}/edit/general`,
          state: {
            scriptData: {
              id: result.scriptId,
              type: 'General',
              config: result.data,
            },
          },
        })
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error)
      logger.error(`添加脚本失败: ${errorMsg}`)
    } finally {
      addLoading.value = false
    }
  }
}

const loadTemplates = async () => {
  templateLoading.value = true
  try {
    templates.value = await getWebConfigTemplates()
    selectedTemplate.value = null
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`加载模板列表失败: ${errorMsg}`)
  } finally {
    templateLoading.value = false
  }
}

const handleConfirmTemplate = async () => {
  if (!selectedTemplate.value) {
    message.warning(t('scripts.toast.selectTemplate'))
    return
  }

  templateLoading.value = true
  try {
    // 1. 先创建通用脚本
    const createResult = await addScript('General')
    if (!createResult) {
      return
    }

    // 2. 使用模板URL导入配置
    const importResult = await importScriptFromWeb(
      createResult.scriptId,
      selectedTemplate.value.downloadUrl
    )

    if (importResult) {
      message.success(
        t('scripts.toast.createdFromTemplate', { name: selectedTemplate.value.configName })
      )
      templateSelectVisible.value = false
      selectedTemplate.value = null

      // 刷新脚本列表
      await loadScripts()

      // 跳转到编辑页面，不传递state数据，让编辑页面从API重新加载最新配置
      router.push(`/scripts/${createResult.scriptId}/edit/general`)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`使用模板创建脚本失败: ${errorMsg}`)
    message.error(t('scripts.toast.templateCreateFailed', { error: errorMsg }))
  } finally {
    templateLoading.value = false
  }
}

const handleCancelTemplate = () => {
  templateSelectVisible.value = false
  selectedTemplate.value = null
  // 返回到创建方式选择
  generalModeSelectVisible.value = true
}

const handleEditScript = (script: Script) => {
  router.push(`/scripts/${script.id}/edit/${getScriptEditPath(script.type)}`)
}

const handleDeleteScript = async (script: Script) => {
  const result = await deleteScript(script.id)
  if (result) {
    loadScripts()
  }
}

const handleCopyScript = async (script: Script) => {
  addLoading.value = true
  copyingScriptId.value = script.id
  try {
    const result = await addScript(script.type, script.id)
    if (result) {
      await loadScripts()
      message.success(t('scripts.toast.copied', { name: script.name }))
    }
  } finally {
    addLoading.value = false
    copyingScriptId.value = null
  }
}

const handleAddUser = (script: Script) => {
  // 根据脚本类型跳转到对应的用户添加页面
  if (script.type === 'MAA') {
    router.push(`/scripts/${script.id}/users/add/maa`)
  } else if (script.type === 'SRC') {
    router.push(`/scripts/${script.id}/users/add/src`)
  } else if (script.type === 'MaaEnd') {
    router.push(`/scripts/${script.id}/users/add/maaend`)
  } else if (script.type === 'M9A') {
    router.push(`/scripts/${script.id}/users/add/m9a`)
  } else if (script.type === 'MaaFW') {
    router.push(`/scripts/${script.id}/users/add/maafw`)
  } else if (script.type === 'Okww') {
    router.push(`/scripts/${script.id}/users/add/okww`)
  } else if (script.type === 'OkNte') {
    router.push(`/scripts/${script.id}/users/add/oknte`)
  } else if (script.type === 'HSR') {
    router.push(`/scripts/${script.id}/users/add/hsr`)
  } else if (script.type === 'BetterGI') {
    router.push(`/scripts/${script.id}/users/add/bettergi`)
  } else {
    router.push(`/scripts/${script.id}/users/add/general`)
  }
}

const handleEditUser = (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (script) {
    // 根据脚本类型跳转到对应的用户编辑页面
    if (script.type === 'MAA') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maa`)
    } else if (script.type === 'SRC') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/src`)
    } else if (script.type === 'MaaEnd') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maaend`)
    } else if (script.type === 'M9A') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/m9a`)
    } else if (script.type === 'MaaFW') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/maafw`)
    } else if (script.type === 'Okww') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/okww`)
    } else if (script.type === 'OkNte') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/oknte`)
    } else if (script.type === 'HSR') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/hsr`)
    } else if (script.type === 'BetterGI') {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/bettergi`)
    } else {
      router.push(`/scripts/${script.id}/users/${user.id}/edit/general`)
    }
  } else {
    message.error(t('scripts.toast.scriptNotFound'))
  }
}

const handleDeleteUser = async (user: User) => {
  // 从用户数据中找到对应的脚本
  const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
  if (!script) {
    message.error(t('scripts.toast.scriptNotFound'))
    return
  }

  const result = await deleteUser(script.id, user.id)
  if (result) {
    // 删除成功后，从本地数据中移除用户
    const userIndex = script.users.findIndex(u => u.id === user.id)
    if (userIndex > -1) {
      script.users.splice(userIndex, 1)
    }
  }
}

const handleStartMAAConfig = async (script: Script) => {
  try {
    // 检查是否已有连接
    const existingConnection = activeConnections.value.get(script.id)
    if (existingConnection) {
      message.warning(t('scripts.toast.alreadyConfiguring'))
      return
    }

    // 调用启动配置任务API
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: script.id,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (response.code === 200) {
      // 显示遮罩层
      showMAAConfigMask.value = true
      currentConfigScript.value = script

      // 订阅WebSocket消息
      const subscriptionIds = [
        // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskNoticeData
          if (data.level === 'error') {
            const errorMsg = data.message
            logger.error(`脚本 ${script.name} 配置异常: ${errorMsg}`)
            message.error(t('scripts.toast.configFailed', { label: 'MAA', error: errorMsg }))
          }
        }),
        // 处理任务结束消息
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskCompletedData
          logger.info(`脚本 ${script.name} 配置任务已结束`)
          // 根据结果显示不同消息
          if (data.outcome === 'success') {
            message.success(t('scripts.toast.configDone', { name: script.name }))
          }
          // 清理连接
          for (const subscriptionId of subscriptionIds) {
            unsubscribe(subscriptionId)
          }
          activeConnections.value.delete(script.id)
          showMAAConfigMask.value = false
          currentConfigScript.value = null
        }),
      ]

      // 记录连接和subscriptionIds
      activeConnections.value.set(script.id, {
        subscriptionIds,
        taskId: response.taskId,
      })
      message.success(t('scripts.toast.configStarted', { name: script.name, label: 'MAA' }))

      // 设置自动断开连接的定时器（30分钟后）
      setTimeout(
        () => {
          if (activeConnections.value.has(script.id)) {
            const connection = activeConnections.value.get(script.id)
            if (connection) {
              for (const subscriptionId of connection.subscriptionIds) {
                unsubscribe(subscriptionId)
              }
            }
            activeConnections.value.delete(script.id)
            // 超时时隐藏遮罩
            showMAAConfigMask.value = false
            currentConfigScript.value = null
            message.info(t('scripts.toast.sessionTimeout', { name: script.name }))
          }
        },
        30 * 60 * 1000
      ) // 30分钟
    } else {
      message.error(response.message || t('scripts.toast.startConfigFailed', { label: 'MAA' }))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动MAA配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.startConfigError', { label: 'MAA', error: errorMsg }))
  }
}

const handleSaveMAAConfig = async (script: Script) => {
  try {
    const connection = activeConnections.value.get(script.id)
    if (!connection) {
      message.error(t('scripts.toast.noSession'))
      return
    }

    // 调用停止配置任务API
    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: connection.taskId,
    })

    if (response.code === 200) {
      // 取消订阅
      for (const subscriptionId of connection.subscriptionIds) {
        unsubscribe(subscriptionId)
      }
      activeConnections.value.delete(script.id)

      // 隐藏遮罩
      showMAAConfigMask.value = false
      currentConfigScript.value = null

      message.success(t('scripts.toast.configSaved', { name: script.name }))
    } else {
      message.error(response.message || t('scripts.toast.saveConfigFailed'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存MAA配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.saveConfigError', { label: 'MAA', error: errorMsg }))
  }
}

const handleStartSRCConfig = async (script: Script) => {
  try {
    // 检查是否已有连接
    const existingConnection = activeConnections.value.get(script.id)
    if (existingConnection) {
      message.warning(t('scripts.toast.alreadyConfiguring'))
      return
    }

    // 调用启动配置任务API
    const response = await Service.addTaskApiDispatchStartPost({
      taskId: script.id,
      mode: TaskCreateIn.mode.SCRIPT_CONFIG,
    })

    if (response.code === 200) {
      // 显示遮罩层
      showSRCConfigMask.value = true
      currentConfigScript.value = script

      // 订阅WebSocket消息
      const subscriptionIds = [
        // 处理任务提示中的错误消息（不取消订阅，等待任务结束消息）
        subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskNoticeData
          if (data.level === 'error') {
            const errorMsg = data.message
            logger.error(`脚本 ${script.name} 配置异常: ${errorMsg}`)
            message.error(t('scripts.toast.configFailed', { label: 'SRC', error: errorMsg }))
          }
        }),
        // 处理任务结束消息
        subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, wsMessage => {
          const data = wsMessage.data as unknown as WSTaskCompletedData
          logger.info(`脚本 ${script.name} 配置任务已结束`)
          // 根据结果显示不同消息
          if (data.outcome === 'success') {
            message.success(t('scripts.toast.configDone', { name: script.name }))
          }
          // 清理连接
          for (const subscriptionId of subscriptionIds) {
            unsubscribe(subscriptionId)
          }
          activeConnections.value.delete(script.id)
          showSRCConfigMask.value = false
          currentConfigScript.value = null
        }),
      ]

      // 记录连接和subscriptionIds
      activeConnections.value.set(script.id, {
        subscriptionIds,
        taskId: response.taskId,
      })
      message.success(t('scripts.toast.configStarted', { name: script.name, label: 'SRC' }))

      // 设置自动断开连接的定时器（30分钟后）
      setTimeout(
        () => {
          if (activeConnections.value.has(script.id)) {
            const connection = activeConnections.value.get(script.id)
            if (connection) {
              for (const subscriptionId of connection.subscriptionIds) {
                unsubscribe(subscriptionId)
              }
            }
            activeConnections.value.delete(script.id)
            // 超时时隐藏遮罩
            showSRCConfigMask.value = false
            currentConfigScript.value = null
            message.info(t('scripts.toast.sessionTimeout', { name: script.name }))
          }
        },
        30 * 60 * 1000
      ) // 30分钟
    } else {
      message.error(response.message || t('scripts.toast.startConfigFailed', { label: 'SRC' }))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动SRC配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.startConfigError', { label: 'SRC', error: errorMsg }))
  }
}

const handleSaveSRCConfig = async (script: Script) => {
  try {
    const connection = activeConnections.value.get(script.id)
    if (!connection) {
      message.error(t('scripts.toast.noSession'))
      return
    }

    // 调用停止配置任务API
    const response = await Service.stopTaskApiDispatchStopPost({
      taskId: connection.taskId,
    })

    if (response.code === 200) {
      // 取消订阅
      for (const subscriptionId of connection.subscriptionIds) {
        unsubscribe(subscriptionId)
      }
      activeConnections.value.delete(script.id)

      // 隐藏遮罩
      showSRCConfigMask.value = false
      currentConfigScript.value = null

      message.success(t('scripts.toast.configSaved', { name: script.name }))
    } else {
      message.error(response.message || t('scripts.toast.saveConfigFailed'))
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存SRC配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.saveConfigError', { label: 'SRC', error: errorMsg }))
  }
}

const clearConfigSession = (
  targetId: string,
  subscriptionIds: string[] | undefined,
  clearState: () => void
) => {
  if (subscriptionIds) {
    for (const subscriptionId of subscriptionIds) {
      unsubscribe(subscriptionId)
    }
  }
  activeConnections.value.delete(targetId)
  clearState()
}

const startConfigSession = async (
  targetId: string,
  label: string,
  setActiveState: () => void,
  clearState: () => void
) => {
  if (activeConnections.value.has(targetId)) {
    message.warning(t('scripts.toast.targetConfiguring'))
    return false
  }

  const response = await Service.addTaskApiDispatchStartPost({
    taskId: targetId,
    mode: TaskCreateIn.mode.SCRIPT_CONFIG,
  })
  if (response.code !== 200 || !response.taskId) {
    throw new Error(response.message || t('scripts.toast.startFailedRaw', { label }))
  }

  setActiveState()
  let sessionEnded = false
  const subscriptionIds: string[] = []
  subscriptionIds.push(
    subscribe({ id: response.taskId, type: WS_TASK_NOTICE }, wsMessage => {
      const data = wsMessage.data as unknown as WSTaskNoticeData
      if (data.level === 'error') {
        message.error(t('scripts.toast.configFailed', { label, error: data.message }))
      }
    }),
    subscribe({ id: response.taskId, type: WS_TASK_COMPLETED }, () => {
      sessionEnded = true
      clearConfigSession(targetId, subscriptionIds, clearState)
    })
  )
  if (sessionEnded) {
    for (const subscriptionId of subscriptionIds) {
      unsubscribe(subscriptionId)
    }
    return false
  }
  activeConnections.value.set(targetId, {
    subscriptionIds,
    taskId: response.taskId,
  })
  return true
}

const stopConfigSession = async (targetId: string, label: string, clearState: () => void) => {
  const connection = activeConnections.value.get(targetId)
  if (!connection) {
    message.error(t('scripts.toast.noSession'))
    return false
  }
  const response = await Service.stopTaskApiDispatchStopPost({
    taskId: connection.taskId,
  })
  if (response.code !== 200) {
    throw new Error(response.message || t('scripts.toast.saveFailedRaw', { label }))
  }
  clearConfigSession(targetId, connection.subscriptionIds, clearState)
  return true
}

const handleStartMaaEndConfig = async (script: Script, user: User | null = null) => {
  try {
    const controllerType = (script.config as any).Game?.ControllerType
    if (!user && controllerType !== 'Win32-Front') {
      message.warning(t('scripts.toast.maaEndUnsupported'))
      return
    }

    const targetId = user?.id ?? script.id
    const clearState = () => {
      showMaaEndConfigMask.value = false
      currentConfigScript.value = null
      currentMaaEndConfigUser.value = null
    }
    const started = await startConfigSession(
      targetId,
      'MaaEnd',
      () => {
        showMaaEndConfigMask.value = true
        currentConfigScript.value = script
        currentMaaEndConfigUser.value = user
      },
      clearState
    )
    if (!started) return

    message.success(
      user
        ? t('scripts.toast.maaEndUserStarted', { script: script.name, user: user.Info.Name })
        : t('scripts.toast.maaEndScriptStarted', { script: script.name })
    )
    setTimeout(
      () => {
        const connection = activeConnections.value.get(targetId)
        if (!connection) return
        clearConfigSession(targetId, connection.subscriptionIds, clearState)
        message.info(
          user
            ? t('scripts.toast.maaEndUserTimeout', { script: script.name, user: user.Info.Name })
            : t('scripts.toast.sessionTimeout', { name: script.name })
        )
      },
      30 * 60 * 1000
    )
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 MaaEnd 配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.startConfigError', { label: 'MaaEnd', error: errorMsg }))
  }
}

const handleStartMaaEndUserConfig = async (script: Script, user: User) => {
  await handleStartMaaEndConfig(script, user)
}

const handleSaveMaaEndConfig = async (script: Script) => {
  try {
    const targetId = currentMaaEndConfigUser.value?.id ?? script.id
    const currentUser = currentMaaEndConfigUser.value
    const saved = await stopConfigSession(targetId, 'MaaEnd', () => {
      showMaaEndConfigMask.value = false
      currentConfigScript.value = null
      currentMaaEndConfigUser.value = null
    })
    if (saved) {
      message.success(
        currentUser
          ? t('scripts.toast.maaEndUserSaved', { script: script.name, user: currentUser.Info.Name })
          : t('scripts.toast.configSaved', { name: script.name })
      )
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 MaaEnd 配置失败: ${errorMsg}`)
    message.error(t('scripts.toast.saveConfigError', { label: 'MaaEnd', error: errorMsg }))
  }
}

const handleStartOkwwConfig = async (script: Script) => {
  try {
    const started = await startConfigSession(
      script.id,
      'ok-ww',
      () => {
        showOkwwConfigMask.value = true
        currentConfigScript.value = script
      },
      () => {
        showOkwwConfigMask.value = false
        currentConfigScript.value = null
      }
    )
    if (started) message.success(t('scripts.toast.okwwStarted', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`启动 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('scripts.toast.okwwStartFailed', { error: errorMsg }))
  }
}

const handleSaveOkwwConfig = async (script: Script) => {
  try {
    const saved = await stopConfigSession(script.id, 'ok-ww', () => {
      showOkwwConfigMask.value = false
      currentConfigScript.value = null
    })
    if (saved) message.success(t('scripts.toast.okwwSaved', { name: script.name }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 ok-ww 设置失败: ${errorMsg}`)
    message.error(t('scripts.toast.okwwSaveFailed', { error: errorMsg }))
  }
}

const handleToggleUserStatus = async (user: User) => {
  try {
    // 找到该用户对应的脚本
    const script = scripts.value.find(s => s.users.some(u => u.id === user.id))
    if (!script) {
      message.error(t('scripts.toast.scriptNotFound'))
      return
    }
    const newStatus = !user.Info.Status

    // 后端是单字段 set：只发送 Status，避免 Info.Tag 等虚拟字段混入触发后端报错
    const result = await updateUser(script.id, user.id, {
      Info: { Status: newStatus },
    })

    if (result) {
      message.success(t('scripts.toast.userStatusUpdated'))
      // 更新本地用户状态
      user.Info.Status = newStatus
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`更新用户状态失败: ${errorMsg}`)
    message.error(t('scripts.toast.userStatusFailed', { error: errorMsg }))
  }
}
</script>

<style scoped>
.maa-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.mask-content {
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  padding: 24px;
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow:
    0 6px 16px 0 rgba(0, 0, 0, 0.08),
    0 3px 6px -4px rgba(0, 0, 0, 0.12),
    0 9px 28px 8px rgba(0, 0, 0, 0.05);
  border: 1px solid var(--ant-color-border);
}

.mask-icon {
  margin-bottom: 16px;
}

.mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.mask-actions {
  display: flex;
  justify-content: center;
}

.link {
  display: inline-flex;
  align-items: center;
}

.link .anticon {
  margin-right: 8px;
}

.loading-container {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 200px);
  text-align: center;
}

.empty-image-container {
  margin-bottom: 16px;
}

.empty-image {
  max-width: 100%;
  height: auto;
}

.empty-title {
  font-size: 18px;
  font-weight: 500;
  margin: 0;
  color: var(--ant-color-text);
}

.empty-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.scripts-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 24px;
  padding: 0 4px;
}

.doc-link {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--ant-color-primary);
  white-space: nowrap;
}

.header-left {
  display: flex;
  flex: 1;
  min-width: 0;
  align-items: center;
  gap: 24px;
}

.script-search {
  width: min(360px, 40vw);
}

.header-actions {
  flex-shrink: 0;
  margin-left: 16px;
}

@media (max-width: 768px) {
  .page-title {
    font-size: 24px;
  }

  .scripts-header {
    align-items: stretch;
    flex-direction: column;
    gap: 16px;
    padding: 0 2px;
  }

  .header-left {
    align-items: stretch;
    flex-direction: column;
    gap: 12px;
  }

  .script-search {
    width: 100%;
  }

  .header-actions {
    margin-left: 0;
  }
}

.page-title {
  margin: 0 0 8px 0;
  font-size: 32px;
  font-weight: 700;
  color: var(--ant-color-text);
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.type-select-modal,
.general-mode-modal,
.template-select-modal {
  text-align: left;
}

.type-select-modal :deep(.ant-modal-header),
.general-mode-modal :deep(.ant-modal-header),
.template-select-modal :deep(.ant-modal-header) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.type-select-modal :deep(.ant-modal-title),
.general-mode-modal :deep(.ant-modal-title),
.template-select-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.type-select-modal :deep(.ant-modal-body),
.general-mode-modal :deep(.ant-modal-body),
.template-select-modal :deep(.ant-modal-body) {
  padding: 24px;
}

.type-select-modal :deep(.ant-modal-footer),
.general-mode-modal :deep(.ant-modal-footer),
.template-select-modal :deep(.ant-modal-footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.type-selection,
.mode-selection,
.template-selection {
  margin-top: 16px;
}

.type-radio-group,
.mode-radio-group {
  display: flex;
  flex-direction: column;
}

/* Hide the small separator (::before) AntD injects between button wrappers */
.type-radio-group :deep(.ant-radio-button-wrapper:not(:first-child)::before) {
  display: none !important;
}

.type-option,
.mode-option {
  height: auto;
  display: flex;
  align-items: center;
  padding: 16px;
  border: 2px solid var(--ant-color-border);
  border-radius: 12px;
  margin-bottom: 12px;
  cursor: pointer;
  background: var(--ant-color-bg-container);
  position: relative;
  overflow: hidden;
}

.type-option:hover,
.mode-option:hover {
  border-color: var(--ant-color-primary);
}

.type-option:deep(.ant-radio-button-input:checked + .ant-radio-button-wrapper),
.mode-option:deep(.ant-radio-button-input:checked + .ant-radio-button-wrapper) {
  border-color: var(--ant-color-primary) !important;
  background: var(--ant-color-primary-bg) !important;
}

/* 选中状态样式 */
.type-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary) !important;
  background: var(--ant-color-primary-bg) !important;
}

.mode-radio-group :deep(.ant-radio-button-wrapper-checked) {
  border-color: var(--ant-color-primary) !important;
  background: var(--ant-color-primary-bg) !important;
}

/* 选中状态的文字颜色增强 */
.type-radio-group :deep(.ant-radio-button-wrapper-checked) .type-title {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.mode-radio-group :deep(.ant-radio-button-wrapper-checked) .mode-title {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.type-content,
.mode-content {
  display: flex;
  align-items: center;
  width: 100%;
}

.type-logo-container,
.mode-icon {
  width: 48px;
  height: 48px;
  margin-right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  flex-shrink: 0;
}

.type-logo {
  width: 32px;
  height: 32px;
}

.mode-icon {
  font-size: 24px;
  color: var(--ant-color-primary);
}

.type-info,
.mode-info {
  flex: 1;
}

.type-title,
.mode-title {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 6px;
  color: var(--ant-color-text);
}

.type-description,
.mode-description {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  margin: 0;
  line-height: 1.4;
}

.templates-container {
  margin-top: 16px;
}

.templates-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.templates-count {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: var(--ant-color-text);
}

.count-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 20px;
  height: 20px;
  padding: 0 6px;
  border-radius: 10px;
  background: var(--ant-color-primary);
  color: #fff;
  font-size: 12px;
  font-weight: 500;
  margin-right: 8px;
}

.count-text {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}

.search-container {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 380px;
  margin-left: 16px;
}

.template-search {
  flex: 1;
  min-width: 0;
}

.search-container .ant-btn {
  flex-shrink: 0;
}

.templates-list {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
  scrollbar-width: thin;
  scrollbar-color: var(--ant-color-border) transparent;
}

.templates-list::-webkit-scrollbar {
  width: 6px !important;
  display: block !important;
}

.templates-list::-webkit-scrollbar-track {
  background: transparent;
}

.templates-list::-webkit-scrollbar-thumb {
  background-color: var(--ant-color-border);
  border-radius: 3px;
}

.templates-list::-webkit-scrollbar-thumb:hover {
  background-color: var(--ant-color-border-secondary);
}

.template-item {
  padding: 16px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  background: var(--ant-color-bg-container);
  position: relative;
  border-left: 3px solid transparent;
}

.template-item:last-child {
  border-bottom: none;
}

.template-item:hover {
  border-left-color: var(--ant-color-primary-hover);
}

.template-item.selected {
  background: var(--ant-color-primary-bg);
  border-left-color: var(--ant-color-primary);
}

.template-item.selected .template-name {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.template-content {
  display: flex;
  flex-direction: column;
}

.template-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.template-info {
  flex: 1;
}

.template-name {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 4px;
  color: var(--ant-color-text);
}

.template-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.template-author,
.template-time {
  display: flex;
  align-items: center;
  gap: 4px;
}

.template-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0;
  line-height: 1.5;
}

.no-search-results,
.no-templates {
  text-align: center;
  padding: 32px 16px;
  color: var(--ant-color-text-secondary);
}

.no-results-icon,
.no-templates-icon {
  font-size: 48px;
  color: var(--ant-color-text-tertiary);
  margin-bottom: 16px;
}

.no-templates-content h3 {
  color: var(--ant-color-text);
  margin: 0 0 8px;
}

.no-templates-content p {
  color: var(--ant-color-text-secondary);
  margin: 0;
}

.no-results-tip {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  margin-top: 4px;
}

/* 创建方式选择弹窗样式 */
.create-mode-modal {
  text-align: left;
}

.create-mode-modal :deep(.ant-modal-header) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.create-mode-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.create-mode-modal :deep(.ant-modal-body) {
  padding: 24px;
}

.create-mode-modal :deep(.ant-modal-footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

/* 脚本选择弹窗样式 */
.script-select-modal {
  text-align: left;
}

.script-select-modal :deep(.ant-modal-header) {
  border-bottom: 2px solid var(--ant-color-border-secondary);
  padding: 20px 24px;
}

.script-select-modal :deep(.ant-modal-title) {
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.script-select-modal :deep(.ant-modal-body) {
  padding: 24px;
  max-height: 500px;
  overflow-y: auto;
}

.script-select-modal :deep(.ant-modal-footer) {
  padding: 16px 24px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.script-selection {
  margin-top: 8px;
}

.scripts-list {
  max-height: 450px;
  overflow-y: auto;
  border: 1px solid var(--ant-color-border);
  border-radius: 6px;
  background: var(--ant-color-bg-container);
}

.script-item {
  padding: 16px;
  border-bottom: 1px solid var(--ant-color-border);
  cursor: pointer;
  background: var(--ant-color-bg-container);
  position: relative;
  border-left: 3px solid transparent;
}

.script-item:last-child {
  border-bottom: none;
}

.script-item:hover {
  border-left-color: var(--ant-color-primary-hover);
}

.script-item.selected {
  background: var(--ant-color-primary-bg);
  border-left-color: var(--ant-color-primary);
}

.script-item.selected .script-name {
  color: var(--ant-color-primary);
  font-weight: 600;
}

.script-item-content {
  display: flex;
  align-items: center;
  width: 100%;
}

.script-icon {
  width: 48px;
  height: 48px;
  margin-right: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  flex-shrink: 0;
}

.type-icon {
  width: 32px;
  height: 32px;
}

.script-info {
  flex: 1;
  min-width: 0;
}

.script-name {
  font-size: 16px;
  font-weight: 500;
  margin: 0 0 6px;
  color: var(--ant-color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.script-meta {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}

.script-type {
  font-weight: 500;
}

.script-type-okww {
  color: var(--ant-color-primary);
}

.script-type-oknte {
  color: var(--ant-color-primary);
}

.script-type-hsr {
  color: var(--ant-color-primary);
}

.script-users {
  display: flex;
  align-items: center;
  gap: 4px;
}

.no-scripts {
  text-align: center;
  padding: 48px 16px;
  color: var(--ant-color-text-secondary);
}
</style>

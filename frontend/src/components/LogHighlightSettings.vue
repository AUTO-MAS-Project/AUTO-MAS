<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ref, computed } from 'vue'
import { QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useLogHighlight, type LogHighlightColors } from '@/composables/useLogHighlight'
import SettingRow from '@/components/ui/SettingRow.vue'
import LogHighlightPreview from './LogHighlightPreview.vue'
import DownloadLogStyleSettings from './DownloadLogStyleSettings.vue'
import { useTheme } from '@/composables/useTheme'
import { message } from 'ant-design-vue'

const { t } = useI18n()

const { isDark } = useTheme()
const {
  lightColors,
  darkColors,
  styles,
  editorConfig,
  defaultLightColors,
  defaultDarkColors,
  setLightColors,
  setDarkColors,
  setStyles,
  setEditorConfig,
  resetToDefaults,
} = useLogHighlight()

// 当前编辑的主题
const editingTheme = ref<'light' | 'dark'>(isDark.value ? 'dark' : 'light')

// 当前编辑的颜色
const currentColors = computed(() =>
  editingTheme.value === 'light' ? lightColors.value : darkColors.value
)

// 颜色配置项分组
const colorGroups: {
  title: string
  items: { key: keyof LogHighlightColors; label: string; description: string }[]
}[] = [
  {
    title: t('core.comp.time'),
    items: [
      {
        key: 'timestamp',
        label: t('core.comp.timestamp'),
        description: t('core.comp.fullDateTime'),
      },
      { key: 'date', label: t('core.comp.date'), description: t('core.comp.standaloneDate') },
    ],
  },
  {
    title: t('core.comp.logLevel'),
    items: [
      {
        key: 'error',
        label: t('core.comp.error'),
        description: t('core.comp.errorFatalCriticalLevel'),
      },
      {
        key: 'warning',
        label: t('core.comp.warning'),
        description: t('core.comp.warnWarningLevel'),
      },
      { key: 'info', label: t('core.comp.info'), description: t('core.comp.infoNoticeLevel') },
      { key: 'debug', label: t('core.comp.debug'), description: t('core.comp.debugLevel') },
      { key: 'trace', label: t('core.comp.trace'), description: t('core.comp.traceVerboseLevel') },
    ],
  },
  {
    title: t('core.comp.structure'),
    items: [
      {
        key: 'module',
        label: t('core.comp.moduleName'),
        description: t('core.comp.moduleThreadNameSquare'),
      },
      {
        key: 'bracket',
        label: t('core.comp.bracketedContent'),
        description: t('core.comp.textInsideParentheses'),
      },
    ],
  },
  {
    title: t('core.comp.network'),
    items: [
      { key: 'ip', label: t('core.comp.ipAddress'), description: t('core.comp.ipv4Address') },
      { key: 'url', label: 'URL', description: t('core.comp.httpHttpsLinks') },
      { key: 'port', label: t('core.comp.port'), description: t('core.comp.portNumber') },
    ],
  },
  {
    title: t('core.comp.fileSystem'),
    items: [
      { key: 'path', label: t('core.comp.filePath'), description: t('core.comp.fullFilePath') },
      {
        key: 'filename',
        label: t('core.comp.fileName'),
        description: t('core.comp.fileNameExtension'),
      },
    ],
  },
  {
    title: t('core.comp.dataType'),
    items: [
      {
        key: 'number',
        label: t('core.comp.number'),
        description: t('core.comp.integersDecimalsScientificNotation'),
      },
      { key: 'string', label: t('core.comp.string'), description: t('core.comp.quotedString') },
      { key: 'boolean', label: t('core.comp.boolean'), description: 'true/false/null' },
      { key: 'uuid', label: 'UUID', description: t('core.comp.uuidFormattedIdentifiers') },
    ],
  },
  {
    title: t('core.comp.keyword'),
    items: [
      {
        key: 'errorKeyword',
        label: t('core.comp.errorKeyword'),
        description: t('core.comp.exceptionErrorFailedSimilar'),
      },
      {
        key: 'success',
        label: t('core.comp.successKeyword'),
        description: t('core.comp.successCompleteDoneSimilar'),
      },
    ],
  },
  {
    title: t('core.comp.specialContent'),
    items: [
      {
        key: 'stackTrace',
        label: t('core.comp.stackTrace'),
        description: t('core.comp.javaPythonStackTraces'),
      },
      { key: 'json', label: 'JSON', description: t('core.comp.jsonObjectsArrays') },
      {
        key: 'variable',
        label: t('core.comp.variable'),
        description: t('core.comp.keyValueVariableNames'),
      },
      {
        key: 'operator',
        label: t('core.comp.operator'),
        description: t('core.comp.otherOperators'),
      },
    ],
  },
]

// 更新颜色
const updateColor = (key: keyof LogHighlightColors, value: string) => {
  const colorValue = value.replace('#', '')
  if (editingTheme.value === 'light') {
    setLightColors({ [key]: colorValue })
  } else {
    setDarkColors({ [key]: colorValue })
  }
}

// 重置为默认
const handleReset = () => {
  resetToDefaults()
  message.success(t('core.comp.resetDefaults'))
}

// 重置单个颜色
const resetSingleColor = (key: keyof LogHighlightColors) => {
  const defaultColors = editingTheme.value === 'light' ? defaultLightColors : defaultDarkColors
  if (editingTheme.value === 'light') {
    setLightColors({ [key]: defaultColors[key] })
  } else {
    setDarkColors({ [key]: defaultColors[key] })
  }
}

// 字体大小选项
const fontSizeOptions = [11, 12, 13, 14, 15, 16, 18, 20]

// 行高选项
const lineHeightOptions = [1.2, 1.4, 1.5, 1.6, 1.8, 2.0]
</script>

<template>
  <div class="log-highlight-settings">
    <!-- 编辑器排版：三行，全部行内控件 -->
    <SettingRow :label="t('core.comp.fontSize')">
      <a-select
        class="log-select"
        :value="editorConfig.fontSize"
        :aria-label="t('core.comp.fontSize')"
        @change="(v: number) => setEditorConfig({ fontSize: v })"
      >
        <a-select-option v-for="size in fontSizeOptions" :key="size" :value="size">
          {{ size }}px
        </a-select-option>
      </a-select>
    </SettingRow>

    <SettingRow :label="t('core.comp.lineHeight')">
      <a-select
        class="log-select"
        :value="editorConfig.lineHeight"
        :aria-label="t('core.comp.lineHeight')"
        @change="(v: number) => setEditorConfig({ lineHeight: v })"
      >
        <a-select-option v-for="h in lineHeightOptions" :key="h" :value="h">
          {{ h }}
        </a-select-option>
      </a-select>
    </SettingRow>

    <SettingRow stacked :label="t('core.comp.boldText')">
      <div class="checkbox-row">
        <a-checkbox
          :checked="styles.timestampBold"
          @change="(e: any) => setStyles({ timestampBold: e.target.checked })"
        >
          {{ t('core.comp.boldTimestamps') }}
        </a-checkbox>
        <a-checkbox
          :checked="styles.levelBold"
          @change="(e: any) => setStyles({ levelBold: e.target.checked })"
        >
          {{ t('core.comp.boldLogLevels') }}
        </a-checkbox>
        <a-checkbox
          :checked="styles.keywordBold"
          @change="(e: any) => setStyles({ keywordBold: e.target.checked })"
        >
          {{ t('core.comp.boldKeywords') }}
        </a-checkbox>
        <a-checkbox
          :checked="styles.urlUnderline"
          @change="(e: any) => setStyles({ urlUnderline: e.target.checked })"
        >
          {{ t('core.comp.urlUnderline') }}
        </a-checkbox>
      </div>
    </SettingRow>

    <a-collapse class="advanced-settings" :bordered="false">
      <a-collapse-panel key="highlight">
        <template #header>
          <div class="advanced-settings-header">
            <span class="advanced-settings-title">{{ t('core.comp.highlightColorsPreview') }}</span>
          </div>
        </template>

        <!-- 颜色配置 -->
        <div class="config-section">
          <div class="log-section-header">
            <div class="section-title">{{ t('core.comp.colors') }}</div>
            <div class="section-actions">
              <a-radio-group v-model:value="editingTheme" button-style="solid" size="small">
                <a-radio-button value="light">{{ t('core.comp.lightTheme') }}</a-radio-button>
                <a-radio-button value="dark">{{ t('core.comp.darkTheme') }}</a-radio-button>
              </a-radio-group>
              <a-button size="small" @click="handleReset">
                <template #icon>
                  <ReloadOutlined />
                </template>
                {{ t('core.comp.resetEverything') }}
              </a-button>
            </div>
          </div>

          <DownloadLogStyleSettings :editing-theme="editingTheme" />

          <div v-for="group in colorGroups" :key="group.title" class="color-group">
            <div class="group-title">{{ group.title }}</div>
            <div class="color-grid">
              <div v-for="item in group.items" :key="item.key" class="color-item">
                <div class="color-info">
                  <span class="color-label">{{ item.label }}</span>
                  <a-tooltip :title="item.description">
                    <QuestionCircleOutlined class="help-icon" />
                  </a-tooltip>
                </div>
                <div class="color-controls">
                  <input
                    type="color"
                    :value="'#' + currentColors[item.key]"
                    class="color-picker"
                    @input="
                      (e: Event) => updateColor(item.key, (e.target as HTMLInputElement).value)
                    "
                  />
                  <span class="color-value">#{{ currentColors[item.key] }}</span>
                  <a-button
                    size="small"
                    type="text"
                    :title="t('core.comp.resetThisColor')"
                    @click="resetSingleColor(item.key)"
                  >
                    <template #icon>
                      <ReloadOutlined />
                    </template>
                  </a-button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 预览 -->
        <div class="config-section">
          <div class="section-title">{{ t('core.comp.preview') }}</div>
          <LogHighlightPreview :editing-theme="editingTheme" />
        </div>
      </a-collapse-panel>
    </a-collapse>
  </div>
</template>

<style scoped>
.log-highlight-settings {
  padding: 0;
}

.log-select {
  width: 140px;
}

.config-section {
  margin-bottom: 20px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.config-section:last-child {
  border-bottom: none;
  margin-bottom: 0;
}

.log-section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 12px;
}

.log-section-header .section-title {
  margin-bottom: 0;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.advanced-settings {
  overflow: hidden;
  margin-top: 4px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
}

.advanced-settings :deep(.ant-collapse-header) {
  align-items: center;
  padding: 12px 16px;
  transition: background-color 0.2s ease;
}

.advanced-settings :deep(.ant-collapse-header:hover) {
  background: var(--ant-color-primary-bg);
}

.advanced-settings :deep(.ant-collapse-item) {
  border-bottom: none;
}

.advanced-settings :deep(.ant-collapse-content) {
  background: transparent;
  border-top-color: var(--ant-color-border-secondary);
}

.advanced-settings :deep(.ant-collapse-content-box) {
  padding: 16px;
}

.advanced-settings-header {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}

.advanced-settings-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.checkbox-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 24px;
}

.checkbox-row :deep(.ant-checkbox-wrapper) {
  font-size: 14px;
  margin-inline-start: 0;
}
</style>

<style scoped src="./logHighlightColors.css"></style>

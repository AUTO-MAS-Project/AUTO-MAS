<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import {
  BugOutlined,
  CloudDownloadOutlined,
  CodeOutlined,
  DownOutlined,
  DownloadOutlined,
  LoadingOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import { computed, onMounted, ref } from 'vue'
import type { RuntimeLaunchModeSetting, RuntimeLaunchModeState } from '@/types/electron'
import type { ScriptType } from '@/types/script'

import { useLogExport } from '@/composables/useLogExport'
import { useMaaEndIssueReport } from '@/composables/useMaaEndIssueReport'
import { useMaaIssueReport } from '@/composables/useMaaIssueReport'
import { useOkwwIssueReport } from '@/composables/useOkwwIssueReport'
import { useOkNteIssueReport } from '@/composables/useOkNteIssueReport'
import { useZzzOdIssueReport } from '@/composables/useZzzOdIssueReport'
import { useWhimboxIssueReport } from '@/composables/useWhimboxIssueReport'
import { useBetterGIIssueReport } from '@/composables/useBetterGIIssueReport'
import { useMaaFWIssueReport } from '@/composables/useMaaFWIssueReport'
import { useM9AIssueReport } from '@/composables/useM9AIssueReport'
import { useMSSIssueReport } from '@/composables/useMSSIssueReport'
import { useScriptApi } from '@/composables/useScriptApi'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import { SCRIPT_LABELS, SCRIPT_LOGOS } from '@/utils/scriptLogos'
import {
  maafwScriptTypeByConfigType,
  resolveMaaFWFlavor,
  type MaaFWFlavor,
} from '@/composables/useMaaFWFlavor'

const { t } = useI18n()

const { openDevTools } = defineProps<{
  openDevTools: () => void
}>()

const logger = window.electronAPI.getLogger('日志管理')
const { exportingLogs, packageLogs: exportLogsZip } = useLogExport()
const exportingDataBackup = ref(false)
const { exporting: exportingMaaEndLogs, exportMaaEndIssueReport } = useMaaEndIssueReport(logger)
const { exporting: exportingMaaLogs, exportMaaIssueReport } = useMaaIssueReport(logger)
const { exporting: exportingOkwwLogs, exportOkwwIssueReport } = useOkwwIssueReport(logger)
const { exporting: exportingOkNteLogs, exportOkNteIssueReport } = useOkNteIssueReport(logger)
const { exporting: exportingZzzOdLogs, exportZzzOdIssueReport } = useZzzOdIssueReport(logger)
const { exporting: exportingWhimboxLogs, exportWhimboxIssueReport } = useWhimboxIssueReport(logger)
const { exporting: exportingBetterGILogs, exportBetterGIIssueReport } =
  useBetterGIIssueReport(logger)
const { exporting: exportingMaaFWLogs, exportMaaFWIssueReport } = useMaaFWIssueReport(logger)
const { exporting: exportingM9ALogs, exportM9AIssueReport } = useM9AIssueReport(logger)
const { exporting: exportingMSSLogs, exportMSSIssueReport } = useMSSIssueReport(logger)

const { getScripts, error: scriptApiError } = useScriptApi()
/** 已添加的脚本类型：设置页只显示这些专项的导出按钮 */
const addedScriptTypes = ref<Set<ScriptType>>(new Set())
/** 脚本列表没读到：这时按「全都显示」处理，免得一次读取失败把所有导出入口都藏掉 */
const addedScriptTypesUnknown = ref(false)

const loadAddedScriptTypes = async () => {
  try {
    // 不接管 loading：这里只决定按钮显不显示，不该让整个设置页跟着转圈
    const scripts = await getScripts(false)
    // getScripts 读失败时不抛错，只把原因写进 error 并返回空数组，照收会误判成「一个专项都没加」
    if (scriptApiError.value) throw new Error(scriptApiError.value)
    addedScriptTypes.value = new Set(scripts.map(script => script.type))
    addedScriptTypesUnknown.value = false
  } catch (error) {
    addedScriptTypesUnknown.value = true
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`读取已添加脚本失败: ${errorMsg}`)
  }
}

/** 添加过其中任一专项才显示对应的导出按钮 */
const hasScriptType = (...types: ScriptType[]): boolean =>
  addedScriptTypesUnknown.value || types.some(type => addedScriptTypes.value.has(type))

// MFW 问题包按脚本导出：下拉里列出 MaaFW 与各特调的脚本，点哪个导哪个
const maafwScriptTypes = maafwScriptTypeByConfigType()
const maafwReportScripts = ref<Array<{ uid: string; name: string; flavor: MaaFWFlavor }>>([])

const loadMaaFWReportScripts = async () => {
  try {
    const scripts = await window.electronAPI?.listMaaFWIssueReportScripts?.(
      Object.keys(maafwScriptTypes)
    )
    maafwReportScripts.value = (scripts ?? []).map(script => ({
      uid: script.uid,
      name: script.name,
      flavor: resolveMaaFWFlavor(maafwScriptTypes[script.type]),
    }))
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`读取 MFW 脚本列表失败: ${errorMsg}`)
  }
}

const handleMaaFWMenuOpenChange = (open: boolean) => {
  if (open) void loadMaaFWReportScripts()
}

const handleMaaFWMenuClick = ({ key }: { key: string | number }) => {
  void exportMaaFWIssueReport(String(key))
}

/** 一块专项问题包磁贴：图标与名字统一取 scriptLogos，避免再引 core.scripts.type.* 的「脚本」后缀 */
interface IssueTile {
  type: ScriptType
  logo: string
  label: string
  visible: boolean
  loading: boolean
  /** 点击导出；MFW 走下拉，没有直接动作 */
  run?: () => void
  /** MFW 按脚本导出，磁贴改成下拉触发 */
  dropdown?: boolean
}

const tileOf = (
  type: ScriptType,
  loading: boolean,
  run?: () => void,
  visibleTypes: ScriptType[] = [type]
): IssueTile => ({
  type,
  logo: SCRIPT_LOGOS[type],
  label: SCRIPT_LABELS[type],
  visible: hasScriptType(...visibleTypes),
  loading,
  run,
})

// 顺序即页面顺序：MFW 仍夹在 BetterGI 与 M9A 之间，与改版前的按钮顺序保持一致
const issueTiles = computed<IssueTile[]>(() => [
  tileOf('MAA', exportingMaaLogs.value, () => void exportMaaIssueReport()),
  tileOf('MaaEnd', exportingMaaEndLogs.value, () => void exportMaaEndIssueReport()),
  tileOf('Okww', exportingOkwwLogs.value, () => void exportOkwwIssueReport()),
  tileOf('OkNte', exportingOkNteLogs.value, () => void exportOkNteIssueReport()),
  tileOf('ZzzOd', exportingZzzOdLogs.value, () => void exportZzzOdIssueReport()),
  tileOf('Whimbox', exportingWhimboxLogs.value, () => void exportWhimboxIssueReport()),
  tileOf('BetterGI', exportingBetterGILogs.value, () => void exportBetterGIIssueReport()),
  {
    ...tileOf('MaaFW', exportingMaaFWLogs.value, undefined, ['MaaFW', 'M9A', 'MSS']),
    dropdown: true,
  },
  tileOf('M9A', exportingM9ALogs.value, () => void exportM9AIssueReport()),
  tileOf('MSS', exportingMSSLogs.value, () => void exportMSSIssueReport()),
])

// Runtime 启动模式：持久化设置 + 当前生效值（重启后生效）
const runtimeLaunchMode = ref<RuntimeLaunchModeSetting>('auto')
const runtimeLaunchModeState = ref<RuntimeLaunchModeState | null>(null)
const runtimeLaunchModeLoading = ref(false)

const runtimeLaunchModeOptions = computed(() => [
  { label: t('core.setting.advanced.runtimeLaunchModeAuto'), value: 'auto' },
  { label: t('core.setting.advanced.runtimeLaunchModeManaged'), value: 'managed' },
])

const runtimeLaunchModeLabels: Record<'development' | 'managed', string> = {
  development: 'runtimeLaunchModeDevelopment',
  managed: 'runtimeLaunchModeManaged',
}

const effectiveModeLabel = computed(() => {
  const state = runtimeLaunchModeState.value
  return state ? t(`core.setting.advanced.${runtimeLaunchModeLabels[state.mode]}`) : ''
})

const loadRuntimeLaunchMode = async () => {
  try {
    const state = await window.electronAPI?.getRuntimeLaunchMode?.()
    if (!state) return
    runtimeLaunchModeState.value = state
    runtimeLaunchMode.value = state.persisted
    logger.info(`Runtime 启动方式: ${state.mode}（来源: ${state.source}）`)
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`读取 Runtime 启动方式失败: ${errorMsg}`)
  }
}

const handleRuntimeLaunchModeChange = async (value: unknown) => {
  if (typeof value !== 'string') return
  const mode = value as RuntimeLaunchModeSetting
  const previous = runtimeLaunchMode.value
  runtimeLaunchMode.value = mode
  runtimeLaunchModeLoading.value = true
  try {
    const state = await window.electronAPI?.setRuntimeLaunchMode?.(mode)
    if (state) {
      runtimeLaunchModeState.value = state
      logger.info(
        `Runtime 启动方式已保存: ${mode}，解析结果: ${state.mode}（来源: ${state.source}），重启后生效`
      )
    }
  } catch (error) {
    runtimeLaunchMode.value = previous
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`保存 Runtime 启动方式失败: ${errorMsg}`)
    message.error(t('core.setting.advanced.runtimeLaunchModeSaveFailed'))
  } finally {
    runtimeLaunchModeLoading.value = false
  }
}

onMounted(() => {
  void loadRuntimeLaunchMode()
  void loadMaaFWReportScripts()
  void loadAddedScriptTypes()
})

const exportDataBackup = async () => {
  exportingDataBackup.value = true
  try {
    const result = await window.electronAPI?.exportDataBackup?.()
    if (!result) {
      message.error(t('core.setting.toast.backupNoResponse'))
      logger.error('导出数据备份失败: 未收到响应')
      return
    }
    if (result.success) {
      message.success(result.message || t('core.setting.toast.backupExported'))
      logger.info(`数据备份导出成功: ${result.zipPath || '路径未知'}`)
      if (result.zipPath) await window.electronAPI?.showItemInFolder?.(result.zipPath)
    } else if (result.error !== '用户取消') {
      const errorMsg = result.error || t('core.setting.toast.backupExportFailed')
      logger.error(`导出数据备份失败: ${errorMsg}`)
      message.error(errorMsg)
    }
  } catch (error) {
    const errorMsg = error instanceof Error ? error.message : String(error)
    logger.error(`导出数据备份失败: ${errorMsg}`)
    message.error(t('core.setting.toast.backupExportError', { error: errorMsg }))
  } finally {
    exportingDataBackup.value = false
  }
}
</script>
<template>
  <div class="tab-content">
    <!-- 备份与导出：两条「标题 + 说明 + 按钮」的行，主色只留给最该被点的数据备份 -->
    <SectionCard
      :title="t('core.setting.advanced.backupExportSection')"
      :icon="CloudDownloadOutlined"
    >
      <div class="export-row">
        <div class="export-row-text">
          <span class="export-row-title">{{ t('core.setting.advanced.exportBackup') }}</span>
          <span class="export-row-desc">{{ t('core.setting.advanced.backupDesc') }}</span>
        </div>
        <a-button type="primary" :loading="exportingDataBackup" @click="exportDataBackup">
          {{ t('core.setting.advanced.exportAction') }}
        </a-button>
      </div>

      <div class="export-row">
        <div class="export-row-text">
          <span class="export-row-title">{{ t('core.setting.advanced.exportLog') }}</span>
          <span class="export-row-desc">{{ t('core.setting.advanced.exportLogDesc') }}</span>
        </div>
        <a-button :loading="exportingLogs" @click="exportLogsZip">
          {{ t('core.setting.advanced.exportAction') }}
        </a-button>
      </div>
    </SectionCard>

    <!-- 专项问题包：一个专项一块磁贴，只出现已添加的脚本；MFW 点开是脚本列表 -->
    <SectionCard
      :title="t('core.setting.advanced.issueSection')"
      :subtitle="t('core.setting.advanced.issueSectionDesc')"
      :icon="BugOutlined"
    >
      <p v-if="issueTiles.every(tile => !tile.visible)" class="issue-empty">
        {{ t('core.setting.advanced.issueSectionEmpty') }}
      </p>

      <div v-else class="issue-grid">
        <template v-for="tile in issueTiles" :key="tile.type">
          <a-dropdown
            v-if="tile.dropdown && tile.visible"
            :trigger="['click']"
            :disabled="tile.loading"
            @open-change="handleMaaFWMenuOpenChange"
          >
            <button type="button" class="issue-tile" :disabled="tile.loading">
              <img :src="tile.logo" alt="" class="issue-tile-logo" />
              <span class="issue-tile-name">{{ tile.label }}</span>
              <DownOutlined v-if="!tile.loading" class="issue-tile-action" aria-hidden="true" />
              <LoadingOutlined v-else class="issue-tile-action is-loading" aria-hidden="true" />
            </button>
            <template #overlay>
              <a-menu @click="handleMaaFWMenuClick">
                <a-menu-item v-for="script in maafwReportScripts" :key="script.uid">
                  {{ script.name }}
                  <a-tag :color="script.flavor.typeTagColor" class="maafw-report-tag">
                    {{ script.flavor.typeTagLabel }}
                  </a-tag>
                </a-menu-item>
                <a-menu-item v-if="maafwReportScripts.length === 0" key="" disabled>
                  {{ t('core.setting.advanced.exportMaaFWEmpty') }}
                </a-menu-item>
              </a-menu>
            </template>
          </a-dropdown>

          <button
            v-else-if="tile.visible"
            type="button"
            class="issue-tile"
            :disabled="tile.loading"
            @click="tile.run?.()"
          >
            <img :src="tile.logo" alt="" class="issue-tile-logo" />
            <span class="issue-tile-name">{{ tile.label }}</span>
            <DownloadOutlined v-if="!tile.loading" class="issue-tile-action" aria-hidden="true" />
            <LoadingOutlined v-else class="issue-tile-action is-loading" aria-hidden="true" />
          </button>
        </template>
      </div>
    </SectionCard>

    <SectionCard :title="t('core.setting.advanced.runtimeDebugSection')" :icon="CodeOutlined">
      <SettingRow
        :label="t('core.setting.advanced.runtimeLaunchMode')"
        :hint="t('core.setting.advanced.runtimeLaunchModeTip')"
      >
        <a-segmented
          :aria-label="t('core.setting.advanced.runtimeLaunchMode')"
          :value="runtimeLaunchMode"
          :options="runtimeLaunchModeOptions"
          :disabled="runtimeLaunchModeLoading"
          @change="handleRuntimeLaunchModeChange"
        />
        <span v-if="runtimeLaunchModeState" class="mode-effective">
          {{
            t('core.setting.advanced.runtimeLaunchModeEffective', {
              mode: effectiveModeLabel,
            })
          }}
          · {{ t('core.setting.advanced.runtimeLaunchModeRestartHint') }}
        </span>
      </SettingRow>

      <SettingRow :label="t('core.setting.advanced.devToolsLabel')">
        <a-button @click="openDevTools">{{ t('core.setting.advanced.openDevTools') }}</a-button>
      </SettingRow>
    </SectionCard>
  </div>
</template>

<style scoped>
.maafw-report-tag {
  margin-inline-start: 8px;
  margin-inline-end: 0;
}

/* 备份与导出：左说明右按钮，两条行分隔线与卡片内其它行一致 */
.export-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-height: 48px;
  padding: 10px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.export-row:last-child {
  padding-bottom: 0;
  border-bottom: 0;
}

.export-row-text {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.export-row-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
}

.export-row-desc {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

/* 一个专项都没添加时给一句说明，避免只留下一张空卡片 */
.issue-empty {
  margin: 0;
  padding: 12px 0 6px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

/* 专项问题包磁贴：默认低调的填充底色，hover 才亮主色，避免一屏全是主色块 */
.issue-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
  padding: 8px 0 6px;
}

.issue-tile {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  height: 48px;
  padding: 0 12px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 10px;
  background: var(--ant-color-fill-quaternary);
  color: var(--ant-color-text);
  font-size: 14px;
  line-height: 22px;
  text-align: start;
  cursor: pointer;
  transition:
    border-color 0.16s,
    background 0.16s;
}

.issue-tile:hover:not(:disabled) {
  border-color: var(--ant-color-primary);
}

.issue-tile:focus-visible {
  border-color: var(--ant-color-primary);
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.issue-tile:disabled {
  cursor: progress;
}

.issue-tile-logo {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  object-fit: contain;
}

.issue-tile-name {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.issue-tile-action {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  transition: color 0.16s;
}

.issue-tile:hover:not(:disabled) .issue-tile-action,
.issue-tile-action.is-loading {
  color: var(--ant-color-primary);
}

.mode-effective {
  flex: 1 1 240px;
  min-width: 0;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
  text-align: right;
}
</style>

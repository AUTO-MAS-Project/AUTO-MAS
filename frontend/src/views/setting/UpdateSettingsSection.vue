<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, ref } from 'vue'
import type { GlobalConfig } from '@/api'
import FluxdownSection from '@/views/setting/FluxdownSection.vue'
import MirrorCdkSettings from './components/MirrorCdkSettings.vue'
import { CloudDownloadOutlined, DownloadOutlined, SyncOutlined } from '@ant-design/icons-vue'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import StatusChip from '@/components/ui/StatusChip.vue'
import SelectableOptionCard from '@/components/SelectableOptionCard.vue'
import { formatPauseUntil, getPauseDisabledDate, isUpdatePaused } from '@/composables/updatePause'
import { formatConfigDate, serializeConfigTime } from '@/utils/configDateTime'

const { t } = useI18n()
const checkingUpdate = ref(false)
const emit = defineEmits<{ fluxdownInstalled: [] }>()

const { settings, updateSourceOptions, updateChannelOptions, handleSettingChange, checkUpdate } =
  defineProps<{
    settings: GlobalConfig
    updateSourceOptions: { label: string; value: string }[]
    updateChannelOptions: { label: string; value: string }[]
    handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
    checkUpdate: () => Promise<void>
  }>()

// MFW 项目包的 GitHub 加速镜像：与后端 Update.GitHubMirror 的 OptionsValidator 一致，
// 多给一项用户选了就会被静默纠回
const githubMirrorOptions = computed(() => [
  { label: t('core.setting.others.githubMirrorAutoShort'), value: 'Auto' },
  { label: t('core.setting.others.githubMirrorOffShort'), value: 'Off' },
])

// 每个更新源一句人话说明：只说用户关心的「这条路是什么」，具体链路留在 ⓘ
const sourceDescriptions = computed<Record<string, string>>(() => ({
  GitHub: t('core.setting.others.sourceGithubDesc'),
  MirrorChyan: t('core.setting.others.sourceMirrorDesc'),
  AutoSite: t('core.setting.others.sourceAutoSiteDesc'),
  CNB: t('core.setting.others.sourceCnbDesc'),
}))

// 暂停更新：暂停中展示状态胶囊，日期选择器始终可改（截止当天恢复）
const pauseUntil = computed(() => settings.Update?.PauseUntil ?? '')
const isPaused = computed(() => isUpdatePaused(pauseUntil.value))
// 回调内会取当前日期，创建一次即可（跨午夜也不会按旧边界放行）
const pauseDisabledDate = getPauseDisabledDate()
const pauseUntilDisplay = computed(() => formatPauseUntil(pauseUntil.value))

const handlePauseUntilChange = (value: string | null) => {
  void handleSettingChange(
    'Update',
    'PauseUntil',
    value ? serializeConfigTime(value + 'T00:00:00') : null
  )
}

// MirrorCdkSettings 只关心保存是否完成，这里吞掉布尔返回值
const handleCdkSettingChange = async (
  category: keyof GlobalConfig,
  key: string,
  value: unknown
): Promise<void> => {
  await handleSettingChange(category, key, value)
}

const handleCheckUpdate = async () => {
  if (checkingUpdate.value) return
  checkingUpdate.value = true
  try {
    await checkUpdate()
  } finally {
    checkingUpdate.value = false
  }
}
</script>

<template>
  <!-- 更新策略：什么时候检查、跟随哪个渠道、暂停到哪天 -->
  <SectionCard :title="t('core.setting.others.updateSection')" :icon="SyncOutlined">
    <template #actions>
      <a-button type="primary" :loading="checkingUpdate" @click="handleCheckUpdate">
        <template #icon><SyncOutlined aria-hidden="true" /></template>
        {{ t('core.setting.others.checkUpdate') }}
      </a-button>
    </template>
    <SettingRow :label="t('core.setting.others.updateBackend')">
      <a-switch
        :checked="!!settings.Update?.IfAutoUpdate"
        :aria-label="t('core.setting.others.updateBackend')"
        @change="
          (checked: boolean | string | number) =>
            handleSettingChange('Update', 'IfAutoUpdate', !!checked)
        "
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.others.updateChannel')"
      :hint="t('core.setting.others.updateChannelTip')"
    >
      <a-segmented
        :value="settings.Update?.Channel ?? 'stable'"
        :options="updateChannelOptions"
        @change="(value: any) => handleSettingChange('Update', 'Channel', value)"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.others.pauseUpdates')"
      :hint="t('core.setting.others.pauseUpdatesTip')"
    >
      <StatusChip v-if="isPaused" tone="warning" dot>
        {{ t('core.setting.others.pauseStatus', { date: pauseUntilDisplay }) }}
      </StatusChip>
      <a-date-picker
        :value="formatConfigDate(pauseUntil) || undefined"
        format="YYYY-MM-DD"
        value-format="YYYY-MM-DD"
        :disabled-date="pauseDisabledDate"
        :placeholder="t('core.setting.others.pausePlaceholder')"
        class="pause-picker"
        @change="handlePauseUntilChange"
      />
    </SettingRow>
  </SectionCard>

  <!-- 更新来源：从哪条线路拿包，走哪条网络链路 -->
  <SectionCard :title="t('core.setting.others.sourceSection')" :icon="CloudDownloadOutlined">
    <SettingRow
      stacked
      :label="t('core.setting.others.updateSource')"
      :hint="t('core.setting.others.updateSourceTip')"
    >
      <a-radio-group
        :value="settings.Update?.Source"
        class="source-cards"
        :aria-label="t('core.setting.others.updateSource')"
        @change="(event: any) => handleSettingChange('Update', 'Source', event.target.value)"
      >
        <SelectableOptionCard
          v-for="option in updateSourceOptions"
          :key="option.value"
          :value="option.value"
          :title="option.label"
          :description="sourceDescriptions[option.value]"
          :selected="settings.Update?.Source === option.value"
          align="start"
          radio-position="end"
          class="source-card"
        />
      </a-radio-group>
    </SettingRow>

    <MirrorCdkSettings :settings="settings" :handle-setting-change="handleCdkSettingChange" />

    <SettingRow :label="t('core.setting.others.proxy')" :hint="t('core.setting.others.proxyTip')">
      <a-input
        :value="settings.Update?.ProxyAddress"
        :placeholder="t('core.setting.others.proxyPlaceholder')"
        class="proxy-input"
        :aria-label="t('core.setting.others.proxy')"
        @blur="(event: any) => handleSettingChange('Update', 'ProxyAddress', event.target.value)"
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.others.githubMirror')"
      :hint="t('core.setting.others.githubMirrorTip')"
    >
      <a-segmented
        :value="settings.Update?.GitHubMirror ?? 'Auto'"
        :options="githubMirrorOptions"
        @change="(value: any) => handleSettingChange('Update', 'GitHubMirror', value)"
      />
    </SettingRow>
  </SectionCard>

  <!-- 下载与安装：更新包的下载方式与断点续传 -->
  <SectionCard :title="t('core.setting.others.downloadSection')" :icon="DownloadOutlined">
    <FluxdownSection
      :settings="settings"
      :handle-setting-change="handleSettingChange"
      @installed="emit('fluxdownInstalled')"
    />
  </SectionCard>
</template>

<style scoped>
.pause-picker {
  width: 168px;
}

.proxy-input {
  width: 204px;
  max-width: 100%;
}

.source-cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  width: 100%;
  gap: 8px;
}

.source-cards :deep(.source-card) {
  width: auto;
  min-width: 0;
}

@container (max-width: 360px) {
  .source-cards {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

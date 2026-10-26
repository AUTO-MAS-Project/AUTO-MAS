<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import { computed } from 'vue'
import type { GlobalConfig } from '@/api'
import FluxdownSection from '@/views/setting/FluxdownSection.vue'
import MirrorCdkSettings from './components/MirrorCdkSettings.vue'
import { formatPauseUntil, getPauseDisabledDate, isUpdatePaused } from '@/composables/updatePause'
import { formatConfigDate, serializeConfigTime } from '@/utils/configDateTime'

const { t } = useI18n()

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
  { label: t('setting.others.githubMirrorAuto'), value: 'Auto' },
  { label: t('setting.others.githubMirrorOff'), value: 'Off' },
])

// 暂停更新：暂停中只展示状态条，未暂停展示日期选择器（最短 1 天、最长 35 天）
const pauseUntil = computed(() => settings.Update?.PauseUntil ?? '')
const isPaused = computed(() => isUpdatePaused(pauseUntil.value))
// 回调内会取当前日期，创建一次即可（跨午夜也不会按旧边界放行）
const pauseDisabledDate = getPauseDisabledDate()
const pauseUntilDisplay = computed(() => formatPauseUntil(pauseUntil.value))

const handlePauseUntilChange = (value: string | null) => {
  void handleSettingChange(
    'Update',
    'PauseUntil',
    value ? serializeConfigTime(`${value}T00:00:00`) : null
  )
}
</script>
<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('setting.others.updateSection') }}</h3>
      <a-button type="primary" size="small" class="section-update-button" @click="checkUpdate">
        <template #icon>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
            <path
              d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
            />
          </svg>
        </template>
        {{ t('setting.others.checkUpdate') }}
      </a-button>
    </div>
    <!-- 暂停中：显著状态条（含副标题提示）；日期选择器常驻，暂停期间也可改截止日期 -->
    <a-alert
      v-if="isPaused"
      type="info"
      show-icon
      class="pause-status-alert"
      :message="t('setting.others.pauseStatus', { date: pauseUntilDisplay })"
      :description="t('setting.others.pauseStatusHint')"
    />
    <a-row :gutter="24">
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.others.pauseUpdates') }}</span>
            <a-tooltip :title="t('setting.others.pauseUpdatesTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-date-picker
            :value="formatConfigDate(pauseUntil) || undefined"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            :disabled-date="pauseDisabledDate"
            :placeholder="t('setting.others.pausePlaceholder')"
            size="large"
            style="width: 100%"
            @change="handlePauseUntilChange"
          />
        </div>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.others.updateBackend') }}</span>
            <a-tooltip :title="t('setting.others.updateBackendTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="settings.Update?.IfAutoUpdate"
            size="large"
            style="width: 100%"
            @change="(checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)"
          >
            <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
            <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
          </a-select>
        </div>
      </a-col>
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.others.updateSource') }}</span>
            <a-tooltip :title="t('setting.others.updateSourceTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="settings.Update?.Source"
            :options="updateSourceOptions"
            size="large"
            style="width: 100%"
            @change="(value: any) => handleSettingChange('Update', 'Source', value)"
          />
        </div>
      </a-col>
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.others.updateChannel') }}</span>
            <a-tooltip :title="t('setting.others.updateChannelTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-select
            :value="settings.Update?.Channel"
            :options="updateChannelOptions"
            size="large"
            style="width: 100%"
            @change="(value: any) => handleSettingChange('Update', 'Channel', value)"
          />
        </div>
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.others.proxy') }}</span>
            <a-tooltip :title="t('setting.others.proxyTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <a-input
            :value="settings.Update?.ProxyAddress"
            :placeholder="t('setting.others.proxyPlaceholder')"
            size="large"
            @blur="(e: any) => handleSettingChange('Update', 'ProxyAddress', e.target.value)"
          />
        </div>
      </a-col>
      <a-col :span="8">
        <div class="form-item-vertical">
          <div class="form-label-wrapper">
            <span class="form-label">{{ t('setting.others.githubMirror') }}</span>
            <a-tooltip :title="t('setting.others.githubMirrorTip')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </div>
          <!-- 只管 MFW 项目包从 GitHub Release 下载；MAS 自身更新与 Mirror 酱源不受影响 -->
          <a-select
            :value="settings.Update?.GitHubMirror ?? 'Auto'"
            :options="githubMirrorOptions"
            size="large"
            style="width: 100%"
            @change="(value: any) => handleSettingChange('Update', 'GitHubMirror', value)"
          />
        </div>
      </a-col>
      <a-col :span="8">
        <MirrorCdkSettings
          :settings="settings"
          :handle-setting-change="
            async (category, key, value) => {
              await handleSettingChange(category, key, value)
            }
          "
        />
      </a-col>
    </a-row>

    <!-- FluxDown 下载器配置：抽出独立子组件以控制本组件尺寸 -->
    <FluxdownSection :settings="settings" :handle-setting-change="handleSettingChange" />
  </div>
</template>

<style scoped>
.section-update-button {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.pause-status-alert {
  margin-bottom: 16px;
}
</style>

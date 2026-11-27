<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  DesktopOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import type { GlobalConfig } from '@/api'
import { useUpdateChecker } from '@/composables/useUpdateChecker'
import { openExternalUrl } from '@/utils/openExternal'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import { useSettingPersistence } from '@/views/setting/useSettingPersistence'
import { useVirtualDisplaySettings } from '../useVirtualDisplaySettings'

const { t } = useI18n()

// 开关与刷新率仍是全局设置里的 Display 字段，读写沿用设置页同一条保存链路（串行队列、埋点）。
const settings = reactive<GlobalConfig>({})
const { restartPolling } = useUpdateChecker()
const { handleSettingChange, refreshSettings } = useSettingPersistence(settings, restartPolling)

// 指向 releases 页而不是某一版安装包的直链：直链会随上游发版失效，而且点下去直接落一个 exe，
// 用户没机会先看清自己在装什么。releases/latest 永远指向最新一版，页面上的 `-setup.exe` 就是它。
const VDD_DOWNLOAD_URL = 'https://github.com/nomi-san/parsec-vdd/releases/latest'

// 分辨率固定 1920x1080：实测只有它 Windows 给 100% 缩放，再高会被自动上缩放，
// 游戏窗口又要面对 DPI 虚拟化——而虚拟屏本来就是为了绕开这类问题。所以这里只让用户
// 选刷新率。驱动的刷新率表是 24/30/60/144/240，写 120 会被 BADMODE 拒绝。
// 选项放在 computed 里，t() 是响应式的。
type VirtualDisplayMode = NonNullable<NonNullable<GlobalConfig['Display']>['VirtualDisplayMode']>
const virtualDisplayModeOptions = computed<{ label: string; value: VirtualDisplayMode }[]>(() => [
  { label: `60 Hz（${t('core.setting.display.refreshDefault')}）`, value: '1920x1080@60' },
  { label: `30 Hz（${t('core.setting.display.refreshLowPower')}）`, value: '1920x1080@30' },
])

const {
  vddHolding,
  vddSwitchDisabled,
  vddWarning,
  vddChecking,
  vddResult,
  vddAllPassed,
  runVirtualDisplayCheck,
  vddDetaching,
  runVirtualDisplayDetach,
} = useVirtualDisplaySettings(() => settings)

function openVddDownload() {
  openExternalUrl(VDD_DOWNLOAD_URL)
}

const handleVirtualDisplayModeChange = (value: unknown) => {
  const option = virtualDisplayModeOptions.value.find(option => option.value === value)
  if (option) void handleSettingChange('Display', 'VirtualDisplayMode', option.value)
}

onMounted(() => {
  void refreshSettings()
})
</script>

<template>
  <!-- 虚拟显示器：驱动下载入口收进卡片头部，操作按钮与检测结果留在卡片内 -->
  <SectionCard :title="t('core.setting.display.section')" :icon="DesktopOutlined" class="vdd-card">
    <template #actions>
      <a-button type="link" size="small" class="header-link" @click="openVddDownload">
        {{ t('core.setting.display.download') }}
      </a-button>
    </template>

    <!-- 原 intro 是一整段告警，正文只留驱动这一句，来龙去脉收进 ⓘ -->
    <p class="card-note">
      <span class="card-note-hint">
        {{ t('core.setting.display.introDriverLink') }}
        <a-tooltip :trigger="['hover', 'focus']">
          <template #title>
            <i18n-t keypath="core.setting.display.intro" tag="span" scope="global">
              <template #driverLink>{{ t('core.setting.display.introDriverLink') }}</template>
            </i18n-t>
          </template>
          <QuestionCircleOutlined
            class="help-icon"
            tabindex="0"
            :aria-label="t('core.setting.display.introDriverLink')"
          />
        </a-tooltip>
      </span>
    </p>

    <SettingRow
      :label="t('core.setting.display.enable')"
      :hint="t('core.setting.display.enableTip')"
    >
      <a-switch
        :checked="settings.Display?.IfEnableVirtualDisplay === true"
        :disabled="vddSwitchDisabled"
        :aria-label="t('core.setting.display.enable')"
        @change="
          (checked: boolean | string | number) =>
            handleSettingChange('Display', 'IfEnableVirtualDisplay', !!checked)
        "
      />
    </SettingRow>

    <SettingRow
      :label="t('core.setting.display.mode')"
      :hint="t('core.setting.display.modeTip')"
      child
      :disabled="!settings.Display?.IfEnableVirtualDisplay"
      :disabled-reason="t('core.setting.display.enableRequiredReason')"
    >
      <a-segmented
        :value="settings.Display?.VirtualDisplayMode"
        :options="virtualDisplayModeOptions"
        :disabled="!settings.Display?.IfEnableVirtualDisplay"
        :aria-label="t('core.setting.display.mode')"
        @change="handleVirtualDisplayModeChange"
      />
    </SettingRow>

    <div class="display-actions">
      <a-tooltip :title="t('core.setting.display.checkTip')">
        <a-button :loading="vddChecking" @click="runVirtualDisplayCheck">
          {{ t('core.setting.display.checkAction') }}
        </a-button>
      </a-tooltip>
      <a-tooltip :title="t('core.setting.display.detachTip')">
        <a-button
          danger
          :disabled="!settings.Display?.IfEnableVirtualDisplay"
          :loading="vddDetaching"
          @click="runVirtualDisplayDetach"
        >
          {{ t('core.setting.display.detachAction') }}
        </a-button>
      </a-tooltip>
    </div>

    <p v-if="settings.Display?.IfEnableVirtualDisplay" class="vdd-holding card-note">
      {{
        vddHolding
          ? t('core.setting.display.holdingNow', { holding: vddHolding })
          : t('core.setting.display.holdingNone')
      }}
    </p>

    <a-alert v-if="vddWarning" type="warning" show-icon class="vdd-result">
      <template #message>{{ vddWarning }}</template>
      <template #description>
        <a href="#" @click.prevent="openVddDownload">
          {{ t('core.setting.display.download') }}
        </a>
      </template>
    </a-alert>

    <a-alert
      v-if="vddResult"
      :type="vddAllPassed ? 'success' : 'warning'"
      show-icon
      class="vdd-result"
    >
      <template #message>
        {{
          vddAllPassed
            ? t('core.setting.display.checkPassed')
            : t('core.setting.display.checkIssue')
        }}
      </template>
      <template #description>
        <p v-if="!vddAllPassed && vddResult.message" class="vdd-summary">
          {{ vddResult.message }}
        </p>
        <ul class="vdd-result-list">
          <li v-for="item in vddResult.results ?? []" :key="item.stage">
            <CheckCircleOutlined v-if="item.passed" class="vdd-ok" />
            <CloseCircleOutlined v-else class="vdd-fail" />
            {{ t(`core.setting.display.stage.${item.stage}`) }} — {{ item.message }}
          </li>
        </ul>
        <p v-if="vddResult.monitors" class="vdd-monitors">
          {{ t('core.setting.display.monitors') }}: {{ vddResult.monitors }}
        </p>
        <p v-if="!(vddResult.results ?? []).some(item => item.stage === 'openable')">
          <a href="#" @click.prevent="openVddDownload">
            {{ t('core.setting.display.download') }}
          </a>
        </p>
      </template>
    </a-alert>
  </SectionCard>
</template>

<style scoped>
/* 标签页里只有这一张卡片，底部外边距交给 .tools-panel 的内边距 */
.vdd-card {
  margin-bottom: 0;
}

.help-icon:focus-visible {
  border-radius: 3px;
  outline: 2px solid var(--ant-color-primary);
  outline-offset: 2px;
}

.help-icon {
  flex: 0 0 auto;
  color: var(--ant-color-text-tertiary);
  font-size: 14px;
  cursor: help;
}

.card-note {
  margin: 0 0 8px;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1.6;
}

.card-note-hint {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.header-link {
  padding: 0;
  height: auto;
}

.display-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 0 8px;
}

.vdd-holding {
  margin: 0;
}

.vdd-result {
  margin-top: 12px;
}

.vdd-summary {
  margin: 0 0 8px;
}

.vdd-result-list {
  margin: 0;
  padding-left: 0;
  list-style: none;
}

.vdd-result-list li {
  margin: 4px 0;
}

.vdd-ok {
  color: var(--ant-color-success);
}

.vdd-fail {
  color: var(--ant-color-warning);
}

.vdd-monitors {
  margin: 8px 0 0;
  word-break: break-all;
  color: var(--ant-color-text-secondary);
}
</style>

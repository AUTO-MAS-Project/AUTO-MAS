<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed, onMounted, ref } from 'vue'
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { GlobalConfig, VirtualDisplayCheckOut } from '@/api'
import { ActionService, GetService } from '@/api'
import { handleExternalLink, openExternalUrl } from '@/utils/openExternal'

const { t } = useI18n()

// 指向 releases 页而不是某一版安装包的直链：直链会随上游发版失效，而且点下去直接落一个 exe，
// 用户没机会先看清自己在装什么。releases/latest 永远指向最新一版，页面上的 `-setup.exe` 就是它。
const VDD_DOWNLOAD_URL = 'https://github.com/nomi-san/parsec-vdd/releases/latest'

// 分辨率固定 1920x1080：实测只有它 Windows 给 100% 缩放，再高会被自动上缩放，
// 游戏窗口又要面对 DPI 虚拟化——而虚拟屏本来就是为了绕开这类问题。所以这里只让用户
// 选刷新率。驱动的刷新率表是 24/30/60/144/240，写 120 会被 BADMODE 拒绝。
// 选项放在 computed 里，t() 是响应式的。
const virtualDisplayModeOptions = computed(() => [
  { label: `60 Hz（${t('setting.display.refreshDefault')}）`, value: '1920x1080@60' },
  { label: `30 Hz（${t('setting.display.refreshLowPower')}）`, value: '1920x1080@30' },
])

// 驱动状态在打开设置页时实时探测一次（只跑前两段，不动桌面拓扑，实测 0.2ms）。
// 刻意不缓存也不持久化：存下来的状态只会变陈旧——驱动可能被卸载、被显卡驱动更新搞坏、
// 或者配置被同步到另一台机器，而实时问一次永远是对的。
const vddDriverReady = ref<boolean | null>(null)
const vddDriverMessage = ref('')
// 守卫此刻挂着的那块屏（设备名与模式），没挂时为 null。只是打开设置页时的一次快照，
// 「立即拆除」按钮不按它禁用——守卫几秒一轮，快照很快就旧了，点了没挂后端会说没挂。
const vddHolding = ref<string | null>(null)

async function refreshVirtualDisplayStatus() {
  try {
    const res = await GetService.virtualDisplayStatusApiSettingVirtualDisplayStatusPost()
    vddDriverReady.value = (res.results ?? []).every(item => item.passed)
    vddDriverMessage.value = res.message ?? ''
    vddHolding.value = res.holding ?? null
  } catch {
    // 探测不出来就不拦——宁可让用户开着不生效，也不要因为一次查询失败把功能锁死。
    vddDriverReady.value = null
    vddDriverMessage.value = ''
    vddHolding.value = null
  }
}

onMounted(refreshVirtualDisplayStatus)

// 驱动不可用时禁用开关，避免「开了但永远不生效」的假保障。
// 但**已经开着**的时候必须留出关掉的余地，否则用户连关都关不掉。
const vddSwitchDisabled = computed(
  () => vddDriverReady.value === false && !settings.Display?.IfEnableVirtualDisplay
)

const vddWarning = computed(() => {
  if (vddDriverReady.value !== false) return ''
  return settings.Display?.IfEnableVirtualDisplay
    ? t('setting.display.enabledButUnavailable', { reason: vddDriverMessage.value })
    : t('setting.display.driverUnavailable', { reason: vddDriverMessage.value })
})

const vddChecking = ref(false)
const vddResult = ref<VirtualDisplayCheckOut | null>(null)
// 结论这一行由前端出：后端文案是中文的，紧挨着英文标签太刺眼。明细仍用后端原文，
// 那里带着版本号、实际模式、错误详情这些动态内容，与全站其它后端文案一致。
const vddAllPassed = computed(() => (vddResult.value?.results ?? []).every(item => item.passed))

async function runVirtualDisplayCheck() {
  vddChecking.value = true
  try {
    vddResult.value = await GetService.checkVirtualDisplayApiSettingVirtualDisplayCheckPost()
    await refreshVirtualDisplayStatus()
  } catch (error) {
    vddResult.value = null
    message.error(t('setting.display.checkFailed'))
  } finally {
    vddChecking.value = false
  }
}

// 手动拆除：真实显示器回来时的询问弹窗之外的兜底入口——弹窗被关掉、或者用户想在任务
// 结束前把屏拆掉，都从这里走。任务在不在跑都照拆，那是用户的决定。
const vddDetaching = ref(false)

async function runVirtualDisplayDetach() {
  vddDetaching.value = true
  try {
    const res = await ActionService.detachVirtualDisplayApiSettingVirtualDisplayDetachPost()
    if (res.code !== 200) {
      message.error(`${t('setting.display.detachFailed')}: ${res.message}`)
      return
    }
    if (res.message === '当前没有挂载虚拟显示器') {
      message.info(t('setting.display.detachNothing'))
    } else {
      message.success(t('setting.display.detachDone'))
    }
    await refreshVirtualDisplayStatus()
  } catch {
    message.error(t('setting.display.detachFailed'))
  } finally {
    vddDetaching.value = false
  }
}

function openVddDownload() {
  openExternalUrl(VDD_DOWNLOAD_URL)
}

const { settings, historyRetentionOptions, voiceTypeOptions, handleSettingChange } = defineProps<{
  settings: GlobalConfig
  historyRetentionOptions: { label: string; value: number }[]
  voiceTypeOptions: { label: string; value: string }[]
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<void>
}>()
</script>
<template>
  <div class="tab-content">
    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.func.startupSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.autoStart') }}</span>
              <a-tooltip :title="t('setting.func.autoStartTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Start?.IfSelfStart"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.startMinimized') }}</span>
              <a-tooltip :title="t('setting.func.startMinimizedTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Start?.IfMinimizeDirectly"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Start', 'IfMinimizeDirectly', checked)
              "
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.func.featureSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.retention') }}</span>
              <a-tooltip :title="t('setting.func.retentionTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.HistoryRetentionTime"
              :options="historyRetentionOptions"
              size="large"
              style="width: 100%"
              @change="
                (value: any) => handleSettingChange('Function', 'HistoryRetentionTime', value)
              "
            />
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.silent') }}</span>
              <a-tooltip :title="t('setting.func.silentTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfSilence"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfSilence', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.preventSleep') }}</span>
              <a-tooltip :title="t('setting.func.preventSleepTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfAllowSleep"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
      <a-row :gutter="24">
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.telemetry') }}</span>
              <a-tooltip :title="t('setting.func.telemetryTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfEnableTelemetry !== false"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Function', 'IfEnableTelemetry', checked)
              "
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.biliPolicy') }}</span>
              <a-tooltip>
                <template #title>
                  <div style="max-width: 300px">
                    <p>{{ t('setting.func.biliIntro') }}</p>
                    <ul style="margin: 8px 0; padding-left: 16px">
                      <li>
                        <a
                          href="https://www.bilibili.com/protocal/licence.html"
                          class="tooltip-link"
                          @click="handleExternalLink"
                          >{{ t('setting.func.biliTerms') }}</a
                        >
                      </li>
                      <li>
                        <a
                          href="https://www.bilibili.com/blackboard/privacy-pc.html"
                          class="tooltip-link"
                          @click="handleExternalLink"
                          >{{ t('setting.func.biliPrivacy') }}</a
                        >
                      </li>
                      <li>
                        <a
                          href="https://game.bilibili.com/yhxy"
                          class="tooltip-link"
                          @click="handleExternalLink"
                          >{{ t('setting.func.biliGame') }}</a
                        >
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfAgreeBilibili"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Function', 'IfAgreeBilibili', checked)
              "
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="8">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.blockAds') }}</span>
              <a-tooltip>
                <template #title>
                  <div style="max-width: 300px">
                    <p>{{ t('setting.func.blockAdsIntro') }}</p>
                    <ul style="margin: 8px 0; padding-left: 16px">
                      <li>
                        <strong>{{ t('emulator.type.mumu') }}</strong
                        >: {{ t('setting.func.blockAdsMumu') }}
                      </li>
                      <li>
                        <strong>{{ t('emulator.type.ldplayer') }}</strong
                        >: {{ t('setting.func.blockAdsLd') }}
                      </li>
                    </ul>
                  </div>
                </template>
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Function?.IfBlockAd"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Function', 'IfBlockAd', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.func.voiceSection') }}</h3>
      </div>
      <a-row :gutter="24">
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.voiceEnable') }}</span>
              <a-tooltip :title="t('setting.func.voiceEnableTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Voice?.Enabled"
              size="large"
              style="width: 100%"
              @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)"
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="12">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.func.voiceType') }}</span>
              <a-tooltip :title="t('setting.func.voiceTypeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Voice?.Type"
              :options="voiceTypeOptions"
              :disabled="!settings.Voice?.Enabled"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
            />
          </div>
        </a-col>
      </a-row>
    </div>

    <div class="form-section">
      <div class="section-header">
        <h3>{{ t('setting.display.section') }}</h3>
      </div>
      <a-alert type="info" show-icon class="vdd-alert">
        <template #message>
          <i18n-t keypath="setting.display.intro" tag="span" scope="global">
            <template #driverLink>
              <a href="#" @click.prevent="openVddDownload">{{
                t('setting.display.introDriverLink')
              }}</a>
            </template>
          </i18n-t>
        </template>
      </a-alert>
      <a-row :gutter="24">
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.display.enable') }}</span>
              <a-tooltip :title="t('setting.display.enableTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Display?.IfEnableVirtualDisplay"
              :disabled="vddSwitchDisabled"
              size="large"
              style="width: 100%"
              @change="
                (checked: any) => handleSettingChange('Display', 'IfEnableVirtualDisplay', checked)
              "
            >
              <a-select-option :value="true">{{ t('common.yes') }}</a-select-option>
              <a-select-option :value="false">{{ t('common.no') }}</a-select-option>
            </a-select>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.display.mode') }}</span>
              <a-tooltip :title="t('setting.display.modeTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-select
              :value="settings.Display?.VirtualDisplayMode"
              :options="virtualDisplayModeOptions"
              :disabled="!settings.Display?.IfEnableVirtualDisplay"
              size="large"
              style="width: 100%"
              @change="(value: any) => handleSettingChange('Display', 'VirtualDisplayMode', value)"
            />
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.display.check') }}</span>
              <a-tooltip :title="t('setting.display.checkTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-button
              size="large"
              style="width: 100%"
              :loading="vddChecking"
              @click="runVirtualDisplayCheck"
            >
              {{ t('setting.display.checkAction') }}
            </a-button>
          </div>
        </a-col>
        <a-col :span="6">
          <div class="form-item-vertical">
            <div class="form-label-wrapper">
              <span class="form-label">{{ t('setting.display.detach') }}</span>
              <a-tooltip :title="t('setting.display.detachTip')">
                <QuestionCircleOutlined class="help-icon" />
              </a-tooltip>
            </div>
            <a-button
              danger
              size="large"
              style="width: 100%"
              :disabled="!settings.Display?.IfEnableVirtualDisplay"
              :loading="vddDetaching"
              @click="runVirtualDisplayDetach"
            >
              {{ t('setting.display.detachAction') }}
            </a-button>
          </div>
        </a-col>
      </a-row>
      <a-row v-if="settings.Display?.IfEnableVirtualDisplay" :gutter="24" class="vdd-result-row">
        <a-col :span="24">
          <p class="vdd-holding">
            {{
              vddHolding
                ? t('setting.display.holdingNow', { holding: vddHolding })
                : t('setting.display.holdingNone')
            }}
          </p>
        </a-col>
      </a-row>
      <a-row v-if="vddWarning" :gutter="24" class="vdd-result-row">
        <a-col :span="24">
          <a-alert type="warning" show-icon :message="vddWarning">
            <template #description>
              <a href="#" @click.prevent="openVddDownload">
                {{ t('setting.display.download') }}
              </a>
            </template>
          </a-alert>
        </a-col>
      </a-row>

      <a-row v-if="vddResult" :gutter="24" class="vdd-result-row">
        <a-col :span="24">
          <a-alert :type="vddAllPassed ? 'success' : 'warning'" show-icon>
            <template #message>
              {{
                vddAllPassed ? t('setting.display.checkPassed') : t('setting.display.checkIssue')
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
                  {{ t(`setting.display.stage.${item.stage}`) }} — {{ item.message }}
                </li>
              </ul>
              <p v-if="vddResult.monitors" class="vdd-monitors">
                {{ t('setting.display.monitors') }}: {{ vddResult.monitors }}
              </p>
              <p v-if="!(vddResult.results ?? []).some(item => item.stage === 'openable')">
                <a href="#" @click.prevent="openVddDownload">
                  {{ t('setting.display.download') }}
                </a>
              </p>
            </template>
          </a-alert>
        </a-col>
      </a-row>
    </div>
  </div>
</template>

<style scoped>
.vdd-alert {
  margin-bottom: 16px;
}

.vdd-result-row {
  margin-top: 16px;
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

.vdd-holding {
  margin: 0;
  font-size: 13px;
  color: var(--ant-color-text-secondary);
}
</style>

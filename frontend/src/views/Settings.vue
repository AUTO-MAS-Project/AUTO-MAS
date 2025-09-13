<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import {
  QuestionCircleOutlined,
  HomeOutlined,
  GithubOutlined,
  QqOutlined,
} from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { ThemeColor, ThemeMode } from '../composables/useTheme'
import { useTheme } from '../composables/useTheme.ts'
import { useSettingsApi } from '../composables/useSettingsApi'
import { useUpdateChecker } from '../composables/useUpdateChecker'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { SettingsData } from '../types/settings'
import { Service, type VersionOut } from '@/api'
import UpdateModal from '@/components/UpdateModal.vue'
import { mirrorManager } from '@/utils/mirrorManager'

const updateData = ref<Record<string, string[]>>({})

const app_version = import.meta.env.VITE_APP_VERSION || '获取版本失败！'

const router = useRouter()
const { themeMode, themeColor, themeColors, setThemeMode, setThemeColor } = useTheme()
const { loading, getSettings, updateSettings } = useSettingsApi()
const { restartPolling } = useUpdateChecker()

const updateVisible = ref(false)

const activeKey = ref('basic')

const backendUpdateInfo = ref<VersionOut | null>(null)

// 镜像配置相关状态
const mirrorConfigStatus = ref({
  isUsingCloudConfig: false,
  version: '',
  lastUpdated: '',
  source: 'fallback' as 'cloud' | 'fallback'
})
const refreshingConfig = ref(false)

const settings = reactive<SettingsData>({
  UI: {
    IfShowTray: false,
    IfToTray: false,
  },
  Function: {
    BossKey: '',
    HistoryRetentionTime: 0,
    IfAgreeBilibili: false,
    IfAllowSleep: false,
    IfSilence: false,
    IfSkipMumuSplashAds: false,
  },
  Notify: {
    SendTaskResultTime: '不推送',
    IfSendStatistic: false,
    IfSendSixStar: false,
    IfPushPlyer: false,
    IfSendMail: false,
    SMTPServerAddress: '',
    AuthorizationCode: '',
    FromAddress: '',
    ToAddress: '',
    IfServerChan: false,
    ServerChanKey: '',
    ServerChanChannel: '',
    ServerChanTag: '',
    IfCompanyWebHookBot: false,
    CompanyWebHookBotUrl: '',
  },
  Voice: {
    Enabled: false,
    Type: 'simple',
  },
  Start: {
    IfSelfStart: false,
    IfMinimizeDirectly: false,
  },
  Update: {
    IfAutoUpdate: false,
    Source: 'GitHub',
    ProxyAddress: '',
    MirrorChyanCDK: '',
  },
})

// 选项配置
const historyRetentionOptions = [
  { label: '7天', value: 7 },
  { label: '15天', value: 15 },
  { label: '30天', value: 30 },
  { label: '60天', value: 60 },
  { label: '90天', value: 90 },
  { label: '180天', value: 180 },
  { label: '365天', value: 365 },
  { label: '永久保留', value: 0 },
]

const sendTaskResultTimeOptions = [
  { label: '不推送', value: '不推送' },
  { label: '任何时刻', value: '任何时刻' },
  { label: '仅失败时', value: '仅失败时' },
]

const updateSourceOptions = [
  { label: 'GitHub', value: 'GitHub' },
  { label: 'Mirror酱', value: 'MirrorChyan' },
  { label: '自建下载站', value: 'AutoSite' },
]

const voiceTypeOptions = [
  { label: '简洁', value: 'simple' },
  { label: '聒噪', value: 'noisy' },
]

const themeModeOptions = [
  { label: '跟随系统', value: 'system' },
  { label: '浅色模式', value: 'light' },
  { label: '深色模式', value: 'dark' },
]

const themeColorLabels: Record<ThemeColor, string> = {
  blue: '蓝色',
  purple: '紫色',
  cyan: '青色',
  green: '绿色',
  magenta: '洋红',
  pink: '粉色',
  red: '红色',
  orange: '橙色',
  yellow: '黄色',
  volcano: '火山红',
  geekblue: '极客蓝',
  lime: '青柠',
  gold: '金色',
}

const themeColorOptions = Object.entries(themeColors).map(([key, color]) => ({
  label: themeColorLabels[key as ThemeColor],
  value: key,
  color,
}))

const loadSettings = async () => {
  const data = await getSettings()
  if (data) {
    Object.assign(settings, data)
  }
}

const saveSettings = async (category: keyof SettingsData, changes: any) => {
  try {
    console.log('保存设置到后端:', { category, changes })
    const updateData = { [category]: changes }
    const result = await updateSettings(updateData)
    if (result) {
      console.log('后端设置保存成功')
      // message.success('设置保存成功')
    } else {
      console.error('后端设置保存失败')
      message.error('设置保存失败')
    }
  } catch (error) {
    console.error('保存设置异常:', error)
    message.error('设置保存失败')
  }
}

const handleSettingChange = async (category: keyof SettingsData, key: string, value: any) => {
  console.log(`设置变更: ${category}.${key} = ${value}`)
  const changes = { [key]: value }
  await saveSettings(category, changes)

  // 如果是UI设置的托盘相关配置，立即更新托盘状态
  if (category === 'UI' && (key === 'IfShowTray' || key === 'IfToTray')) {
    try {
      console.log('检测到托盘设置变更，尝试更新托盘状态...')
      if ((window as any).electronAPI && (window as any).electronAPI.updateTraySettings) {
        console.log('调用 electronAPI.updateTraySettings:', { [key]: value })
        await (window as any).electronAPI.updateTraySettings({ [key]: value })
      } else {
        console.warn('electronAPI.updateTraySettings 不可用')
      }
    } catch (error) {
      console.error('更新托盘设置失败:', error)
      message.error('托盘设置更新失败')
    }
  }

  // 如果是自动检查更新设置变更，重新启动定时任务
  if (category === 'Update' && key === 'IfAutoUpdate') {
    try {
      console.log(`检测到自动检查更新设置变更: ${value}`)
      await restartPolling()
      if (value) {
        message.success('已启用自动检查更新')
      } else {
        message.success('已禁用自动检查更新')
      }
    } catch (error) {
      console.error('重新启动更新检查任务失败:', error)
      message.error('更新检查设置变更失败')
    }
  }
}

const getBackendVersion = async () => {
  try {
    backendUpdateInfo.value = await Service.getGitVersionApiInfoVersionPost()
  } catch (error) {
    console.error('Failed to get backend version:', error)
    return '获取后端版本失败！'
  }
}

const handleThemeModeChange = (e: any) => {
  setThemeMode(e.target.value as ThemeMode)
}

const handleThemeColorChange = (value: SelectValue) => {
  if (typeof value === 'string') {
    setThemeColor(value as ThemeColor)
  }
}

const goToLogs = () => {
  router.push('/logs')
}

const openDevTools = () => {
  if ((window as any).electronAPI) {
    ;(window as any).electronAPI.openDevTools()
  }
}

const version = import.meta.env.VITE_APP_VERSION || '获取版本失败！'

const checkUpdate = async () => {
  try {
    const response = await Service.checkUpdateApiUpdateCheckPost({
      current_version: version,
      if_force: true, // 手动检查强制获取最新信息
    })
    if (response.code === 200) {
      if (response.if_need_update) {
        updateData.value = response.update_info
        updateVisible.value = true
      } else {
        message.success('暂无更新~')
      }
    } else {
      message.error(response.message || '获取更新失败')
    }
  } catch (error) {
    console.error('获取更新失败:', error)
    message.error('获取更新失败！')
  }
}

// 镜像配置相关方法
const updateMirrorConfigStatus = () => {
  const status = mirrorManager.getConfigStatus()
  mirrorConfigStatus.value = status
}

const refreshMirrorConfig = async () => {
  refreshingConfig.value = true
  try {
    const result = await mirrorManager.refreshCloudConfig()
    if (result.success) {
      message.success('镜像配置刷新成功')
      updateMirrorConfigStatus()
    } else {
      message.warning(result.error || '刷新失败，继续使用当前配置')
    }
  } catch (error) {
    console.error('刷新镜像配置失败:', error)
    message.error('刷新镜像配置失败')
  } finally {
    refreshingConfig.value = false
  }
}

const goToMirrorTest = () => {
  router.push('/mirror-test')
}

// 确认回调
const onUpdateConfirmed = () => {
  updateVisible.value = false
}

onMounted(() => {
  loadSettings()
  getBackendVersion()
  updateMirrorConfigStatus()
})
</script>

<template>
  <div class="settings-container">
    <div class="settings-header">
      <h1 class="page-title">设置</h1>
    </div>

    <div class="settings-content">
      <a-tabs v-model:activeKey="activeKey" type="card" :loading="loading" class="settings-tabs">
        <!-- 界面设置 -->
        <a-tab-pane key="basic" tab="界面设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>外观配置</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">主题模式</span>
                      <a-tooltip title="界面外观主题">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-radio-group
                      :value="themeMode"
                      @change="handleThemeModeChange"
                      :options="themeModeOptions"
                      size="large"
                    />
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">主题色</span>
                      <a-tooltip title="界面主色调">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      :value="themeColor"
                      @change="handleThemeColorChange"
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option
                        v-for="option in themeColorOptions"
                        :key="option.value"
                        :value="option.value"
                      >
                        <div style="display: flex; align-items: center; gap: 8px">
                          <div
                            :style="{
                              width: '16px',
                              height: '16px',
                              borderRadius: '50%',
                              backgroundColor: option.color,
                            }"
                          />
                          {{ option.label }}
                        </div>
                      </a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h3>系统托盘</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">常态显示托盘图标</span>
                      <a-tooltip title="即使界面未最小化仍显示系统托盘图标">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.UI.IfShowTray"
                      @change="(checked: any) => handleSettingChange('UI', 'IfShowTray', checked)"
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">最小化到托盘</span>
                      <a-tooltip title="界面最小化时隐藏到系统托盘">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.UI.IfToTray"
                      @change="(checked: any) => handleSettingChange('UI', 'IfToTray', checked)"
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 功能设置 -->
        <a-tab-pane key="function" tab="功能设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>功能设置</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">历史记录保留时间</span>
                      <a-tooltip title="超过该时间的历史记录将被自动清理">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Function.HistoryRetentionTime"
                      @change="
                        (value: any) =>
                          handleSettingChange('Function', 'HistoryRetentionTime', value)
                      "
                      :options="historyRetentionOptions"
                      size="large"
                      style="width: 100%"
                    />
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">运行时阻止系统休眠</span>
                      <a-tooltip title="程序运行时阻止系统进入休眠状态，不影响电脑进入熄屏">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Function.IfAllowSleep"
                      @change="
                        (checked: any) => handleSettingChange('Function', 'IfAllowSleep', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">静默模式</span>
                      <a-tooltip title="将各代理窗口置于后台运行，减少对前台的干扰">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Function.IfSilence"
                      @change="
                        (checked: any) => handleSettingChange('Function', 'IfSilence', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">模拟器老板键</span>
                      <a-tooltip
                        title="程序依靠模拟器老板键隐藏模拟器窗口，需要开启静默模式后才能填写，请直接输入文字，多个键位之间请用「+」隔开"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Function.BossKey"
                      @blur="handleSettingChange('Function', 'BossKey', settings.Function.BossKey)"
                      :disabled="!settings.Function.IfSilence"
                      placeholder="请输入对应模拟器老板键，例如: Alt+Q"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">托管Bilibili游戏隐私政策</span>
                      <a-tooltip>
                        <template #title>
                          <div style="max-width: 300px">
                            <p>
                              开启本项即代表您已完整阅读并同意以下协议，并授权本程序在其认定需要时以其认定合适的方法替您处理相关弹窗：
                            </p>
                            <ul style="margin: 8px 0; padding-left: 16px">
                              <li>
                                <a
                                  href="https://www.bilibili.com/protocal/licence.html"
                                  target="_blank"
                                  class="tooltip-link"
                                  @click.stop
                                >
                                  《哔哩哔哩弹幕网用户使用协议》
                                </a>
                              </li>
                              <li>
                                <a
                                  href="https://www.bilibili.com/blackboard/privacy-pc.html"
                                  target="_blank"
                                  class="tooltip-link"
                                  @click.stop
                                >
                                  《哔哩哔哩隐私政策》
                                </a>
                              </li>
                              <li>
                                <a
                                  href="https://game.bilibili.com/yhxy"
                                  target="_blank"
                                  class="tooltip-link"
                                  @click.stop
                                >
                                  《哔哩哔哩游戏中心用户协议》
                                </a>
                              </li>
                            </ul>
                          </div>
                        </template>
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Function.IfAgreeBilibili"
                      @change="
                        (checked: any) =>
                          handleSettingChange('Function', 'IfAgreeBilibili', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">屏蔽MuMu启动广告</span>
                      <a-tooltip title="MuMu模拟器启动时屏蔽启动广告">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Function.IfSkipMumuSplashAds"
                      @change="
                        (checked: any) =>
                          handleSettingChange('Function', 'IfSkipMumuSplashAds', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 通知设置 -->
        <a-tab-pane key="notify" tab="通知设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>通知内容</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="8">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">推送任务结果时机</span>
                      <a-tooltip title="在选定的时机推送任务执行结果">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.SendTaskResultTime"
                      @change="
                        (value: any) => handleSettingChange('Notify', 'SendTaskResultTime', value)
                      "
                      :options="sendTaskResultTimeOptions"
                      size="large"
                      style="width: 100%"
                    />
                  </div>
                </a-col>
                <a-col :span="8">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">推送统计信息</span>
                      <a-tooltip title="推送自动代理统计信息的通知">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.IfSendStatistic"
                      @change="
                        (checked: any) => handleSettingChange('Notify', 'IfSendStatistic', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="8">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">推送公招高资喜报</span>
                      <a-tooltip title="公招出现「高级资深干员」词条时推送喜报">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.IfSendSixStar"
                      @change="
                        (checked: any) => handleSettingChange('Notify', 'IfSendSixStar', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h3>系统通知</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">启用系统通知</span>
                      <a-tooltip title="使用plyer推送系统级通知，不会在通知中心停留">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.IfPushPlyer"
                      @change="
                        (checked: any) => handleSettingChange('Notify', 'IfPushPlyer', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h3>邮件通知</h3>
                <a
                  href="https://doc.auto-mas.top/docs/advanced-features.html#smtp-%E9%82%AE%E4%BB%B6%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
                  target="_blank"
                  class="section-doc-link"
                  title="查看电子邮箱配置文档"
                >
                  文档
                </a>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">启用邮件通知</span>
                      <a-tooltip title="使用电子邮件推送通知">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.IfSendMail"
                      @change="
                        (checked: any) => handleSettingChange('Notify', 'IfSendMail', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">SMTP服务器地址</span>
                      <a-tooltip title="发信邮箱的SMTP服务器地址">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Notify.SMTPServerAddress"
                      @blur="
                        handleSettingChange(
                          'Notify',
                          'SMTPServerAddress',
                          settings.Notify.SMTPServerAddress
                        )
                      "
                      :disabled="!settings.Notify.IfSendMail"
                      placeholder="请输入发信邮箱SMTP服务器地址"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">发信邮箱地址</span>
                      <a-tooltip title="发送通知的邮箱地址">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Notify.FromAddress"
                      @blur="
                        handleSettingChange('Notify', 'FromAddress', settings.Notify.FromAddress)
                      "
                      :disabled="!settings.Notify.IfSendMail"
                      placeholder="请输入发信邮箱地址"
                      size="large"
                    />
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">发信邮箱授权码</span>
                      <a-tooltip title="用于替代您的邮箱密码进行第三方客户端登录的一种特殊密码">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input-password
                      v-model:value="settings.Notify.AuthorizationCode"
                      @blur="
                        handleSettingChange(
                          'Notify',
                          'AuthorizationCode',
                          settings.Notify.AuthorizationCode
                        )
                      "
                      :disabled="!settings.Notify.IfSendMail"
                      placeholder="请输入发信邮箱授权码"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">收信邮箱地址</span>
                      <a-tooltip title="接收邮件的邮箱地址">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Notify.ToAddress"
                      @blur="handleSettingChange('Notify', 'ToAddress', settings.Notify.ToAddress)"
                      :disabled="!settings.Notify.IfSendMail"
                      placeholder="请输入收信邮箱地址"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h3>Server酱通知</h3>
                <a
                  href="https://doc.auto-mas.top/docs/advanced-features.html#serverchan-%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
                  target="_blank"
                  class="section-doc-link"
                  title="查看Server酱配置文档"
                >
                  文档
                </a>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">启用Server酱通知</span>
                      <a-tooltip>
                        <template #title>
                          <div>使用Server酱推送通知</div>
                        </template>
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.IfServerChan"
                      @change="
                        (checked: any) => handleSettingChange('Notify', 'IfServerChan', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">Server酱Key</span>
                      <a-tooltip>
                        <template #title>
                          <div>Server酱的SendKey，请自行查看文档以获取</div>
                        </template>
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Notify.ServerChanKey"
                      @blur="
                        handleSettingChange(
                          'Notify',
                          'ServerChanKey',
                          settings.Notify.ServerChanKey
                        )
                      "
                      :disabled="!settings.Notify.IfServerChan"
                      placeholder="请输入Server酱SendKey"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h3>企业微信机器人通知</h3>
                <a
                  href="https://doc.auto-mas.top/docs/advanced-features.html#%E4%BC%81%E4%B8%9A%E5%BE%AE%E4%BF%A1%E7%BE%A4%E6%9C%BA%E5%99%A8%E4%BA%BA%E9%80%9A%E7%9F%A5%E6%8E%A8%E9%80%81%E6%B8%A0%E9%81%93"
                  target="_blank"
                  class="section-doc-link"
                  title="查看企业微信机器人配置文档"
                >
                  文档
                </a>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">启用企业微信机器人通知</span>
                      <a-tooltip title="使用企业微信机器人推送通知">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Notify.IfCompanyWebHookBot"
                      @change="
                        (checked: any) =>
                          handleSettingChange('Notify', 'IfCompanyWebHookBot', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">Webhook URL</span>
                      <a-tooltip title="企业微信机器人的Webhook地址">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Notify.CompanyWebHookBotUrl"
                      @blur="
                        handleSettingChange(
                          'Notify',
                          'CompanyWebHookBotUrl',
                          settings.Notify.CompanyWebHookBotUrl
                        )
                      "
                      :disabled="!settings.Notify.IfCompanyWebHookBot"
                      placeholder="请输入Webhook URL"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 更新设置 -->
        <a-tab-pane key="update" tab="更新设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>更新配置</h3>
                <a-button 
                  type="primary" 
                  @click="checkUpdate" 
                  size="medium" 
                  class="section-update-button"
                >
                  <template #icon>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
                      <path
                        d="M12 4V1L8 5l4 4V6c3.31 0 6 2.69 6 6 0 1.01-.25 1.97-.7 2.8l1.46 1.46C19.54 15.03 20 13.57 20 12c0-4.42-3.58-8-8-8zm0 14c-3.31 0-6-2.69-6-6 0-1.01.25-1.97.7-2.8L5.24 7.74C4.46 8.97 4 10.43 4 12c0 4.42 3.58 8 8 8v3l4-4-4-4v3z"
                      />
                    </svg>
                  </template>
                  检查更新
                </a-button>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">自动检查更新</span>
                      <a-tooltip title="启动时自动检测软件更新">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Update.IfAutoUpdate"
                      @change="
                        (checked: any) => handleSettingChange('Update', 'IfAutoUpdate', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">更新源</span>
                      <a-tooltip title="选择下载软件更新的来源">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Update.Source"
                      @change="(value: any) => handleSettingChange('Update', 'Source', value)"
                      :options="updateSourceOptions"
                      size="large"
                      style="width: 100%"
                    />
                  </div>
                </a-col>
              </a-row>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">网络代理地址</span>
                      <a-tooltip
                        title="使用网络代理软件时，若出现网络连接问题，请尝试设置代理地址，此设置全局生效"
                      >
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Update.ProxyAddress"
                      @blur="
                        handleSettingChange('Update', 'ProxyAddress', settings.Update.ProxyAddress)
                      "
                      placeholder="请输入网络代理地址"
                      size="large"
                    />
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">Mirror酱 CDK</span>
                      <a-tooltip>
                        <template #title>
                          <div>
                            Mirror酱CDK是使用Mirror源进行高速下载的凭证，可前往
                            <a
                              href="https://mirrorchyan.com/zh/get-start?source=auto-mas-setting"
                              target="_blank"
                              class="tooltip-link"
                              @click.stop
                            >
                              Mirror酱官网
                            </a>
                            获取
                          </div>
                        </template>
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-input
                      v-model:value="settings.Update.MirrorChyanCDK"
                      @blur="
                        handleSettingChange(
                          'Update',
                          'MirrorChyanCDK',
                          settings.Update.MirrorChyanCDK
                        )
                      "
                      :disabled="settings.Update.Source !== 'MirrorChyan'"
                      placeholder="使用Mirror源时请输入Mirror酱CDK"
                      size="large"
                    />
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 启动设置 -->
        <a-tab-pane key="start" tab="启动设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>启动配置</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">开机自启</span>
                      <a-tooltip title="在系统启动时自动启动应用">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Start.IfSelfStart"
                      @change="
                        (checked: any) => handleSettingChange('Start', 'IfSelfStart', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">启动后直接最小化</span>
                      <a-tooltip title="启动后直接最小化">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Start.IfMinimizeDirectly"
                      @change="
                        (checked: any) =>
                          handleSettingChange('Start', 'IfMinimizeDirectly', checked)
                      "
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 语音设置 -->
        <a-tab-pane key="voice" tab="语音设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>语音配置</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">启用音效</span>
                      <a-tooltip title="是否启用音效功能">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Voice.Enabled"
                      @change="(checked: any) => handleSettingChange('Voice', 'Enabled', checked)"
                      size="large"
                      style="width: 100%"
                    >
                      <a-select-option :value="true">是</a-select-option>
                      <a-select-option :value="false">否</a-select-option>
                    </a-select>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">音效模式</span>
                      <a-tooltip title="选择音效的播报模式">
                        <QuestionCircleOutlined class="help-icon" />
                      </a-tooltip>
                    </div>
                    <a-select
                      v-model:value="settings.Voice.Type"
                      @change="(value: any) => handleSettingChange('Voice', 'Type', value)"
                      :options="voiceTypeOptions"
                      :disabled="!settings.Voice.Enabled"
                      size="large"
                      style="width: 100%"
                    />
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 高级设置 -->
        <a-tab-pane key="advanced" tab="高级设置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>开发者选项</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="24">
                  <a-space size="large">
                    <a-button type="primary" @click="goToLogs" size="large"> 查看日志 </a-button>
                    <a-button @click="openDevTools" size="large"> 打开开发者工具 </a-button>
                  </a-space>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 镜像配置 -->
        <a-tab-pane key="mirrors" tab="镜像配置">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>镜像站配置</h3>
                <p class="section-description">
                  管理下载站和加速站配置，支持从云端自动更新最新的镜像站列表
                </p>
              </div>
              
              <a-row :gutter="24">
                <a-col :span="24">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">配置状态</span>
                    </div>
                    <a-descriptions :column="1" bordered size="small">
                      <a-descriptions-item label="配置来源">
                        <a-tag :color="mirrorConfigStatus.source === 'cloud' ? 'green' : 'orange'">
                          {{ mirrorConfigStatus.source === 'cloud' ? '云端配置' : '本地兜底配置' }}
                        </a-tag>
                      </a-descriptions-item>
                      <a-descriptions-item label="配置版本" v-if="mirrorConfigStatus.version">
                        {{ mirrorConfigStatus.version }}
                      </a-descriptions-item>
                      <a-descriptions-item label="最后更新" v-if="mirrorConfigStatus.lastUpdated">
                        {{ new Date(mirrorConfigStatus.lastUpdated).toLocaleString() }}
                      </a-descriptions-item>
                    </a-descriptions>
                  </div>
                </a-col>
              </a-row>

              <a-row :gutter="24" style="margin-top: 24px;">
                <a-col :span="24">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">配置管理</span>
                    </div>
                    <a-space size="large">
                      <a-button 
                        type="primary" 
                        @click="refreshMirrorConfig"
                        :loading="refreshingConfig"
                        size="large"
                      >
                        更新云端最新配置
                      </a-button>
<!--                      <a-button -->
<!--                        @click="updateMirrorConfigStatus"-->
<!--                        size="large"-->
<!--                      >-->
<!--                        更新状态-->
<!--                      </a-button>-->
                      <a-button 
                        @click="goToMirrorTest"
                        size="large"
                      >
                        测试页面
                      </a-button>
                    </a-space>
                  </div>
                </a-col>
              </a-row>

              <a-row :gutter="24" style="margin-top: 24px;">
                <a-col :span="24">
                  <div class="form-item-vertical">
                    <div class="form-label-wrapper">
                      <span class="form-label">说明</span>
                    </div>
                    <a-alert
                      message="镜像配置说明"
                      type="info"
                      show-icon
                    >
                      <template #description>
                        <ul style="margin: 8px 0; padding-left: 20px;">
                          <li>应用启动时会自动尝试从云端拉取最新的镜像站配置</li>
                          <li>可以手动点击"刷新云端配置"按钮获取最新配置</li>
                        </ul>
                      </template>
                    </a-alert>
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>

        <!-- 其他 -->
        <a-tab-pane key="others" tab="其他">
          <div class="tab-content">
            <div class="form-section">
              <div class="section-header">
                <h3>项目链接</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="8">
                  <div class="link-card">
                    <div class="link-icon">
                      <HomeOutlined />
                    </div>
                    <div class="link-content">
                      <h4>软件官网</h4>
                      <p>查看最新版本和功能介绍</p>
                      <a href="https://auto-mas.top" target="_blank" class="link-button">
                        访问官网
                      </a>
                    </div>
                  </div>
                </a-col>
                <a-col :span="8">
                  <div class="link-card">
                    <div class="link-icon">
                      <GithubOutlined />
                    </div>
                    <div class="link-content">
                      <h4>GitHub仓库</h4>
                      <p>查看源代码、提交issue和贡献</p>
                      <a
                        href="https://github.com/AUTO-MAS-Project/AUTO-MAS"
                        target="_blank"
                        class="link-button"
                      >
                        访问仓库
                      </a>
                    </div>
                  </div>
                </a-col>
                <a-col :span="8">
                  <div class="link-card">
                    <div class="link-icon">
                      <QqOutlined />
                    </div>
                    <div class="link-content">
                      <h4>用户QQ群</h4>
                      <p>加入社区，获取帮助和交流</p>
                      <a href="https://qm.qq.com/q/bd9fISNoME" target="_blank" class="link-button">
                        加入群聊
                      </a>
                    </div>
                  </div>
                </a-col>
              </a-row>
            </div>

            <div class="form-section">
              <div class="section-header">
                <h3>应用信息</h3>
              </div>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="info-item">
                    <span class="info-label">软件名称：</span>
                    <span class="info-value">AUTO-MAS</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">许可证：</span>
                    <span class="info-value">GPL-3.0 license</span>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="info-item">
                    <span class="info-label">开发者：</span>
                    <span class="info-value">AUTO-MAS Team</span>
                  </div>
                  <!--                  <div class="info-item">-->
                  <!--                    <span class="info-label">当前版本：</span>-->
                  <!--                    <span class="info-value">{{app_version}}</span>-->
                  <!--                  </div>-->
                </a-col>
              </a-row>
              <a-divider></a-divider>
              <a-row :gutter="24">
                <a-col :span="12">
                  <div class="info-item">
                    <span class="info-label">当前前端版本：</span>
                    <span class="info-value">{{ version }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">当前后端哈希值：</span>
                    <span class="info-value">{{ backendUpdateInfo?.current_hash }}</span>
                  </div>
                </a-col>
                <a-col :span="12">
                  <div class="info-item">
                    <span class="info-label">当前后端版本：</span>
                    <span class="info-value">{{ backendUpdateInfo?.current_version }}</span>
                  </div>
                  <div class="info-item">
                    <span class="info-label">后端更新时间：</span>
                    <span class="info-value">{{ backendUpdateInfo?.current_time }}</span>
                  </div>
                </a-col>
              </a-row>
            </div>
          </div>
        </a-tab-pane>
      </a-tabs>
    </div>
    <!-- 更新模态框 -->
    <UpdateModal
      v-if="updateVisible"
      v-model:visible="updateVisible"
      :update-data="updateData"
      @confirmed="onUpdateConfirmed"
    />
  </div>
</template>

<style scoped>
.settings-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

.settings-header {
  margin-bottom: 24px;
}

.page-title {
  margin: 0;
  font-size: 32px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.settings-content {
  background: var(--ant-color-bg-container);
  border-radius: 12px;
}

.settings-tabs {
  margin: 0;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab) {
  background: transparent;
  border: 1px solid var(--ant-color-border);
  border-radius: 8px 8px 0 0;
  margin-right: 8px;
}

.settings-tabs :deep(.ant-tabs-card > .ant-tabs-nav .ant-tabs-tab-active) {
  background: var(--ant-color-bg-container);
  border-bottom-color: var(--ant-color-bg-container);
}

.tab-content {
  padding: 24px;
}

/* form-section 样式 - 来自 ScriptEdit.vue */
.form-section {
  margin-bottom: 32px;
}

.form-section:last-child {
  margin-bottom: 0;
}

.section-header {
  margin-bottom: 20px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--ant-color-border-secondary);
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header h3 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: var(--ant-color-text);
  display: flex;
  align-items: center;
  gap: 12px;
}

.section-header h3::before {
  content: '';
  width: 4px;
  height: 24px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover));
  border-radius: 2px;
}

/* section标题右侧文档链接 */
.section-doc-link {
  color: var(--ant-color-primary) !important;
  text-decoration: none;
  font-size: 14px;
  font-weight: 500;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid var(--ant-color-primary);
  transition: all 0.2s ease;
  display: flex;
  align-items: center;
  gap: 4px;
}

.section-doc-link:hover {
  color: var(--ant-color-primary-hover) !important;
  background-color: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-hover);
  text-decoration: none;
}

/* section标题右侧检查更新按钮 */
.section-update-button {
  height: 32px;
  padding: 0 12px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 6px;
  box-shadow: 0 2px 6px rgba(22, 119, 255, 0.2);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  align-items: center;
  gap: 6px;
  background: linear-gradient(135deg, var(--ant-color-primary), var(--ant-color-primary-hover)) !important;
  border: none !important;
  color: white !important;
}

.section-update-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(22, 119, 255, 0.3);
  background: linear-gradient(135deg, #4096ff, #1677ff) !important;
  color: white !important;
}

.section-update-button:active {
  transform: translateY(0);
  color: white !important;
}

.section-update-button:focus {
  color: white !important;
}

.section-update-button svg {
  transition: transform 0.3s ease;
}

.section-update-button:hover svg {
  transform: rotate(180deg);
}

/* 垂直排列的表单项 */
.form-item-vertical {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.form-label-wrapper {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表单标签样式 */
.form-label {
  font-weight: 600;
  color: var(--ant-color-text);
  font-size: 14px;
}

.help-icon {
  color: #8c8c8c;
  font-size: 14px;
}

/* 超链接样式 */
.tooltip-link {
  color: var(--ant-color-primary) !important;
  text-decoration: underline;
  transition: color 0.2s ease;
}

.tooltip-link:hover {
  color: var(--ant-color-primary-hover) !important;
  text-decoration: underline;
}

/* 依赖提示样式 */
.dependency-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
  font-weight: normal;
  margin-left: 8px;
}

/* 链接卡片样式 */
.link-card {
  background: var(--ant-color-bg-container);
  border: 1px solid var(--ant-color-border);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
  transition: all 0.3s ease;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.link-card:hover {
  border-color: var(--ant-color-primary);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  transform: translateY(-2px);
}

.link-icon {
  font-size: 48px;
  margin-bottom: 16px;
  line-height: 1;
  color: var(--ant-color-primary);
  display: flex;
  justify-content: center;
  align-items: center;
}

.link-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.link-content h4 {
  margin: 0 0 8px 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.link-content p {
  margin: 0 0 16px 0;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  line-height: 1.5;
  flex: 1;
}

.link-button {
  display: inline-block;
  padding: 8px 16px;
  background: var(--ant-color-primary);
  color: white !important;
  text-decoration: none;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  transition: background-color 0.2s ease;
  margin-top: auto;
}

.link-button:hover {
  background: var(--ant-color-primary-hover);
  color: white !important;
  text-decoration: none;
}

/* 信息展示样式 */
.info-item {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  line-height: 1.5;
}

.info-label {
  font-weight: 600;
  color: var(--ant-color-text);
  min-width: 100px;
  flex-shrink: 0;
}

.info-value {
  color: var(--ant-color-text-secondary);
  margin-left: 8px;
}
</style>

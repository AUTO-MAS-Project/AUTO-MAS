<script setup lang="ts">
import { ref, computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import {
  Button,
  Card,
  Divider,
  Radio,
  Select,
  Space,
  Switch,
  Tabs,
  InputNumber,
  Input,
  message,
} from 'ant-design-vue'
import type { ThemeColor, ThemeMode } from '../composables/useTheme'
import { useTheme } from '../composables/useTheme.ts'
import { useSettingsApi } from '../composables/useSettingsApi'
import type { SelectValue } from 'ant-design-vue/es/select'
import type { SettingsData } from '../types/settings'

const router = useRouter()
const { themeMode, themeColor, themeColors, setThemeMode, setThemeColor, isDark } = useTheme()
const { loading, getSettings, updateSettings } = useSettingsApi()

const textColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.88)' : 'rgba(0, 0, 0, 0.88)'
)
const textSecondaryColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.65)' : 'rgba(0, 0, 0, 0.65)'
)

const activeKey = ref('basic')

const settings = reactive<SettingsData>({
  Function: {
    BossKey: '',
    HistoryRetentionTime: 0,
    HomeImageMode: '默认',
    IfAgreeBilibili: false,
    IfAllowSleep: false,
    IfSilence: false,
    IfSkipMumuSplashAds: false,
    UnattendedMode: false,
  },
  Notify: {
    AuthorizationCode: '',
    CompanyWebHookBotUrl: '',
    FromAddress: '',
    IfCompanyWebHookBot: false,
    IfPushPlyer: false,
    IfSendMail: false,
    IfSendSixStar: false,
    IfSendStatistic: false,
    IfServerChan: false,
    SMTPServerAddress: '',
    SendTaskResultTime: '不推送',
    ServerChanChannel: '',
    ServerChanKey: '',
    ServerChanTag: '',
    ToAddress: '',
  },
  Update: {
    IfAutoUpdate: false,
    MirrorChyanCDK: '',
    ProxyAddress: '',
    ProxyUrlList: [],
    ThreadNumb: 8,
    UpdateType: 'stable',
  },
  Start: {
    IfMinimizeDirectly: false,
    IfSelfStart: false,
  },
  UI: {
    IfShowTray: false,
    IfToTray: false,
    location: '100x100',
    maximized: false,
    size: '1200x700',
  },
  Voice: {
    Enabled: false,
    Type: 'simple',
  },
})

// 选项配置
const homeImageModeOptions = [
  { label: '默认', value: '默认' },
  { label: '自定义', value: '自定义' },
  { label: '主题图像', value: '主题图像' },
]

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

const updateTypeOptions = [
  { label: '稳定版', value: 'stable' },
  { label: '测试版', value: 'beta' },
]

const voiceTypeOptions = [
  { label: '简单', value: 'simple' },
  { label: '详细', value: 'noisy' },
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
    const updateData = { [category]: changes }
    const result = await updateSettings(updateData)
    if (result) {
      // message.success('设置保存成功')
    } else {
      message.error('设置保存失败')
    }
  } catch (error) {
    message.error('设置保存失败')
  }
}

const handleSettingChange = async (category: keyof SettingsData, key: string, value: any) => {
  const changes = { [key]: value }
  await saveSettings(category, changes)
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

onMounted(() => {
  loadSettings()
})
</script>

<template>
  <div class="settings-container">
    <h1>设置</h1>
    <Tabs v-model:activeKey="activeKey" type="card" :loading="loading">
      <!-- 基础设置 -->
      <Tabs.TabPane key="basic" tab="外观设置">
        <Card title="外观设置" :bordered="false">
          <Space direction="vertical" size="middle" style="width: 100%">
            <div class="setting-item">
              <h3>主题模式</h3>
              <p class="setting-description">选择应用程序的外观主题</p>
              <Radio.Group
                :value="themeMode"
                @change="handleThemeModeChange"
                :options="themeModeOptions"
              />
            </div>

            <div class="setting-item">
              <h3>主题色</h3>
              <p class="setting-description">选择应用程序的主色调</p>
              <Select :value="themeColor" @change="handleThemeColorChange" style="width: 200px">
                <Select.Option
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
                </Select.Option>
              </Select>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 功能设置 -->
      <Tabs.TabPane key="function" tab="功能设置">
        <Card title="功能配置" :bordered="false">
          <Space direction="vertical" size="large" style="width: 100%">
            <div class="setting-item">
              <h3>Boss键</h3>
              <p class="setting-description">设置快速隐藏窗口的快捷键</p>
              <Input
                v-model:value="settings.Function.BossKey"
                @blur="handleSettingChange('Function', 'BossKey', settings.Function.BossKey)"
                placeholder="例如: Ctrl+H"
                style="width: 300px"
              />
            </div>

            <div class="setting-item">
              <h3>历史记录保留时间</h3>
              <p class="setting-description">设置历史记录的保留时间</p>
              <Select
                v-model:value="settings.Function.HistoryRetentionTime"
                @change="value => handleSettingChange('Function', 'HistoryRetentionTime', value)"
                :options="historyRetentionOptions"
                style="width: 200px"
              />
            </div>

            <div class="setting-item">
              <h3>主页图像模式</h3>
              <p class="setting-description">选择主页显示的图像模式</p>
              <Select
                v-model:value="settings.Function.HomeImageMode"
                @change="value => handleSettingChange('Function', 'HomeImageMode', value)"
                :options="homeImageModeOptions"
                style="width: 200px"
              />
            </div>

            <div class="setting-item">
              <h3>功能开关</h3>
              <Space direction="vertical" size="middle">
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Function.IfAllowSleep"
                    @change="checked => handleSettingChange('Function', 'IfAllowSleep', checked)"
                  />
                  <span class="switch-label">启动时阻止系统休眠</span>
                </div>
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Function.IfSilence"
                    @change="checked => handleSettingChange('Function', 'IfSilence', checked)"
                  />
                  <span class="switch-label">静默模式</span>
                </div>
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Function.UnattendedMode"
                    @change="checked => handleSettingChange('Function', 'UnattendedMode', checked)"
                  />
                  <span class="switch-label">无人值守模式</span>
                </div>
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Function.IfAgreeBilibili"
                    @change="checked => handleSettingChange('Function', 'IfAgreeBilibili', checked)"
                  />
                  <span class="switch-label">托管Bilibili游戏隐私政策</span>
                </div>
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Function.IfSkipMumuSplashAds"
                    @change="
                      checked => handleSettingChange('Function', 'IfSkipMumuSplashAds', checked)
                    "
                  />
                  <span class="switch-label">跳过MuMu模拟器启动广告</span>
                </div>
              </Space>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 通知设置 -->
      <Tabs.TabPane key="notify" tab="通知设置">
        <Card title="通知配置" :bordered="false">
          <Space direction="vertical" size="large" style="width: 100%">
            <div class="setting-item">
              <h3>任务结果推送时间</h3>
              <p class="setting-description">设置何时推送任务执行结果</p>
              <Select
                v-model:value="settings.Notify.SendTaskResultTime"
                @change="value => handleSettingChange('Notify', 'SendTaskResultTime', value)"
                :options="sendTaskResultTimeOptions"
                style="width: 200px"
              />
            </div>

            <div class="setting-item">
              <h3>通知开关</h3>
              <Space direction="vertical" size="middle">
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Notify.IfSendStatistic"
                    @change="checked => handleSettingChange('Notify', 'IfSendStatistic', checked)"
                  />
                  <span class="switch-label">发送统计信息</span>
                </div>
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Notify.IfSendSixStar"
                    @change="checked => handleSettingChange('Notify', 'IfSendSixStar', checked)"
                  />
                  <span class="switch-label">发送六星通知</span>
                </div>
              </Space>
            </div>

            <div class="setting-item">
              <h3>邮件通知</h3>
              <Space direction="vertical" size="middle" style="width: 100%">
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Notify.IfSendMail"
                    @change="checked => handleSettingChange('Notify', 'IfSendMail', checked)"
                  />
                  <span class="switch-label">启用邮件通知</span>
                </div>
                <div class="input-group">
                  <label>SMTP服务器地址</label>
                  <Input
                    v-model:value="settings.Notify.SMTPServerAddress"
                    @blur="
                      handleSettingChange(
                        'Notify',
                        'SMTPServerAddress',
                        settings.Notify.SMTPServerAddress
                      )
                    "
                    placeholder="例如: smtp.gmail.com"
                    style="width: 300px"
                  />
                </div>
                <div class="input-group">
                  <label>授权码</label>
                  <Input.Password
                    v-model:value="settings.Notify.AuthorizationCode"
                    @blur="
                      handleSettingChange(
                        'Notify',
                        'AuthorizationCode',
                        settings.Notify.AuthorizationCode
                      )
                    "
                    placeholder="邮箱授权码"
                    style="width: 300px"
                  />
                </div>
                <div class="input-group">
                  <label>发件人地址</label>
                  <Input
                    v-model:value="settings.Notify.FromAddress"
                    @blur="
                      handleSettingChange('Notify', 'FromAddress', settings.Notify.FromAddress)
                    "
                    placeholder="发件人邮箱地址"
                    style="width: 300px"
                  />
                </div>
                <div class="input-group">
                  <label>收件人地址</label>
                  <Input
                    v-model:value="settings.Notify.ToAddress"
                    @blur="handleSettingChange('Notify', 'ToAddress', settings.Notify.ToAddress)"
                    placeholder="收件人邮箱地址"
                    style="width: 300px"
                  />
                </div>
              </Space>
            </div>

            <div class="setting-item">
              <h3>Server酱通知</h3>
              <Space direction="vertical" size="middle" style="width: 100%">
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Notify.IfServerChan"
                    @change="checked => handleSettingChange('Notify', 'IfServerChan', checked)"
                  />
                  <span class="switch-label">启用Server酱通知</span>
                </div>
                <div class="input-group">
                  <label>Server酱Key</label>
                  <Input
                    v-model:value="settings.Notify.ServerChanKey"
                    @blur="
                      handleSettingChange('Notify', 'ServerChanKey', settings.Notify.ServerChanKey)
                    "
                    placeholder="Server酱推送Key"
                    style="width: 300px"
                  />
                </div>
              </Space>
            </div>

            <div class="setting-item">
              <h3>企业微信机器人</h3>
              <Space direction="vertical" size="middle" style="width: 100%">
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.Notify.IfCompanyWebHookBot"
                    @change="
                      checked => handleSettingChange('Notify', 'IfCompanyWebHookBot', checked)
                    "
                  />
                  <span class="switch-label">启用企业微信机器人</span>
                </div>
                <div class="input-group">
                  <label>Webhook URL</label>
                  <Input
                    v-model:value="settings.Notify.CompanyWebHookBotUrl"
                    @blur="
                      handleSettingChange(
                        'Notify',
                        'CompanyWebHookBotUrl',
                        settings.Notify.CompanyWebHookBotUrl
                      )
                    "
                    placeholder="企业微信机器人Webhook地址"
                    style="width: 400px"
                  />
                </div>
              </Space>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 更新设置 -->
      <Tabs.TabPane key="update" tab="更新设置">
        <Card title="更新配置" :bordered="false">
          <Space direction="vertical" size="large" style="width: 100%">
            <div class="setting-item">
              <h3>自动更新</h3>
              <p class="setting-description">是否启用自动更新功能</p>
              <Switch
                v-model:checked="settings.Update.IfAutoUpdate"
                @change="checked => handleSettingChange('Update', 'IfAutoUpdate', checked)"
              />
            </div>

            <div class="setting-item">
              <h3>更新类型</h3>
              <p class="setting-description">选择更新版本类型</p>
              <Select
                v-model:value="settings.Update.UpdateType"
                @change="value => handleSettingChange('Update', 'UpdateType', value)"
                :options="updateTypeOptions"
                style="width: 200px"
              />
            </div>

            <div class="setting-item">
              <h3>代理设置</h3>
              <Space direction="vertical" size="middle" style="width: 100%">
                <div class="input-group">
                  <label>代理地址</label>
                  <Input
                    v-model:value="settings.Update.ProxyAddress"
                    @blur="
                      handleSettingChange('Update', 'ProxyAddress', settings.Update.ProxyAddress)
                    "
                    placeholder="例如: http://127.0.0.1:7890"
                    style="width: 300px"
                  />
                </div>
              </Space>
            </div>

            <div class="setting-item">
              <h3>Mirror酱 CDK</h3>
              <p class="setting-description">设置Mirror酱CDK</p>
              <Input
                v-model:value="settings.Update.MirrorChyanCDK"
                @blur="
                  handleSettingChange('Update', 'MirrorChyanCDK', settings.Update.MirrorChyanCDK)
                "
                placeholder="镜像CDK"
                style="width: 300px"
              />
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 启动设置 -->
      <Tabs.TabPane key="start" tab="启动设置">
        <Card title="启动配置" :bordered="false">
          <Space direction="vertical" size="large" style="width: 100%">
            <div class="setting-item">
              <h3>开机自启</h3>
              <p class="setting-description">是否在系统启动时自动启动应用</p>
              <Switch
                v-model:checked="settings.Start.IfSelfStart"
                @change="checked => handleSettingChange('Start', 'IfSelfStart', checked)"
              />
            </div>

            <div class="setting-item">
              <h3>启动后直接最小化</h3>
              <p class="setting-description">启动后是否直接最小化到系统托盘</p>
              <Switch
                v-model:checked="settings.Start.IfMinimizeDirectly"
                @change="checked => handleSettingChange('Start', 'IfMinimizeDirectly', checked)"
              />
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 界面设置 -->
      <Tabs.TabPane key="ui" tab="界面设置">
        <Card title="界面配置" :bordered="false">
          <Space direction="vertical" size="large" style="width: 100%">
            <div class="setting-item">
              <h3>系统托盘</h3>
              <Space direction="vertical" size="middle">
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.UI.IfShowTray"
                    @change="checked => handleSettingChange('UI', 'IfShowTray', checked)"
                  />
                  <span class="switch-label">显示系统托盘图标</span>
                </div>
                <div class="switch-item">
                  <Switch
                    v-model:checked="settings.UI.IfToTray"
                    @change="checked => handleSettingChange('UI', 'IfToTray', checked)"
                  />
                  <span class="switch-label">关闭时最小化到托盘</span>
                </div>
              </Space>
            </div>

            <!--            <div class="setting-item">-->
            <!--              <h3>窗口设置</h3>-->
            <!--              <Space direction="vertical" size="middle" style="width: 100%">-->
            <!--                <div class="input-group">-->
            <!--                  <label>窗口大小</label>-->
            <!--                  <Input v-model:value="settings.UI.size" @blur="handleSettingChange('UI', 'size', settings.UI.size)"-->
            <!--                    placeholder="例如: 1200x700" style="width: 200px" />-->
            <!--                </div>-->
            <!--                <div class="input-group">-->
            <!--                  <label>窗口位置</label>-->
            <!--                  <Input v-model:value="settings.UI.location"-->
            <!--                    @blur="handleSettingChange('UI', 'location', settings.UI.location)" placeholder="例如: 100x100"-->
            <!--                    style="width: 200px" />-->
            <!--                </div>-->
            <!--                <div class="switch-item">-->
            <!--                  <Switch v-model:checked="settings.UI.maximized"-->
            <!--                    @change="(checked) => handleSettingChange('UI', 'maximized', checked)" />-->
            <!--                  <span class="switch-label">启动时最大化窗口</span>-->
            <!--                </div>-->
            <!--              </Space>-->
            <!--            </div>-->
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 语音设置 -->
      <Tabs.TabPane key="voice" tab="语音设置">
        <Card title="语音配置" :bordered="false">
          <Space direction="vertical" size="large" style="width: 100%">
            <div class="setting-item">
              <h3>语音提示</h3>
              <p class="setting-description">是否启用语音提示功能</p>
              <Switch
                v-model:checked="settings.Voice.Enabled"
                @change="checked => handleSettingChange('Voice', 'Enabled', checked)"
              />
            </div>

            <div class="setting-item">
              <h3>语音类型</h3>
              <p class="setting-description">选择语音提示的详细程度</p>
              <Select
                v-model:value="settings.Voice.Type"
                @change="value => handleSettingChange('Voice', 'Type', value)"
                :options="voiceTypeOptions"
                style="width: 200px"
                :disabled="!settings.Voice.Enabled"
              />
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 高级设置 -->
      <Tabs.TabPane key="advanced" tab="高级设置">
        <Card title="开发者选项" :bordered="false">
          <Space direction="vertical" size="middle" style="width: 100%">
            <div class="setting-item">
              <h3>日志管理</h3>
              <p class="setting-description">查看和管理应用程序日志文件</p>
              <Button type="primary" @click="goToLogs">查看日志</Button>
            </div>

            <div class="setting-item">
              <h3>开发者工具</h3>
              <p class="setting-description">打开浏览器开发者工具进行调试</p>
              <Button type="primary" @click="openDevTools">打开 F12 开发者工具</Button>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>
    </Tabs>
  </div>
</template>

<style scoped>
.settings-container {
  max-width: 1000px;
  margin: 0 auto;
  padding: 20px;
}

.settings-container h1 {
  margin: 0 0 24px 0;
  font-size: 36px;
  font-weight: 600;
  color: v-bind(textColor);
}

.setting-item h3 {
  margin: 0 0 8px 0;
  font-weight: 600;
  font-size: 20px;
  color: v-bind(textColor);
}

.setting-description {
  margin: 0 0 12px 0;
  color: v-bind(textSecondaryColor);
  font-size: 14px;
  line-height: 1.5;
}

.switch-item {
  display: flex;
  align-items: center;
  gap: 12px;
}

.switch-label {
  color: v-bind(textColor);
  font-size: 14px;
  user-select: none;
}

.input-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input-group label {
  color: v-bind(textColor);
  font-size: 14px;
  font-weight: 500;
  margin: 0;
}

:deep(.ant-card-head-title) {
  color: v-bind(textColor);
  font-weight: 600;
  font-size: 28px;
}

:deep(.ant-tabs-tab) {
  color: v-bind(textSecondaryColor);
}
</style>

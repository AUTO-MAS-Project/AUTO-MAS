<script setup lang="ts">
import { ref, computed } from 'vue'
import { Button, Card, Divider, Radio, Select, Space, Switch, Tabs } from 'ant-design-vue'
import type { ThemeColor, ThemeMode } from '../composables/useTheme'
import { useTheme } from '../composables/useTheme.ts'
import type { SelectValue } from 'ant-design-vue/es/select'

const { themeMode, themeColor, themeColors, setThemeMode, setThemeColor, isDark } = useTheme()

// 主题感知的颜色
const textColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.88)' : 'rgba(0, 0, 0, 0.88)'
)
const textSecondaryColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.65)' : 'rgba(0, 0, 0, 0.65)'
)
const textTertiaryColor = computed(() =>
  isDark.value ? 'rgba(255, 255, 255, 0.45)' : 'rgba(0, 0, 0, 0.45)'
)

const activeKey = ref('basic')

// 主题模式选项
const themeModeOptions = [
  { label: '跟随系统', value: 'system' },
  { label: '浅色模式', value: 'light' },
  { label: '深色模式', value: 'dark' },
]

// 主题色中文映射
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
  gold: '金色'
}

// 主题色选项
const themeColorOptions = Object.entries(themeColors).map(([key, color]) => ({
  label: themeColorLabels[key as ThemeColor],
  value: key,
  color,
}))

const handleThemeModeChange = (e: any) => {
  setThemeMode(e.target.value as ThemeMode)
}

const handleThemeColorChange = (value: SelectValue) => {
  if (typeof value === 'string') {
    setThemeColor(value as ThemeColor)
  }
}

const openDevTools = () => {
  // 通过 Electron 的 preload 脚本调用开发者工具
  if (window.electronAPI) {
    window.electronAPI.openDevTools()
  }
}
</script>

<template>
  <div class="settings-container">
    <h1>设置</h1>

    <Tabs v-model:activeKey="activeKey" type="card">
      <!-- 基础设置 -->
      <Tabs.TabPane key="basic" tab="基础设置">
        <Card title="外观设置" :bordered="false">
          <Space direction="vertical" size="middle" style="width: 100%">
            <!-- 主题模式 -->
            <div class="setting-item">
              <h4>主题模式</h4>
              <p class="setting-description">选择应用程序的外观主题</p>
              <Radio.Group
                :value="themeMode"
                @change="handleThemeModeChange"
                :options="themeModeOptions"
              />
            </div>

            <Divider />

            <!-- 主题色 -->
            <div class="setting-item">
              <h4>主题色</h4>
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

            <Divider />

            <!-- 语言设置 -->
            <div class="setting-item">
              <h4>语言</h4>
              <p class="setting-description">选择应用程序界面语言</p>
              <Select value="zh-CN" style="width: 200px" disabled>
                <Select.Option value="zh-CN">简体中文</Select.Option>
                <Select.Option value="en-US">English</Select.Option>
              </Select>
              <p class="setting-note">多语言支持即将推出</p>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 通知设置 -->
      <Tabs.TabPane key="notification" tab="通知设置">
        <Card title="通知配置" :bordered="false">
          <Space direction="vertical" size="middle" style="width: 100%">
            <!-- 桌面通知 -->
            <div class="setting-item">
              <h4>桌面通知</h4>
              <p class="setting-description">启用系统桌面通知</p>
              <Switch :checked="true" />
            </div>

            <Divider />

            <!-- 声音提醒 -->
            <div class="setting-item">
              <h4>声音提醒</h4>
              <p class="setting-description">任务完成时播放提示音</p>
              <Switch :checked="false" />
            </div>

            <Divider />

            <!-- 通知类型 -->
            <div class="setting-item">
              <h4>通知类型</h4>
              <p class="setting-description">选择需要接收通知的事件类型</p>
              <div style="margin-top: 12px">
                <div style="margin-bottom: 8px">
                  <Switch :checked="true" style="margin-right: 8px" />
                  任务执行完成
                </div>
                <div style="margin-bottom: 8px">
                  <Switch :checked="true" style="margin-right: 8px" />
                  任务执行失败
                </div>
                <div style="margin-bottom: 8px">
                  <Switch :checked="false" style="margin-right: 8px" />
                  计划任务开始
                </div>
                <div>
                  <Switch :checked="false" style="margin-right: 8px" />
                  系统状态变更
                </div>
              </div>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 更新设置 -->
      <Tabs.TabPane key="update" tab="更新设置">
        <Card title="自动更新" :bordered="false">
          <Space direction="vertical" size="middle" style="width: 100%">
            <!-- 自动检查更新 -->
            <div class="setting-item">
              <h4>自动检查更新</h4>
              <p class="setting-description">启动时自动检查应用程序更新</p>
              <Switch :checked="true" />
            </div>

            <Divider />

            <!-- 更新频率 -->
            <div class="setting-item">
              <h4>检查频率</h4>
              <p class="setting-description">设置检查更新的频率</p>
              <Select value="daily" style="width: 200px">
                <Select.Option value="startup">每次启动</Select.Option>
                <Select.Option value="daily">每天</Select.Option>
                <Select.Option value="weekly">每周</Select.Option>
                <Select.Option value="manual">手动检查</Select.Option>
              </Select>
            </div>

            <Divider />

            <!-- 预发布版本 -->
            <div class="setting-item">
              <h4>预发布版本</h4>
              <p class="setting-description">接收 Beta 版本和预发布版本的更新</p>
              <Switch :checked="false" />
              <p class="setting-note">预发布版本可能包含未完全测试的功能</p>
            </div>

            <Divider />

            <!-- 当前版本信息 -->
            <div class="setting-item">
              <h4>版本信息</h4>
              <p class="setting-description">当前应用程序版本</p>
              <div style="margin-top: 12px">
                <p><strong>版本:</strong> v1.0.0</p>
                <p><strong>构建时间:</strong> 2024-02-08</p>
                <Button type="primary" style="margin-top: 8px">检查更新</Button>
              </div>
            </div>
          </Space>
        </Card>
      </Tabs.TabPane>

      <!-- 高级设置 -->
      <Tabs.TabPane key="advanced" tab="高级设置">
        <Card title="开发者选项" :bordered="false">
          <Space direction="vertical" size="middle" style="width: 100%">
            <!-- 开发者工具 -->
            <div class="setting-item">
              <h4>开发者工具</h4>
              <p class="setting-description">打开浏览器开发者工具进行调试</p>
              <Button type="primary" @click="openDevTools"> 打开 F12 开发者工具 </Button>
            </div>

            <Divider />

            <!-- 日志级别 -->
            <div class="setting-item">
              <h4>日志级别</h4>
              <p class="setting-description">设置应用程序日志记录级别</p>
              <Select value="info" style="width: 200px">
                <Select.Option value="error">错误</Select.Option>
                <Select.Option value="warn">警告</Select.Option>
                <Select.Option value="info">信息</Select.Option>
                <Select.Option value="debug">调试</Select.Option>
              </Select>
            </div>

            <Divider />

            <!-- 性能监控 -->
            <div class="setting-item">
              <h4>性能监控</h4>
              <p class="setting-description">启用性能监控和统计信息收集</p>
              <Switch :checked="false" />
            </div>

            <Divider />

            <!-- 数据重置 -->
            <div class="setting-item">
              <h4>数据管理</h4>
              <p class="setting-description">重置应用程序数据和设置</p>
              <div style="margin-top: 12px">
                <Button danger style="margin-right: 8px">清除缓存</Button>
                <Button danger type="primary">重置所有设置</Button>
              </div>
              <p class="setting-note">重置操作不可撤销，请谨慎操作</p>
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
}

.setting-item {
  margin-bottom: 0px;
}

.setting-item h4 {
  margin: 0 0 8px 0;
  font-weight: 600;
  font-size: 16px;
  color: v-bind(textColor);
}

.setting-description {
  margin: 0 0 12px 0;
  color: v-bind(textSecondaryColor);
  font-size: 14px;
  line-height: 1.5;
}

.setting-note {
  margin: 8px 0 0 0;
  color: v-bind(textTertiaryColor);
  font-size: 12px;
  font-style: italic;
}

:deep(.ant-card) {
  box-shadow:
    0 1px 2px 0 rgba(0, 0, 0, 0.03),
    0 1px 6px -1px rgba(0, 0, 0, 0.02),
    0 2px 4px 0 rgba(0, 0, 0, 0.02);
}

:deep(.ant-card-head-title) {
  font-weight: 600;
  font-size: 18px;
}

:deep(.ant-tabs-card .ant-tabs-tab) {
  padding: 8px 20px;
  font-weight: 500;
}

:deep(.ant-tabs-card .ant-tabs-tab-active) {
  font-weight: 600;
}

:deep(.ant-tabs-content-holder) {
  padding-top: 0px;
}

:deep(.ant-divider) {
  margin: 12px 0;
}

:deep(.ant-switch) {
  margin-right: 8px;
}

/* 响应式设计 */
@media (max-width: 768px) {
  .settings-container {
    max-width: 100%;
    padding: 0 16px;
  }

  :deep(.ant-tabs-card .ant-tabs-tab) {
    padding: 8px 12px;
    font-size: 14px;
  }
}
</style>

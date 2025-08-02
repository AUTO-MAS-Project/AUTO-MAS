<script setup lang="ts">
import { Card, Row, Col, Radio, Button, Select, Space, Divider } from 'ant-design-vue'
import { useTheme } from '../composables/useTheme'
import type { ThemeMode, ThemeColor } from '../composables/useTheme'

const { themeMode, themeColor, themeColors, setThemeMode, setThemeColor } = useTheme()

// 主题模式选项
const themeModeOptions = [
  { label: '跟随系统', value: 'system' },
  { label: '浅色模式', value: 'light' },
  { label: '深色模式', value: 'dark' },
]

// 主题色选项
const themeColorOptions = Object.entries(themeColors).map(([key, color]) => ({
  label: key.charAt(0).toUpperCase() + key.slice(1),
  value: key,
  color,
}))

const handleThemeModeChange = (e: any) => {
  setThemeMode(e.target.value as ThemeMode)
}

const handleThemeColorChange = (value: ThemeColor) => {
  setThemeColor(value)
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

    <Row :gutter="[24, 24]">
      <Col :span="24">
        <Card title="外观设置" size="small">
          <Space direction="vertical" size="large" style="width: 100%">
            <!-- 深色模式切换 -->
            <div>
              <h4>主题模式</h4>
              <Radio.Group
                :value="themeMode"
                @change="handleThemeModeChange"
                :options="themeModeOptions"
              />
            </div>

            <Divider />

            <!-- 主题色切换 -->
            <div>
              <h4>主题色</h4>
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
      </Col>

      <Col :span="24">
        <Card title="开发者工具" size="small">
          <Space direction="vertical" size="middle">
            <div>
              <h4>调试工具</h4>
              <p style="color: var(--ant-color-text-secondary); margin-bottom: 12px">
                打开浏览器开发者工具进行调试
              </p>
              <Button type="primary" @click="openDevTools"> 打开 F12 开发者工具 </Button>
            </div>
          </Space>
        </Card>
      </Col>
    </Row>
  </div>
</template>

<style scoped>
.settings-container {
  max-width: 800px;
}

h4 {
  margin: 0 0 8px 0;
  font-weight: 600;
}

:deep(.ant-card-head-title) {
  font-weight: 600;
}
</style>

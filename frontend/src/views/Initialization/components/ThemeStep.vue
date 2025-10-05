<template>
  <div class="step-panel">
    <h3>选择您的主题偏好</h3>
    <div class="theme-settings">
      <div class="setting-group">
        <label>主题模式</label>
        <a-radio-group v-model:value="selectedThemeMode" @change="onThemeModeChange">
          <a-radio-button value="light">浅色模式</a-radio-button>
          <a-radio-button value="dark">深色模式</a-radio-button>
          <a-radio-button value="system">跟随系统</a-radio-button>
        </a-radio-group>
      </div>
      <div class="setting-group">
        <label>主题色彩</label>
        <div class="color-picker">
          <div
            v-for="(color, key) in themeColors"
            :key="key"
            class="color-option"
            :class="{ active: selectedThemeColor === key }"
            :style="{ backgroundColor: color }"
            @click="onThemeColorChange(key)"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useTheme } from '@/composables/useTheme.ts'
import { getConfig, saveThemeConfig } from '@/utils/config.ts'
import type { ThemeMode, ThemeColor } from '@/composables/useTheme.ts'

const { themeColors, setThemeMode, setThemeColor } = useTheme()

const selectedThemeMode = ref<ThemeMode>('system')
const selectedThemeColor = ref<ThemeColor>('blue')

async function onThemeModeChange() {
  setThemeMode(selectedThemeMode.value)
  await saveSettings()
}

async function onThemeColorChange(color: ThemeColor) {
  selectedThemeColor.value = color
  setThemeColor(color)
  await saveSettings()
}

async function saveSettings() {
  await saveThemeConfig(selectedThemeMode.value, selectedThemeColor.value)
  console.log('主题设置已保存:', {
    themeMode: selectedThemeMode.value,
    themeColor: selectedThemeColor.value,
  })
}

async function loadSettings() {
  try {
    const config = await getConfig()
    selectedThemeMode.value = config.themeMode
    selectedThemeColor.value = config.themeColor
    setThemeMode(selectedThemeMode.value)
    setThemeColor(selectedThemeColor.value)
    console.log('主题设置已加载:', {
      themeMode: selectedThemeMode.value,
      themeColor: selectedThemeColor.value,
    })
  } catch (error) {
    console.warn('Failed to load theme settings:', error)
  }
}

// 暴露给父组件的方法
defineExpose({
  loadSettings,
  saveSettings,
  selectedThemeMode,
  selectedThemeColor,
})

// 组件挂载时加载设置
onMounted(async () => {
  await loadSettings()
})
</script>

<style scoped>
.step-panel {
  padding: 20px;
  background: var(--ant-color-bg-elevated);
  border-radius: 8px;
  border: 1px solid var(--ant-color-border);
}

.step-panel h3 {
  font-size: 20px;
  font-weight: 600;
  color: var(--ant-color-text);
  margin-bottom: 20px;
}

.theme-settings {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.setting-group {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.setting-group label {
  font-weight: 500;
  color: var(--ant-color-text);
}

.color-picker {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.color-option {
  width: 40px;
  height: 40px;
  border-radius: 8px;
  cursor: pointer;
  border: 2px solid transparent;
  transition: all 0.2s ease;
}

.color-option:hover {
  transform: scale(1.1);
}

.color-option.active {
  border-color: var(--ant-color-text);
  transform: scale(1.1);
}
</style>

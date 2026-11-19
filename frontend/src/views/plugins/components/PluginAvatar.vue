<script setup lang="ts">
import { AppstoreOutlined } from '@ant-design/icons-vue'
import type { PluginIcon } from '../pluginCenterModel'

/** 插件图标：专项 logo / 应用图标、首字母色块或通用插件图标，取哪种由 resolvePluginIcon 决定。 */
withDefaults(defineProps<{ icon: PluginIcon; size?: number }>(), { size: 40 })
</script>

<template>
  <img
    v-if="icon.kind === 'image'"
    class="plugin-avatar"
    :src="icon.src"
    alt=""
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
  <span
    v-else
    class="plugin-avatar plugin-avatar--block"
    :class="`plugin-avatar--${icon.tone}`"
    aria-hidden="true"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.4)}px` }"
  >
    <template v-if="icon.kind === 'initial'">{{ icon.text }}</template>
    <AppstoreOutlined v-else />
  </span>
</template>

<style scoped>
.plugin-avatar {
  flex: none;
  border-radius: 8px;
  object-fit: cover;
}

.plugin-avatar--block {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  line-height: 1;
}

.plugin-avatar--primary {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.plugin-avatar--success {
  color: var(--ant-color-success);
  background: var(--ant-color-success-bg);
}

.plugin-avatar--warning {
  color: var(--ant-color-warning-text);
  background: var(--ant-color-warning-bg);
}

.plugin-avatar--neutral {
  color: var(--ant-color-text-secondary);
  background: var(--ant-color-fill-secondary);
}
</style>

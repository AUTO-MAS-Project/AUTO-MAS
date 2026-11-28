<script setup lang="ts">
import { computed, ref } from 'vue'
import { AppstoreOutlined } from '@ant-design/icons-vue'
import type { PluginIcon } from '../pluginCenterModel'

/** 插件图标：专项 logo / 应用图标、首字母色块或通用插件图标，取哪种由 resolvePluginIcon 决定。 */
const props = withDefaults(defineProps<{ icon: PluginIcon; size?: number }>(), { size: 40 })
const failedSrc = ref<string>()
const displayedIcon = computed<PluginIcon>(() => {
  const icon = props.icon
  return icon.kind === 'image' && icon.src === failedSrc.value
    ? (icon.fallback ?? { kind: 'generic', tone: 'neutral' })
    : icon
})
</script>

<template>
  <img
    v-if="displayedIcon.kind === 'image'"
    class="plugin-avatar"
    :src="displayedIcon.src"
    @error="failedSrc = displayedIcon.src"
    alt=""
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
  <span
    v-else
    class="plugin-avatar plugin-avatar--block"
    :class="`plugin-avatar--${displayedIcon.tone}`"
    aria-hidden="true"
    :style="{ width: `${size}px`, height: `${size}px`, fontSize: `${Math.round(size * 0.4)}px` }"
  >
    <template v-if="displayedIcon.kind === 'initial'">{{ displayedIcon.text }}</template>
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

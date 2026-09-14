<template>
  <teleport to="body">
    <div v-if="open" class="gui-session-mask">
      <div class="mask-content">
        <div v-if="icon" class="mask-icon">
          <component :is="icon" :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
        </div>
        <h2 class="mask-title">{{ title }}</h2>
        <p v-if="description" class="mask-description">
          {{ description }}
        </p>
        <div v-if="$slots.actions" class="mask-actions">
          <slot name="actions" />
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import type { Component } from 'vue'

/**
 * 通用原生 GUI 会话遮罩（纯展示层，与会话状态解耦）。
 *
 * 各专项拉起脚本原生 GUI（配置/查看会话）期间显示全屏遮罩，阻断页面操作；
 * 开关状态、文案、图标、按钮由父组件按自身会话机制传入——专项只负责
 * 「何时显示/隐藏 + 按钮行为」，本组件只负责视觉。
 *
 * 参考接入：``ZzzOdUserEdit.vue``（配置会话 / 查看会话两个遮罩）。
 */
withDefaults(
  defineProps<{
    /** 是否显示遮罩（由专项会话状态驱动，如 useXxxGuiSession 的 showXxxMask） */
    open: boolean
    /** 遮罩标题 */
    title: string
    /** 图标组件（如 SettingOutlined / EyeOutlined）；不传则不显示 */
    icon?: Component
    /** 说明文案（可含换行） */
    description?: string
  }>(),
  {
    icon: undefined,
    description: '',
  }
)
</script>

<style scoped>
.gui-session-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.65);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
}

.mask-content {
  text-align: center;
  color: #fff;
  max-width: 420px;
  padding: 0 24px;
}

.mask-icon {
  margin-bottom: 24px;
}

.mask-title {
  color: #fff;
  font-size: 24px;
  margin-bottom: 16px;
}

.mask-description {
  color: rgba(255, 255, 255, 0.85);
  font-size: 14px;
  line-height: 1.8;
  margin-bottom: 32px;
  white-space: pre-line;
}

.mask-actions {
  display: flex;
  justify-content: center;
}
</style>

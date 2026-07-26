<template>
  <transition name="script-config-mask-fade">
    <div
      v-if="visible"
      class="script-config-mask"
      role="dialog"
      aria-modal="true"
      :aria-label="ariaLabel"
    >
      <div class="script-config-mask-content">
        <div class="script-config-mask-icon">
          <SettingOutlined :style="{ fontSize: '48px', color: 'var(--ant-color-primary)' }" />
        </div>
        <h2 class="script-config-mask-title">{{ title }}</h2>
        <p class="script-config-mask-description">
          {{ descriptionLine1 }}
          <br />
          {{ descriptionLine2 }}
        </p>
        <div class="script-config-mask-actions">
          <a-button
            v-if="script"
            type="primary"
            size="large"
            :loading="saving"
            @click="emit('save', script)"
          >
            保存配置
          </a-button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { SettingOutlined } from '@ant-design/icons-vue'
import type { Script } from '@/types/script'
import type { ScriptConfigSessionKind } from '@/views/scripts/composables/useScriptConfigSession'

interface Props {
  visible: boolean
  script: Script | null
  kind: ScriptConfigSessionKind | null
  saving?: boolean
}

interface Emits {
  (event: 'save', script: Script): void
}

const props = withDefaults(defineProps<Props>(), {
  saving: false,
})
const emit = defineEmits<Emits>()

const COPY: Record<
  ScriptConfigSessionKind,
  {
    title: string
    line1: string
    line2: string
    ariaLabel: string
  }
> = {
  SRC: {
    title: '正在进行SRC配置',
    line1: '当前正在配置SRC脚本，请在SRC配置界面完成相关设置。',
    line2: '配置完成后，请点击“保存配置”按钮来解除页面锁定。',
    ariaLabel: 'SRC 配置遮罩层',
  },
  MaaEnd: {
    title: '正在进行 MaaEnd 配置',
    line1: '当前正在配置 MaaEnd 脚本，请在 MaaEnd 配置界面完成相关设置。',
    line2: '配置完成后，点击“保存配置”解除页面锁定。',
    ariaLabel: 'MaaEnd 配置遮罩层',
  },
}

const copy = computed(() => (props.kind ? COPY[props.kind] : null))

const title = computed(() => copy.value?.title ?? '')
const descriptionLine1 = computed(() => copy.value?.line1 ?? '')
const descriptionLine2 = computed(() => copy.value?.line2 ?? '')
const ariaLabel = computed(() => copy.value?.ariaLabel ?? '脚本配置遮罩层')
</script>

<style scoped>
.script-config-mask {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: color-mix(in srgb, #000 45%, transparent);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 9999;
}

.script-config-mask-content {
  background: var(--v6-color-surface-elevated);
  border-radius: var(--v6-radius-card);
  padding: var(--v6-space-6);
  max-width: 480px;
  width: 100%;
  text-align: center;
  box-shadow: var(--v6-shadow-elevated);
  border: 1px solid var(--v6-color-border);
}

.script-config-mask-icon {
  margin-bottom: 16px;
}

.script-config-mask-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 8px;
  color: var(--ant-color-text);
}

.script-config-mask-description {
  font-size: 14px;
  color: var(--ant-color-text-secondary);
  margin: 0 0 24px;
  line-height: 1.5;
}

.script-config-mask-actions {
  display: flex;
  justify-content: center;
}

.script-config-mask-fade-enter-active,
.script-config-mask-fade-leave-active {
  transition: opacity var(--v6-motion-fast, 160ms) var(--v6-ease-out, ease);
}

.script-config-mask-fade-enter-from,
.script-config-mask-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .script-config-mask-fade-enter-active,
  .script-config-mask-fade-leave-active {
    transition: none;
  }
}
</style>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted } from 'vue'
import {
  CheckOutlined,
  CloseOutlined,
  DownloadOutlined,
  EyeOutlined,
  RollbackOutlined,
} from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import { useAppearanceTryOnStore } from '@/stores/appearanceTryOn'

defineOptions({ name: 'AppearanceTryOnDock' })

const { t } = useI18n()
const tryOn = useAppearanceTryOnStore()

const subtitle = computed(() => {
  const current = tryOn.session
  if (!current) return ''
  return current.hasBundledMascot
    ? t('core.themeStore.tryOn.mascotUnchanged', { original: tryOn.originalLabel })
    : t('core.themeStore.tryOn.sandboxHint', { original: tryOn.originalLabel })
})

const primaryActionLabel = computed(() => {
  const current = tryOn.session
  if (!current) return ''
  if (current.source === 'upload') return t('core.themeStore.tryOn.returnToUpload')
  if (current.source === 'installed') return t('core.themeStore.tryOn.applyInstalled')
  return current.versionNo !== null
    ? t('core.themeStore.tryOn.installVersion', { version: current.versionNo })
    : t('core.themeStore.install')
})

const beginCompare = (): void => {
  tryOn.setComparing(true)
}

const endCompare = (): void => {
  if (tryOn.comparing) tryOn.setComparing(false)
}

const handleCompareKeydown = (event: KeyboardEvent): void => {
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    beginCompare()
  }
}

const handleCompareKeyup = (event: KeyboardEvent): void => {
  if (event.key === ' ' || event.key === 'Enter') {
    event.preventDefault()
    endCompare()
  }
}

onMounted(() => {
  window.addEventListener('pointerup', endCompare)
  window.addEventListener('blur', endCompare)
})

onBeforeUnmount(() => {
  window.removeEventListener('pointerup', endCompare)
  window.removeEventListener('blur', endCompare)
})
</script>

<template>
  <Transition name="tryon-dock">
    <div v-if="tryOn.active && tryOn.session" class="tryon-dock" role="region" aria-live="polite">
      <div class="tryon-dock-left">
        <img
          v-if="tryOn.session.coverUrl"
          :src="tryOn.session.coverUrl"
          :alt="tryOn.session.title"
          class="tryon-dock-thumb"
        />
        <span v-else class="tryon-dock-icon">
          <EyeOutlined />
        </span>
        <div class="tryon-dock-meta">
          <div class="tryon-dock-title-row">
            <span class="tryon-dock-title">
              {{
                t('core.themeStore.tryOn.bannerTitle', {
                  name: tryOn.session.title,
                  version: tryOn.session.versionNo ? ` v${tryOn.session.versionNo}` : '',
                })
              }}
            </span>
            <a-tag :color="tryOn.comparing ? 'default' : 'processing'" class="tryon-dock-tag">
              {{
                tryOn.comparing
                  ? t('core.themeStore.tryOn.comparingBadge')
                  : t('core.themeStore.tryOn.sandboxBadge')
              }}
            </a-tag>
          </div>
          <div class="tryon-dock-sub">{{ subtitle }}</div>
        </div>
      </div>

      <div class="tryon-dock-actions">
        <a-button
          size="small"
          :type="tryOn.comparing ? 'primary' : 'default'"
          :disabled="tryOn.applying"
          @pointerdown.prevent="beginCompare"
          @pointerup="endCompare"
          @pointerleave="endCompare"
          @pointercancel="endCompare"
          @blur="endCompare"
          @keydown="handleCompareKeydown"
          @keyup="handleCompareKeyup"
        >
          <template #icon><EyeOutlined /></template>
          {{ t('core.themeStore.tryOn.holdToCompare') }}
        </a-button>
        <a-button size="small" :disabled="tryOn.applying" @click="tryOn.exit()">
          <template #icon><CloseOutlined /></template>
          {{ t('core.themeStore.tryOn.exit') }}
        </a-button>
        <a-button
          size="small"
          type="primary"
          :loading="tryOn.applying"
          @click="void tryOn.applyCurrent()"
        >
          <template #icon>
            <RollbackOutlined v-if="tryOn.session.source === 'upload'" />
            <CheckOutlined v-else-if="tryOn.session.source === 'installed'" />
            <DownloadOutlined v-else />
          </template>
          {{ primaryActionLabel }}
        </a-button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.tryon-dock {
  position: fixed;
  right: 24px;
  bottom: 16px;
  left: 184px;
  z-index: 950;
  display: flex;
  flex-wrap: wrap;
  gap: 12px 16px;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  padding: 8px 16px;
  border: 1px solid var(--ant-color-primary-border);
  border-radius: 12px;
  background: var(--ant-color-bg-elevated);
  box-shadow: var(--ant-box-shadow-secondary);
}

.tryon-dock-left {
  display: flex;
  min-width: 0;
  flex: 1 1 320px;
  gap: 12px;
  align-items: center;
}

.tryon-dock-thumb {
  width: 52px;
  height: 34px;
  flex: none;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 6px;
  object-fit: cover;
}

.tryon-dock-icon {
  display: inline-flex;
  width: 34px;
  height: 34px;
  flex: none;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
}

.tryon-dock-meta {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.tryon-dock-title-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.tryon-dock-title {
  color: var(--ant-color-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 20px;
}

.tryon-dock-tag {
  margin-inline-end: 0;
}

.tryon-dock-sub {
  overflow: hidden;
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 18px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tryon-dock-actions {
  display: flex;
  flex-wrap: wrap;
  flex: none;
  gap: 8px;
  align-items: center;
}

.tryon-dock-enter-active,
.tryon-dock-leave-active {
  transition:
    opacity 0.18s ease,
    transform 0.18s ease;
}

.tryon-dock-enter-from,
.tryon-dock-leave-to {
  opacity: 0;
  transform: translateY(12px);
}

@media (max-width: 900px) {
  .tryon-dock {
    left: 24px;
  }
}
</style>

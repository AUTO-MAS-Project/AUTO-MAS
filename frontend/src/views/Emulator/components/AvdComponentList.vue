<script setup lang="ts">
/** 魔改 AVD 根目录里的组件：名称、版本（与下载大小、内测包或本地 SDK 标记）、状态。模拟器不下载，缺了只提示用内测包。 */
import { useI18n } from 'vue-i18n'

import type { Emulator2AvdComponentItem } from '@/api'
import { formatBytes } from '@/utils/byteFormat'
import { componentDetail, componentState } from '../avdLogic'

defineProps<{ components: Emulator2AvdComponentItem[] }>()

const { t } = useI18n()

const componentText = (item: Emulator2AvdComponentItem) => {
  const state = componentState(item)
  if (state === 'ready') return t('emulator2.avd.componentReady')
  if (state === 'needsPackage') return t('emulator2.avd.needsTestPackage')
  if (state === 'partial') {
    return t('emulator2.avd.componentPartial', {
      size: `${formatBytes(item.downloadedBytes ?? 0)} / ${formatBytes(item.sizeBytes ?? 0)}`,
    })
  }
  return t('emulator2.avd.componentMissing')
}

const componentColor = (item: Emulator2AvdComponentItem) => {
  const state = componentState(item)
  if (state === 'ready') return 'success'
  if (state === 'partial') return 'processing'
  return item.optional ? 'default' : 'warning'
}
</script>

<template>
  <h4 class="block-title">{{ t('emulator2.avd.components') }}</h4>
  <div class="component-list">
    <div v-for="item in components" :key="item.id" class="component-row">
      <span class="component-name">{{ item.name }}</span>
      <span class="component-meta">
        {{ componentDetail(item).version }}
        <template v-if="componentDetail(item).testPackage">
          · {{ t('emulator2.avd.testPackage') }}</template
        >
        <template v-else-if="componentDetail(item).localSdk">
          · {{ t('emulator2.avd.localSdk') }}</template
        >
        <template v-else-if="componentDetail(item).sizeBytes">
          · {{ formatBytes(componentDetail(item).sizeBytes ?? 0) }}</template
        >
        <template v-if="item.optional"> · {{ t('emulator2.avd.optional') }}</template>
      </span>
      <a-tag :color="componentColor(item)">{{ componentText(item) }}</a-tag>
    </div>
    <a-alert
      v-if="components.some(item => componentState(item) === 'needsPackage')"
      type="warning"
      show-icon
      :message="t('emulator2.avd.testPackageHint')"
    />
  </div>
</template>

<style scoped>
.block-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.component-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.component-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.component-name {
  flex-shrink: 0;
  font-weight: 500;
}

.component-meta {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>

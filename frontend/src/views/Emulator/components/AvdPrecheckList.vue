<script setup lang="ts">
/**
 * 魔改 AVD 开机前的电脑检查：通过的一行显示，不满足的用醒目的提示框写出原因和建议。
 * 硬件虚拟化没通过时给「开启」按钮，点了由外层调接口；开完要重启，按钮换成提示。
 */
import { useI18n } from 'vue-i18n'

import type { Emulator2AvdPrecheckItem } from '@/api'
import { hasHypervisorAction, precheckLevel, type PrecheckLevel } from '../avdLogic'

defineProps<{
  items: Emulator2AvdPrecheckItem[]
  /** 正在开启（等系统确认框 / dism） */
  enabling?: boolean
  /** 这次已经开启成功，等重启 */
  restartPending?: boolean
}>()
const emit = defineEmits<{ enableHypervisor: [] }>()

const { t } = useI18n()

const LEVEL_COLOR: Record<PrecheckLevel, string> = {
  ok: 'success',
  error: 'error',
  warning: 'warning',
  unknown: 'default',
}

const levelText = (level: PrecheckLevel) => t(`emulator2.avd.precheck.${level}`)

const failing = (item: Emulator2AvdPrecheckItem) => {
  const level = precheckLevel(item)
  return level === 'error' || level === 'warning'
}
</script>

<template>
  <h4 class="block-title">{{ t('emulator2.avd.prechecks') }}</h4>
  <div class="precheck-list">
    <template v-for="item in items" :key="item.id">
      <a-alert
        v-if="failing(item)"
        :type="precheckLevel(item) === 'error' ? 'error' : 'warning'"
        show-icon
        :message="`${item.title}：${item.reason}`"
        :description="item.advice || undefined"
      >
        <template v-if="hasHypervisorAction(item)" #action>
          <a-tag v-if="restartPending" color="processing">
            {{ t('emulator2.avd.hypervisorPending') }}
          </a-tag>
          <a-button
            v-else
            size="small"
            type="primary"
            :loading="enabling"
            @click="emit('enableHypervisor')"
          >
            {{ t('emulator2.avd.enableHypervisor') }}
          </a-button>
        </template>
      </a-alert>
      <div v-else class="precheck-row">
        <a-tag :color="LEVEL_COLOR[precheckLevel(item)]">
          {{ levelText(precheckLevel(item)) }}
        </a-tag>
        <span class="precheck-title">{{ item.title }}</span>
        <span class="precheck-reason">{{ item.reason }}</span>
      </div>
    </template>
  </div>
</template>

<style scoped>
.block-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.precheck-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.precheck-row {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.precheck-title {
  flex-shrink: 0;
  font-weight: 500;
}

.precheck-reason {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>

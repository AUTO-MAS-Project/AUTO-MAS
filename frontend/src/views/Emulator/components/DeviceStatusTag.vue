<script setup lang="ts">
/**
 * 设备表「状态」一列。占位行、删除这类没有目标状态的操作直接写明在干什么（``label``）；
 * 其余按状态显示，新建失败悬停看原因。availability 优先：这次没枚举到就不该显示成离线。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { LoadingOutlined } from '@ant-design/icons-vue'

import type { Emulator2DeviceItem } from '@/api'
import { DeviceStatus, isTransitional } from '../emulator2Status'

const props = defineProps<{
  device: Pick<Emulator2DeviceItem, 'availability' | 'creationError'>
  /** 这一行此刻应显示的状态（已并进进行中的操作） */
  status: number
  label?: string
}>()

const { t } = useI18n()

const tag = computed(() => {
  if (props.device.availability === 'unavailable') {
    return { color: 'default', text: t('core.emulator2.status.unavailable') }
  }
  if (props.device.availability === 'missing') {
    return { color: 'warning', text: t('core.emulator2.status.missing') }
  }
  const map: Record<number, { color: string; text: string }> = {
    [DeviceStatus.ONLINE]: { color: 'success', text: t('core.emulator.deviceStatus.online') },
    [DeviceStatus.OFFLINE]: { color: 'default', text: t('core.emulator.deviceStatus.offline') },
    [DeviceStatus.STARTING]: {
      color: 'processing',
      text: t('core.emulator.deviceStatus.starting'),
    },
    [DeviceStatus.CLOSING]: { color: 'processing', text: t('core.emulator.deviceStatus.closing') },
    [DeviceStatus.ERROR]: { color: 'error', text: t('core.emulator.deviceStatus.error') },
    [DeviceStatus.NOT_FOUND]: { color: 'default', text: t('core.emulator.deviceStatus.notFound') },
    [DeviceStatus.CREATING]: { color: 'processing', text: t('core.emulator2.busy.creating') },
    [DeviceStatus.CREATE_FAILED]: { color: 'error', text: t('core.emulator2.status.createFailed') },
  }
  return map[props.status] ?? { color: 'default', text: t('core.emulator.deviceStatus.unknown') }
})
</script>

<template>
  <a-tag v-if="label" color="processing">
    <LoadingOutlined style="margin-right: 4px" />
    {{ label }}
  </a-tag>
  <a-tooltip v-else :title="device.creationError || undefined">
    <a-tag :color="tag.color">
      <LoadingOutlined v-if="isTransitional(status)" style="margin-right: 4px" />
      {{ tag.text }}
    </a-tag>
  </a-tooltip>
</template>

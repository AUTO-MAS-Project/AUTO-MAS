<template>
  <a-button
    :loading="loading"
    @click="$emit('click')"
  >
    <template v-if="iconComponent" #icon>
      <component :is="iconComponent" />
    </template>
    {{ action.label }}
  </a-button>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  AppstoreOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  ToolOutlined,
} from '@ant-design/icons-vue'
import type { HeaderSchemaAction } from '@/utils/schemaActions'

const props = defineProps<{
  action: HeaderSchemaAction
  loading?: boolean
}>()

defineEmits<{
  (e: 'click'): void
}>()

const iconMap = {
  AppstoreOutlined,
  PlayCircleOutlined,
  SettingOutlined,
  ToolOutlined,
  appstore: AppstoreOutlined,
  play: PlayCircleOutlined,
  setting: SettingOutlined,
  settings: SettingOutlined,
  tool: ToolOutlined,
} as const

const iconComponent = computed(() => {
  const icon = String(props.action.icon || '').trim()
  return icon ? iconMap[icon as keyof typeof iconMap] : null
})
</script>

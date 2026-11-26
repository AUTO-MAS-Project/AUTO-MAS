<script setup lang="ts">
import { CloudDownloadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { WhimboxConfig_Update } from '@/api'
import { SwitchTile } from '@/components/ui'

defineProps<{ ready: boolean }>()
const update = defineModel<WhimboxConfig_Update>('update', { required: true })
const emit = defineEmits<{ change: [enabled: boolean] }>()
const { t } = useI18n()

const handleEnabled = (enabled: boolean) => {
  update.value = { ...update.value, TakeoverEnabled: enabled }
  emit('change', enabled)
}
</script>

<template>
  <SwitchTile
    :checked="update.TakeoverEnabled ?? false"
    variant="card"
    :icon="CloudDownloadOutlined"
    :title="t('core.edit.whimboxUpdateBeforeRun')"
    :description="t('core.edit.whimboxUpdateBeforeRunHint')"
    :disabled="!ready"
    @change="handleEnabled"
  />
</template>

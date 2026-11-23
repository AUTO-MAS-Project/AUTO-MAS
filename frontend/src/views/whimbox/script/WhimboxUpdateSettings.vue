<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { WhimboxConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { SectionCard } from '@/components/ui'

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
  <SectionCard variant="plain" :title="t('core.edit.updateTakeover')">
    <a-form-item>
      <template #label>
        <FieldLabelWithHint
          :text="t('core.edit.whimboxUpdateBeforeRun')"
          :hint="t('core.edit.whimboxUpdateBeforeRunHint')"
          variant="form"
        />
      </template>
      <a-switch :checked="update.TakeoverEnabled" :disabled="!ready" @change="handleEnabled" />
    </a-form-item>
  </SectionCard>
</template>

<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>

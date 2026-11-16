<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { WhimboxConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

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
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('core.edit.updateTakeover') }}</h3>
    </div>
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
  </div>
</template>

<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { MaaEndConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

defineProps<{ ready: boolean }>()
const update = defineModel<MaaEndConfig_Update>('update', { required: true })
const emit = defineEmits<{ save: [key: string, value: boolean | string] }>()
const { t } = useI18n()
</script>

<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ t('core.edit.maaEndProgramUpdate') }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverSwitch')"
              :hint="t('core.edit.maaEndProgramUpdateHint')"
              variant="form"
            />
          </template>
          <a-switch
            v-model:checked="update.TakeoverEnabled"
            :disabled="!ready"
            @change="(value: boolean) => emit('save', 'TakeoverEnabled', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item :label="t('core.edit.updateChannel')">
          <a-select
            v-model:value="update.Channel"
            :disabled="!ready"
            size="large"
            :options="[
              { label: t('core.setting.channel.stable'), value: 'stable' },
              { label: t('core.setting.channel.beta'), value: 'beta' },
            ]"
            @change="(value: string) => emit('save', 'Channel', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverCdk')"
              :hint="t('core.edit.maaEndUpdateCdkHint')"
              variant="form"
            />
          </template>
          <a-input-password
            v-model:value="update.MirrorChyanCDK"
            :disabled="!ready || !update.TakeoverEnabled"
            size="large"
            autocomplete="off"
            :placeholder="t('core.edit.updateTakeoverCdkPlaceholder')"
            @blur="emit('save', 'MirrorChyanCDK', update.MirrorChyanCDK ?? '')"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>
<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>

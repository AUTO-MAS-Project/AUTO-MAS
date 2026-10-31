<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'

defineProps<{
  ready: boolean
  enabled: boolean
  channel: 'stable' | 'beta'
  cdk: string
  title: string
  hint: string
  cdkHint: string
}>()
const emit = defineEmits<{
  enabled: [value: boolean]
  channel: [value: 'stable' | 'beta']
  cdk: [value: string]
  saveCdk: []
}>()
const { t } = useI18n()
</script>

<template>
  <div class="form-section">
    <div class="section-header">
      <h3>{{ title }}</h3>
    </div>
    <a-row :gutter="24">
      <a-col :span="8">
        <a-form-item :label="t('core.edit.updateChannel')">
          <a-select
            :value="channel"
            :disabled="!ready"
            size="large"
            :options="[
              { label: t('core.setting.channel.stable'), value: 'stable' },
              { label: t('core.setting.channel.beta'), value: 'beta' },
            ]"
            @change="(value: 'stable' | 'beta') => emit('channel', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverSwitch')"
              :hint="hint"
              variant="form"
            />
          </template>
          <a-switch
            :checked="enabled"
            size="large"
            :disabled="!ready"
            @change="(value: boolean) => emit('enabled', value)"
          />
        </a-form-item>
      </a-col>
      <a-col :span="8">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverCdk')"
              :hint="cdkHint"
              variant="form"
            />
          </template>
          <a-input-password
            :value="cdk"
            :placeholder="t('core.edit.updateTakeoverCdkPlaceholder')"
            size="large"
            class="modern-input"
            autocomplete="off"
            :disabled="!ready || !enabled"
            @update:value="(value: string) => emit('cdk', value)"
            @blur="emit('saveCdk')"
          />
          <slot name="cdk-status" />
        </a-form-item>
      </a-col>
    </a-row>
  </div>
</template>

<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>

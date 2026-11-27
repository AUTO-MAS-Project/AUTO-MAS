<script setup lang="ts">
import { AppstoreOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { SectionCard } from '@/components/ui'

withDefaults(
  defineProps<{
    name: string
    nameField?: string | null
    nameHint?: string
    placeholder?: string
  }>(),
  { nameField: 'name', nameHint: undefined, placeholder: undefined }
)
const emit = defineEmits<{
  'update:name': [value: string]
  saveName: [value: string]
}>()
const { t } = useI18n()
</script>

<template>
  <SectionCard variant="card" :title="t('core.edit.basicInfo')" :icon="AppstoreOutlined">
    <template v-if="$slots.actions" #actions>
      <slot name="actions" />
    </template>
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <a-form-item :name="nameField ?? undefined">
          <template #label>
            <FieldLabelWithHint :text="t('core.edit.scriptName')" :hint="nameHint" variant="form" />
          </template>
          <a-input
            :value="name"
            :placeholder="placeholder ?? t('core.edit.enterScriptName')"
            size="large"
            class="modern-input"
            @update:value="emit('update:name', $event)"
            @blur="emit('saveName', name)"
          />
        </a-form-item>
      </a-col>
      <a-col v-if="$slots.path" :xs="24" :md="12">
        <slot name="path" />
      </a-col>
    </a-row>
  </SectionCard>
</template>

<style scoped src="@/styles/scriptEdit.css"></style>

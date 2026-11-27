<script setup lang="ts">
import { computed, useSlots } from 'vue'
import ConfigLockPanel from '@/components/ConfigLockPanel.vue'
import GameBindingSection from '@/components/GameBindingSection.vue'
import ScriptEditHeader from '@/components/ScriptEditHeader.vue'
import { ConfigEditShell } from '@/components/ui'
import type { ScriptType } from '@/types/script'

interface EditForm {
  model: Record<string, any>
  rules?: Record<string, any>
}

withDefaults(
  defineProps<{
    scriptId: string
    loading: boolean
    header: {
      scriptType: ScriptType
      title?: string
      docUrl?: string
      logoSrc?: string
      logoAlt?: string
      logoFallbackSrc?: string
      cancelDisabled?: boolean
    }
    form: EditForm
    bodyForm?: EditForm
    formLabel?: string
    bindingVisible?: boolean
  }>(),
  { bindingVisible: true, bodyForm: undefined, formLabel: undefined }
)

const emit = defineEmits<{ cancel: [] }>()
const slots = useSlots()
const hasBodySlots = computed(() =>
  Boolean(
    slots['script-config'] ||
    slots['game-config'] ||
    slots['game-update'] ||
    slots.run ||
    slots['program-update'] ||
    slots.advanced
  )
)
</script>

<template>
  <ConfigEditShell :surface="false" :max-width="1040">
    <template #header>
      <ScriptEditHeader v-bind="header" @cancel="emit('cancel')">
        <template v-if="$slots['extra-actions']" #extra-actions>
          <slot name="extra-actions" />
        </template>
        <template v-if="$slots['after-doc-actions']" #after-doc-actions>
          <slot name="after-doc-actions" />
        </template>
      </ScriptEditHeader>
    </template>

    <ConfigLockPanel
      :script-id="scriptId"
      content-class="script-edit-content"
      :role="formLabel ? 'form' : undefined"
      :aria-label="formLabel"
    >
      <slot name="notice" />
      <a-spin :spinning="loading">
        <slot name="before-basic" />
        <a-form :model="form.model" :rules="form.rules" layout="vertical" class="config-form">
          <slot name="basic" />
        </a-form>
        <div v-show="bindingVisible">
          <GameBindingSection :script-id="scriptId" />
        </div>
        <a-form
          v-if="hasBodySlots"
          :model="(bodyForm ?? form).model"
          :rules="(bodyForm ?? form).rules"
          layout="vertical"
          class="config-form"
        >
          <slot name="script-config" />
          <slot name="game-config" />
          <slot name="game-update" />
          <slot name="run" />
          <slot name="program-update" />
          <slot name="advanced" />
        </a-form>
        <slot name="after-form" />
      </a-spin>
    </ConfigLockPanel>

    <template v-if="$slots.overlay" #overlay>
      <slot name="overlay" />
    </template>
  </ConfigEditShell>
</template>

<style scoped>
.script-edit-content {
  flex: 1;
  width: 100%;
}

.config-form :deep(.ant-form-item) {
  margin-bottom: 18px;
}
</style>

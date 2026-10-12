<script setup lang="ts">
import { ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'

import type { MyAppearanceItem } from '@/composables/useShareApi'
import type { MyAppearanceStore } from '../useMyAppearances'

const props = defineProps<{
  open: boolean
  item: MyAppearanceItem | null
  store: MyAppearanceStore
}>()

const emit = defineEmits<{
  (event: 'update:open', value: boolean): void
}>()

const DESCRIPTION_MAX = 2000

const { t } = useI18n()
const description = ref('')
const saving = ref(false)

const close = (): void => {
  if (saving.value) return
  emit('update:open', false)
}

const save = async (): Promise<void> => {
  const item = props.item
  if (!item || saving.value) return
  saving.value = true
  try {
    const result = await props.store.updateDescription(item.fileId, description.value.trim())
    if (!result.ok) {
      message.error(result.message || t('themeStore.mine.descriptionFailed'))
      return
    }
    message.success(t('themeStore.mine.descriptionSaved'))
    emit('update:open', false)
  } finally {
    saving.value = false
  }
}

watch(
  () => props.open,
  isOpen => {
    if (isOpen) description.value = props.item?.description ?? ''
  }
)
</script>

<template>
  <a-modal
    :open="open"
    :width="520"
    :z-index="90"
    :style="{ top: '48px' }"
    :title="t('themeStore.mine.editDescription')"
    :closable="!saving"
    :keyboard="!saving"
    :mask-closable="!saving"
    :confirm-loading="saving"
    :ok-text="t('common.confirm')"
    :cancel-text="t('common.cancel')"
    @ok="save"
    @cancel="close"
  >
    <div v-if="item" class="description-target">{{ item.displayName || item.fileKey }}</div>
    <a-textarea
      v-model:value="description"
      :maxlength="DESCRIPTION_MAX"
      show-count
      :auto-size="{ minRows: 4, maxRows: 10 }"
      :disabled="saving"
    />
  </a-modal>
</template>

<style scoped>
.description-target {
  margin-bottom: 8px;
  color: var(--ant-color-text-secondary);
  overflow-wrap: anywhere;
}
</style>

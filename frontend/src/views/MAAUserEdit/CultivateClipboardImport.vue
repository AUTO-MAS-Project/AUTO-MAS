<template>
  <a-button :disabled="disabled" :loading="busy" @click="readClipboard">
    {{ t(busy ? 'edit.maaCultivateImporting' : 'edit.maaCultivateImportClipboard') }}
  </a-button>
  <a-modal
    v-model:open="manualOpen"
    wrap-class-name="maa-plan-settings-modal"
    centered
    :title="t('edit.maaCultivateImportClipboard')"
    :ok-text="t('edit.maaCultivateImportSubmit')"
    :cancel-text="t('common.cancel')"
    :confirm-loading="busy"
    :ok-button-props="{ disabled: disabled || !manualText.trim() }"
    :cancel-button-props="{ disabled: busy }"
    :closable="!busy"
    :mask-closable="false"
    :keyboard="!busy"
    @ok="importText(manualText)"
  >
    <p>{{ t('edit.maaCultivateImportPasteHint') }}</p>
    <a-textarea
      v-model:value="manualText"
      :disabled="disabled || busy"
      :placeholder="t('edit.maaCultivateImportPlaceholder')"
      :auto-size="{ minRows: 5, maxRows: 10 }"
    />
  </a-modal>
  <a-modal
    v-model:open="reportOpen"
    :title="t('edit.maaCultivateImportSkipped', { count: skippedMessages.length })"
    wrap-class-name="maa-plan-settings-modal"
    centered
    destroy-on-close
  >
    <ul class="cultivate-import-skipped">
      <li v-for="(text, index) in skippedMessages" :key="index">{{ text }}</li>
    </ul>
    <template #footer>
      <a-button type="primary" @click="reportOpen = false">{{ t('common.confirm') }}</a-button>
    </template>
  </a-modal>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { CultivateImportResult } from './cultivateTargets'

const props = defineProps<{
  disabled: boolean
  importTargets: (content: string) => Promise<CultivateImportResult>
}>()
const emit = defineEmits<{ busy: [value: boolean]; imported: [operatorIds: string[]] }>()
const { t } = useI18n()
const busy = ref(false)
const manualOpen = ref(false)
const manualText = ref('')
const reportOpen = ref(false)
const skippedMessages = ref<string[]>([])

const setBusy = (value: boolean) => {
  busy.value = value
  emit('busy', value)
}

const applyImport = async (content: string) => {
  if (!content.trim()) throw new Error(t('edit.maaCultivateImportEmpty'))
  const result = await props.importTargets(content)
  if (result.added || result.updated) {
    message.success(
      t('edit.maaCultivateImportSuccess', { added: result.added, updated: result.updated })
    )
    emit('imported', result.operatorIds)
  } else if (!result.skipped?.length) {
    message.info(t('edit.maaCultivateImportUnchanged'))
  }
  // 后端已校验导入文本；这里只检查等级字段，用于说明被忽略的目标。
  const payload: unknown = JSON.parse(content.trim())
  if (
    Array.isArray(payload) &&
    payload.some(item => item && typeof item === 'object' && 'level' in item)
  ) {
    message.warning(t('edit.maaCultivateImportLevelIgnored'))
  }
  if (result.added || result.updated || !result.skipped?.length) {
    manualOpen.value = false
    manualText.value = ''
  }
  if (result.skipped?.length) {
    skippedMessages.value = result.skipped
    reportOpen.value = true
  }
}

const importText = async (content: string) => {
  if (props.disabled || busy.value) return
  setBusy(true)
  try {
    await applyImport(content)
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.maaCultivateImportFailed'))
  } finally {
    setBusy(false)
  }
}

const readClipboard = async () => {
  if (props.disabled || busy.value) return
  setBusy(true)
  try {
    let content: string
    try {
      content = await navigator.clipboard.readText()
    } catch {
      manualOpen.value = true
      return
    }
    await applyImport(content)
  } catch (error) {
    message.error(error instanceof Error ? error.message : t('edit.maaCultivateImportFailed'))
  } finally {
    setBusy(false)
  }
}
</script>

<style scoped>
.cultivate-import-skipped {
  margin: 0;
  padding-inline-start: 20px;
}
</style>

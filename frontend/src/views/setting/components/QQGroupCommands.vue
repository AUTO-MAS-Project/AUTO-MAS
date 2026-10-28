<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  members: string[]
  saving: boolean
  disabled: boolean
  save: (members: string[]) => Promise<boolean>
}>()
const { t } = useI18n()
const draft = defineModel<string>({ required: true })
const values = computed(() => [
  ...new Set(
    draft.value
      .split(/\r?\n/)
      .map(v => v.trim())
      .filter(Boolean)
  ),
])
const dirty = computed(() => JSON.stringify(values.value) !== JSON.stringify(props.members))
const invalid = computed(
  () => values.value.length > 100 || values.value.some(v => v.length > 128 || /\s/.test(v))
)
</script>

<template>
  <a-form-item
    :label="t('setting.notify.openclawQqCommandWhitelist')"
    html-for="qq-command-whitelist"
    :validate-status="invalid ? 'error' : undefined"
    :help="invalid ? t('setting.notify.openclawQqWhitelistInvalid') : undefined"
  >
    <a-space direction="vertical" class="group-commands">
      <a-typography-paragraph type="secondary">
        {{ t('setting.notify.openclawQqGroupCommandHint') }}
      </a-typography-paragraph>
      <a-textarea
        id="qq-command-whitelist"
        v-model:value="draft"
        :auto-size="{ minRows: 3, maxRows: 6 }"
        :disabled="disabled"
        :placeholder="t('setting.notify.openclawQqWhitelistPlaceholder')"
      />
      <a-alert
        v-if="!values.length"
        type="info"
        show-icon
        :message="t('setting.notify.openclawQqWhitelistEmpty')"
      />
      <a-button :loading="saving" :disabled="disabled || !dirty || invalid" @click="save(values)">
        {{ t('setting.notify.openclawQqWhitelistSave') }}
      </a-button>
    </a-space>
  </a-form-item>
</template>

<style scoped>
.group-commands {
  width: 100%;
}
</style>

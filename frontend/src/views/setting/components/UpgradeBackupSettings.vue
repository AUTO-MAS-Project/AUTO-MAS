<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import { getConfig, saveConfig, type FrontendConfig } from '@/utils/config'

const { t } = useI18n()
type Preferences = Required<NonNullable<FrontendConfig['upgradeBackup']>>
const preferences = ref<Preferences>({ enabled: true, directory: null })
const loading = ref(true)
const saving = ref(false)
const available = ref(false)

onMounted(async () => {
  try {
    const config = await getConfig({ strict: true })
    preferences.value = { ...preferences.value, ...config.upgradeBackup }
    available.value = true
  } catch {
    message.error(t('core.update.backupSettings.loadFailed'))
  } finally {
    loading.value = false
  }
})

async function update(patch: Partial<Preferences>) {
  await saveConfig({ upgradeBackup: patch })
  preferences.value = { ...preferences.value, ...patch }
}

async function setEnabled(checked: boolean | string | number) {
  saving.value = true
  try {
    await update({ enabled: checked === true })
  } catch {
    message.error(t('core.update.backupSettings.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function setDirectory(reset: boolean) {
  saving.value = true
  try {
    const directory = reset ? null : await window.electronAPI.selectFolder()
    if (reset || directory !== null) await update({ directory })
  } catch {
    message.error(t('core.update.backupSettings.directoryFailed'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <SettingRow
    :label="t('core.update.backupSettings.enabled')"
    :description="t('core.update.backupSettings.enabledDescription')"
  >
    <a-switch
      :checked="preferences.enabled"
      :loading="loading || saving"
      :disabled="!available"
      :aria-label="t('core.update.backupSettings.enabled')"
      @change="setEnabled"
    />
  </SettingRow>
  <SettingRow
    :label="t('core.update.backupSettings.directory')"
    :description="t('core.update.backupSettings.directoryDescription')"
    :disabled="!preferences.enabled"
  >
    <a-flex :gap="4" style="width: 100%">
      <a-input
        readonly
        :disabled="!available || !preferences.enabled"
        :value="preferences.directory ?? t('core.update.backupSettings.defaultDirectory')"
        :title="preferences.directory ?? undefined"
        :aria-label="t('core.update.backupSettings.directory')"
        style="min-width: 0; flex: 1"
      />
      <a-button
        :disabled="!available || !preferences.enabled || saving"
        @click="setDirectory(false)"
      >
        {{ t('core.update.backupSettings.chooseDirectory') }}
      </a-button>
      <a-button
        v-if="preferences.directory"
        :disabled="!preferences.enabled || saving"
        @click="setDirectory(true)"
      >
        {{ t('core.update.backupSettings.resetDirectory') }}
      </a-button>
    </a-flex>
  </SettingRow>
</template>

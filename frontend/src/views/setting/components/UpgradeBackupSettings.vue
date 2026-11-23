<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import AppModal from '@/components/ui/AppModal.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import { getConfig, saveConfig } from '@/utils/config'
import type { UpgradeBackupDirectory, UpgradeBackupSelection } from '@/types/upgradeBackup'

const { t } = useI18n()
const logger = window.electronAPI.getLogger('升级备份设置')
const enabled = ref(true)
const directory = ref<UpgradeBackupDirectory>()
const selection = ref<UpgradeBackupSelection>()
const confirmOpen = ref(false)
const moving = ref(false)
const loading = ref(true)
const saving = ref(false)
const available = ref(false)

onMounted(async () => {
  try {
    const [config, current] = await Promise.all([
      getConfig({ strict: true }),
      window.electronAPI.getUpgradeBackupDirectory(),
    ])
    enabled.value = config.upgradeBackup?.enabled ?? true
    directory.value = current
    available.value = true
  } catch {
    message.error(t('core.update.backupSettings.loadFailed'))
  } finally {
    loading.value = false
  }
})

async function setEnabled(checked: boolean | string | number) {
  saving.value = true
  try {
    const next = checked === true
    await saveConfig({ upgradeBackup: { enabled: next } })
    enabled.value = next
  } catch {
    message.error(t('core.update.backupSettings.saveFailed'))
  } finally {
    saving.value = false
  }
}

async function setDirectory(reset: boolean) {
  saving.value = true
  try {
    const chosen = await window.electronAPI.chooseUpgradeBackupDirectory(reset)
    if (!chosen) return
    selection.value = chosen
    confirmOpen.value = true
  } catch {
    message.error(t('core.update.backupSettings.directoryFailed'))
  } finally {
    saving.value = false
  }
}

async function cancelDirectoryChange() {
  const chosen = selection.value
  selection.value = undefined
  if (!chosen) return
  try {
    await window.electronAPI.cancelUpgradeBackupDirectory(chosen.id)
  } catch {
    logger.warn('关闭弹窗后未能释放备份目录选择')
  }
}

async function confirmDirectoryChange() {
  const chosen = selection.value
  if (!chosen || moving.value) return
  moving.value = true
  try {
    directory.value = await window.electronAPI.confirmUpgradeBackupDirectory(chosen.id)
    if (directory.value.cleanupPending)
      message.warning(t('core.update.backupSettings.cleanupPending'))
  } catch {
    message.error(t('core.update.backupSettings.directoryFailed'))
  } finally {
    moving.value = false
    confirmOpen.value = false
    selection.value = undefined
  }
}
</script>

<template>
  <SettingRow
    :label="t('core.update.backupSettings.enabled')"
    :description="t('core.update.backupSettings.enabledDescription')"
  >
    <a-switch
      :checked="enabled"
      :loading="loading || saving"
      :disabled="!available || confirmOpen"
      :aria-label="t('core.update.backupSettings.enabled')"
      @change="setEnabled"
    />
  </SettingRow>
  <SettingRow
    :label="t('core.update.backupSettings.directory')"
    :description="t('core.update.backupSettings.directoryDescription')"
    :disabled="!enabled"
  >
    <a-flex :gap="4" style="width: 100%">
      <a-input
        readonly
        :disabled="!available || !enabled"
        :value="directory?.directory ?? t('core.update.backupSettings.defaultDirectory')"
        :title="directory?.resolvedDirectory"
        :aria-label="t('core.update.backupSettings.directory')"
        style="min-width: 0; flex: 1"
      />
      <a-button
        :disabled="!available || !enabled || saving || confirmOpen"
        @click="setDirectory(false)"
      >
        {{ t('core.update.backupSettings.chooseDirectory') }}
      </a-button>
      <a-button
        v-if="directory?.directory"
        :disabled="!enabled || saving || confirmOpen"
        @click="setDirectory(true)"
      >
        {{ t('core.update.backupSettings.resetDirectory') }}
      </a-button>
    </a-flex>
  </SettingRow>
  <AppModal
    v-model:open="confirmOpen"
    :title="t('core.update.backupSettings.confirmTitle')"
    :ok-text="t('core.update.backupSettings.moveAction')"
    :mask-closable="false"
    :submitting="moving"
    @ok="confirmDirectoryChange"
    @cancel="cancelDirectoryChange"
  >
    <dl v-if="selection" class="backup-directory-comparison">
      <dt>{{ t('core.update.backupSettings.currentDirectory') }}</dt>
      <dd>{{ selection.current }}</dd>
      <dt>{{ t('core.update.backupSettings.targetDirectory') }}</dt>
      <dd>{{ selection.target }}</dd>
    </dl>
    <p>{{ t('core.update.backupSettings.confirmDescription') }}</p>
  </AppModal>
</template>

<style scoped>
.backup-directory-comparison {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 8px 16px;
  margin-block: 0 16px;
}

.backup-directory-comparison dd {
  margin: 0;
  overflow-wrap: anywhere;
}
</style>

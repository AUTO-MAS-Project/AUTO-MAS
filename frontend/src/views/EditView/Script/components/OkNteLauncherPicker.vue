<template>
  <PathPickerField
    :model-value="path"
    mode="folder"
    :placeholder="t('core.edit.pickGameLauncherDirectory')"
    :pick-label="t('core.edit.pickDirectory')"
    :disabled="disabled"
    @pick="pickDirectory"
  >
    <template #after-pick>
      <a-button size="large" :disabled="disabled" @click="pickFile">
        {{ t('core.edit.okntePickLauncherFile') }}
      </a-button>
    </template>
  </PathPickerField>
  <span class="control-hint">{{ t('core.edit.okntePickDirHint') }}</span>
</template>

<script setup lang="ts">
import { Modal } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import PathPickerField from '@/components/PathPickerField.vue'

defineProps<{ path?: string | null; disabled: boolean }>()
const emit = defineEmits<{ select: [path: string] }>()
const { t } = useI18n()

const pickFile = async () => {
  const paths = await window.electronAPI.selectFile([{ name: 'Executable', extensions: ['exe'] }])
  const picked = paths?.[0]?.replace(/\\/g, '/')
  if (!picked) return
  if (!picked.toLowerCase().endsWith('.exe') || picked.toLowerCase().endsWith('/htgame.exe')) {
    Modal.error({
      title: t('core.edit.oknteLauncherNotFoundTitle'),
      content: t('core.edit.oknteLauncherInvalid'),
      okText: t('core.edit.gotIt'),
    })
    return
  }
  emit('select', picked)
}

const pickDirectory = async () => {
  const picked = await window.electronAPI.selectFolder()
  if (!picked) return
  const normalized = picked.replace(/\\/g, '/')
  const anchor = 'Neverness To Everness'
  const idx = normalized.toLowerCase().indexOf(anchor.toLowerCase())
  if (idx !== -1) {
    const root = `${normalized.substring(0, idx)}${anchor}`
    const candidates = [
      `${root}/NTEGlobalLauncher.exe`,
      ...['NTEGame.exe', 'NTEGlobalGame.exe', 'NTETWGame.exe'].map(
        exe => `${root}/NTELauncher/${exe}`
      ),
    ]
    for (const candidate of candidates) {
      if (await window.electronAPI.fileExists(candidate)) {
        emit('select', candidate)
        return
      }
    }
  }
  Modal.error({
    title: t('core.edit.oknteLauncherNotFoundTitle'),
    content: t('core.edit.oknteLauncherNotFound'),
    okText: t('core.edit.gotIt'),
  })
}
</script>

<style scoped src="@/styles/scriptEditForm.css"></style>

<script setup lang="ts">
import { CloudSyncOutlined } from '@ant-design/icons-vue'
import { nextTick } from 'vue'
import { useI18n } from 'vue-i18n'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { SectionCard, SwitchTile } from '@/components/ui'

const props = defineProps<{
  checkUpdate: boolean
  autoInstallApk: boolean
  timeLimit: number | null | undefined
  checkDescription: string
}>()
const emit = defineEmits<{
  'update:checkUpdate': [value: boolean]
  'update:autoInstallApk': [value: boolean]
  'update:timeLimit': [value: number | null]
  save: [
    key: 'IfCheckGameUpdate' | 'IfAutoInstallGameApk' | 'GameUpdateTimeLimit',
    value: boolean | number | null,
  ]
}>()
const { t } = useI18n()

async function saveTimeLimit() {
  // 数字框可能在失焦时校正数值，等父表单收到新值再保存。
  await nextTick()
  emit('save', 'GameUpdateTimeLimit', props.timeLimit ?? null)
}
</script>

<template>
  <SectionCard variant="card" :title="t('core.edit.gameUpdate')" :icon="CloudSyncOutlined">
    <a-row :gutter="[16, 12]" class="switch-tile-row">
      <a-col :xs="24" :md="12">
        <SwitchTile
          :checked="checkUpdate"
          :title="t('core.edit.checkGameUpdateBefore')"
          :description="checkDescription"
          @update:checked="emit('update:checkUpdate', $event)"
          @change="emit('save', 'IfCheckGameUpdate', $event)"
        />
      </a-col>
      <a-col :xs="24" :md="12">
        <SwitchTile
          :checked="autoInstallApk"
          :title="t('core.edit.installGamePackageAutomatically')"
          :description="t('core.edit.whenClientDetectedAs')"
          :disabled="!checkUpdate"
          @update:checked="emit('update:autoInstallApk', $event)"
          @change="emit('save', 'IfAutoInstallGameApk', $event)"
        />
      </a-col>
    </a-row>
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.gameUpdateTimeoutMinutes')"
              :hint="t('core.edit.timeoutDownloadingInstallingGame')"
              variant="form"
            />
          </template>
          <a-input-number
            :value="timeLimit"
            :min="1"
            :max="9999"
            :disabled="!checkUpdate"
            class="modern-number-input"
            style="width: 100%"
            @update:value="emit('update:timeLimit', $event)"
            @blur="saveTimeLimit"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </SectionCard>
</template>

<style scoped src="@/styles/scriptEdit.css"></style>

<style scoped>
.switch-tile-row {
  margin-bottom: 16px;
}
</style>

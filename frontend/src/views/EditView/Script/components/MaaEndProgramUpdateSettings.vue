<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import type { MaaEndConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { CloudDownloadOutlined } from '@ant-design/icons-vue'
import { SectionCard, SwitchTile } from '@/components/ui'
import UpdatePackageMode from './UpdatePackageMode.vue'

defineProps<{ ready: boolean }>()
const update = defineModel<MaaEndConfig_Update>('update', { required: true })
const packageMode = computed({
  get: () => update.value.PackageMode ?? 'full',
  set: (value: 'full' | 'incremental') => {
    update.value.PackageMode = value
  },
})
const emit = defineEmits<{ save: [key: string, value: boolean | string] }>()
const { t } = useI18n()
const handleChannel = (channel: 'stable' | 'beta') => {
  update.value = { ...update.value, Channel: channel }
  emit('save', 'Channel', channel)
}
function handleTakeoverChange(value: boolean) {
  update.value.TakeoverEnabled = value
  emit('save', 'TakeoverEnabled', value)
}
</script>

<template>
  <SectionCard
    variant="card"
    :title="t('core.edit.maaEndProgramUpdate')"
    :icon="CloudDownloadOutlined"
  >
    <a-row :gutter="24">
      <a-col :xs="24" :md="12">
        <a-form-item :label="t('core.edit.updateChannel')">
          <a-select
            :value="update.Channel"
            :disabled="!ready"
            :options="[
              { label: t('core.setting.channel.stable'), value: 'stable' },
              { label: t('core.setting.channel.beta'), value: 'beta' },
            ]"
            @change="handleChannel"
          />
        </a-form-item>
      </a-col>
      <a-col :xs="24" :md="12">
        <UpdatePackageMode
          v-model="packageMode"
          :disabled="!ready || !update.TakeoverEnabled"
          @change="emit('save', 'PackageMode', $event)"
        />
      </a-col>
      <a-col :xs="24" :md="12">
        <a-form-item>
          <template #label>
            <FieldLabelWithHint
              :text="t('core.edit.updateTakeoverCdk')"
              :hint="t('core.edit.maaEndUpdateCdkHint')"
              variant="form"
            />
          </template>
          <a-input-password
            v-model:value="update.MirrorChyanCDK"
            :disabled="!ready || !update.TakeoverEnabled"
            autocomplete="off"
            :placeholder="t('core.edit.updateTakeoverCdkPlaceholder')"
            @blur="emit('save', 'MirrorChyanCDK', update.MirrorChyanCDK ?? '')"
          />
        </a-form-item>
      </a-col>
    </a-row>
    <a-row :gutter="24" style="margin-bottom: 12px">
      <a-col :xs="24" :md="12">
        <SwitchTile
          :checked="Boolean(update.TakeoverEnabled)"
          :title="t('core.edit.updateTakeoverSwitch')"
          :description="t('core.edit.maaEndProgramUpdateHint')"
          :disabled="!ready"
          @change="handleTakeoverChange"
        />
      </a-col>
    </a-row>
  </SectionCard>
</template>
<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>

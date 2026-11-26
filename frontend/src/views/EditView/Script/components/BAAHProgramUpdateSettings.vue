<script setup lang="ts">
import { CloudDownloadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { BAAHConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { SectionCard, SwitchTile } from '@/components/ui'

defineProps<{ ready: boolean }>()
const update = defineModel<BAAHConfig_Update>('update', { required: true })
const emit = defineEmits<{ save: [key: string, value: boolean | string] }>()
const { t } = useI18n()
const handleChannel = (channel: 'stable' | 'beta') => {
  update.value = { ...update.value, Channel: channel }
  emit('save', 'Channel', channel)
}
</script>

<template>
  <SectionCard
    variant="card"
    :title="t('core.edit.baahProgramUpdate')"
    :icon="CloudDownloadOutlined"
  >
    <a-row :gutter="24" style="margin-bottom: 16px">
      <a-col :xs="24" :md="12">
        <SwitchTile
          :checked="update.TakeoverEnabled ?? false"
          :title="t('core.edit.updateTakeoverSwitch')"
          :description="t('core.edit.baahProgramUpdateHint')"
          :disabled="!ready"
          @update:checked="update.TakeoverEnabled = $event"
          @change="emit('save', 'TakeoverEnabled', $event)"
        />
      </a-col>
    </a-row>
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
  </SectionCard>
</template>
<style scoped src="@/styles/scriptEditForm.css"></style>
<style scoped src="@/styles/scriptEdit.css"></style>

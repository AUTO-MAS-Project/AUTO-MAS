<script setup lang="ts">
import { CloudDownloadOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { BAAHConfig_Update, BetterGIConfig_Update } from '@/api'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import { SectionCard, SwitchTile } from '@/components/ui'

defineProps<{
  ready: boolean
  title: string
  takeoverHint: string
}>()
const update = defineModel<BAAHConfig_Update | BetterGIConfig_Update>('update', { required: true })
const emit = defineEmits<{ save: [key: string, value: boolean | string] }>()
const { t } = useI18n()

function handleChannel(channel: 'stable' | 'beta') {
  update.value = { ...update.value, Channel: channel }
  emit('save', 'Channel', channel)
}
</script>

<template>
  <SectionCard variant="card" :title="title" :icon="CloudDownloadOutlined">
    <a-row :gutter="24" style="margin-bottom: 16px">
      <a-col :xs="24" :md="12">
        <SwitchTile
          :checked="update.TakeoverEnabled ?? false"
          :title="t('core.edit.updateTakeoverSwitch')"
          :description="takeoverHint"
          :disabled="!ready"
          @update:checked="update = { ...update, TakeoverEnabled: $event }"
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
            :value="update.MirrorChyanCDK ?? ''"
            :disabled="!ready || !update.TakeoverEnabled"
            autocomplete="off"
            :placeholder="t('core.edit.updateTakeoverCdkPlaceholder')"
            @update:value="update = { ...update, MirrorChyanCDK: $event }"
            @blur="emit('save', 'MirrorChyanCDK', update.MirrorChyanCDK ?? '')"
          />
        </a-form-item>
      </a-col>
    </a-row>
  </SectionCard>
</template>

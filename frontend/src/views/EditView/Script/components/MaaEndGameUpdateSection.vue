<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ThunderboltOutlined } from '@ant-design/icons-vue'
import { SwitchTile } from '@/components/ui'
import FieldLabelWithHint from '@/components/FieldLabelWithHint.vue'
import type { MaaEndScriptConfig } from '@/types/script'
defineProps<{ launcherMode: boolean; disabled: boolean }>()
const game = defineModel<MaaEndScriptConfig['Game']>('game', { required: true })
const emit = defineEmits<{ save: [key: string, value: boolean]; timeoutBlur: []; check: [] }>()
const { t } = useI18n()
</script>
<template>
  <a-row :gutter="24">
    <a-col :xs="24" :md="12">
      <a-form-item>
        <template #label>
          <FieldLabelWithHint
            :text="t('core.edit.gameUpdateTimeoutMinutes')"
            :hint="t('core.edit.endfieldUpdateTimeoutHint')"
            variant="form"
          />
        </template>
        <a-input-number
          v-model:value="game.UpdateTimeLimit"
          :min="1"
          :max="9999"
          :precision="0"
          style="width: 100%"
          @blur="emit('timeoutBlur')"
        />
      </a-form-item>
    </a-col>
    <a-col :xs="24" :md="12">
      <a-form-item :label="t('core.edit.endfieldManualUpdate')">
        <a-tooltip :title="game.Path ? '' : t('core.edit.pickEndfieldExePath')">
          <span class="endfield-update-check">
            <a-button :disabled="disabled || !game.Path" @click="emit('check')">
              <template #icon>
                <ThunderboltOutlined />
              </template>
              {{ t('core.edit.checkUpdates') }}
            </a-button>
          </span>
        </a-tooltip>
      </a-form-item>
    </a-col>
  </a-row>
  <a-row :gutter="24" style="margin-bottom: 12px">
    <a-col :xs="24" :md="12">
      <SwitchTile
        v-model:checked="game.IfAutoUpdate"
        :title="t('core.edit.endfieldAutoUpdate')"
        :description="
          launcherMode
            ? t('core.edit.maaEndAutoUpdateLauncherHint')
            : t('core.edit.endfieldAutoUpdateHint')
        "
        :disabled="launcherMode"
        @change="emit('save', 'IfAutoUpdate', $event)"
      />
    </a-col>
  </a-row>
</template>
<style scoped src="@/styles/scriptEditForm.css"></style>

<style scoped>
.endfield-update-check {
  display: inline-block;
}
</style>

<template>
  <div>
    <div class="sanity-task-toggle" :class="{ 'sanity-task-enabled': showDetail }">
      <span>{{ t('core.edit.maaEndEnableSanity') }}</span>
      <a-switch
        :checked="enabled"
        :disabled="disabled"
        :aria-label="t('core.edit.maaEndEnableSanity')"
        @change="(value: boolean) => emit('enable', value)"
      />
    </div>
    <template v-if="showDetail">
      <a-form-item :label="t('core.edit.maaEndSanityStrategy')">
        <a-radio-group
          :value="strategy"
          :disabled="disabled"
          class="strategy-options"
          @change="handleStrategyChange"
        >
          <a-radio-button
            v-for="option in sanityStrategyOptions"
            :key="option.value"
            :value="option.value"
          >
            {{ option.label }}
          </a-radio-button>
        </a-radio-group>
      </a-form-item>
      <a-form-item v-if="strategy === 'Native'">
        <a-space direction="vertical" size="middle" style="width: 100%">
          <a-alert type="info" show-icon :message="t('core.edit.maaEndNativeSanityHint')" />
          <a-button
            :loading="configLoading"
            :disabled="disabled || showConfigMask"
            @click="emit('configure')"
          >
            <template #icon><SettingOutlined /></template>
            {{ t('core.edit.maaEndConfigureInventory') }}
          </a-button>
          <span>{{ t('core.edit.maaEndInventorySourceHint') }}</span>
        </a-space>
      </a-form-item>
    </template>

    <p v-if="showDetail && strategy === 'Inventory'" class="strategy-hint">
      {{ t('core.edit.maaEndImsStrategyHint') }}
    </p>
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { SettingOutlined } from '@ant-design/icons-vue'
import type { RadioChangeEvent } from 'ant-design-vue'
defineProps<{
  enabled: boolean
  showDetail: boolean
  strategy: string
  disabled: boolean
  configLoading: boolean
  showConfigMask: boolean
}>()
const emit = defineEmits<{ enable: [value: boolean]; save: [value: string]; configure: [] }>()
const { t } = useI18n()
const handleStrategyChange = (event: RadioChangeEvent) => emit('save', event.target.value)
const sanityStrategyOptions = computed(() => [
  { label: t('core.edit.maaEndPlannedStrategy'), value: 'MAS' },
  { label: t('core.edit.maaEndOriginalStrategy'), value: 'Native' },
  { label: t('core.edit.maaEndImsTitle'), value: 'Inventory' },
])
</script>

<style scoped>
.sanity-task-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 32px;
}

.sanity-task-enabled {
  padding-bottom: 12px;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}
.strategy-options {
  display: flex;
  flex-wrap: wrap;
}
.strategy-hint {
  margin: 0;
  color: var(--ant-color-text-secondary);
}
</style>

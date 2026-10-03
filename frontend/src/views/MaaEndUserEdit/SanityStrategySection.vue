<template>
  <div>
    <div class="sanity-task-toggle" :class="{ 'sanity-task-enabled': showDetail }">
      <span>{{ t('edit.maaEndEnableSanity') }}</span>
      <a-switch
        :checked="enabled"
        :disabled="disabled"
        :aria-label="t('edit.maaEndEnableSanity')"
        @change="(value: boolean) => emit('enable', value)"
      />
    </div>
    <template v-if="showDetail">
      <a-form-item :label="t('edit.maaEndSanityStrategy')">
        <a-select
          :value="strategy"
          :options="sanityStrategyOptions"
          :disabled="disabled"
          @change="(value: string) => emit('save', value)"
        />
      </a-form-item>
      <a-form-item v-if="strategy === 'Native'">
        <a-space direction="vertical" size="middle" style="width: 100%">
          <a-alert type="info" show-icon :message="t('edit.maaEndNativeSanityHint')" />
          <a-button
            :loading="configLoading"
            :disabled="disabled || showConfigMask"
            @click="emit('configure')"
          >
            <template #icon><SettingOutlined /></template>
            {{ t('edit.maaEndConfigureInventory') }}
          </a-button>
          <span>{{ t('edit.maaEndInventorySourceHint') }}</span>
        </a-space>
      </a-form-item>
    </template>

    <a-alert
      v-if="showDetail && strategy === 'Inventory'"
      type="info"
      show-icon
      :message="t('edit.maaEndImsStrategyHint')"
    />
  </div>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { SettingOutlined } from '@ant-design/icons-vue'
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
const sanityStrategyOptions = computed(() => [
  { label: t('edit.maaEndMasSanityStrategy'), value: 'MAS' },
  { label: t('edit.maaEndNativeSanityStrategy'), value: 'Native' },
  { label: t('edit.maaEndImsTitle'), value: 'Inventory' },
])
</script>

<style scoped>
.sanity-task-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 44px;
}

.sanity-task-enabled {
  margin-bottom: 24px;
}
</style>

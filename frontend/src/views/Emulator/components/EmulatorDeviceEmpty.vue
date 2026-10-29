<script setup lang="ts">
import { h } from 'vue'
import { useI18n } from 'vue-i18n'
import { FolderOpenOutlined, PlayCircleOutlined } from '@ant-design/icons-vue'

defineProps<{ needsPath: boolean }>()
const emit = defineEmits<{ selectPath: []; start: [] }>()
const { t } = useI18n()
</script>

<template>
  <div class="empty-devices" :class="{ 'path-required': needsPath }">
    <a-empty
      :description="t(needsPath ? 'core.emulator.pathRequired' : 'core.emulator.noDevice')"
      :image-style="needsPath ? { display: 'none' } : undefined"
      :style="needsPath ? { margin: 0 } : undefined"
    >
      <template #default>
        <a-button
          v-if="needsPath"
          type="primary"
          size="small"
          :icon="h(FolderOpenOutlined)"
          @click="emit('selectPath')"
        >
          {{ t('core.emulator.selectPath') }}
        </a-button>
        <a-button
          v-else
          type="primary"
          size="small"
          :icon="h(PlayCircleOutlined)"
          @click="emit('start')"
        >
          {{ t('core.emulator.startEmulator') }}
        </a-button>
      </template>
    </a-empty>
  </div>
</template>

<style scoped>
.empty-devices {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 0;
  text-align: center;
}

.path-required {
  padding: 0;
}
</style>

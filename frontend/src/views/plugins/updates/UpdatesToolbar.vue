<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { usePluginCenter } from '../usePluginCenter'
import { batchUpdateState } from './updatesModel'

/**
 * 「更新」页签在外壳工具条右侧的区域：「全部更新」按目录顺序排队执行，一项失败即停。
 * 外壳只在更新页签渲染它，不传属性。
 */
const { t } = useI18n()
const { data, installation, lock } = usePluginCenter()

const batch = computed(() => batchUpdateState(data.updates.value))
const running = ref(false)

const updateAll = async () => {
  if (running.value || lock.busy.value) return
  running.value = true
  try {
    await installation.installSequence(batch.value.targets.map(entry => entry.document))
  } finally {
    running.value = false
  }
}
</script>

<template>
  <div class="updates-toolbar">
    <a-button
      v-if="batch.visible"
      type="primary"
      :loading="running"
      :disabled="!running && (lock.busy.value || !batch.editable)"
      @click="updateAll"
      >{{ t('core.plugins.updates.updateAll') }}</a-button
    >
  </div>
</template>

<style scoped>
.updates-toolbar {
  display: flex;
  flex: 1 1 auto;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}
</style>

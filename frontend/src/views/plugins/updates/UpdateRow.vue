<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PluginReleaseNotes from '../components/PluginReleaseNotes.vue'
import PluginAvatar from '../components/PluginAvatar.vue'
import PluginOriginTag from '../components/PluginOriginTag.vue'
import PluginStatusTag from '../components/PluginStatusTag.vue'
import { actionEditable, updateActionLabel, type PluginUpdateView } from '../pluginCenterModel'
import type { InstallTask } from '../usePluginInstallation'
import { showsUpdateButton, updatePhaseStatus } from './updatesModel'

/** 「更新」列表的一行：图标、名称、现版本到新版本、官方标识、阶段与「更新至」。 */
const props = defineProps<{
  item: PluginUpdateView
  task: InstallTask | null
  /** 插件中心有其他操作在执行。 */
  busy: boolean
}>()
const emit = defineEmits<{ update: [] }>()
const { t } = useI18n()

const entry = computed(() => props.item.entry)
const phase = computed(() => updatePhaseStatus(props.task))
const showButton = computed(() => showsUpdateButton(entry.value, props.task))
const buttonText = computed(() => {
  const label = updateActionLabel(props.item.toVersion)
  return t(label.key, label.params)
})
</script>

<template>
  <div class="update-row">
    <PluginAvatar :icon="entry.icon" />
    <div class="update-row-main">
      <PluginReleaseNotes :notes="entry.updateNotes" upgrade>
        <div class="update-row-title">
          <strong class="update-row-name">{{ entry.name }}</strong>
          <span v-if="item.fromVersion || item.toVersion" class="update-row-versions">
            <span v-if="item.fromVersion" class="update-row-version">{{ item.fromVersion }}</span>
            <span v-if="item.fromVersion && item.toVersion" aria-hidden="true">→</span>
            <span v-if="item.toVersion" class="update-row-version update-row-version--next">{{
              item.toVersion
            }}</span>
          </span>
          <PluginOriginTag :official="entry.official" :local="item.installed?.local" />
        </div>
      </PluginReleaseNotes>
    </div>
    <div class="update-row-actions">
      <PluginStatusTag v-if="phase" :status="phase" />
      <a-button
        v-if="showButton"
        :disabled="busy || !actionEditable(entry, 'install')"
        @click="emit('update')"
        >{{ buttonText }}</a-button
      >
    </div>
  </div>
</template>

<style scoped>
.update-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 14px 0;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.update-row:has([aria-expanded="true"]) {
  align-items: flex-start;
}

.update-row:first-child {
  border-top: 0;
}

.update-row-main {
  display: flex;
  flex: 1 1 320px;
  min-width: 0;
  flex-direction: column;
  gap: 4px;
}

.update-row-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.update-row-name {
  font-weight: 600;
  overflow-wrap: anywhere;
}

.update-row-versions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--ant-color-text-secondary);
}

.update-row-version {
  padding: 0 6px;
  border-radius: 4px;
  font-size: 12px;
  line-height: 20px;
  background: var(--ant-color-fill-secondary);
}

.update-row-version--next {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.update-row-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 12px;
  margin-left: auto;
}
</style>

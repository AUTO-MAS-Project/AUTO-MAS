<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import PluginAvatar from '../components/PluginAvatar.vue'
import PluginOriginTag from '../components/PluginOriginTag.vue'
import {
  installPhaseLabelKey,
  isInstallPhaseActive,
  isInstallRestartPhase,
  joinSegments,
  usageSegments,
  type InstalledPluginView,
  type LifecycleAction,
} from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'
import InstalledDetail from './InstalledDetail.vue'
import InstalledRowActions from './InstalledRowActions.vue'

/** 已安装列表的一行：点左侧信息区展开详情，右侧是状态与操作。 */
const props = defineProps<{ view: InstalledPluginView; expanded: boolean }>()
const emit = defineEmits<{
  toggle: []
  lifecycle: [action: LifecycleAction]
  upgrade: []
}>()

const { t } = useI18n()
const { data, lock, installation } = usePluginCenter()

/** 正在执行的启停卸载沿用过渡状态词条；卸载没有对应的运行状态，单列一条。 */
const RUNNING_LABELS: Record<LifecycleAction, string> = {
  enable: 'core.plugins.state.enabling',
  disable: 'core.plugins.state.disabling',
  reload: 'core.plugins.state.reloading',
  uninstall: 'core.plugins.operation.uninstalling',
}

const subtitle = computed(() => {
  const view = props.view
  return joinSegments([
    view.author,
    joinSegments(view.tags.slice(0, 2)),
    ...usageSegments(data.usageOf(view)).map(segment => t(segment.key, { count: segment.count })),
    view.drift ? t(`core.plugins.drift.${view.drift}`) : null,
  ])
})

const upgradeTask = computed(() =>
  props.view.upgrade ? installation.taskOf(props.view.upgrade.uid) : null
)
const upgrading = computed(() => isInstallPhaseActive(upgradeTask.value?.phase))
const processingLabel = computed(() => {
  const current = lock.current.value
  if (current?.uid === props.view.uid && current.action !== 'install')
    return t(RUNNING_LABELS[current.action])
  const task = upgradeTask.value
  if (!task || !upgrading.value) return null
  return t(
    task.phase === 'queued'
      ? 'core.plugins.installPhase.queued'
      : 'core.plugins.installPhase.upgrading'
  )
})
/** 等待重启、重启、恢复这几段的长说明放在信息区，不塞进状态位。 */
const progressDetail = computed(() => {
  const task = upgradeTask.value
  return task && isInstallRestartPhase(task.phase)
    ? t(installPhaseLabelKey(task.phase, task.upgrade))
    : null
})
</script>

<template>
  <div class="installed-row" :class="{ 'is-expanded': expanded }">
    <div class="installed-row-line">
      <button
        type="button"
        class="installed-row-main"
        :aria-expanded="expanded"
        @click="emit('toggle')"
      >
        <PluginAvatar :icon="view.icon" />
        <span class="installed-row-text">
          <span class="installed-row-title">
            <strong class="installed-row-name">{{ view.name }}</strong>
            <span v-if="view.version" class="installed-row-version">{{ view.version }}</span>
            <PluginOriginTag :official="view.official" :local="view.local && !view.core" />
          </span>
          <span v-if="subtitle" class="installed-row-sub">{{ subtitle }}</span>
          <span v-if="progressDetail" class="installed-row-sub">{{ progressDetail }}</span>
          <span v-if="view.error" class="installed-row-error" :title="view.error">{{
            view.error
          }}</span>
        </span>
      </button>
      <InstalledRowActions
        :view="view"
        :processing-label="processingLabel"
        :upgrading="upgrading"
        @lifecycle="action => emit('lifecycle', action)"
        @upgrade="emit('upgrade')"
      />
    </div>
    <InstalledDetail v-if="expanded" :view="view" />
  </div>
</template>

<style scoped>
.installed-row + .installed-row {
  border-top: 1px solid var(--ant-color-border-secondary);
}

.installed-row-line {
  display: flex;
  min-height: 72px;
  padding: 0 16px;
  align-items: center;
  flex-wrap: wrap;
  column-gap: 12px;
  transition: background-color 0.15s;
}

.installed-row-line:hover,
.installed-row.is-expanded .installed-row-line {
  background: var(--ant-color-fill-quaternary);
}

.installed-row-main {
  display: flex;
  min-width: 0;
  padding: 14px 0;
  flex: 1 1 320px;
  align-items: center;
  gap: 12px;
  border: 0;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.installed-row-main:focus-visible {
  border-radius: 6px;
  outline: 2px solid var(--ant-color-primary-border);
  /* 画在按钮内侧：外层分组容器有圆角裁切，往外画会被裁掉一边。 */
  outline-offset: -2px;
}

.installed-row-text {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
}

.installed-row-title {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.installed-row-name {
  font-size: 15px;
  font-weight: 600;
  line-height: 24px;
  overflow-wrap: anywhere;
}

.installed-row-version {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}

.installed-row-sub,
.installed-row-error {
  font-size: 12px;
  line-height: 20px;
  overflow-wrap: anywhere;
}

.installed-row-sub {
  color: var(--ant-color-text-secondary);
}

.installed-row-error {
  overflow: hidden;
  color: var(--ant-color-error);
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

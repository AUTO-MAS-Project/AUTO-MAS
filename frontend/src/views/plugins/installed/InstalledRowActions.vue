<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { MoreOutlined, SettingOutlined } from '@ant-design/icons-vue'
import PluginStatusTag from '../components/PluginStatusTag.vue'
import {
  LIFECYCLE_LABEL_KEYS,
  actionEditable,
  actionVisible,
  showSettingsEntry,
  toggleState,
  updateActionLabel,
  usesInlineToggle,
  type InstalledPluginView,
  type LifecycleAction,
} from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'

/**
 * 已安装行右侧的状态与操作。按钮出不出现、能不能点只看后端界面提示；
 * 同一时刻只允许一个插件操作，忙时全部置灰。
 */
interface PrimaryAction {
  kind: LifecycleAction | 'upgrade'
  label: string
  editable: boolean
}
interface MenuAction {
  action: LifecycleAction
  label: string
  editable: boolean
  danger: boolean
}

const props = defineProps<{
  view: InstalledPluginView
  /** 本行正在进行的操作文案；为空时显示插件状态。 */
  processingLabel: string | null
  /** 本行的更新正在进行。 */
  upgrading: boolean
}>()
const emit = defineEmits<{ lifecycle: [action: LifecycleAction]; upgrade: [] }>()

const { t } = useI18n()
const router = useRouter()
const { data, lock } = usePluginCenter()

const busy = computed(() => lock.busy.value)
const runningAction = computed(() =>
  lock.current.value?.uid === props.view.uid ? lock.current.value.action : null
)
const inline = computed(() => usesInlineToggle(props.view))
const toggle = computed(() => toggleState(props.view))
// 核心插件不能停用，后端给的开关恒为不可操作，不放一个永远点不了的开关。
const showSwitch = computed(
  () => inline.value && toggle.value.visible && !(props.view.core && !toggle.value.editable)
)
const showSettings = computed(() => showSettingsEntry(data.settingsVisibility(props.view)))

const primary = computed<PrimaryAction | null>(() => {
  const view = props.view
  // 一行只放一个主按钮：更新 > 重载新代码 > 异常重试 > 启用专项。
  if (view.upgrade && actionVisible(view.upgrade, 'install')) {
    const label = updateActionLabel(view.upgrade.version)
    return {
      kind: 'upgrade',
      label: t(label.key, label.params),
      editable: actionEditable(view.upgrade, 'install'),
    }
  }
  if (view.drift === 'needs_reload' && actionVisible(view, 'reload'))
    return {
      kind: 'reload',
      label: t('core.plugins.reload'),
      editable: actionEditable(view, 'reload'),
    }
  if (view.fault) {
    const retry = actionVisible(view, 'reload')
      ? 'reload'
      : actionVisible(view, 'enable')
        ? 'enable'
        : null
    if (retry)
      return { kind: retry, label: t('core.common.retry'), editable: actionEditable(view, retry) }
  }
  if (!inline.value && toggle.value.action === 'enable' && actionVisible(view, 'enable'))
    return {
      kind: 'enable',
      label: t('core.plugins.enable'),
      editable: actionEditable(view, 'enable'),
    }
  return null
})

const menuActions = computed<MenuAction[]>(() => {
  const view = props.view
  const item = (action: LifecycleAction, danger = false): MenuAction => ({
    action,
    label: t(LIFECYCLE_LABEL_KEYS[action]),
    editable: actionEditable(view, action),
    danger,
  })
  const items: MenuAction[] = []
  if (actionVisible(view, 'reload') && primary.value?.kind !== 'reload') items.push(item('reload'))
  if (!inline.value) {
    // 带数据的专项不用行内开关，启停收进「更多」。
    if (
      toggle.value.action === 'enable' &&
      actionVisible(view, 'enable') &&
      primary.value?.kind !== 'enable'
    )
      items.push(item('enable'))
    if (toggle.value.checked && actionVisible(view, 'disable')) items.push(item('disable'))
  }
  if (actionVisible(view, 'uninstall')) items.push(item('uninstall', true))
  return items
})

const runPrimary = () => {
  const action = primary.value
  if (!action) return
  if (action.kind === 'upgrade') emit('upgrade')
  else emit('lifecycle', action.kind)
}
const pickMenu = ({ key }: { key: string | number }) => {
  const found = menuActions.value.find(item => item.action === key)
  if (found?.editable) emit('lifecycle', found.action)
}
const openSettings = () =>
  router.push({ name: 'PluginSettings', params: { pluginId: props.view.uid } })
</script>

<template>
  <div class="installed-row-actions">
    <a-tag
      v-if="processingLabel"
      class="installed-row-processing"
      color="processing"
      :bordered="false"
      role="status"
      >{{ processingLabel }}</a-tag
    >
    <PluginStatusTag v-else :status="view.status" />
    <a-button
      v-if="primary"
      :loading="primary.kind === 'upgrade' ? upgrading : runningAction === primary.kind"
      :disabled="busy || !primary.editable"
      @click.stop="runPrimary"
      >{{ primary.label }}</a-button
    >
    <a-switch
      v-if="showSwitch"
      :aria-label="`${view.name} ${t('core.plugins.attribute.enabled')}`"
      :checked="toggle.checked"
      :loading="runningAction === 'enable' || runningAction === 'disable'"
      :disabled="busy || !toggle.editable"
      @change="emit('lifecycle', toggle.action)"
    />
    <a-button v-if="showSettings" @click.stop="openSettings"
      ><template #icon><SettingOutlined /></template>{{ t('core.plugins.settings') }}</a-button
    >
    <a-dropdown v-if="menuActions.length" placement="bottomRight" :disabled="busy">
      <a-button type="text" :disabled="busy" :aria-label="t('core.plugins.moreActions')"
        ><template #icon><MoreOutlined /></template
      ></a-button>
      <template #overlay>
        <a-menu @click="pickMenu">
          <a-menu-item
            v-for="item in menuActions"
            :key="item.action"
            :disabled="!item.editable"
            :danger="item.danger"
            >{{ item.label }}</a-menu-item
          >
        </a-menu>
      </template>
    </a-dropdown>
  </div>
</template>

<style scoped>
.installed-row-actions {
  display: flex;
  margin-left: auto;
  padding: 4px 0;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px 12px;
}

.installed-row-processing {
  margin-inline-end: 0;
}
</style>

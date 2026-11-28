<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { message } from 'ant-design-vue'
import { createReusableTemplate } from '@vueuse/core'
import PluginUiMount from '@/components/PluginUiMount.vue'
import type { PluginUiEditor } from '@/composables/usePluginUiBridge'
import { usePluginRegistry } from '@/composables/usePluginScriptTypes'
import { compatibleWheel, indexPluginScriptTypes } from '@/utils/pluginScriptTypes'
import { usePluginSettingsDraft } from '@/views/plugins/settings/usePluginSettingsDraft'
import type { SettingGroupChangeHandler } from '../settingTypes'
import { useI18n } from 'vue-i18n'
import type { NotifyChannelOut } from '@/api/models/NotifyChannelOut'
import { handleExternalLink } from '@/utils/openExternal'
import { scopeFields, normalizeGroup } from '../notifyChannelView'
import ClawBinding, { type ClawBindingState } from './ClawBinding.vue'
import NotifyFieldRenderer from './NotifyFieldRenderer.vue'
import WebhookManager from '@/components/WebhookManager.vue'
import AppModal from '@/components/ui/AppModal.vue'
import { channelIcon, channelIconColor } from './notifyChannelIcons'

const props = withDefaults(
  defineProps<{
    configUid: string
    saveGroup: SettingGroupChangeHandler
    open: boolean
    channel: NotifyChannelOut | null
    /** 全局通知配置的扁平取值源（settings.Notify） */
    values: Record<string, unknown>
    /** 保存函数，签名固定 (group, name, value) */
    save: (group: string, name: string, value: unknown) => unknown
    /** Claw 渠道的提升绑定状态；非 Claw 渠道传 null */
    clawBinding?: ClawBindingState | null
    /** 嵌套浮层容器；弹窗场景传弹窗 wrap 节点，让浮层整体压在标题栏之下 */
    getPopupContainer?: () => HTMLElement
  }>(),
  {
    clawBinding: null,
    getPopupContainer: undefined,
  }
)

const emit = defineEmits<{
  close: []
  /** Webhook 列表重载后透传条目，供卡片摘要使用 */
  listed: [names: string[]]
}>()

const { t, locale } = useI18n()

const icon = computed(() => channelIcon(props.channel?.icon))
const iconColor = computed(() => channelIconColor(props.channel?.icon))
const groupTag = computed(() =>
  props.channel && normalizeGroup(props.channel.group) === 'custom'
    ? t('core.setting.notify.customGroup')
    : t('core.setting.notify.channelsGroup')
)
const fields = computed(() => (props.channel ? scopeFields(props.channel, 'global') : []))
const enableGroup = computed(() => props.channel?.enableField?.[0] ?? null)
const enableName = computed(() => props.channel?.enableField?.[1] ?? null)
const enabled = computed(() => {
  const name = enableName.value
  return name != null && props.values[name] === true
})
const isClaw = computed(() => (props.channel?.customBlock ?? '').startsWith('claw:'))
const clawConnected = computed(() => !!props.clawBinding?.status?.connected)
const switchChecked = computed(() => enabled.value && (!isClaw.value || clawConnected.value))
const stateText = computed(() =>
  t(switchChecked.value ? 'core.setting.notify.stateEnabled' : 'core.setting.notify.stateDisabled')
)
// 未绑定时开关不可点（沿用 ClawBinding 原逻辑：未连接 / 查询中 / 解绑中都禁用）
const switchDisabled = computed(() => {
  if (isClaw.value && props.clawBinding) {
    return !clawConnected.value || props.clawBinding.statusLoading || props.clawBinding.unbinding
  }
  return false
})

const saving = ref(false)
const setEnabled = async (value: boolean | string | number) => {
  if (enableGroup.value == null || enableName.value == null) return
  saving.value = true
  try {
    await props.save(enableGroup.value, enableName.value, Boolean(value))
  } finally {
    saving.value = false
  }
}

const [DefineFields, ChannelFields] = createReusableTemplate<{ secretOnly?: boolean }>()
const registry = usePluginRegistry(computed(() => props.open))
const wheel = computed(() =>
  compatibleWheel(
    indexPluginScriptTypes(registry.data.value?.data).notificationPanels.get(
      props.channel?.key ?? ''
    )
  )
)
const refreshWheel = async () => (await registry.refetch()).isSuccess && !!wheel.value
const draft = usePluginSettingsDraft()
const revision = ref(0)
const hints = computed(() =>
  fields.value
    .filter(field => field.group === 'Notify' && field.control !== 'password')
    .map(field => ({
      field: field.name,
      editable: true,
    }))
)
const savedValues = computed(() => ({
  Notify: Object.fromEntries(hints.value.map(h => [h.field, props.values[h.field]])),
}))
watch(
  [() => props.channel?.key, savedValues],
  ([key, values], previous) => {
    draft.reset(values, { keepDraft: !!key && key === previous?.[0] })
    revision.value++
  },
  { immediate: true }
)
const editor = computed<PluginUiEditor>(() => ({
  locale: locale.value,
  locked: !props.open || !props.configUid,
  busy: saving.value,
  configRevision: revision.value,
  groups: [{ name: 'Notify', hints: hints.value }],
  values: draft.values,
  async save(changes, commit) {
    const activation = wheel.value
    if (!activation || !props.open || saving.value)
      return { ok: false, code: 'read_only', message: t('core.plugins.saveFailed') }
    for (const { group, field, value } of changes) draft.update(group, field, value)
    if (!commit || !changes.length) return { ok: true }
    const submitted = draft.snapshot()
    const key = props.channel?.key
    saving.value = true
    try {
      if (await props.saveGroup('Notify', draft.patch(submitted, changes).Notify!, activation)) {
        if (props.channel?.key === key) {
          draft.commit(submitted, changes)
          draft.reset(savedValues.value, { keepDraft: true })
          revision.value++
        }
        return { ok: true }
      }
      return { ok: false, code: 'save_failed', message: t('core.plugins.saveFailed') }
    } finally {
      saving.value = false
    }
  },
  // 渠道描述只声明普通字段；绑定、测试等动作由宿主控件持有。
  runAction: async () => 'error',
  notify: (severity, text) => void message[severity](text),
}))

const hasDraftField = (name: string) =>
  Object.prototype.hasOwnProperty.call(savedValues.value.Notify, name)
const saveField = async (group: string, name: string, value: unknown) => {
  const key = props.channel?.key
  const saved = await props.save(group, name, value)
  if (saved && key === props.channel?.key && hasDraftField(name)) draft.discardField(group, name)
}

// Webhook 摘要：条目名缺省时用 uid 兜底，避免出现空名字串在列表里
const onWebhookListed = (items: { name: string; uid: string }[]) =>
  emit(
    'listed',
    items.map(item => item.name || item.uid)
  )
</script>

<template>
  <!-- z-index 900 让弹窗连同遮罩整体压在标题栏（1000）之下；
       内部嵌套浮层挂 wrap 容器后也在这个层叠上下文里 -->
  <!-- transition 名不对应任何 CSS = 瞬显瞬隐；对齐 Scripts.vue 配置MAA 遮罩
       （.maa-config-mask）的无动画行为：长淡入在主线程被内容挂载卡住时会
       掉帧，被感知成遮罩闪一下 -->
  <AppModal
    :open="open"
    :width="480"
    footer="none"
    :closable="false"
    :destroy-on-close="false"
    scroll="none"
    :z-index="900"
    wrap-class-name="notify-channel-modal"
    mask-transition-name="notify-mask-fade"
    transition-name="notify-panel-zoom"
    :body-style="{ padding: 0 }"
    @cancel="emit('close')"
  >
    <!-- key 加在内容根节点：换渠道重置弹窗内容，但弹窗本身不重挂 -->
    <div v-if="channel" :key="channel.key" class="modal-inner">
      <div class="modal-head">
        <div class="modal-title-row">
          <span class="chan-icon-head" :style="{ '--c': iconColor, color: iconColor }">
            <component :is="icon" />
          </span>
          <span class="name">{{ t(channel.nameKey) }}</span>
          <span class="tag">{{ groupTag }}</span>
          <a
            v-if="channel.docUrl"
            :href="channel.docUrl"
            class="doc-link"
            @click="handleExternalLink"
          >
            {{ t('core.common.doc') }}
          </a>
          <button
            type="button"
            class="close"
            :aria-label="t('core.common.close')"
            @click="emit('close')"
          >
            ✕
          </button>
        </div>
        <div v-if="channel.descKey" class="modal-desc">{{ t(channel.descKey) }}</div>
      </div>

      <div class="modal-body">
        <div v-if="enableName" class="modal-state">
          <div class="state-main">
            <span class="switch-label">{{ stateText }}</span>
            <a-switch
              :checked="switchChecked"
              :loading="saving"
              :disabled="switchDisabled"
              :aria-label="stateText"
              @change="setEnabled"
            />
          </div>
          <div class="state-hint">{{ t('core.setting.notify.instantHint') }}</div>
        </div>
        <div v-else class="body-hint">{{ t('core.setting.notify.instantHint') }}</div>

        <ClawBinding
          v-if="isClaw && clawBinding"
          :binding="clawBinding"
          :get-container="getPopupContainer"
        />
        <WebhookManager
          v-else-if="channel.customBlock === 'webhook_list'"
          compact
          mode="global"
          :get-popup-container="getPopupContainer"
          @listed="onWebhookListed"
        />

        <DefineFields v-slot="{ secretOnly }">
          <NotifyFieldRenderer
            v-for="field in secretOnly ? fields.filter(f => f.control === 'password') : fields"
            :key="field.name"
            :field="field"
            :value="
              hasDraftField(field.name) ? draft.values.Notify[field.name] : values[field.name]
            "
            :get-popup-container="getPopupContainer"
            @save="value => saveField(field.group, field.name, value)"
          />
        </DefineFields>
        <PluginUiMount
          v-if="open && wheel && configUid"
          :mount="wheel"
          :editor="editor"
          :refresh="refreshWheel"
          :target="{
            kind: 'notification',
            channelId: channel.key,
            configUid,
            scriptId: null,
            userId: null,
            planId: null,
          }"
        >
          <ChannelFields :secret-only="true" />
          <template #fallback><ChannelFields /></template>
        </PluginUiMount>
        <ChannelFields v-else />
      </div>
    </div>
  </AppModal>
</template>

<style scoped src="./notifyChannel.css"></style>

<style scoped>
.modal-inner {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.modal-head {
  flex: 0 0 auto;
  padding: 16px 20px 14px;
  border-bottom: 1px solid var(--ant-color-split);
}

.modal-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
}

.chan-icon-head {
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  border-radius: var(--ant-border-radius-sm);
  display: grid;
  place-items: center;
  font-size: 17px;
  background: color-mix(in srgb, var(--c) 12%, transparent);
}

.modal-title-row .name {
  font-size: 16px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.doc-link {
  margin-left: auto;
  font-size: 13px;
  color: var(--ant-color-primary);
}

.doc-link:hover {
  color: var(--ant-color-primary-hover);
}

.close {
  margin-left: 8px;
  border: none;
  background: transparent;
  color: var(--ant-color-text-tertiary);
  font-size: 15px;
  padding: 2px 6px;
  border-radius: var(--ant-border-radius-sm);
  cursor: pointer;
}

.close:hover {
  background: var(--ant-color-fill-tertiary);
  color: var(--ant-color-text);
}

.modal-desc {
  margin-top: 8px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--ant-color-text-tertiary);
}

/* 恰好一个滚动者：低窗口高度下内容在弹窗体内滚动，页面与弹窗壳都不滚 */
.modal-body {
  overflow-y: auto;
  max-height: calc(100vh - 240px);
  padding: 16px 20px 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.modal-state {
  display: flex;
  flex-direction: column;
  gap: 4px;
  background: var(--ant-color-fill-quaternary);
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius);
  padding: 8px 14px;
}

.state-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.switch-label {
  font-size: 14px;
  color: var(--ant-color-text);
}

.state-hint,
.body-hint {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>

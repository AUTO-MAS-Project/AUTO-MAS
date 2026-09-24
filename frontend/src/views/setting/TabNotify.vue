<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { GlobalConfig, NotifyChannelOut } from '@/api'
import { Service } from '@/api'
import { useClawBinding } from './useClawBinding'
import NotifyChannelCard from './components/NotifyChannelCard.vue'
import NotifyChannelModal from './components/NotifyChannelModal.vue'
import {
  FALLBACK_POLICY_FIELDS,
  channelSummary,
  groupChannels,
  idleStateKey,
  scopeFields,
} from './notifyChannelView'
import NotifyFieldRenderer from './components/NotifyFieldRenderer.vue'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<void>
  testNotify: () => Promise<void>
  testingNotify: boolean
}>()

const { t } = useI18n()

// ==================== 渠道描述 ====================

const channels = ref<NotifyChannelOut[]>([])
const channelsLoading = ref(false)
const channelsError = ref(false)

const loadChannels = async () => {
  channelsLoading.value = true
  channelsError.value = false
  try {
    const response = await Service.getNotifyChannelsApiSettingNotifyChannelsGet()
    // 后端错误约定是 HTTP 200 + code:500，axios 不抛异常，要按 code 分支
    if (response.code !== 200 || !response.channels) {
      throw new Error(response.message || '')
    }
    channels.value = response.channels
  } catch (error) {
    channelsError.value = true
    channels.value = []
    const logger = window.electronAPI.getLogger('通知设置')
    logger.error(`加载通知渠道描述失败: ${String(error)}`)
  } finally {
    channelsLoading.value = false
  }
}

onMounted(() => {
  void loadChannels()
  void loadWebhookNames()
})

// ==================== 分组与状态 ====================

// GlobalConfig_Notify 是封闭类型、没有索引签名，取值时显式窄化
const notifyValues = computed<Record<string, unknown>>(
  () => (props.settings.Notify as Record<string, unknown> | undefined) ?? {}
)

// Claw 绑定状态提升到本组件：a-tab-pane 懒挂载且挂载后常驻，只有这里调用
// useClawBinding 才能保证每渠道单实例；提到更上层会在用户停留在别的设置页时查询并回写。
const weixinBinding = reactive(
  useClawBinding('weixin', value => props.handleSettingChange('Notify', 'IfOpenClawWeixin', value))
)
const qqBinding = reactive(
  useClawBinding('qq', value => props.handleSettingChange('Notify', 'IfOpenClawQQ', value))
)

const clawConnected = computed<Record<string, boolean>>(() => ({
  'claw:weixin': !!weixinBinding.status?.connected,
  'claw:qq': !!qqBinding.status?.connected,
}))

// Webhook 条目名由 WebhookManager 列表重载后的 listed 事件刷新；
// WebhookManager 只在配置弹窗里挂载，页面加载时先预取一次，避免卡片首屏假「0 条」。
const webhookNames = ref<string[]>([])

const loadWebhookNames = async () => {
  try {
    const response = await Service.getWebhookApiSettingWebhookGetPost({
      scriptId: null,
      userId: null,
      webhookId: null,
    })
    if (response.code !== 200) return
    webhookNames.value = response.index.map(item => response.data[item.uid]?.Info?.Name || item.uid)
  } catch {
    // 摘要失败不影响页面，打开弹窗后由列表重载补上
  }
}

const groups = computed(() => groupChannels(channels.value, 'global', notifyValues.value))

const summaryOf = (channel: NotifyChannelOut) =>
  channelSummary(channel, notifyValues.value, t, {
    clawConnected: clawConnected.value,
    webhookNames: webhookNames.value,
  })

const policyFields = computed(() => {
  if (groups.value.policy) return scopeFields(groups.value.policy, 'global')
  // 描述端点失败或描述表缺失 policy 段时兜底渲染，
  // 保证「通知内容」三个全局策略仍可改（§5.4；保存不依赖描述表）
  return FALLBACK_POLICY_FIELDS
})

const policyTitle = computed(() =>
  groups.value.policy ? t(groups.value.policy.nameKey) : t('setting.notify.contentSection')
)

// ==================== 配置弹窗 ====================

const activeKey = ref<string | null>(null)
const activeChannel = computed(
  () => channels.value.find(channel => channel.key === activeKey.value) ?? null
)

// 键盘切换（卡片上按 Enter/Space）与 Esc 关闭都不会先触发 blur，
// 提交未失焦的编辑必须是关闭/切换的第一步；blur() 同步生效。
const commitFocus = () => {
  ;(document.activeElement as HTMLElement | null)?.blur?.()
}

const activeClawBinding = computed(() => {
  if (activeChannel.value?.customBlock === 'claw:weixin') return weixinBinding
  if (activeChannel.value?.customBlock === 'claw:qq') return qqBinding
  return null
})

const closeClawSessions = () => {
  weixinBinding.close()
  qqBinding.close()
}

const closeModal = () => {
  commitFocus()
  // 二维码会话同步收掉：弹窗悬空会继续轮询并可能静默启用渠道
  closeClawSessions()
  activeKey.value = null
}

const openChannel = (key: string) => {
  commitFocus()
  // 开着二维码切渠道不会触发组件卸载钩子，显式收掉
  if (activeKey.value != null && activeKey.value !== key) closeClawSessions()
  activeKey.value = key
}

const saveField = (group: string, name: string, value: unknown) =>
  props.handleSettingChange(group as keyof GlobalConfig, name, value)

const onWebhookListed = (names: string[]) => {
  webhookNames.value = names
}

// 嵌套浮层挂到弹窗 wrap 节点：wrap-class-name 落在带 z-index 900 的层叠上下文上，
// 二维码/表单弹窗与下拉都随之压在标题栏之下
const modalPopupContainer = () =>
  document.querySelector<HTMLElement>('.notify-channel-modal') ?? document.body
</script>

<template>
  <div class="tab-content notify-tab">
    <div class="toolbar">
      <div class="toolbar-right">
        <a
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html"
          class="toolbar-link"
          @click="handleExternalLink"
        >
          {{ t('setting.notify.usageDoc') }}
        </a>
        <a-button type="primary" :loading="testingNotify" size="middle" @click="testNotify">
          {{ t('setting.notify.sendTest') }}
        </a-button>
      </div>
    </div>

    <a-alert
      v-if="channelsError"
      type="error"
      show-icon
      :message="t('setting.notify.loadFailed')"
      class="channels-error"
    >
      <template #action>
        <a-button size="small" :loading="channelsLoading" @click="loadChannels">
          {{ t('setting.notify.retryLoad') }}
        </a-button>
      </template>
    </a-alert>

    <!-- 通知内容：全局推送策略，非渠道段，不参与渠道分组；
         描述端点失败时用本地兜底字段，保证这里仍可改 -->
    <section v-if="policyFields.length" class="panel">
      <div class="panel-head">
        <h3>{{ policyTitle }}</h3>
      </div>
      <div class="policy-grid">
        <NotifyFieldRenderer
          v-for="field in policyFields"
          :key="field.name"
          :field="field"
          :value="notifyValues[field.name]"
          inline
          @save="value => saveField(field.group, field.name, value)"
        />
      </div>
    </section>

    <template v-if="!channelsError">
      <section class="panel">
        <div class="panel-head">
          <i class="dot" />
          <h3 class="count">
            {{ t('setting.notify.countTemplate', { n: groups.active.length }) }}
          </h3>
        </div>
        <div v-if="groups.active.length" class="cards">
          <NotifyChannelCard
            v-for="channel in groups.active"
            :key="channel.key"
            :channel="channel"
            variant="card"
            :state-text="t('setting.notify.stateEnabled')"
            :state-active="true"
            :summary="summaryOf(channel)"
            @open="openChannel"
          />
        </div>
        <a-empty
          v-else
          :description="t('setting.notify.activeEmpty')"
          :image-style="{ height: '48px' }"
        />
      </section>

      <section class="panel dashed">
        <div class="panel-head">
          <i class="dot off" />
          <h3 class="count">{{ t('setting.notify.idleSection') }}</h3>
        </div>
        <div v-if="groups.idle.length" class="rows">
          <NotifyChannelCard
            v-for="channel in groups.idle"
            :key="channel.key"
            :channel="channel"
            variant="row"
            :state-text="
              t(
                `setting.notify.${idleStateKey(channel, { clawConnected: clawConnected, webhookNames: [] })}`
              )
            "
            :state-active="false"
            :summary="''"
            @open="openChannel"
          />
        </div>
        <a-empty
          v-else
          :description="t('setting.notify.idleEmpty')"
          :image-style="{ height: '48px' }"
        />
      </section>

      <section class="panel">
        <div class="panel-head">
          <i class="dot" :class="{ off: !webhookNames.length }" />
          <h3>{{ t('setting.notify.customSection') }}</h3>
        </div>
        <div v-if="groups.custom.length" class="cards">
          <NotifyChannelCard
            v-for="channel in groups.custom"
            :key="channel.key"
            :channel="channel"
            variant="card"
            :state-text="t('setting.notify.webhookCount', { n: webhookNames.length })"
            :state-active="webhookNames.length > 0"
            :summary="summaryOf(channel)"
            @open="openChannel"
          />
        </div>
        <a-empty
          v-else
          :description="t('setting.notify.customEmpty')"
          :image-style="{ height: '48px' }"
        />
      </section>
    </template>

    <NotifyChannelModal
      :open="activeChannel != null"
      :channel="activeChannel"
      scope="global"
      :values="notifyValues"
      :save="saveField"
      :claw-binding="activeClawBinding"
      :get-popup-container="modalPopupContainer"
      @close="closeModal"
      @listed="onWebhookListed"
    />
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 16px;
}

.toolbar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 12px;
}

.toolbar-link {
  color: var(--ant-color-primary);
  text-decoration: none;
  font-size: 14px;
}

.toolbar-link:hover {
  color: var(--ant-color-primary-hover);
}

.channels-error {
  margin-bottom: 16px;
}

.panel {
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.panel.dashed {
  border-style: dashed;
}

.panel-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}

.panel-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.panel-head .count {
  font-size: 13px;
  font-weight: 400;
  color: var(--ant-color-text-secondary);
}

.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--ant-color-success);
  display: inline-block;
  flex: 0 0 7px;
}

.dot.off {
  background: var(--ant-color-text-tertiary);
  opacity: 0.5;
}

.policy-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 16px 32px;
}

.cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 12px;
}

.rows {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 10px;
}
</style>

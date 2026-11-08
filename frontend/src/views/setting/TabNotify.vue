<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ApiOutlined, BellOutlined, FileTextOutlined } from '@ant-design/icons-vue'
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
  isChannelEnabled,
  sortChannels,
  idleStateKey,
  scopeFields,
} from './notifyChannelView'
import NotifyFieldRenderer from './components/NotifyFieldRenderer.vue'
import SectionCard from '@/components/ui/SectionCard.vue'
import { handleExternalLink } from '@/utils/openExternal'

const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: (category: keyof GlobalConfig, key: string, value: any) => Promise<boolean>
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
const qqBinding = reactive(
  useClawBinding('qq', value => props.handleSettingChange('Notify', 'IfOpenClawQQ', value))
)

const clawConnected = computed<Record<string, boolean>>(() => ({
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
const channelCards = computed(() => sortChannels([...groups.value.active, ...groups.value.idle]))

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
  groups.value.policy ? t(groups.value.policy.nameKey) : t('core.setting.notify.contentSection')
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
  if (activeChannel.value?.customBlock === 'claw:qq') return qqBinding
  return null
})

const closeClawSessions = () => {
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
    <!-- 通知内容：全局推送策略，非渠道段，不参与渠道分组；
         描述端点失败时用本地兜底字段，保证这里仍可改 -->
    <SectionCard v-if="policyFields.length" :title="policyTitle" :icon="FileTextOutlined">
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
    </SectionCard>

    <SectionCard :title="t('core.setting.notify.channelsTitle')" :icon="BellOutlined">
      <template #actions>
        <a-button
          href="https://doc.auto-mas.top/docs/advanced-features/notification.html"
          @click="handleExternalLink"
        >
          {{ t('core.setting.notify.usageDoc') }}
        </a-button>
        <a-button type="primary" :loading="testingNotify" @click="testNotify">
          {{ t('core.setting.notify.sendTest') }}
        </a-button>
      </template>
      <a-alert
        v-if="channelsError"
        type="error"
        show-icon
        :message="t('core.setting.notify.loadFailed')"
        class="channels-error"
      >
        <template #action>
          <a-button size="small" :loading="channelsLoading" @click="loadChannels">
            {{ t('core.setting.notify.retryLoad') }}
          </a-button>
        </template>
      </a-alert>
      <div v-else-if="channelsLoading" class="channels-loading"><a-spin /></div>
      <div v-else-if="channelCards.length" class="channel-grid">
        <NotifyChannelCard
          v-for="channel in channelCards"
          :key="channel.key"
          :channel="channel"
          variant="card"
          :state-text="
            t(
              `core.setting.notify.${isChannelEnabled(channel, notifyValues) ? 'stateEnabled' : idleStateKey(channel, { clawConnected, webhookNames: [] })}`
            )
          "
          :state-active="isChannelEnabled(channel, notifyValues)"
          :summary="summaryOf(channel)"
          @open="openChannel"
        />
      </div>
      <NoData v-else :image-style="{ height: '48px' }" />
    </SectionCard>

    <SectionCard v-if="!channelsError" :icon="ApiOutlined">
      <template #title>
        <i class="dot" :class="{ off: !webhookNames.length }" />
        {{ t('core.setting.notify.customSection') }}
        <span class="card-count">{{ groups.custom.length }}</span>
      </template>
      <div v-if="groups.custom.length" class="cards">
        <NotifyChannelCard
          v-for="channel in groups.custom"
          :key="channel.key"
          :channel="channel"
          variant="card"
          :state-text="t('core.setting.notify.webhookCount', { n: webhookNames.length })"
          :state-active="webhookNames.length > 0"
          :summary="summaryOf(channel)"
          @open="openChannel"
        />
      </div>
      <NoData
        v-else
        :description="t('core.setting.notify.customEmpty')"
        :image-style="{ height: '48px' }"
      />
    </SectionCard>

    <NotifyChannelModal
      :open="activeChannel != null"
      :channel="activeChannel"
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
.channels-error {
  margin-bottom: 16px;
}

.channels-loading {
  display: grid;
  place-items: center;
  min-height: 120px;
}

/* 卡片头部状态点：绿点表示该组至少有一个渠道可用，灰点表示全未启用 */
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

.card-count {
  margin-left: 2px;
  padding: 0 6px;
  border-radius: 999px;
  background: var(--ant-color-fill-secondary);
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  font-weight: 400;
  line-height: 18px;
}

.policy-grid {
  display: flex;
  flex-direction: column;
  padding: 4px 0 10px;
}

.policy-grid :deep(.field-item) {
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.policy-grid :deep(.field-item:last-child) {
  border-bottom: 0;
}

.cards,
.channel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 12px;
  padding: 4px 0 10px;
}

.channel-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@container (max-width: 480px) {
  .channel-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>

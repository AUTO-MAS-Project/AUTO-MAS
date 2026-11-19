<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import PluginAvatar from '../components/PluginAvatar.vue'
import type { InstalledPluginView, LifecycleDecision } from '../pluginCenterModel'
import type { GuardedAction } from './useInstalledActions'

/**
 * 停用与卸载被拦住时的弹层：有托管在用时列出托管并引导去托管管理；
 * 用量还不知道（加载中或失败）时不当成没有托管，提示重试。
 */
const props = defineProps<{
  view: InstalledPluginView | null
  action: GuardedAction | null
  decision: LifecycleDecision | null
  usageLoading: boolean
}>()
const emit = defineEmits<{ close: []; retry: [] }>()

const { t } = useI18n()
const router = useRouter()

const open = computed(
  () =>
    props.view !== null &&
    props.action !== null &&
    (props.decision?.kind === 'blockedInUse' || props.decision?.kind === 'blockedUnknown')
)
const title = computed(() =>
  props.view && props.action
    ? t(`core.plugins.guard.${props.action}Title`, { name: props.view.name })
    : ''
)
const scripts = computed(() =>
  props.decision?.kind === 'blockedInUse' ? props.decision.scripts : []
)
const unknownReason = computed(() =>
  props.decision?.kind === 'blockedUnknown' ? props.decision.reason : null
)

const goScripts = () => {
  emit('close')
  void router.push({ name: 'Scripts' })
}
</script>

<template>
  <a-modal :open="open" :width="420" :mask-closable="false" @cancel="emit('close')">
    <template #title>
      <span class="guard-title">
        <PluginAvatar v-if="view" :icon="view.icon" :size="32" />
        <span>{{ title }}</span>
      </span>
    </template>
    <div class="guard-body">
      <template v-if="scripts.length">
        <a-alert
          type="warning"
          :message="t('core.plugins.guard.inUse', { count: scripts.length })"
        />
        <div>
          <div class="guard-caption">{{ t('core.plugins.guard.inUseList') }}</div>
          <ul class="guard-scripts">
            <li v-for="script in scripts" :key="script.uid">
              <span class="guard-script-name">{{ script.name }}</span>
              <span v-if="script.accounts" class="guard-caption">{{
                t('core.plugins.usage.accounts', { count: script.accounts })
              }}</span>
            </li>
          </ul>
        </div>
      </template>
      <a-alert
        v-else-if="unknownReason"
        :type="unknownReason === 'failed' ? 'error' : 'info'"
        :message="
          t(
            unknownReason === 'failed'
              ? 'core.plugins.guard.usageFailed'
              : 'core.plugins.guard.usageLoading'
          )
        "
      />
    </div>
    <template #footer>
      <a-button @click="emit('close')">{{ t('core.common.close') }}</a-button>
      <a-button v-if="scripts.length" type="primary" @click="goScripts">{{
        t('core.plugins.guard.goScripts')
      }}</a-button>
      <a-button v-else type="primary" :loading="usageLoading" @click="emit('retry')">{{
        t('core.common.retry')
      }}</a-button>
    </template>
  </a-modal>
</template>

<style scoped>
.guard-title {
  display: inline-flex;
  min-width: 0;
  align-items: center;
  gap: 12px;
}

.guard-body {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.guard-caption {
  color: var(--ant-color-text-secondary);
  font-size: 12px;
  line-height: 20px;
}

.guard-scripts {
  display: flex;
  margin: 4px 0 0;
  padding: 0;
  flex-direction: column;
  gap: 6px;
  list-style: none;
}

.guard-scripts li {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.guard-script-name {
  min-width: 0;
  overflow-wrap: anywhere;
}
</style>

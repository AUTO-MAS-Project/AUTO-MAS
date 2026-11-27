<template>
  <template v-if="routeVisible && (bindingSupported || hasBinding || !query.data.value)">
    <!-- 账号页形态：紧凑覆写开关，默认跟随托管不干扰表单 -->
    <div
      v-if="userId"
      class="game-binding-card account-override-box"
      :class="{ 'account-override-box--expanded': overrideEnabled }"
    >
      <div class="override-header">
        <div class="override-meta">
          <div class="override-title">{{ t('core.games.accountBinding') }}</div>
          <div v-if="!error && !bindingWarning" class="override-desc">
            {{
              overrideEnabled
                ? t('core.games.accountOverrideDesc')
                : t('core.games.inheritHint', { name: inheritedName })
            }}
          </div>
        </div>
        <div class="override-actions">
          <router-link v-if="overrideEnabled" to="/games" class="manage-link">
            {{ t('core.games.manageTargets') }} →
          </router-link>
          <a-switch
            :checked="overrideEnabled"
            :disabled="controlsDisabled"
            :loading="saving"
            :aria-label="t('core.games.accountBinding')"
            @change="toggleOverride"
          />
        </div>
      </div>
      <a-alert
        v-if="error"
        type="error"
        :message="error.message"
        show-icon
        class="binding-alert binding-alert--header"
      >
        <template #action>
          <a-button size="small" @click="reload">{{ t('core.games.retry') }}</a-button>
        </template>
      </a-alert>
      <div v-if="overrideEnabled" class="override-body">
        <a-alert
          v-if="bindingWarning"
          type="warning"
          :message="bindingWarning"
          show-icon
          class="binding-alert"
        />
        <a-form layout="vertical" :disabled="controlsDisabled">
          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('core.games.target')" class="compact-form-item">
                <a-select
                  :value="binding.game_id"
                  :loading="query.isPending.value"
                  show-search
                  option-filter-prop="label"
                  @change="selectTarget"
                >
                  <a-select-option value="-">{{ t('core.games.noTarget') }}</a-select-option>
                  <a-select-option
                    v-for="option in options.data.value?.data ?? []"
                    :key="option.value"
                    :value="option.value"
                    :label="option.label"
                    :disabled="!!option.disabledReason"
                    :title="option.disabledReason ?? option.warning ?? undefined"
                  >
                    {{ option.label
                    }}<span v-if="option.disabledReason"> — {{ option.disabledReason }}</span
                    ><span v-else-if="option.warning" class="option-warning">
                      — {{ option.warning }}</span
                    >
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('core.games.device')" class="compact-form-item">
                <a-select
                  :value="binding.device_id"
                  :disabled="!bindingSupported || binding.game_id === '-'"
                  @change="selectDevice"
                >
                  <a-select-option value="-">{{ t('core.games.selectDevice') }}</a-select-option>
                  <a-select-option
                    v-for="device in deviceOptions"
                    :key="device.value"
                    :value="device.value"
                    :disabled="device.disabled"
                  >
                    {{ device.label }}
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
          </a-row>
        </a-form>
      </div>
    </div>

    <!-- 托管页形态：按 variant 渲染为内嵌 plain 分区或独立分组白卡 -->
    <SectionCard
      v-else
      :variant="variant === 'section' ? 'plain' : 'card'"
      :title="t('core.games.defaultBinding')"
      :icon="variant === 'card' ? DesktopOutlined : undefined"
      class="game-binding-card"
      :class="variant === 'section' ? 'game-binding-section' : 'game-binding-standalone'"
    >
      <template #actions>
        <router-link to="/games" class="manage-link">
          {{ t('core.games.manageTargets') }} →
        </router-link>
      </template>
      <a-alert v-if="error" type="error" :message="error.message" show-icon class="binding-alert">
        <template #action>
          <a-button size="small" @click="reload">{{ t('core.games.retry') }}</a-button>
        </template>
      </a-alert>
      <a-alert
        v-if="bindingWarning"
        type="warning"
        :message="bindingWarning"
        show-icon
        class="binding-alert"
      >
        <template v-if="bindingProblem" #action>
          <a-button size="small" :disabled="controlsDisabled" @click="resetBinding">
            {{ t('core.edit.clear') }}
          </a-button>
        </template>
      </a-alert>
      <a-form layout="vertical" :disabled="controlsDisabled">
        <a-row :gutter="24">
          <a-col :xs="24" :md="12">
            <a-form-item :label="t('core.games.target')" class="binding-form-item">
              <a-select
                :value="binding.game_id"
                :loading="query.isPending.value"
                :disabled="controlsDisabled"
                show-search
                option-filter-prop="label"
                @change="selectTarget"
              >
                <a-select-option value="-">{{ t('core.games.noTarget') }}</a-select-option>
                <a-select-option
                  v-for="option in options.data.value?.data ?? []"
                  :key="option.value"
                  :value="option.value"
                  :label="option.label"
                  :disabled="!!option.disabledReason"
                  :title="option.disabledReason ?? option.warning ?? undefined"
                >
                  {{ option.label
                  }}<span v-if="option.disabledReason"> — {{ option.disabledReason }}</span
                  ><span v-else-if="option.warning" class="option-warning">
                    — {{ option.warning }}</span
                  >
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item :label="t('core.games.device')" class="binding-form-item">
              <a-select
                :value="binding.device_id"
                :disabled="controlsDisabled || !bindingSupported || binding.game_id === '-'"
                @change="selectDevice"
              >
                <a-select-option value="-">{{ t('core.games.selectDevice') }}</a-select-option>
                <a-select-option
                  v-for="device in deviceOptions"
                  :key="device.value"
                  :value="device.value"
                  :disabled="device.disabled"
                >
                  {{ device.label }}
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>
    </SectionCard>
  </template>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { DesktopOutlined } from '@ant-design/icons-vue'
import { SectionCard } from '@/components/ui'
import { useGameBinding } from '@/composables/useGameBinding'

const props = withDefaults(
  defineProps<{
    scriptId: string
    variant?: 'card' | 'section'
  }>(),
  { variant: 'card' }
)

const { t } = useI18n()
const route = useRoute()
const userId = computed(() =>
  typeof route.params.userId === 'string' ? route.params.userId : undefined
)
const routeVisible = computed(
  () => route.meta.scriptPage !== 'userAdd' && !route.path.includes('/users/add/')
)
const {
  binding,
  query,
  options,
  bindingSupported,
  hasBinding,
  bindingProblem,
  bindingWarning,
  deviceOptions,
  inheritedName,
  saving,
  controlsDisabled,
  overrideEnabled,
  error,
  toggleOverride,
  resetBinding,
  selectTarget,
  selectDevice,
  reload,
} = useGameBinding({ scriptId: () => props.scriptId, userId, enabled: routeVisible })
</script>

<style scoped>
.game-binding-standalone {
  margin-bottom: 16px;
}

.binding-alert {
  margin-bottom: 12px;
}

.binding-alert--header {
  margin-top: 12px;
  margin-bottom: 0;
}

.manage-link {
  font-size: 13px;
  color: var(--ant-color-link);
}

.account-override-box {
  margin-top: 16px;
  padding: 12px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: var(--ant-border-radius-lg);
  background: var(--app-appearance-surface-bg, var(--ant-color-bg-container));
}

.override-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.override-meta {
  min-width: 0;
}

.override-title {
  font-size: 14px;
  font-weight: 600;
  line-height: 22px;
  color: var(--ant-color-text);
}

.override-desc {
  margin-top: 2px;
  font-size: 12px;
  line-height: 20px;
  color: var(--ant-color-text-secondary);
}

.override-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.override-body {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

.binding-form-item {
  margin-bottom: 12px;
}

.option-warning {
  color: var(--ant-color-warning);
}

.compact-form-item {
  margin-bottom: 0;
}
</style>

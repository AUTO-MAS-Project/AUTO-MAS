<template>
  <template v-if="visible">
    <!-- 账号页形态：紧凑覆写开关，默认跟随托管不干扰表单 -->
    <div
      v-if="userId"
      class="game-binding-card account-override-box"
      :class="{ 'account-override-box--expanded': overrideEnabled }"
    >
      <div class="override-header">
        <div class="override-meta">
          <div class="override-title">{{ t('core.games.accountBinding') }}</div>
          <div v-if="!error" class="override-desc">
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
          v-if="binding.unavailable_reason"
          type="warning"
          :message="binding.unavailable_reason"
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
                    :title="option.disabledReason ?? undefined"
                  >
                    {{ option.label
                    }}<span v-if="option.disabledReason"> — {{ option.disabledReason }}</span>
                  </a-select-option>
                </a-select>
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('core.games.device')" class="compact-form-item">
                <a-select
                  :value="binding.device_id"
                  :disabled="binding.game_id === '-'"
                  @change="selectDevice"
                >
                  <a-select-option value="-">{{ t('core.games.selectDevice') }}</a-select-option>
                  <a-select-option
                    v-for="device in devices"
                    :key="device.uid"
                    :value="device.uid"
                    :disabled="isDeletedDevice(device.document)"
                  >
                    {{ device.document.info?.name
                    }}<span v-if="isDeletedDevice(device.document)">
                      ({{ t('core.games.deleted') }})</span
                    >
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
        v-if="binding.unavailable_reason"
        type="warning"
        :message="binding.unavailable_reason"
        show-icon
        class="binding-alert"
      />
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
                  :title="option.disabledReason ?? undefined"
                >
                  {{ option.label
                  }}<span v-if="option.disabledReason"> — {{ option.disabledReason }}</span>
                </a-select-option>
              </a-select>
            </a-form-item>
          </a-col>
          <a-col :xs="24" :md="12">
            <a-form-item :label="t('core.games.device')" class="binding-form-item">
              <a-select
                :value="binding.device_id"
                :disabled="controlsDisabled || binding.game_id === '-'"
                @change="selectDevice"
              >
                <a-select-option value="-">{{ t('core.games.selectDevice') }}</a-select-option>
                <a-select-option
                  v-for="device in devices"
                  :key="device.uid"
                  :value="device.uid"
                  :disabled="isDeletedDevice(device.document)"
                >
                  {{ device.document.info?.name
                  }}<span v-if="isDeletedDevice(device.document)">
                    ({{ t('core.games.deleted') }})</span
                  >
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
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { DesktopOutlined } from '@ant-design/icons-vue'
import { SectionCard } from '@/components/ui'
import { useConfigQuery } from '@/services/configUiSync'
import { Service } from '@/api'
import { useGamesApi, checkedGameResponse, useGameBindingQuery } from '@/composables/useGamesApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useSaveQueue } from '@/composables/useSaveQueue'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { gameDevices, isDeletedDevice, type GameBindingValue } from '@/types/games'

const props = withDefaults(
  defineProps<{
    scriptId: string
    variant?: 'card' | 'section'
  }>(),
  { variant: 'card' }
)

const { t } = useI18n()
const route = useRoute()
const client = useQueryClient()
const games = useGamesApi()
const { updateScript } = useScriptApi()
const { updateUser } = useUserApi()
const userId = computed(() =>
  typeof route.params.userId === 'string' ? route.params.userId : undefined
)
const visible = computed(
  () => route.meta.scriptPage !== 'userAdd' && !route.path.includes('/users/add/')
)
const { configLocked } = useScriptConfigLock(() =>
  userId.value ? { scriptId: props.scriptId, userId: userId.value } : props.scriptId
)
const binding = ref<GameBindingValue>({ game_id: '-', device_id: '-' })
const overrideDraftOpen = ref(false)
const queryKey = computed(() => ['game-binding', props.scriptId, userId.value])
const query = useGameBindingQuery(() => props.scriptId, userId, visible)
const options = useConfigQuery({
  queryKey: computed(() => ['game-binding-options', props.scriptId, userId.value]),
  enabled: computed(() => visible.value && !!props.scriptId),
  queryFn: async () =>
    checkedGameResponse(
      await Service.gameBindingOptionsApiGamesBindingOptionsPost({
        scriptId: props.scriptId,
        userId: userId.value,
      })
    ),
})
const selected = computed(() => games.rows.value.find(game => game.uid === binding.value.game_id))
const devices = computed(() => (selected.value ? gameDevices(selected.value) : []))
const inheritedName = computed(
  () =>
    games.rows.value.find(game => game.uid === query.data.value?.inherited?.game_id)?.document.info
      ?.name ?? t('core.games.noTarget')
)
const userSaveQueue = useSaveQueue()
const save = useMutation({
  mutationKey: computed(() => ['game-binding-save', props.scriptId, userId.value]),
  scope: { id: `script-save:${props.scriptId}` },
  retry: false,
  mutationFn: async (value: GameBindingValue) => {
    const currentUserId = userId.value
    const ok = currentUserId
      ? await userSaveQueue.enqueue(
          () => updateUser(props.scriptId, currentUserId, { game: value }),
          'game'
        )
      : await updateScript(props.scriptId, { game: value })
    if (!ok) throw new Error(t('core.games.saveFailed'))
  },
  onSettled: () => client.invalidateQueries({ queryKey: queryKey.value }),
})
const saving = save.isPending
const controlsDisabled = computed(() => configLocked.value || saving.value || query.isPending.value)
const overrideEnabled = computed(
  () =>
    overrideDraftOpen.value ||
    binding.value.game_id !== '-' ||
    Boolean(binding.value.unavailable_reason)
)
const error = computed(() => query.error.value ?? options.error.value ?? save.error.value)

watch(
  () => [props.scriptId, userId.value] as const,
  () => {
    overrideDraftOpen.value = false
  }
)

watch(
  () => query.data.value,
  data => {
    binding.value = {
      game_id: data?.binding?.game_id ?? '-',
      device_id: data?.binding?.device_id ?? '-',
      unavailable_reason: data?.binding?.unavailable_reason,
    }
  },
  { immediate: true }
)

async function toggleOverride(checked: unknown) {
  const next = Boolean(checked)
  if (next) {
    overrideDraftOpen.value = true
    return
  }
  const previous = { ...binding.value }
  const needsReset =
    previous.game_id !== '-' || previous.device_id !== '-' || Boolean(previous.unavailable_reason)
  overrideDraftOpen.value = false
  if (!needsReset) return
  binding.value = { game_id: '-', device_id: '-', unavailable_reason: undefined }
  try {
    await save.mutateAsync({ game_id: '-', device_id: '-' })
  } catch {
    // 写入失败时恢复原绑定状态，避免 UI 与服务端不一致导致无法重试关闭。
    binding.value = previous
  }
}

async function selectTarget(value: unknown) {
  if (typeof value !== 'string') return
  const target = games.rows.value.find(game => game.uid === value)
  const device =
    target?.type.kind === 'client'
      ? (gameDevices(target).find(device => !isDeletedDevice(device.document))?.uid ?? '-')
      : '-'
  binding.value = { game_id: value, device_id: device }
  if (value !== '-') overrideDraftOpen.value = false
  await save.mutateAsync({ ...binding.value }).catch(() => {})
}

async function selectDevice(value: unknown) {
  if (typeof value !== 'string') return
  binding.value = { ...binding.value, device_id: value }
  await save.mutateAsync({ ...binding.value }).catch(() => {})
}

function reload() {
  void query.refetch()
  void options.refetch()
  void games.refresh()
}
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

.compact-form-item {
  margin-bottom: 0;
}
</style>

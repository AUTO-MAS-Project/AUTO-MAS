<template>
  <a-card
    v-if="visible"
    class="game-binding-card"
    :title="t(userId ? 'core.games.accountBinding' : 'core.games.defaultBinding')"
    size="small"
  >
    <a-alert v-if="error" type="error" :message="error.message" show-icon>
      <template #action
        ><a-button size="small" @click="reload">{{ t('core.games.retry') }}</a-button></template
      >
    </a-alert>
    <a-alert
      v-if="binding.unavailable_reason"
      type="warning"
      :message="binding.unavailable_reason"
      show-icon
      class="binding-warning"
    />
    <a-form layout="vertical" :disabled="configLocked || saving || query.isPending.value">
      <a-row :gutter="16">
        <a-col :xs="24" :md="12">
          <a-form-item :label="t('core.games.target')">
            <a-select
              :value="binding.game_id"
              :loading="query.isPending.value"
              show-search
              option-filter-prop="label"
              @change="selectTarget"
            >
              <a-select-option value="-">{{
                t(userId ? 'core.games.inherit' : 'core.games.noTarget')
              }}</a-select-option>
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
          <a-form-item :label="t('core.games.device')">
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
    <a-typography-paragraph v-if="userId && binding.game_id === '-'" type="secondary">
      {{ t('core.games.inheritHint', { name: inheritedName }) }}
    </a-typography-paragraph>
    <router-link to="/games">{{ t('core.games.manageTargets') }}</router-link>
  </a-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useMutation, useQueryClient } from '@tanstack/vue-query'
import { useConfigQuery } from '@/services/configUiSync'
import { Service } from '@/api'
import { useGamesApi, checkedGameResponse, useGameBindingQuery } from '@/composables/useGamesApi'
import { useScriptApi } from '@/composables/useScriptApi'
import { useUserApi } from '@/composables/useUserApi'
import { useScriptConfigLock } from '@/composables/useScriptConfigLock'
import { gameDevices, isDeletedDevice, type GameBindingValue } from '@/types/games'

const props = defineProps<{ scriptId: string }>()
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
const save = useMutation({
  mutationKey: computed(() => ['game-binding-save', props.scriptId, userId.value]),
  scope: { id: `script-save:${props.scriptId}` },
  retry: false,
  mutationFn: async (value: GameBindingValue) => {
    const ok = userId.value
      ? await updateUser(props.scriptId, userId.value, { game: value })
      : await updateScript(props.scriptId, { game: value })
    if (!ok) throw new Error(t('core.games.saveFailed'))
  },
  onSettled: () => client.invalidateQueries({ queryKey: queryKey.value }),
})
const saving = save.isPending
const error = computed(() => query.error.value ?? options.error.value ?? save.error.value)
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

async function selectTarget(value: unknown) {
  if (typeof value !== 'string') return
  const target = games.rows.value.find(game => game.uid === value)
  const device =
    target?.type.kind === 'client'
      ? (gameDevices(target).find(device => !isDeletedDevice(device.document))?.uid ?? '-')
      : '-'
  binding.value = { game_id: value, device_id: device }
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
.game-binding-card {
  margin-bottom: 16px;
}
.binding-warning {
  margin-bottom: 16px;
}
</style>

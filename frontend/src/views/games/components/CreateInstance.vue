<template>
  <a-modal
    :open="open"
    :title="
      t(
        game.type.type === 'general_emulator'
          ? 'core.games.addConnection'
          : 'core.games.createInstance'
      )
    "
    :ok-button-props="{ disabled: !canCreate }"
    :confirm-loading="saving || action?.state === 'busy'"
    :mask-closable="false"
    @ok="create"
    @cancel="close"
  >
    <a-form layout="vertical">
      <a-form-item :label="t('core.games.name')"><a-input v-model:value="name" /></a-form-item>
      <template v-if="game.type.type === 'avd'">
        <a-form-item :label="t('core.games.settingsFields.memoryMb')"
          ><a-select
            v-model:value="memory"
            :options="
              [2048, 3072, 4096, 6144, 8192].map(value => ({ value, label: `${value} MB` }))
            "
        /></a-form-item>
        <a-form-item :label="t('core.games.settingsFields.cpu')"
          ><a-select
            v-model:value="cpu"
            :options="[2, 4, 6].map(value => ({ value, label: String(value) }))"
        /></a-form-item>
        <a-form-item :label="t('core.games.settingsFields.fps')"
          ><a-select
            v-model:value="fps"
            :options="[30, 60].map(value => ({ value, label: String(value) }))"
        /></a-form-item>
        <a-form-item :label="t('core.games.resolution')"
          ><a-select
            v-model:value="resolution"
            :options="[
              { value: 720, label: '1280 × 720' },
              { value: 1080, label: '1920 × 1080' },
            ]"
        /></a-form-item>
        <a-form-item :label="t('core.games.dataPartition')"
          ><a-input-number v-model:value="partition" :min="8" :max="256"
        /></a-form-item>
      </template>
    </a-form>
    <a-alert v-if="error" type="error" :message="error" show-icon />
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useConfirm } from '@/composables/useConfirm'
import { gameActionHint, type GameRow } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { useGameTriggers } from '@/composables/useGameTriggers'

const props = defineProps<{ open: boolean; game: GameRow }>()
const emit = defineEmits<{ close: [] }>()
const { t } = useI18n()
const { confirm } = useConfirm()
const api = useGamesApi(),
  operations = useGameTriggers()
const action = computed(() => gameActionHint(props.game, props.game.uid, 'create_instance'))
const canCreate = computed(() => action.value?.editable === true)
const name = ref(''),
  memory = ref(4096),
  cpu = ref(4),
  fps = ref(60),
  resolution = ref(720),
  partition = ref(32)
const saving = ref(false),
  error = ref('')
watch(
  () => props.open,
  open => {
    if (open) {
      name.value = ''
      error.value = ''
    }
  }
)
async function create() {
  if (saving.value || !canCreate.value) return
  saving.value = true
  error.value = ''
  try {
    await api.update(props.game, {
      creation:
        props.game.type.type === 'avd'
          ? {
              name: name.value,
              memory_mb: memory.value,
              cpu: cpu.value,
              fps: fps.value,
              resolution: resolution.value,
              data_partition_gb: partition.value,
            }
          : { name: name.value },
    })
    await operations.run(props.game, props.game.uid, 'create_instance')
    emit('close')
  } catch (e) {
    error.value = String(e)
  } finally {
    saving.value = false
  }
}
function close() {
  if (!name.value) {
    emit('close')
    return
  }
  void confirm({ tone: 'warning', title: t('core.games.discard'), onOk: () => emit('close') })
}
</script>

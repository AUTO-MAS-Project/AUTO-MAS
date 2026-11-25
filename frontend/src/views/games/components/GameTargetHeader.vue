<template>
  <header class="detail-header">
    <div class="detail-identity">
      <div class="detail-title-row">
        <h2 class="detail-title">{{ targetName }}</h2>
        <a-tag>{{ game.type.name }}</a-tag>
        <StatusChip v-if="targetInUse" tone="processing">{{ t('core.games.inUse') }}</StatusChip>
      </div>
      <div v-if="displayPath" class="detail-path-row">
        <FolderOpenOutlined class="path-icon" />
        <span class="detail-path" :title="displayPath">{{ displayPath }}</span>
        <a-button type="text" size="small" :aria-label="t('core.games.copyPath')" @click="copyPath">
          <template #icon><CopyOutlined /></template>
        </a-button>
      </div>
    </div>

    <a-space wrap class="detail-actions">
      <a-button
        v-if="hint('refresh')"
        :loading="hint('refresh')?.state === 'busy'"
        :disabled="!canRun('refresh')"
        @click="refreshDevices"
      >
        <template #icon><ReloadOutlined /></template>
        {{ t('core.games.refresh') }}
      </a-button>
      <a-button
        v-if="hint('create_instance')"
        type="primary"
        ghost
        :disabled="!canRun('create_instance')"
        :loading="hint('create_instance')?.state === 'busy'"
        @click="emit('createInstance')"
      >
        <template #icon><PlusOutlined /></template>
        {{
          t(
            game.type.type === 'general_emulator'
              ? 'core.games.addConnection'
              : 'core.games.createInstance'
          )
        }}
      </a-button>
      <a-dropdown v-if="hasBatchMenu">
        <a-button> {{ t('core.games.more') }} <DownOutlined /> </a-button>
        <template #overlay>
          <a-menu @click="headerMenuAction">
            <a-menu-item
              v-if="hint('stable_mode')"
              key="stable_mode"
              :disabled="!canRun('stable_mode')"
            >
              {{ t('core.games.applyStableMode') }}
            </a-menu-item>
            <a-menu-item v-if="hint('capture')" key="capture" :disabled="!canRun('capture')">
              {{ t('core.games.capture') }}
            </a-menu-item>
            <a-menu-divider v-if="hint('delete')" />
            <a-menu-item v-if="hint('delete')" key="delete" danger :disabled="!canRun('delete')">
              {{ t('core.games.delete') }}
            </a-menu-item>
          </a-menu>
        </template>
      </a-dropdown>
      <a-button v-else-if="hint('delete')" danger :disabled="!canRun('delete')" @click="remove">
        <template #icon><DeleteOutlined /></template>
        {{ t('core.games.delete') }}
      </a-button>
    </a-space>
  </header>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import {
  CopyOutlined,
  DeleteOutlined,
  DownOutlined,
  FolderOpenOutlined,
  PlusOutlined,
  ReloadOutlined,
} from '@ant-design/icons-vue'
import { StatusChip } from '@/components/ui'
import { useConfirm } from '@/composables/useConfirm'
import { Service } from '@/api'
import { gameActionHint, type GameRow } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { useGameTriggers } from '@/composables/useGameTriggers'
import { isTargetInUse, resolveEditableGameTarget } from '../gamePresentation'

const props = defineProps<{ game: GameRow }>()
const emit = defineEmits<{ createInstance: [] }>()

const { t } = useI18n()
const { confirm } = useConfirm()
const api = useGamesApi()
const operations = useGameTriggers()

const hint = (field: string) => gameActionHint(props.game, props.game.uid, field)
const canRun = (field: string) => hint(field)?.editable === true
const targetName = computed(() => props.game.document.info?.name || t('core.emulator.unnamed'))
const displayPath = computed(() => {
  const path = props.game.document.info?.path
  if (path) return path
  return props.game.type.type === 'general_emulator' ? t('core.games.noLaunchProgram') : ''
})
const targetInUse = computed(() => isTargetInUse(props.game))
const hasBatchMenu = computed(() => Boolean(hint('stable_mode') || hint('capture')))

async function copyPath() {
  if (!displayPath.value) return
  try {
    await navigator.clipboard.writeText(displayPath.value)
    message.success(t('core.games.pathCopied'))
  } catch {
    message.error(t('core.comp.copyFailed'))
  }
}

async function refreshDevices() {
  if (!canRun('refresh')) return
  try {
    await operations.run(props.game, props.game.uid, 'refresh')
  } catch (error) {
    message.error(String(error))
  }
}

function remove() {
  if (!canRun('delete')) return
  const targetUid = props.game.uid
  const description = props.game.document.info?.name ?? undefined
  void confirm({
    tone: 'danger',
    title: t('core.games.deleteConfirm'),
    description,
    onOk: async () => {
      const target = resolveEditableGameTarget(api.rows.value, targetUid, 'delete')
      if (!target) return
      await api.remove(target).catch(error => message.error(String(error)))
    },
  })
}

function headerMenuAction({ key }: { key: string | number }) {
  if (key === 'delete') {
    remove()
    return
  }
  if ((key !== 'stable_mode' && key !== 'capture') || !canRun(key)) return
  const stable = key === 'stable_mode'
  const targetUid = props.game.uid
  void confirm({
    tone: 'warning',
    title: t(stable ? 'core.games.applyStableMode' : 'core.games.capture'),
    onOk: async () => {
      const target = resolveEditableGameTarget(api.rows.value, targetUid, key)
      if (!target) return
      try {
        const result = await api.change(target.type.type, stable ? 'stable_mode' : 'capture', () =>
          stable
            ? Service.applyStableModeApiGamesStableModeApplyPost({ gameId: target.uid })
            : Service.captureBaselinesApiGamesGuardCapturePost({ gameId: target.uid })
        )
        const values = Object.values(result.data ?? {}) as unknown[]
        const failures = values.filter(
          item => typeof item === 'object' && item !== null && 'ok' in item && item.ok === false
        ).length
        if (failures)
          message.warning(
            t('core.games.partialSettings', { failed: failures, total: values.length })
          )
      } catch (error) {
        message.error(String(error))
      }
    },
  })
}
</script>

<style scoped>
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  flex-wrap: wrap;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.detail-identity {
  min-width: 0;
  flex: 1 1 280px;
}

.detail-title-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.detail-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.detail-path-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  min-width: 0;
}

.path-icon {
  color: var(--ant-color-text-tertiary);
  flex-shrink: 0;
}

.detail-path {
  font-family: var(--font-monospace);
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>

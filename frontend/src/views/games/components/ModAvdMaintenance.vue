<template>
  <div class="avd-maintenance">
    <div class="maintenance-header-bar">
      <div v-if="updateInfo" class="maintenance-versions">
        <div class="ver-block">
          <span class="ver-label">{{ t('core.games.installedVersion') }}</span>
          <span class="ver-val">{{ text(updateInfo, 'currentVersion') || '—' }}</span>
        </div>
        <div class="ver-divider" aria-hidden="true" />
        <div class="ver-block">
          <span class="ver-label">{{ t('core.games.latestVersion') }}</span>
          <span class="ver-val" :class="{ 'ver-val--primary': hasUpdate }">
            {{ text(updateInfo, 'latestVersion') || '—' }}
          </span>
        </div>
        <template v-if="text(updateInfo, 'requiredAutoMas')">
          <div class="ver-divider" aria-hidden="true" />
          <div class="ver-block">
            <span class="ver-label">{{ t('core.games.requiredAutoMas') }}</span>
            <span class="ver-val">{{ text(updateInfo, 'requiredAutoMas') }}</span>
          </div>
        </template>
        <template v-if="text(updateInfo, 'preparedVersion')">
          <div class="ver-divider" aria-hidden="true" />
          <div class="ver-block">
            <span class="ver-label">{{ t('core.games.preparedVersion') }}</span>
            <span class="ver-val">{{ text(updateInfo, 'preparedVersion') }}</span>
          </div>
        </template>
      </div>

      <a-space wrap class="maintenance-actions">
        <a-button
          v-if="hint('check_components')"
          :loading="running('check_components')"
          :disabled="!canRun('check_components')"
          @click="run('check_components')"
        >
          <template #icon><ToolOutlined /></template>
          {{ t('core.games.checkComponents') }}
        </a-button>
        <a-button
          v-if="hint('check_update')"
          :loading="running('check_update')"
          :disabled="!canRun('check_update')"
          @click="run('check_update')"
        >
          {{ t('core.games.checkUpdate') }}
        </a-button>
        <a-button
          v-if="hint('update')"
          type="primary"
          :loading="running('update')"
          :disabled="!canRun('update')"
          @click="update"
        >
          <template #icon><CloudDownloadOutlined /></template>
          {{ t('core.games.update') }}
        </a-button>
      </a-space>
    </div>

    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-alert v-if="updateWarning" type="warning" :message="updateWarning" show-icon />

    <template v-if="progress">
      <a-progress
        v-if="typeof progress.percent === 'number'"
        :percent="Math.round(progress.percent)"
        :status="
          progress.status === 'failed'
            ? 'exception'
            : progress.status === 'success'
              ? 'success'
              : 'active'
        "
      />
      <a-typography-paragraph v-if="text(progress, 'message')" class="progress-message">
        {{ text(progress, 'message') }}
      </a-typography-paragraph>
    </template>

    <a-table
      v-if="components.length"
      :data-source="components"
      :columns="componentColumns"
      row-key="id"
      :pagination="false"
      size="small"
    >
      <template #bodyCell="{ column, record }">
        <template v-if="column.key === 'installed'">
          <StatusChip :tone="record.installed ? 'success' : 'warning'">
            {{ t(record.installed ? 'core.games.ready' : 'core.games.missing') }}
          </StatusChip>
        </template>
      </template>
    </a-table>

    <div v-if="prechecks.length" class="precheck-grid">
      <a-alert
        v-for="item in prechecks"
        :key="text(item, 'id')"
        :type="item.ok === true ? 'success' : item.blocking === false ? 'warning' : 'error'"
        :message="text(item, 'title')"
        :description="
          [text(item, 'reason'), text(item, 'advice')].filter(Boolean).join(' ') || undefined
        "
        show-icon
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { CloudDownloadOutlined, ToolOutlined } from '@ant-design/icons-vue'
import { StatusChip } from '@/components/ui'
import { useConfirm } from '@/composables/useConfirm'
import { gameActionHint, type GameRow } from '@/types/games'
import { useGamesApi } from '@/composables/useGamesApi'
import { useGameTriggers } from '@/composables/useGameTriggers'
import { hasModAvdUpdate, resolveEditableGameTarget } from '../gamePresentation'

const props = defineProps<{ game: GameRow }>()
const { t } = useI18n()
const { confirm } = useConfirm()
const api = useGamesApi()
const operations = useGameTriggers()
const error = ref('')

function record(value: unknown): Record<string, unknown> | undefined {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : undefined
}
function rows(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.flatMap(item => (record(item) ? [record(item)!] : [])) : []
}
function text(value: Record<string, unknown>, key: string): string {
  return typeof value[key] === 'string' ? value[key] : ''
}

const maintenance = computed(() => props.game.runtime.maintenance ?? {})
const updateInfo = computed(() => record(maintenance.value.update))
const hasUpdate = computed(() => hasModAvdUpdate(props.game))
const progress = computed(
  () => record(maintenance.value.progress) ?? record(updateInfo.value?.progress)
)
const components = computed(() => rows(record(maintenance.value.components)?.components))
const prechecks = computed(() => rows(record(maintenance.value.components)?.items))
const hint = (action: string) => gameActionHint(props.game, props.game.uid, action)
const running = (action: string) => hint(action)?.state === 'busy'
const canRun = (action: string) => hint(action)?.editable === true
const updateWarning = computed(() =>
  updateInfo.value
    ? text(updateInfo.value, 'checkError') || text(updateInfo.value, 'notUpdatableReason')
    : ''
)
const componentColumns = computed(() => [
  { title: t('core.games.component'), dataIndex: 'name' },
  { title: t('core.games.version'), dataIndex: 'version', width: 130 },
  { title: t('core.games.status'), key: 'installed', width: 110 },
])

async function run(action: string) {
  if (!canRun(action)) return
  error.value = ''
  try {
    await operations.run(props.game, props.game.uid, action)
  } catch (e) {
    error.value = String(e)
  }
}

function update() {
  if (!canRun('update')) return
  const targetUid = props.game.uid
  void confirm({
    tone: 'warning',
    title: t('core.games.updateConfirm'),
    description: t('core.games.updateHint'),
    onOk: async () => {
      const target = resolveEditableGameTarget(api.rows.value, targetUid, 'update')
      if (!target) return
      error.value = ''
      try {
        await operations.run(target, target.uid, 'update')
      } catch (e) {
        error.value = String(e)
      }
    },
  })
}
</script>

<style scoped>
.avd-maintenance {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.maintenance-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 12px 14px;
  border-radius: var(--ant-border-radius);
  background: var(--ant-color-fill-quaternary);
}

.maintenance-versions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.ver-block {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ver-label {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.ver-val {
  font-size: 13px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.ver-val--primary {
  color: var(--ant-color-primary);
}

.ver-divider {
  width: 1px;
  height: 24px;
  background: var(--ant-color-border-secondary);
}

.maintenance-actions {
  margin-inline-start: auto;
}

.progress-message {
  margin-bottom: 0;
}

.precheck-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 8px;
}
</style>

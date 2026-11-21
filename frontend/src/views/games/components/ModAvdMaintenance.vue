<template>
  <section class="avd-maintenance">
    <a-space wrap>
      <a-button
        v-if="hint('check_components')"
        :loading="running('check_components')"
        :disabled="!canRun('check_components')"
        @click="run('check_components')"
        >{{ t('core.games.checkComponents') }}</a-button
      >
      <a-button
        v-if="hint('check_update')"
        :loading="running('check_update')"
        :disabled="!canRun('check_update')"
        @click="run('check_update')"
        >{{ t('core.games.checkUpdate') }}</a-button
      >
      <a-button
        v-if="hint('update')"
        type="primary"
        :loading="running('update')"
        :disabled="!canRun('update')"
        @click="update"
        >{{ t('core.games.update') }}</a-button
      >
    </a-space>
    <a-alert v-if="error" type="error" :message="error" show-icon />
    <a-descriptions v-if="updateInfo" :column="2" size="small">
      <a-descriptions-item :label="t('core.games.installedVersion')">{{
        text(updateInfo, 'currentVersion') || '—'
      }}</a-descriptions-item>
      <a-descriptions-item :label="t('core.games.latestVersion')">{{
        text(updateInfo, 'latestVersion') || '—'
      }}</a-descriptions-item>
      <a-descriptions-item
        v-if="text(updateInfo, 'requiredAutoMas')"
        :label="t('core.games.requiredAutoMas')"
        >{{ text(updateInfo, 'requiredAutoMas') }}</a-descriptions-item
      >
      <a-descriptions-item
        v-if="text(updateInfo, 'preparedVersion')"
        :label="t('core.games.preparedVersion')"
        >{{ text(updateInfo, 'preparedVersion') }}</a-descriptions-item
      >
    </a-descriptions>
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
      <a-typography-paragraph>{{ text(progress, 'message') }}</a-typography-paragraph>
    </template>
    <a-table
      v-if="components.length"
      :data-source="components"
      :columns="componentColumns"
      row-key="id"
      :pagination="false"
      size="small"
    >
      <template #bodyCell="{ column, record }"
        ><template v-if="column.key === 'installed'"
          ><a-tag :color="record.installed ? 'success' : 'warning'">{{
            t(record.installed ? 'core.games.ready' : 'core.games.missing')
          }}</a-tag></template
        ></template
      >
    </a-table>
    <a-alert
      v-for="item in prechecks"
      :key="text(item, 'id')"
      :type="item.ok === true ? 'success' : item.blocking === false ? 'warning' : 'error'"
      :message="text(item, 'title')"
      :description="[text(item, 'reason'), text(item, 'advice')].filter(Boolean).join(' ')"
      show-icon
    />
  </section>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Modal } from 'ant-design-vue'
import { gameActionHint, type GameRow } from '@/types/games'
import { useGameTriggers } from '@/composables/useGameTriggers'

const props = defineProps<{ game: GameRow }>()
const { t } = useI18n()
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
  { title: t('core.games.version'), dataIndex: 'version' },
  { title: t('core.games.status'), key: 'installed', width: 120 },
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
  Modal.confirm({
    title: t('core.games.updateConfirm'),
    content: t('core.games.updateHint'),
    onOk: () => run('update'),
  })
}
</script>

<style scoped>
.avd-maintenance {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 16px;
}
</style>

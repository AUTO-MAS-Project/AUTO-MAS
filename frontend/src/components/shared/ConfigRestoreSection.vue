<template>
  <!-- ══ 配置恢复（历史备份浏览 / 预览 / 查看详细 / 一键恢复；MAS 在前脚本在后）══ -->
  <AppModal
    :open="open"
    :title="t('core.edit.configRestoreTitle')"
    footer="none"
    width="520px"
    @update:open="emit('update:open', $event)"
  >
    <a-alert
      v-if="disabled"
      class="restore-lock-alert"
      type="warning"
      show-icon
      :message="t('core.edit.configLocked')"
    />
    <a-segmented
      v-model:value="restoreTarget"
      block
      class="restore-target-switch"
      :options="targetOptions"
    />
    <p class="restore-desc">
      {{
        currentTarget?.kind === 'user'
          ? (userDesc ?? t('core.edit.configRestoreMasDesc', { script: scriptName }))
          : (scriptDesc ?? t('core.edit.configRestoreScriptDesc', { script: scriptName }))
      }}
      <!-- 当前配置来源（三态专项才有；用户靠它与备份标签对比是否需要跨来源恢复） -->
      <span v-if="currentSource" class="restore-current-source">
        {{ t('core.edit.configRestoreCurrentSource', { mode: t(sourceLabelKey(currentSource)) }) }}
      </span>
    </p>
    <a-spin :spinning="backupsLoading">
      <NoData v-if="!backups.length" :description="t('core.edit.configRestoreEmpty')" />
      <a-list v-else :data-source="backups" size="small" row-key="time">
        <template #renderItem="{ item }">
          <a-list-item>
            <div class="backup-main">
              <span class="backup-time">{{ formatBackupTime(item.time) }}</span>
              <!-- 备份时点的配置来源标签（共享/独立/原生；旧版备份无标注不显示） -->
              <a-tag v-if="item.base" :color="modeTag(item.base).color">
                {{ modeTag(item.base).label }}
              </a-tag>
            </div>
            <a-space>
              <a-button type="link" size="small" @click="previewItem = item">
                {{ t('core.edit.configRestorePreview') }}
              </a-button>
              <a-button
                size="small"
                :disabled="disabled || restoring || blockedRestoreTimes.has(item.time)"
                @click="confirmRestore(item)"
              >
                {{ t('core.edit.configRestoreAction') }}
              </a-button>
            </a-space>
          </a-list-item>
        </template>
      </a-list>
    </a-spin>
  </AppModal>

  <ConfigRestorePreview
    v-if="previewItem && currentTarget"
    :key="previewItem.time"
    :item="previewItem"
    :target="currentTarget"
    :api="api"
    :script-name="scriptName"
    :disabled="disabled"
    :field-labels="fieldLabels"
    :format-value="formatValue"
    :on-detail="onDetail"
    :current-source="currentSource"
    @close="previewItem = null"
    @allowed="setRestoreAllowed"
  >
    <template v-for="(_, name) in $slots" #[name]="scope"
      ><slot :name="name" v-bind="scope"
    /></template>
  </ConfigRestorePreview>
</template>
<script setup lang="ts">
import { computed, h, inject, onScopeDispose, ref, watch } from 'vue'
import { routeLocationKey } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { AppModal } from '@/components/ui'
import { useConfirm } from '@/composables/useConfirm'
import {
  buildCorruptedForceConfirm,
  buildRestoreConfirm,
  corruptedForceConfirmContent,
  sourceLabelKey,
  sourceTagColor,
} from '@/utils/configRestoreMode'
import ConfigRestorePreview from './ConfigRestorePreview.vue'
import { formatBackupTime, type BackupItem, type ConfigRestoreProps } from './configRestore'

const props = defineProps<ConfigRestoreProps>()
const emit = defineEmits<{ 'update:open': [open: boolean] }>()
const { t } = useI18n()
const { confirm } = useConfirm()
const route = inject(routeLocationKey, null)
const selection = ref('')
const currentTarget = computed(
  () => props.targets.find(item => item.key === selection.value) ?? props.targets[0]
)
const restoreTarget = computed({
  get: () => currentTarget.value?.key ?? '',
  set: key => {
    selection.value = key
  },
})
const targetOptions = computed(() =>
  props.targets.map(tgt => ({
    label:
      tgt.kind === 'user'
        ? t('core.edit.configRestoreTargetMas')
        : t('core.edit.configRestoreTargetScript', { script: props.scriptName }),
    value: tgt.key,
  }))
)
const backups = ref<BackupItem[]>([])
const backupsLoading = ref(false)
/** 当前配置来源（仅三态专项非空）：与备份标签比对决定是否提示跨来源 */
const currentSource = ref<string | null>(null)
const blockedRestoreTimes = ref(new Set<string>())
/** 配置来源标签（备份时点 Info.Base → 文案与标签色）；未知值按独立兜底 */
const modeTag = (base: string): { label: string; color: string } => ({
  label: t(sourceLabelKey(base)),
  color: sourceTagColor(base),
})

const previewItem = ref<BackupItem | null>(null)
const restoring = ref(false)
let generation = 0

function setRestoreAllowed(time: string, allowed: boolean) {
  if (previewItem.value?.time !== time) return
  if (allowed) blockedRestoreTimes.value.delete(time)
  else blockedRestoreTimes.value.add(time)
}

async function loadBackups(version: number) {
  backupsLoading.value = true
  blockedRestoreTimes.value.clear()
  try {
    const resp = await props.api.list(restoreTarget.value)
    if (version !== generation) return
    if (resp.code !== 200) throw new Error(resp.message || t('core.edit.configRestoreListFailed'))
    backups.value = resp.data ?? []
    currentSource.value = resp.base ?? null
  } catch (error) {
    if (version !== generation) return
    backups.value = []
    currentSource.value = null
    message.error(error instanceof Error ? error.message : t('core.edit.configRestoreListFailed'))
  } finally {
    if (version === generation) backupsLoading.value = false
  }
}

watch(
  [
    () => props.open,
    restoreTarget,
    () => props.scriptId ?? route?.params.scriptId,
    () => (props.userId === undefined ? route?.params.userId : props.userId),
  ],
  () => {
    generation++
    previewItem.value = null
    backups.value = []
    currentSource.value = null
    restoring.value = false
    if (props.open && restoreTarget.value) void loadBackups(generation)
  },
  { immediate: true, flush: 'sync' }
)
onScopeDispose(() => {
  generation++
})

function confirmRestore(item: BackupItem) {
  const version = generation
  const target = restoreTarget.value
  const allowed = () =>
    version === generation && !props.disabled && !blockedRestoreTimes.value.has(item.time)
  if (!allowed() || restoring.value) return
  const { title, paragraphs } = buildRestoreConfirm(
    t,
    {
      title: t('core.edit.configRestoreConfirmTitle'),
      desc: t('core.edit.configRestoreConfirmDesc'),
    },
    item.base,
    currentSource.value
  )
  if (props.dirty) paragraphs.push(t('core.plugins.restoreDiscardDraft'))
  void confirm({
    tone: 'danger',
    title,
    description: h(
      'div',
      paragraphs.map(text =>
        h('p', { style: { color: 'var(--ant-color-error)', margin: '0 0 8px' } }, text)
      )
    ),
    okText: t('core.edit.configRestoreAction'),
    onOk: () => restore(false),
  })

  async function restore(force: boolean) {
    if (!allowed() || restoring.value) return
    restoring.value = true
    try {
      const resp = await props.api.restore(target, item.time, force || undefined)
      if (version !== generation) return
      if (resp.code === 409 && !force) {
        const copy = buildCorruptedForceConfirm(t, resp.message ?? '')
        void confirm({
          tone: 'danger',
          title: copy.title,
          description: corruptedForceConfirmContent(copy.detail, copy.desc),
          okText: copy.okText,
          cancelText: t('core.edit.cancel'),
          onOk: () => restore(true),
        })
        return
      }
      if (resp.code !== 200) throw new Error(resp.message || t('core.edit.configRestoreFailed'))
      message.success(t('core.edit.configRestoreSuccess'))
      await props.onRestored?.(target, item)
      if (version === generation) await loadBackups(version)
    } catch (error) {
      if (version === generation)
        message.error(error instanceof Error ? error.message : t('core.edit.configRestoreFailed'))
    } finally {
      if (version === generation) restoring.value = false
    }
  }
}
</script>

<style scoped>
.restore-lock-alert {
  margin-bottom: 12px;
}

.restore-target-switch {
  margin-bottom: 12px;
}

/* 恢复目标分段器：低频工具内的选择，选中态只用中性灰填充与主文字色 */
.restore-target-switch :deep(.ant-segmented-item-selected) {
  background: var(--ant-color-fill-secondary);
  box-shadow: none;
}

.restore-target-switch :deep(.ant-segmented-item-selected .ant-segmented-item-label) {
  color: var(--ant-color-text);
}

.restore-desc {
  margin: 0 0 12px;
  color: var(--ant-color-text-secondary);
  font-size: 13px;
}

/* 当前配置来源：与描述同段换行展示，供用户比对各备份的来源标签 */
.restore-current-source {
  display: block;
  margin-top: 2px;
}

.backup-main {
  display: flex;
  align-items: center;
  gap: 8px;
}

.backup-time {
  color: var(--ant-color-text-secondary);
  font-variant-numeric: tabular-nums;
}
</style>

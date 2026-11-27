<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message } from 'ant-design-vue'
import { BlockOutlined } from '@ant-design/icons-vue'
import { useI18n } from 'vue-i18n'
import type { GlobalConfig } from '@/api'
import SectionCard from '@/components/ui/SectionCard.vue'
import SettingRow from '@/components/ui/SettingRow.vue'
import { getConfig, saveConfig } from '@/utils/config'
import type { SettingChangeHandler } from '@/views/setting/settingTypes'
import { useDesktopSessionTargets } from './useDesktopSessionTargets'
import type { DesktopSessionRequest } from '../../../electron/services/desktopSessionProtocol'

/**
 * 设置 → 功能里的桌面分身卡片：集中管理在分身里跑的队列和托管。
 * 清单存在后端 GlobalConfig.DesktopSession.Targets，读写走设置页的保存链路；
 * 分辨率与最小化方式只有 Electron 用，存在 frontend_config。
 */
const props = defineProps<{
  settings: GlobalConfig
  handleSettingChange: SettingChangeHandler
}>()

const { t } = useI18n()
const text = (key: string) => t(`bootstrap.desktopSession.${key}`)

const supported = ref<boolean>()
const starting = ref<string | null>(null)
const mode = ref<DesktopSessionRequest['mode']>('proxy')
const resolution = ref<DesktopSessionRequest['resolution']>('1080p')

const {
  loading: loadingTargets,
  adding,
  atLimit,
  candidates,
  rows: targetRows,
  launchableIds,
  load: loadTargets,
  add: addTarget,
  remove: removeTarget,
} = useDesktopSessionTargets({
  settings: () => props.settings,
  save: props.handleSettingChange,
  onAddRejected: issue => message.warning(text(issue)),
  onLoadFailed: () => message.error(text('loadTasksFailed')),
})

const addOptions = computed(() =>
  candidates.value.map(({ target, powerAction }) => {
    const label = `${t(`core.scheduler.scope.${target.kind}`)} · ${target.name}`
    return {
      value: target.value,
      disabled: powerAction,
      label: powerAction ? `${label} · ${text('powerAction')}` : label,
    }
  })
)

const rows = computed(() =>
  targetRows.value.map(row => ({
    ...row,
    kindLabel: row.kind ? text(row.kind === 'queue' ? 'queueLabel' : 'scriptLabel') : undefined,
    issueText: row.issue ? text(row.issue) : undefined,
  }))
)

async function open(queueIds: string[], key: string) {
  const launch = window.electronAPI?.desktopSessionOpen
  if (!launch || supported.value !== true) return
  starting.value = key
  try {
    await launch({ queueIds: [...queueIds], mode: mode.value, resolution: resolution.value })
  } catch {
    message.error(text('openFailed'))
  } finally {
    starting.value = null
  }
}

function saveConnection(patch: {
  desktopSessionMode?: DesktopSessionRequest['mode']
  desktopSessionResolution?: DesktopSessionRequest['resolution']
}) {
  // saveConfig 内部已按提交顺序串行落盘；失败时本次打开仍用界面上的值。
  void saveConfig(patch).catch(() => undefined)
}

function changeMode(value: unknown) {
  if (value !== 'proxy' && value !== 'native') return
  mode.value = value
  saveConnection({ desktopSessionMode: value })
}

function changeResolution(value: unknown) {
  if (value !== '1080p' && value !== 'primary') return
  resolution.value = value
  saveConnection({ desktopSessionResolution: value })
}

onMounted(async () => {
  void loadTargets()
  try {
    const config = await getConfig()
    if (config.desktopSessionMode === 'native') mode.value = 'native'
    if (config.desktopSessionResolution === 'primary') resolution.value = 'primary'
  } catch {
    // 读不到偏好时用默认参数。
  }
  supported.value = (await window.electronAPI?.desktopSessionSupported?.()) === true
})
</script>

<template>
  <SectionCard :title="text('title')" :icon="BlockOutlined">
    <a-alert type="warning" show-icon class="card-alert" :message="text('experimental')" />
    <a-alert
      v-if="supported === false"
      type="info"
      show-icon
      class="card-alert"
      :message="text('unsupported')"
    />

    <SettingRow :label="text('resolution')">
      <a-select
        :value="resolution"
        class="row-select"
        :aria-label="text('resolution')"
        :options="[
          { value: '1080p', label: '1920 × 1080' },
          { value: 'primary', label: text('primaryResolution') },
        ]"
        @change="changeResolution"
      />
    </SettingRow>

    <SettingRow :label="text('minimizeMode')">
      <a-select
        :value="mode"
        class="row-select"
        :aria-label="text('minimizeMode')"
        :options="[
          { value: 'proxy', label: text('proxy') },
          { value: 'native', label: text('native') },
        ]"
        @change="changeMode"
      />
    </SettingRow>

    <SettingRow stacked>
      <div class="targets">
        <a-select
          :value="null"
          show-search
          class="add-select"
          option-filter-prop="label"
          :options="addOptions"
          :loading="loadingTargets || adding"
          :disabled="atLimit || adding"
          :placeholder="text('selectTasks')"
          :aria-label="text('selectTasks')"
          @dropdown-visible-change="
            (visible: boolean) => visible && !loadingTargets && loadTargets()
          "
          @select="addTarget"
        />
        <a-list v-if="rows.length" size="small" bordered :data-source="rows" class="target-list">
          <template #renderItem="{ item }">
            <a-list-item>
              <template #actions>
                <a-button
                  type="link"
                  size="small"
                  :disabled="supported !== true || !item.launchable"
                  :loading="starting === item.id"
                  @click="open([item.id], item.id)"
                >
                  {{ text('start') }}
                </a-button>
                <a-button type="link" size="small" danger @click="removeTarget(item.id)">
                  {{ text('removeTarget') }}
                </a-button>
              </template>
              <div class="target-main">
                <span class="target-name">
                  <a-tag v-if="item.kindLabel" class="target-kind">{{ item.kindLabel }}</a-tag>
                  <span class="target-label" :title="item.name">{{ item.name }}</span>
                </span>
                <a-tag v-if="item.issueText" color="warning" class="target-issue">
                  {{ item.issueText }}
                </a-tag>
              </div>
            </a-list-item>
          </template>
        </a-list>
      </div>
    </SettingRow>

    <template #footer>
      <div class="footer-actions">
        <a-button
          :disabled="supported !== true || starting !== null"
          :loading="starting === 'open'"
          @click="open([], 'open')"
        >
          {{ text('open') }}
        </a-button>
        <a-button
          type="primary"
          :disabled="supported !== true || starting !== null || !launchableIds.length"
          :loading="starting === 'all'"
          @click="open(launchableIds, 'all')"
        >
          {{ text('openWithTasks') }}
        </a-button>
      </div>
    </template>
  </SectionCard>
</template>

<style scoped>
.card-alert {
  margin-bottom: 8px;
}

.row-select,
.add-select,
.targets {
  width: 100%;
}

.targets {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.target-list :deep(.ant-list-item) {
  gap: 8px;
}

.target-list :deep(.ant-list-item-action) {
  flex: 0 0 auto;
  margin-inline-start: 0;
}

.target-main {
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  min-width: 0;
}

.target-name {
  display: flex;
  align-items: center;
  max-width: 100%;
  min-width: 0;
}

.target-kind {
  flex: 0 0 auto;
}

.target-label {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.target-issue {
  max-width: 100%;
  margin-inline-end: 0;
  white-space: normal;
}

.footer-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  margin-inline-start: auto;
}
</style>

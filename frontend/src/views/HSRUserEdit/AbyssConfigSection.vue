<!--
  三深渊导入 + 快照展示（内嵌小组件）。
  从 M7A config.yaml 导入三深渊白名单快照，并展示三份快照摘要。
-->
<template>
  <div class="abyss-block">
    <a-row :gutter="24" class="abyss-row">
      <a-col :span="24">
        <a-button
          size="large"
          :disabled="loading || isImporting || !m7aPath"
          :loading="isImporting"
          @click="handleImportClick"
        >
          从 M7A 导入三深渊配置
        </a-button>
        <div v-if="!m7aPath" class="form-item-hint hint-warning">
          请先在脚本配置页配置三月七路径
        </div>
        <div v-else class="form-item-hint">
          从 <code>{{ m7aPath }}\config.yaml</code> 读取三深渊白名单快照，写入当前用户配置。
        </div>
      </a-col>
    </a-row>

    <a-row :gutter="24">
      <a-col v-for="card in snapshotCards" :key="card.key" :xs="24" :md="8">
        <a-card size="small" class="snapshot-card">
          <div class="snapshot-title">{{ card.title }}</div>
          <div class="snapshot-divider" />

          <template v-if="card.summary.success">
            <div class="snapshot-line">
              <span class="snapshot-label">状态</span>
              <a-tag :color="card.summary.enable ? 'green' : 'orange'">
                {{ card.summary.enable ? '已启用' : '已禁用' }}
              </a-tag>
            </div>
            <div class="snapshot-line">
              <span class="snapshot-label">关卡</span>
              <span>{{ card.summary.levelText }}</span>
            </div>
            <div v-for="team in card.summary.teams" :key="team.key" class="snapshot-line">
              <span class="snapshot-label">{{ team.label }}</span>
              <a-tag :color="team.configured ? 'green' : 'default'">
                {{ team.configured ? '已配置' : '未配置' }}
              </a-tag>
            </div>
          </template>

          <div v-else class="snapshot-error">
            {{ card.summary.error }}
          </div>
        </a-card>
      </a-col>
    </a-row>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { message } from 'ant-design-vue'
import type { AbyssSnapshotImportItem, AbyssSnapshotImportOut, HSRConfig_Info } from '@/api'
import { useUserApi } from '@/composables/useUserApi'
import { parseAbyssSnapshots } from '@/views/HSRUserEdit/snapshot'
import type { HSRAbyssKey } from '@/views/HSRUserEdit/snapshot'
import type { HSRUserConfigAbyss } from '@/views/HSRUserEdit/types'

const props = defineProps<{
  formData: { Abyss?: HSRUserConfigAbyss | null }
  loading: boolean
  scriptConfig: { Info?: HSRConfig_Info | null } | null
  scriptId: string
  userId: string
}>()

const emit = defineEmits<{
  imported: [AbyssSnapshotImportOut]
}>()

const { importM7aAbyssSnapshot } = useUserApi()
const isImporting = ref(false)

interface SnapshotSummary {
  success: boolean
  error?: string
  enable?: boolean
  levelText: string
  teams: SnapshotTeam[]
}

interface SnapshotTeam {
  key: string
  label: string
  configured: boolean
}

const m7aPath = computed(() => props.scriptConfig?.Info?.M7APath ?? '')

const handleImportClick = async () => {
  if (!m7aPath.value) {
    message.warning('请先在脚本配置页配置三月七路径')
    return
  }
  if (!props.scriptId || !props.userId) {
    message.warning('用户尚未创建完成，无法导入')
    return
  }
  if (isImporting.value) return
  isImporting.value = true
  try {
    const response = await importM7aAbyssSnapshot(props.scriptId, props.userId)
    if (!response) {
      // useUserApi 内部已 message.error
      return
    }
    // 摘要消息
    const successCount = Array.isArray(response?.items)
      ? response.items.filter((item: AbyssSnapshotImportItem) => item.success).length
      : 0
    message.success(response?.message || `已从 M7A config.yaml 导入 ${successCount}/3 个三深渊快照`)
    emit('imported', response)
  } finally {
    isImporting.value = false
  }
}

const emptyTeams = (): SnapshotTeam[] => [
  {
    key: 'none',
    label: '队伍',
    configured: false,
  },
]

const hasConfiguredValue = (value: unknown): boolean => {
  if (Array.isArray(value)) return value.length > 0
  if (value && typeof value === 'object') return Object.keys(value).length > 0
  return value !== undefined && value !== null && value !== ''
}

const collectTeams = (snapshot: Record<string, unknown>, prefix: string) => {
  const teams = Object.keys(snapshot)
    .map(key => {
      const match = key.match(new RegExp(`^${prefix}_team(\\d+)$`))
      return match
        ? {
            key,
            index: Number(match[1]),
            label: `队伍${match[1]}`,
            configured: hasConfiguredValue(snapshot[key]),
          }
        : null
    })
    .filter((team): team is SnapshotTeam & { index: number } => team !== null)
    .sort((a, b) => a.index - b.index)
  return teams.length ? teams : emptyTeams()
}

const parseSnapshotCollection = (): Partial<Record<HSRAbyssKey, Record<string, unknown>>> => {
  return parseAbyssSnapshots(props.formData.Abyss?.Snapshots)
}

const parseSnapshot = (
  snapshot: Record<string, unknown> | null | undefined,
  prefix: string
): SnapshotSummary => {
  if (!snapshot) {
    return {
      success: false,
      error: '未导入',
      levelText: '-',
      teams: emptyTeams(),
    }
  }

  if (typeof snapshot !== 'object' || Array.isArray(snapshot)) {
    return {
      levelText: '-',
      success: false,
      error: `快照不是 JSON 对象（类型：${Array.isArray(snapshot) ? 'Array' : typeof snapshot}）`,
      teams: emptyTeams(),
    }
  }

  if (Object.keys(snapshot).length === 0) {
    return {
      success: false,
      error: '未导入',
      levelText: '-',
      teams: emptyTeams(),
    }
  }

  const level = snapshot[`${prefix}_level`]
  const levelText = Array.isArray(level) && level.length >= 2 ? `${level[0]} ~ ${level[1]}` : '-'

  return {
    success: true,
    enable: snapshot[`${prefix}_enable`] ?? false,
    levelText,
    teams: collectTeams(snapshot, prefix),
  }
}

const snapshotCards = computed(() => {
  const snapshots = parseSnapshotCollection()
  return [
    {
      key: 'ForgottenHall',
      title: '混沌回忆',
      summary: parseSnapshot(snapshots.ForgottenHall, 'forgottenhall'),
    },
    {
      key: 'PureFiction',
      title: '虚构叙事',
      summary: parseSnapshot(snapshots.PureFiction, 'purefiction'),
    },
    {
      key: 'Apocalyptic',
      title: '末日幻影',
      summary: parseSnapshot(snapshots.Apocalyptic, 'apocalyptic'),
    },
  ]
})
</script>

<style scoped>
.abyss-block {
  margin-top: 4px;
}

.abyss-row {
  margin-bottom: 16px;
}

.hint-warning {
  color: var(--ant-color-warning);
}

.snapshot-card {
  height: 100%;
}

.snapshot-title {
  font-size: 14px;
  font-weight: 600;
}

.snapshot-divider {
  margin: 8px 0;
  border-bottom: 1px solid var(--ant-color-border);
}

.snapshot-line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  font-size: 13px;
}

.snapshot-label {
  min-width: 56px;
  color: var(--ant-color-text-tertiary);
}

.snapshot-error {
  color: var(--ant-color-error);
  font-size: 13px;
}
</style>

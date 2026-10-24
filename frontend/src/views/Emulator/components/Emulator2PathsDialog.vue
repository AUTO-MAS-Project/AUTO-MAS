<script setup lang="ts">
/**
 * 模拟器路径管理弹窗：本配置纳管的各条路径（雷电 / MuMu 安装、魔改 AVD 根目录），可添加、移除；
 * 魔改 AVD 另有「管理与更新」入口，有新版本或版本过旧时在卡片上标出来，点标记也进管理弹窗。
 *
 * 标记只读本地状态和缓存里的查询结果：打开本弹窗时取一次；从卡片进「管理与更新」、更新完关掉
 * 那个弹窗（``managing`` 变回 false）时再取一次，免得卡片还挂着旧标记。
 */
import { h, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { PlusOutlined, SearchOutlined } from '@ant-design/icons-vue'

import type { Emulator2PathItem } from '@/api'
import { useAvdUpdateApi } from '@/composables/useAvdUpdateApi'
import { updateBadge } from '../avdLogic'
import { typeColor, typeLabelOf } from '../emulator2Types'

const open = defineModel<boolean>('open', { required: true })
/** ``managing``：魔改 AVD 的「管理与更新」弹窗是否开在本弹窗上面 */
const props = defineProps<{ paths: Emulator2PathItem[]; managing: boolean }>()
const emit = defineEmits<{
  addAvd: []
  search: []
  manageAvd: [root: string]
  remove: [path: Emulator2PathItem]
}>()

const { t } = useI18n()
const logger = window.electronAPI.getLogger('Emulator2')
const updateApi = useAvdUpdateApi()

const typeLabel = (type: string | undefined) => typeLabelOf(t, type)

/** 魔改 AVD 路径的更新标记，按 pathId 存 */
const badges = ref<Record<string, ReturnType<typeof updateBadge>>>({})

const loadBadges = async () => {
  const result: Record<string, ReturnType<typeof updateBadge>> = {}
  for (const path of props.paths.filter(item => item.type === 'avd')) {
    try {
      result[path.pathId] = updateBadge(await updateApi.getStatus(path.installPath))
    } catch (error) {
      logger.warn(`读取魔改 AVD 更新状态失败 (${path.installPath}): ${String(error)}`)
    }
  }
  badges.value = result
}

watch(open, value => {
  if (value) void loadBadges()
})

// 从卡片进去更新完回来，卡片上的标记跟着刷新
watch(
  () => props.managing,
  managing => {
    if (!managing && open.value) void loadBadges()
  }
)
</script>

<template>
  <a-modal v-model:open="open" :title="t('emulator2.pathsTitle')" width="760px" :footer="null">
    <div class="section-header">
      <span class="section-hint">{{ t('emulator2.pathsHint') }}</span>
      <a-space :size="8">
        <a-button size="small" :icon="h(PlusOutlined)" @click="emit('addAvd')">
          {{ t('emulator2.avd.add') }}
        </a-button>
        <a-button
          size="small"
          type="primary"
          ghost
          :icon="h(SearchOutlined)"
          @click="emit('search')"
        >
          {{ t('emulator2.searchAndAdd') }}
        </a-button>
      </a-space>
    </div>

    <a-empty v-if="!paths.length" :description="t('emulator2.noPath')">
      <a-space :size="8">
        <a-button :icon="h(PlusOutlined)" @click="emit('addAvd')">
          {{ t('emulator2.avd.add') }}
        </a-button>
        <a-button type="primary" :icon="h(SearchOutlined)" @click="emit('search')">
          {{ t('emulator2.searchAndAdd') }}
        </a-button>
      </a-space>
    </a-empty>

    <div v-else class="path-grid">
      <a-card v-for="path in paths" :key="path.pathId" size="small" class="path-card">
        <template #title>
          <a-space :size="6">
            <a-tag :color="typeColor(path.type)">{{ typeLabel(path.type) }}</a-tag>
            <span class="path-alias">{{ path.alias }}</span>
            <span class="path-version">{{ path.version }}</span>
          </a-space>
        </template>
        <template #extra>
          <a-button
            v-if="path.type === 'avd'"
            type="text"
            size="small"
            @click="emit('manageAvd', path.installPath)"
          >
            {{ t('emulator2.avd.manage') }}
          </a-button>
          <a-button type="text" size="small" danger @click="emit('remove', path)">
            {{ t('emulator2.removePath') }}
          </a-button>
        </template>
        <div class="path-line">{{ path.installPath }}</div>
        <div class="path-sub">
          {{
            t('emulator2.slotRange', {
              slots: (path.slots ?? []).map(s => `#${s}`).join(' ') || '—',
            })
          }}
          <a-tag
            v-if="badges[path.pathId]"
            :color="badges[path.pathId]?.kind === 'outdated' ? 'error' : 'processing'"
            class="update-badge"
            @click="emit('manageAvd', path.installPath)"
          >
            {{
              badges[path.pathId]?.kind === 'outdated'
                ? t('emulator2.avd.update.badgeOutdated')
                : t('emulator2.avd.update.badgeAvailable', {
                    version: badges[path.pathId]?.version,
                  })
            }}
          </a-tag>
        </div>
      </a-card>
    </div>
  </a-modal>
</template>

<style scoped>
.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.section-hint {
  margin-left: 8px;
  font-size: 13px;
  font-weight: 400;
  color: var(--ant-color-text-tertiary);
}

.path-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
}

.path-alias {
  font-weight: 600;
}

.path-version,
.path-sub {
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}

.path-line {
  font-size: 13px;
  color: var(--ant-color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.update-badge {
  margin-left: 8px;
  cursor: pointer;
}
</style>

<template>
  <div class="cultivate-main" :aria-busy="loading">
    <div
      v-if="loading"
      class="cultivate-list-loading"
      role="status"
      :aria-label="t('plugins.maa_adapter.edit.maaCultivateCatalogLoading')"
    >
      <a-spin />
    </div>
    <template v-else>
      <a-pagination
        v-if="views.length > pageSize"
        v-model:current="page"
        class="cultivate-pagination"
        size="small"
        :page-size="pageSize"
        :total="views.length"
        :show-size-changer="false"
        :disabled="busy"
      />
      <div v-if="views.length" class="cultivate-rows">
        <CultivateOperatorGroup
          v-for="view in visibleViews"
          :key="view.operatorId"
          :view="view"
          :selected="selected.has(view.operatorId)"
          :collapsed="collapsed.has(view.operatorId)"
          :busy="busy"
          :skland-bound="sklandBound"
          @toggle-selection="(id, checked) => emit('toggle-selection', id, checked)"
          @toggle-collapse="emit('toggle-collapse', $event)"
          @remove="emit('remove', $event)"
          @goal-change="
            (id, kind, targetId, level) => emit('goal-change', id, kind, targetId, level)
          "
        />
        <!-- 已绑定但快照缺专精/模组观测：目标保留、暂停刷取，须明确提示。 -->
        <div v-if="sklandDegraded" class="cultivate-hint">
          {{ t('plugins.maa_adapter.edit.maaCultivateSklandDegradedHint') }}
        </div>
      </div>
      <NoData
        v-else
        :description="
          t(
            filterActive
              ? 'plugins.maa_adapter.edit.maaCultivateSearchEmpty'
              : 'plugins.maa_adapter.edit.maaCultivateEmpty'
          )
        "
        :image-style="{ height: '48px' }"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import CultivateOperatorGroup from './CultivateOperatorGroup.vue'
import type { CultivateOperatorView } from './cultivateGoalLines'
import type { CultivateGoalKind } from './cultivateTargets'

const props = defineProps<{
  views: CultivateOperatorView[]
  pageSize: number
  loading: boolean
  busy: boolean
  selected: ReadonlySet<string>
  collapsed: ReadonlySet<string>
  sklandBound: boolean
  sklandDegraded: boolean
  filterActive: boolean
}>()
const page = defineModel<number>('page', { required: true })
const emit = defineEmits<{
  'toggle-selection': [operatorId: string, checked: boolean]
  'toggle-collapse': [operatorId: string]
  remove: [operatorId: string]
  'goal-change': [operatorId: string, kind: CultivateGoalKind, targetId: string, level: unknown]
}>()
const { t } = useI18n()
const visibleViews = computed(() =>
  props.views.slice((page.value - 1) * props.pageSize, page.value * props.pageSize)
)
</script>

<style scoped>
.cultivate-main {
  flex: 1 1 460px;
  min-width: 0;
}

.cultivate-list-loading {
  display: flex;
  min-height: 240px;
  align-items: center;
  justify-content: center;
}

.cultivate-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cultivate-pagination {
  display: flex;
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.cultivate-hint {
  margin-top: 4px;
  font-size: 12px;
  color: var(--ant-color-text-tertiary);
}
</style>

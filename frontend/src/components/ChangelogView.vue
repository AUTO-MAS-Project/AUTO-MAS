<template>
  <div class="changelog-view">
    <div v-if="sections.length === 0" class="changelog-empty">
      {{ emptyText || t('comp.changelog.empty') }}
    </div>

    <!-- 多个版本：最新版默认展开，更老的版本折叠 -->
    <a-collapse
      v-else-if="sections.length > 1"
      v-model:activeKey="activeVersions"
      :bordered="false"
      class="changelog-collapse"
    >
      <a-collapse-panel v-for="section in sections" :key="section.version">
        <template #header>
          <span class="changelog-version">{{ section.version }}</span>
        </template>
        <ChangelogCategoryList :categories="section.categories" />
      </a-collapse-panel>
    </a-collapse>

    <!-- 只有一个版本：不套折叠层 -->
    <div v-else class="changelog-single">
      <div class="changelog-version changelog-version--single">{{ sections[0].version }}</div>
      <ChangelogCategoryList :categories="sections[0].categories" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ChangelogCategoryList from './ChangelogCategoryList.vue'
import { buildChangelogSections, type ChangelogData } from '@/utils/changelog'

const props = defineProps<{
  /** 版本号 -> 分类 -> 条目 */
  data: ChangelogData | null | undefined
  /** 没有任何内容时显示的文案；不传则用词表默认值 */
  emptyText?: string
}>()

const { t } = useI18n()

const sections = computed(() => buildChangelogSections(props.data))

// 默认只展开最新版；数据换了就重置
const activeVersions = ref<string[]>([])
watch(
  sections,
  value => {
    activeVersions.value = value.length > 0 ? [value[0].version] : []
  },
  { immediate: true }
)
</script>

<style scoped>
.changelog-view {
  line-height: 1.6;
  color: var(--ant-color-text);
  overflow-wrap: anywhere;
  word-break: break-word;
}

.changelog-empty {
  padding: 24px 0;
  text-align: center;
  color: var(--ant-color-text-tertiary);
}

.changelog-version {
  font-size: 15px;
  font-weight: 600;
  color: var(--ant-color-text);
}

.changelog-version--single {
  margin-bottom: 8px;
}

.changelog-collapse {
  background: transparent;
}

.changelog-collapse :deep(.ant-collapse-item) {
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.changelog-collapse :deep(.ant-collapse-header) {
  padding-left: 0 !important;
}

.changelog-collapse :deep(.ant-collapse-content-box) {
  padding: 0 0 12px 0 !important;
}
</style>

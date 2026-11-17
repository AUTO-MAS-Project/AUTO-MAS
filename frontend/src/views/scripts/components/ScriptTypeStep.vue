<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { SearchOutlined } from '@ant-design/icons-vue'
import SelectableOptionCard from '@/components/SelectableOptionCard.vue'
import SelectableOptionList from '@/components/SelectableOptionList.vue'
import NoData from '@/components/NoData.vue'
import ApiRetryAlert from '@/components/ApiRetryAlert.vue'
import type { ScriptType } from '@/types/script'
import {
  SCRIPT_TYPE_OPTIONS,
  filterScriptTypeOptions,
  splitScriptTypeOptions,
} from './scriptCreateFlow'

const props = defineProps<{ types: string[]; loading: boolean; error: string | null }>()
const selectedType = defineModel<ScriptType>({ required: true })
const emit = defineEmits<{ retry: [] }>()
const { t } = useI18n()
const typeKeyword = ref('')
const typeOptions = computed(() =>
  // 仅展示后端已启用的能力；前端元数据只提供卡片的文案、分组和图标。
  SCRIPT_TYPE_OPTIONS.filter(option => props.types.includes(option.value)).map(option => ({
    ...option,
    title: t(option.titleKey),
    description: t(option.descriptionKey),
  }))
)
const filteredTypes = computed(() =>
  filterScriptTypeOptions(typeOptions.value, typeKeyword.value, t)
)
const typeSections = computed(() => splitScriptTypeOptions(filteredTypes.value))
const clearTypeFilters = () => {
  // 清空类型搜索，重新展示全部可创建类型。
  typeKeyword.value = ''
}
</script>

<template>
  <ApiRetryAlert :error="error" :loading="loading" @retry="emit('retry')" />
  <a-spin :spinning="loading">
    <div v-if="!error">
      <div class="list-toolbar single">
        <a-input
          v-model:value="typeKeyword"
          allow-clear
          :placeholder="t('core.scripts.create.typeSearch')"
        >
          <template #prefix><SearchOutlined /></template>
        </a-input>
      </div>
      <SelectableOptionList v-if="filteredTypes.length" v-model="selectedType">
        <section v-if="typeSections.general.length" class="type-section">
          <div class="type-section-heading">
            <span class="type-section-title">{{ t('core.scripts.create.groupGeneral') }}</span>
          </div>
          <div class="type-grid">
            <SelectableOptionCard
              v-for="option in typeSections.general"
              :key="option.value"
              :value="option.value"
              :title="option.title"
              :description="option.description"
              :selected="selectedType === option.value"
              radio-position="end"
            >
              <template #icon>
                <img :src="option.icon" :alt="option.title" class="selectable-option-image" />
              </template>
            </SelectableOptionCard>
          </div>
        </section>
        <section v-if="typeSections.specialized.length" class="type-section specialized-section">
          <div class="type-section-heading">
            <span class="type-section-title">{{ t('core.scripts.create.groupSpecialized') }}</span>
          </div>
          <div class="type-grid">
            <SelectableOptionCard
              v-for="option in typeSections.specialized"
              :key="option.value"
              :value="option.value"
              :title="option.title"
              :description="option.description"
              :selected="selectedType === option.value"
              radio-position="end"
            >
              <template #icon>
                <img :src="option.icon" :alt="option.title" class="selectable-option-image" />
              </template>
            </SelectableOptionCard>
          </div>
        </section>
      </SelectableOptionList>
      <NoData v-else-if="!loading" :description="t('core.scripts.create.noTypeMatch')">
        <a-button @click="clearTypeFilters">{{ t('core.scripts.clearSearch') }}</a-button>
      </NoData>
    </div>
  </a-spin>
</template>

<style scoped>
.list-toolbar {
  margin-bottom: 16px;
}
.type-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.type-sections {
  display: flex;
  width: 100%;
  flex-direction: column;
  gap: 18px;
}

.type-section-heading {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.type-section-title {
  color: var(--ant-color-text);
  font-size: 13px;
  font-weight: 600;
}

.type-section-count,
.type-section-hint {
  color: var(--ant-color-text-tertiary);
  font-size: 11px;
}

.specialized-section {
  padding-top: 14px;
  border-top: 1px solid var(--ant-color-border-secondary);
}

@media (max-width: 760px) {
  .type-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <a-modal
    :open="open"
    :title="title || t('core.taskboard.editGames')"
    :width="'min(1000px, 92vw)'"
    :ok-text="t('core.taskboard.save')"
    :cancel-text="t('core.taskboard.cancel')"
    @ok="onOk"
    @cancel="close"
  >
    <p class="tb-edit-hint">{{ hint || t('core.taskboard.editGamesHint') }}</p>
    <div class="tb-edit-tools">
      <a-input-search
        v-model:value="keyword"
        :placeholder="t('core.taskboard.searchGames')"
        allow-clear
        style="flex: 1"
      />
      <a-button size="small" @click="draft = options.map(option => option.key)">
        {{ t('core.taskboard.selectAll') }}
      </a-button>
      <a-button size="small" @click="draft = []">{{ t('core.taskboard.clear') }}</a-button>
      <span class="tb-edit-count-total">
        {{ t('core.taskboard.selectedCount', { p0: draft.length }) }}
      </span>
    </div>
    <div class="tb-pick-grid">
      <div
        v-for="option in filteredOptions"
        :key="option.key"
        class="tb-pick"
        :class="{ on: draft.includes(option.key) }"
        @click="toggle(option.key)"
      >
        <a-checkbox
          :checked="draft.includes(option.key)"
          class="tb-pick-check"
          @click.stop="toggle(option.key)"
        />
        <div class="tb-pick-thumb">
          <img
            v-if="option.cover"
            :src="option.cover"
            :alt="option.name"
            loading="lazy"
            referrerpolicy="no-referrer"
            @error="hideCover"
          />
        </div>
        <div class="tb-pick-name" :title="option.name">{{ option.name }}</div>
        <div v-if="showCounts !== false" class="tb-pick-cnt">
          {{ t('core.taskboard.activeCount', { p0: option.activeCount ?? 0 }) }}
        </div>
      </div>
      <NoData
        v-if="!filteredOptions.length"
        class="tb-pick-empty"
        :description="t('core.taskboard.empty')"
      />
    </div>
  </a-modal>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { matchesKeyword } from '@/utils/searchMatch'
import type { TaskboardGameOption } from '@/types/taskboard'

interface PickerOption extends TaskboardGameOption {
  activeCount?: number
}

const props = defineProps<{
  title?: string
  hint?: string
  showCounts?: boolean
  open: boolean
  options: PickerOption[]
  selected: string[]
}>()

const emit = defineEmits<{
  'update:open': [value: boolean]
  save: [keys: string[]]
}>()

const { t } = useI18n()
const draft = ref<string[]>([])
const keyword = ref('')

watch(
  () => props.open,
  open => {
    if (!open) return
    draft.value = [...props.selected]
    keyword.value = ''
  },
  { immediate: true }
)

const filteredOptions = computed(() => {
  const kw = keyword.value.trim()
  if (!kw) return props.options
  return props.options.filter(option => matchesKeyword(option.name, kw))
})

const toggle = (key: string) => {
  draft.value = draft.value.includes(key)
    ? draft.value.filter(item => item !== key)
    : [...draft.value, key]
}

const close = () => emit('update:open', false)

// 保存只上报勾选结果，成功与否由页面决定；失败时弹窗保持打开、草稿不丢。
const onOk = () => emit('save', [...draft.value])

const hideCover = (ev: Event) => {
  const img = ev.target as HTMLImageElement
  img.style.display = 'none'
}
</script>

<style scoped>
.tb-edit-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-edit-tools {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}

.tb-edit-count-total {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  white-space: nowrap;
}

.tb-pick-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: 12px;
  padding: 2px;
}

.tb-pick {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 10px 8px 12px;
  border: 2px solid transparent;
  border-radius: 12px;
  cursor: pointer;
  transition: background 0.15s;
  min-width: 0;
}

.tb-pick:hover {
  background: var(--ant-color-fill-quaternary);
}

.tb-pick.on {
  background: var(--ant-color-primary-bg);
  border-color: var(--ant-color-primary-border);
}

.tb-pick-check {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
}

.tb-pick-thumb {
  width: 100%;
  aspect-ratio: 16 / 9;
  border-radius: 8px;
  overflow: hidden;
  background: var(--ant-color-fill-secondary);
}

.tb-pick-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.tb-pick-name {
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 14px;
  color: var(--ant-color-text);
}

.tb-pick-cnt {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
}

.tb-pick-empty {
  grid-column: 1 / -1;
  padding: 24px;
  text-align: center;
  font-size: 14px;
  color: var(--ant-color-text-secondary);
}
</style>

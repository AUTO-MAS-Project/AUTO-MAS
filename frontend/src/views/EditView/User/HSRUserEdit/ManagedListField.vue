<template>
  <div class="list-field">
    <div v-if="rows.length" class="list-rows">
      <div v-for="(row, index) in rows" :key="index" class="list-row">
        <a-input
          v-model:value="row.first"
          :placeholder="isTeams ? t('edit.hsrInstanceName') : t('edit.hsrBorrowCharacter')"
          :disabled="disabled"
          class="list-first"
          @blur="commit"
        />
        <a-input-number
          v-if="isTeams"
          :value="teamNumber(row.second)"
          :min="1"
          :precision="0"
          :placeholder="t('edit.hsrTeamNumber')"
          :disabled="disabled"
          class="list-second-number"
          @change="handleTeamChange(row, $event)"
        />
        <a-input
          v-else
          v-model:value="row.second"
          :placeholder="t('edit.hsrBorrowFriend')"
          :disabled="disabled"
          class="list-second"
          @blur="commit"
        />
        <a-button
          type="text"
          size="small"
          :disabled="disabled"
          :aria-label="t('edit.hsrRemoveRow')"
          @click="removeRow(index)"
        >
          <template #icon>
            <DeleteOutlined />
          </template>
        </a-button>
      </div>
    </div>
    <div v-else class="list-empty">{{ t('edit.hsrListEmpty') }}</div>
    <a-button size="small" type="dashed" :disabled="disabled" class="list-add" @click="addRow">
      <template #icon>
        <PlusOutlined />
      </template>
      {{ t('edit.hsrAddRow') }}
    </a-button>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import { listFieldToRows, rowsToListField, type HSRListRow } from './managedFields'

const { t } = useI18n()

// 三月七 instance_teams（副本名 + 队伍号）与 borrow_friends（角色名 + 好友名）的行编辑器。
// 行数据是本组件自己的状态，文本框用 v-model 绑在行上、失焦才提交，父级重渲染不会冲掉输入。
const props = defineProps<{
  fieldKey: string
  value: unknown
  disabled: boolean
}>()

const emit = defineEmits<{
  change: [value: unknown[]]
}>()

const isTeams = computed(() => props.fieldKey === 'instance_teams')

const rows = ref<HSRListRow[]>(listFieldToRows(props.fieldKey, props.value))

const serialize = (value: readonly HSRListRow[]) =>
  JSON.stringify(rowsToListField(props.fieldKey, value))

// 外部值变了（切换引擎、恢复原值）才重建行；自己刚提交的值与行一致，不会把没填完的空行冲掉
watch(
  () => [props.fieldKey, JSON.stringify(props.value)] as const,
  () => {
    const incoming = listFieldToRows(props.fieldKey, props.value)
    if (serialize(incoming) !== serialize(rows.value)) rows.value = incoming
  }
)

// 只在归一化后的内容真变了时提交（失焦但没改、只加了空行都不保存）
const commit = () => {
  if (serialize(rows.value) === serialize(listFieldToRows(props.fieldKey, props.value))) return
  emit('change', rowsToListField(props.fieldKey, rows.value))
}

const teamNumber = (value: string) => {
  const parsed = Number(value)
  return value !== '' && Number.isFinite(parsed) ? parsed : undefined
}

const handleTeamChange = (row: HSRListRow, value: unknown) => {
  row.second = value === null || value === undefined || value === '' ? '' : String(value)
  commit()
}

const addRow = () => {
  rows.value.push({ first: '', second: isTeams.value ? '1' : '' })
}

const removeRow = (index: number) => {
  rows.value.splice(index, 1)
  commit()
}
</script>

<style scoped>
.list-field {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.list-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.list-first,
.list-second {
  flex: 1;
  min-width: 0;
}

.list-second-number {
  width: 120px;
}

.list-empty {
  color: var(--ant-color-text-tertiary);
  font-size: 13px;
}

.list-add {
  align-self: flex-start;
}
</style>

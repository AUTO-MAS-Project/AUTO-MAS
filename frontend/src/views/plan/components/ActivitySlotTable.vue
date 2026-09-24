<template>
  <a-table
    class="activity-slot-table"
    :columns="columns"
    :data-source="rows"
    :pagination="false"
    row-key="key"
    size="small"
    :row-class-name="rowClassName"
  >
    <template #bodyCell="{ column, record }">
      <span v-if="column.key === 'slot'" class="slot-name">{{ record.label }}</span>

      <template v-else-if="column.key === 'stage'">
        <template v-if="record.stageCode">
          <span class="stage-code">{{ record.stageCode }}</span>
          <span class="stage-mat">{{ record.stageMat }}</span>
          <span v-if="record.notStarted" class="tag-future">
            {{ t('plan.activity.notStarted') }}
          </span>
        </template>
        <span v-else class="stage-none">
          {{ record.skeleton ? t('plan.activity.pendingEntry') : t('plan.activity.noStage') }}
        </span>
      </template>

      <div v-else-if="column.key === 'users'" class="chips">
        <span
          v-for="item in record.users"
          :key="item.userId"
          class="chip"
          :class="item.variant"
          :title="item.title"
        >
          <span class="ava">{{ item.userName.slice(0, 1) }}</span>
          <span class="nm">{{ item.userName }}</span>
          <span class="srv">{{ item.serverName }}</span>
          <button
            class="x"
            type="button"
            :disabled="saving"
            :title="t('plan.activity.remove')"
            @click="emit('remove', item.user)"
          >✕</button>
        </span>

        <a-popover
          :open="openSlotKey === record.key"
          trigger="click"
          placement="bottomLeft"
          @open-change="
            (open: boolean) => {
              if (open) openSlotKey = record.key
              else if (openSlotKey === record.key) openSlotKey = ''
            }
          "
        >
          <template #content>
            <div class="pk-head" v-if="record.candidates.unassigned.length">
              {{ t('plan.activity.candidateUnassigned') }}
            </div>
            <button
              v-for="cand in record.candidates.unassigned"
              :key="cand.userId"
              class="pk"
              type="button"
              :disabled="saving"
              @click="onPick(cand, record)"
            >
              <span>{{ cand.userName }} · {{ cand.serverName }}</span>
              <span class="frm">{{ t('plan.activity.joinSlot') }}</span>
            </button>
            <div class="pk-head" v-if="record.candidates.fromOtherSlots.length">
              {{ t('plan.activity.candidateOtherSlots') }}
            </div>
            <button
              v-for="cand in record.candidates.fromOtherSlots"
              :key="cand.userId"
              class="pk"
              type="button"
              :disabled="saving"
              @click="onPick(cand, record)"
            >
              <span>{{ cand.userName }} · {{ cand.serverName }}</span>
              <span class="frm move">
                {{ t('plan.activity.currentSlot', { slot: cand.fromLabel }) }}
              </span>
            </button>
            <div
              class="pk-head"
              v-if="
                !record.candidates.unassigned.length &&
                !record.candidates.fromOtherSlots.length
              "
            >
              {{ t('plan.activity.noCandidates') }}
            </div>
          </template>
          <button class="add-btn" type="button" :disabled="saving">
            ＋ {{ t('plan.activity.addUser') }}
          </button>
        </a-popover>
      </div>

      <span v-else-if="column.key === 'status'" class="st" :class="record.statusClass">
        <span class="d"></span>{{ record.statusText }}
      </span>
    </template>
  </a-table>
</template>

<script setup lang="ts">
// 活动关槽位表：只负责渲染视图模型（文案与状态由 useActivityStageAssignment 算好），
// 用户选择通过 assign / remove 事件回传，自身不碰数据与接口。
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ActivityUserRow } from './activityStageSlots'
import type { SlotCandidate, SlotViewRow } from './useActivityStageAssignment'

defineProps<{
  /** 槽位行渲染模型（含本槽用户与候选） */
  rows: SlotViewRow[]
  saving: boolean
}>()

const emit = defineEmits<{
  (e: 'assign', user: ActivityUserRow, row: SlotViewRow): void
  (e: 'remove', user: ActivityUserRow): void
}>()

const { t } = useI18n()

/** 当前展开「添加用户」弹层的槽位键（同时只开一个） */
const openSlotKey = ref('')

// 列定义：标题走词表，宽度对齐原表格的固定列（a-table 自己管表头与行样式）
const columns = computed(() => [
  { title: t('plan.activity.colSlot'), key: 'slot', width: 130 },
  { title: t('plan.activity.colStage'), key: 'stage', width: 230 },
  { title: t('plan.activity.colUsers'), key: 'users' },
  { title: t('plan.activity.colStatus'), key: 'status', width: 240 },
])

const rowClassName = (row: SlotViewRow): string => row.rowClass

const onPick = (cand: SlotCandidate, row: SlotViewRow) => {
  openSlotKey.value = ''
  emit('assign', cand.user, row)
}
</script>

<style scoped>
/* 行级置灰（a-table 行类名，靠 :deep 穿透其内部 td）：待开启期 / 本期无此关 */
.activity-slot-table :deep(.slots-row-gap > td) {
  opacity: 0.65;
}

.activity-slot-table :deep(.slots-row-missing > td) {
  opacity: 0.55;
}

.slot-name {
  font-weight: 600;
  white-space: nowrap;
}

.stage-code {
  font-weight: 600;
}

.stage-mat {
  font-size: 12px;
  color: var(--ant-color-text-secondary);
  margin-left: 8px;
}

.stage-none {
  color: var(--ant-color-text-tertiary);
}

.tag-future {
  display: inline-block;
  font-size: 11px;
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
  border-radius: 3px;
  padding: 0 6px;
  margin-left: 6px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  border: 1px solid var(--ant-color-border);
  border-radius: 16px;
  padding: 3px 6px 3px 4px;
  font-size: 13px;
  background: var(--ant-color-bg-container);
}

.chip .ava {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--ant-color-primary-bg);
  color: var(--ant-color-primary);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 600;
}

.chip .nm {
  white-space: nowrap;
}

.chip .srv {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.chip .x {
  border: none;
  background: none;
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  line-height: 1;
  padding: 2px 4px;
  border-radius: 50%;
  cursor: pointer;
}

.chip .x:hover:not(:disabled) {
  color: var(--ant-color-error);
  background: var(--ant-color-error-bg);
}

.chip.off {
  border-style: dashed;
  color: var(--ant-color-text-tertiary);
}

.chip.dim {
  opacity: 0.6;
}

.add-btn {
  border: 1px dashed var(--ant-color-border);
  background: none;
  color: var(--ant-color-text-tertiary);
  border-radius: 16px;
  padding: 3px 12px;
  font-size: 13px;
  cursor: pointer;
}

.add-btn:hover:not(:disabled) {
  color: var(--ant-color-primary);
  border-color: var(--ant-color-primary);
}

.pk-head {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
  padding: 6px 10px 2px;
}

.pk {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  width: 100%;
  border: none;
  background: none;
  color: var(--ant-color-text);
  text-align: left;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}

.pk:hover {
  background: var(--ant-color-fill-quaternary);
}

.pk .frm {
  font-size: 11px;
  color: var(--ant-color-text-tertiary);
}

.pk .frm.move {
  color: var(--ant-color-warning);
}

.st {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  white-space: normal;
}

.st .d {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.st.ok {
  color: var(--ant-color-text-secondary);
}

.st.ok .d {
  background: var(--ant-color-success);
}

.st.warn {
  color: var(--ant-color-warning);
}

.st.warn .d {
  background: var(--ant-color-warning);
}

.st.muted {
  color: var(--ant-color-text-tertiary);
}

.st.muted .d {
  background: var(--ant-color-text-quaternary);
}

.st.idle {
  color: var(--ant-color-text-quaternary);
}

.st.idle .d {
  background: none;
  border: 1px solid var(--ant-color-border);
}
</style>

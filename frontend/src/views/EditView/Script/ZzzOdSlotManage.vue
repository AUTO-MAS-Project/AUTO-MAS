<template>
  <div class="slot-manage-section">
    <!-- 实例槽管理：脚本级诊断（槽目录按安装目录归池、跨脚本共享），默认折叠 -->
    <a-collapse v-model:activeKey="panelKeys" ghost class="slot-manage" @change="handlePanelChange">
      <a-collapse-panel key="slots">
        <template #header>
          <h3 class="slot-manage-title">
            {{ t('edit.zzzodSlotsManage') }}
            <a-tooltip :title="t('edit.zzzodSlotsManageHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </h3>
        </template>
        <div class="slot-manage-actions">
          <a-space :size="8">
            <a-button size="small" :loading="slotsLoading" @click="loadSlotView">
              <template #icon><ReloadOutlined /></template>
              {{ t('edit.zzzodSlotsRefresh') }}
            </a-button>
            <a-button
              size="small"
              danger
              :loading="slotsLoading"
              :disabled="slotActionBusy"
              @click="confirmCleanOrphanSlots"
            >
              <template #icon><ClearOutlined /></template>
              {{ t('edit.zzzodSlotsClean') }}
            </a-button>
          </a-space>
        </div>
        <a-tabs v-model:activeKey="slotTab" size="small">
          <a-tab-pane key="slots" :tab="t('edit.zzzodSlotTabSlots')">
            <a-table
              size="small"
              row-key="idx"
              :columns="slotColumns"
              :data-source="slots"
              :loading="slotsLoading"
              :pagination="false"
              :locale="{ emptyText: t('edit.zzzodSlotEmpty') }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'idx'">
                  {{ String(record.idx).padStart(2, '0') }}
                </template>
                <template v-else-if="column.key === 'kind'">
                  <a-tag :color="slotKindColor(record.kind)">
                    {{ slotKindLabel(record.kind) }}
                  </a-tag>
                  <a-tooltip
                    v-if="slotNativeConflict(record)"
                    :title="t('edit.zzzodSlotNativeConflictHint')"
                  >
                    <a-tag color="warning" class="slot-conflict-tag">
                      {{ t('edit.zzzodSlotNativeConflict') }}
                    </a-tag>
                  </a-tooltip>
                </template>
                <template v-else-if="column.key === 'owner'">
                  {{ slotOwnerText(record) }}
                </template>
                <template v-else-if="column.key === 'dir'">
                  {{ record.has_dir ? t('edit.zzzodSlotHasDir') : t('edit.zzzodSlotNoDir') }}
                </template>
                <template v-else-if="column.key === 'size'">
                  {{ formatSlotSize(record.size) }}
                </template>
              </template>
            </a-table>
          </a-tab-pane>
          <a-tab-pane key="recycle" :tab="recycleTabLabel">
            <div class="slot-manage-hint-row">
              <a-typography-text type="secondary" class="slot-manage-hint">
                {{ t('edit.zzzodRecycleHint') }}
              </a-typography-text>
              <a-button
                size="small"
                danger
                :loading="recycleLoading"
                :disabled="!recycleRows.length || slotActionBusy"
                @click="confirmClearRecycle"
              >
                <template #icon><ClearOutlined /></template>
                {{ t('edit.zzzodRecycleClear') }}
              </a-button>
            </div>
            <a-table
              size="small"
              row-key="key"
              :columns="recycleColumns"
              :data-source="recycleRows"
              :loading="recycleLoading"
              :pagination="false"
              :locale="{ emptyText: t('edit.zzzodRecycleEmpty') }"
            >
              <template #bodyCell="{ column, record }">
                <template v-if="column.key === 'slot'">
                  {{ String(record.slot).padStart(2, '0') }}
                </template>
                <template v-else-if="column.key === 'kind'">
                  {{ recycleKindLabel(record.kind) }}
                </template>
                <template v-else-if="column.key === 'ts'">
                  {{ formatArchiveTs(record.ts) }}
                </template>
                <template v-else-if="column.key === 'files'">
                  {{ record.files }}
                </template>
                <template v-else-if="column.key === 'size'">
                  {{ formatSlotSize(record.size) }}
                </template>
                <template v-else-if="column.key === 'ops'">
                  <a-space :size="4">
                    <a-button size="small" type="link" @click="openRecycleFolder(record)">
                      {{ t('edit.zzzodRecycleOpen') }}
                    </a-button>
                    <a-button
                      v-if="record.kind === 'slot'"
                      size="small"
                      type="link"
                      :disabled="slotActionBusy"
                      @click="confirmRestoreRecycle(record)"
                    >
                      {{ t('edit.zzzodRecycleRestore') }}
                    </a-button>
                  </a-space>
                </template>
              </template>
            </a-table>
          </a-tab-pane>
        </a-tabs>
      </a-collapse-panel>
    </a-collapse>

    <!-- 恢复落到某个用户的绑定槽：只物化到裸槽号的恢复没有出口，MAS 不会认领它 -->
    <a-modal
      v-model:open="restoreTarget.open"
      :title="t('edit.zzzodRecycleRestore')"
      :confirm-loading="restoring"
      :ok-text="t('edit.zzzodRecycleRestore')"
      @ok="submitRestore"
    >
      <a-typography-paragraph type="secondary">
        {{
          t('edit.zzzodRecycleRestoreTargetHint', {
            slot: String(restoreTarget.entry?.slot ?? 0).padStart(2, '0'),
            ts: restoreTarget.entry ? formatArchiveTs(restoreTarget.entry.ts) : '',
          })
        }}
      </a-typography-paragraph>
      <a-radio-group v-model:value="restoreTarget.mode" class="restore-mode">
        <a-radio value="existing">{{ t('edit.zzzodRecycleRestoreToUser') }}</a-radio>
        <a-radio value="new">{{ t('edit.zzzodRecycleRestoreToNewUser') }}</a-radio>
      </a-radio-group>
      <a-select
        v-if="restoreTarget.mode === 'existing'"
        v-model:value="restoreTarget.userId"
        class="restore-mode-target"
        show-search
        option-filter-prop="label"
        :loading="usersLoading"
        :options="userOptions"
        :placeholder="t('edit.zzzodRecycleRestoreUserPlaceholder')"
      />
      <a-input
        v-else
        v-model:value="restoreTarget.newUserName"
        class="restore-mode-target"
        :maxlength="32"
        :placeholder="t('edit.zzzodRecycleRestoreNewUserName')"
      />
      <a-typography-text v-if="restoreTargetSlot" type="warning" class="restore-target-hint">
        {{
          t('edit.zzzodRecycleRestoreOverwriteHint', {
            slot: String(restoreTargetSlot).padStart(2, '0'),
          })
        }}
      </a-typography-text>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { ClearOutlined, QuestionCircleOutlined, ReloadOutlined } from '@ant-design/icons-vue'
import { useZzzOdSlotManage } from '@/composables/useZzzOdSlotManage'

const props = defineProps<{
  scriptId: string
}>()

const { t } = useI18n()
const {
  panelKeys,
  slotTab,
  slots,
  slotsLoading,
  recycleRows,
  recycleLoading,
  slotActionBusy,
  slotColumns,
  recycleColumns,
  recycleTabLabel,
  slotKindLabel,
  slotKindColor,
  slotNativeConflict,
  slotOwnerText,
  recycleKindLabel,
  formatSlotSize,
  formatArchiveTs,
  loadSlotView,
  handlePanelChange,
  confirmCleanOrphanSlots,
  openRecycleFolder,
  confirmClearRecycle,
  restoring,
  restoreTarget,
  restoreTargetSlot,
  userOptions,
  usersLoading,
  submitRestore,
  confirmRestoreRecycle,
} = useZzzOdSlotManage(() => props.scriptId)
</script>

<style scoped>
/* 与页面其它 section 同节奏 */
.slot-manage-section {
  margin-bottom: 12px;
}

.help-icon {
  color: var(--ant-color-text-tertiary);
  cursor: help;
}

/* 实例槽管理：折叠面板标题与其它 section 标题同节奏，展开区不套卡片 */
.slot-manage :deep(.ant-collapse-header) {
  padding: 0 0 8px;
  align-items: center;
  border-bottom: 1px solid var(--ant-color-border-secondary);
}

.slot-manage :deep(.ant-collapse-content-box) {
  padding: 12px 0 0;
}

.slot-manage-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.slot-manage-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 8px;
}

.slot-manage-hint {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
}

.slot-manage-hint-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.slot-manage-hint-row .slot-manage-hint {
  margin-bottom: 0;
  flex: 1;
  min-width: 0;
}

.restore-mode {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.slot-conflict-tag {
  margin-left: 4px;
}

.restore-mode-target {
  width: 100%;
  margin-top: 8px;
}

.restore-target-hint {
  display: block;
  margin-top: 8px;
  font-size: 12px;
}
</style>

<script setup lang="ts">
import { computed, ref, h } from 'vue'
import { useI18n } from 'vue-i18n'
import { message, Modal } from 'ant-design-vue'
import {
  PlusOutlined,
  EditOutlined,
  DeleteOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons-vue'
import { Service, type ZzzOdInstanceOut } from '@/api'
const props = defineProps<{
  scriptId: string
  locked: boolean
  selected: number | null
  select: (idx: number) => Promise<void>
  deleted: (idx: number) => void
  instances: ZzzOdInstanceOut[]
  updateInstances: (instances: ZzzOdInstanceOut[]) => void
  trackWrite: <T>(operation: () => Promise<T>) => Promise<T>
}>()
const { scriptId } = props
const configLocked = computed(() => props.locked)
const nativeInstanceIdx = computed(() => props.selected)
// 在途写入可晚于管理区块卸载；由页面级快照所有者接收结果。
const instances = computed({ get: () => props.instances, set: props.updateInstances })
const { t } = useI18n()
// ══ 实例管理（原生来源：添加 / 重命名 / 删除 / 参与「全部实例」开关，实时写回 one_dragon.yml）══
const instanceName = ref('')

const addInstanceOpen = ref(false)

const renameInstanceOpen = ref(false)

const renameTarget = ref<ZzzOdInstanceOut | null>(null)

const instanceOpLoading = ref(false)

const openAddInstance = () => {
  instanceName.value = ''
  addInstanceOpen.value = true
}

const confirmAddInstance = async () => {
  if (configLocked.value) return
  const name = instanceName.value.trim()
  if (!name) {
    message.error(t('edit.zzzodInstanceNameRequired'))
    return
  }
  instanceOpLoading.value = true
  try {
    const resp = await props.trackWrite(() =>
      Service.addZzzodInstanceApiApiScriptsZzzodInstancesAddPost({
        scriptId,
        name,
      })
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodAddInstanceFailed'))
    }
    const updated = resp.data || []
    instances.value = updated
    addInstanceOpen.value = false
    // 选中新实例并加载其原生配置（账号/任务区跟随切换）
    const added = [...updated].reverse().find(item => item.name === name)
    if (added) {
      await props.select(added.idx)
    }
    message.success(t('edit.zzzodAddInstanceSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodAddInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

const openRenameInstance = (inst: ZzzOdInstanceOut) => {
  renameTarget.value = inst
  instanceName.value = inst.name
  renameInstanceOpen.value = true
}

const confirmRenameInstance = async () => {
  if (configLocked.value) return
  const target = renameTarget.value
  const name = instanceName.value.trim()
  if (!target || !name) {
    message.error(t('edit.zzzodInstanceNameRequired'))
    return
  }
  instanceOpLoading.value = true
  try {
    const resp = await props.trackWrite(() =>
      Service.renameZzzodInstanceApiApiScriptsZzzodInstancesRenamePost({
        scriptId,
        instanceIdx: target.idx,
        name,
      })
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodRenameInstanceFailed'))
    }
    instances.value = resp.data || []
    renameInstanceOpen.value = false
    renameTarget.value = null
    message.success(t('edit.zzzodRenameInstanceSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodRenameInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

const openDeleteInstance = (inst: ZzzOdInstanceOut) => {
  Modal.confirm({
    title: t('edit.zzzodDeleteInstance'),
    content: h(
      'p',
      { style: { color: 'var(--ant-color-error)', margin: 0 } },
      t('edit.zzzodDeleteInstanceConfirm', {
        inst: `${String(inst.idx).padStart(2, '0')} - ${inst.name}`,
      })
    ),
    okText: t('edit.zzzodDeleteInstance'),
    okButtonProps: { danger: true },
    onOk: () => deleteInstance(inst),
  })
}

const deleteInstance = async (inst: ZzzOdInstanceOut) => {
  if (configLocked.value) return
  instanceOpLoading.value = true
  try {
    const resp = await props.trackWrite(() =>
      Service.deleteZzzodInstanceApiApiScriptsZzzodInstancesDeletePost({
        scriptId,
        instanceIdx: inst.idx,
      })
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodDeleteInstanceFailed'))
    }
    instances.value = resp.data || []
    props.deleted(inst.idx)
    message.success(t('edit.zzzodDeleteInstanceSuccess'))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodDeleteInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}

const toggleInstanceActiveInOd = async (inst: ZzzOdInstanceOut, value: boolean) => {
  if (configLocked.value) return
  try {
    const resp = await props.trackWrite(() =>
      Service.setZzzodInstanceActiveInOdApiApiScriptsZzzodInstancesActiveInOdPost({
        scriptId,
        instanceIdx: inst.idx,
        activeInOd: value,
      })
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodInstanceFlagFailed'))
    }
    instances.value = resp.data || []
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodInstanceFlagFailed'))
  }
}

/** 切换实例「运行前切换账号」：一条龙原生能力（force_login_before_run），MAS 不干涉 */
const toggleInstanceForceLogin = async (inst: ZzzOdInstanceOut, value: boolean) => {
  if (configLocked.value) return
  try {
    const resp = await props.trackWrite(() =>
      Service.setZzzodInstanceForceLoginApiApiScriptsZzzodInstancesForceLoginPost({
        scriptId,
        instanceIdx: inst.idx,
        forceLogin: value,
      })
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodInstanceForceLoginFailed'))
    }
    instances.value = resp.data || []
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodInstanceForceLoginFailed'))
  }
}

/** 显式设为当前活跃：「仅运行当前」运行时跑的就是它；原生来源页编辑不自动改活跃 */
const setActiveInstance = async (inst: ZzzOdInstanceOut) => {
  if (configLocked.value) return
  instanceOpLoading.value = true
  try {
    const resp = await props.trackWrite(() =>
      Service.setZzzodActiveInstanceApiApiScriptsZzzodInstancesSetActivePost({
        scriptId,
        instanceIdx: inst.idx,
      })
    )
    if (resp.code !== 200) {
      throw new Error(resp.message || t('edit.zzzodSetActiveInstanceFailed'))
    }
    instances.value = resp.data || []
    message.success(t('edit.zzzodSetInstanceActiveSuccess', { name: inst.name }))
  } catch (e) {
    message.error(e instanceof Error ? e.message : t('edit.zzzodSetActiveInstanceFailed'))
  } finally {
    instanceOpLoading.value = false
  }
}
</script>
<template>
  <div class="instance-manage">
    <div class="instance-manage-header">
      <span class="form-label">
        {{ t('edit.zzzodInstancesManage') }}
        <a-tooltip :title="t('edit.zzzodInstancesManageHint')">
          <QuestionCircleOutlined class="help-icon" />
        </a-tooltip>
      </span>
      <a-button type="primary" size="small" :loading="instanceOpLoading" @click="openAddInstance">
        <template #icon><PlusOutlined /></template>
        {{ t('edit.zzzodAddInstance') }}
      </a-button>
    </div>
    <div v-if="instances.length" class="instance-manage-list">
      <div
        v-for="inst in instances"
        :key="inst.idx"
        class="instance-manage-row"
        :class="{ selected: inst.idx === nativeInstanceIdx }"
      >
        <div class="instance-manage-info">
          <span
            class="instance-manage-name"
            :title="`${String(inst.idx).padStart(2, '0')} - ${inst.name}`"
          >
            {{ String(inst.idx).padStart(2, '0') }} - {{ inst.name }}
          </span>
          <a-tooltip v-if="inst.active" :title="t('edit.zzzodInstanceActiveTagHint')">
            <a-tag color="processing" class="instance-manage-tag">
              {{ t('edit.zzzodInstanceActiveTag') }}
            </a-tag>
          </a-tooltip>
          <a-tooltip v-else :title="t('edit.zzzodSetInstanceActive')">
            <a-tag
              class="instance-manage-tag instance-manage-tag-set"
              @click="setActiveInstance(inst)"
            >
              {{ t('edit.zzzodInstanceSetActiveTag') }}
            </a-tag>
          </a-tooltip>
        </div>
        <div class="instance-manage-ops">
          <span class="instance-manage-switch-label">
            {{ t('edit.zzzodInstanceRunAllSwitch') }}
          </span>
          <a-tooltip :title="t('edit.zzzodInstanceActiveInOd')">
            <a-switch
              size="small"
              :checked="inst.active_in_od"
              @change="(checked: boolean) => toggleInstanceActiveInOd(inst, checked)"
            />
          </a-tooltip>
          <span class="instance-manage-switch-label">
            {{ t('edit.zzzodInstanceForceLoginSwitch') }}
          </span>
          <a-tooltip :title="t('edit.zzzodInstanceForceLoginHint')">
            <a-switch
              size="small"
              :checked="inst.force_login_before_run"
              @change="(checked: boolean) => toggleInstanceForceLogin(inst, checked)"
            />
          </a-tooltip>
          <a-divider type="vertical" class="instance-manage-divider" />
          <a-tooltip :title="t('edit.zzzodRenameInstance')">
            <a-button
              size="small"
              type="text"
              :aria-label="t('edit.zzzodRenameInstance')"
              @click="openRenameInstance(inst)"
            >
              <template #icon><EditOutlined /></template>
            </a-button>
          </a-tooltip>
          <a-tooltip :title="t('edit.zzzodDeleteInstance')">
            <a-button
              size="small"
              type="text"
              danger
              :aria-label="t('edit.zzzodDeleteInstance')"
              @click="openDeleteInstance(inst)"
            >
              <template #icon><DeleteOutlined /></template>
            </a-button>
          </a-tooltip>
        </div>
      </div>
    </div>
  </div>
  <a-modal
    v-model:open="addInstanceOpen"
    :title="t('edit.zzzodAddInstance')"
    :ok-text="t('edit.zzzodAddInstance')"
    :cancel-text="t('edit.cancel')"
    :confirm-loading="instanceOpLoading"
    @ok="confirmAddInstance"
  >
    <a-form layout="vertical" class="config-form">
      <a-form-item>
        <template #label>
          <span class="form-label">
            {{ t('edit.zzzodInstanceName') }}
            <a-tooltip :title="t('edit.zzzodInstanceNameHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-input
          v-model:value="instanceName"
          :placeholder="t('edit.zzzodInstanceNamePlaceholder')"
          size="large"
          class="modern-input"
          @press-enter="confirmAddInstance"
        />
      </a-form-item>
    </a-form>
  </a-modal>
  <a-modal
    v-model:open="renameInstanceOpen"
    :title="t('edit.zzzodRenameInstance')"
    :ok-text="t('edit.zzzodRenameInstance')"
    :cancel-text="t('edit.cancel')"
    :confirm-loading="instanceOpLoading"
    @ok="confirmRenameInstance"
  >
    <a-form layout="vertical" class="config-form">
      <a-form-item>
        <template #label>
          <span class="form-label">
            {{ t('edit.zzzodInstanceName') }}
            <a-tooltip :title="t('edit.zzzodInstanceNameHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-input
          v-model:value="instanceName"
          :placeholder="t('edit.zzzodInstanceNamePlaceholder')"
          size="large"
          class="modern-input"
          @press-enter="confirmRenameInstance"
        />
      </a-form-item>
    </a-form>
  </a-modal>
</template>
<style scoped>
@import './zzzodFormControls.css';
.instance-manage {
  margin-bottom: 16px;
}

.instance-manage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.instance-manage-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.instance-manage-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  border: 1px solid var(--ant-color-border-secondary);
  border-radius: 8px;
  background: var(--ant-color-fill-quaternary);
  transition:
    border-color 0.2s,
    background 0.2s;
}

.instance-manage-row:hover {
  background: var(--ant-color-fill-tertiary);
}

.instance-manage-row.selected {
  border-color: var(--ant-color-primary);
}

.instance-manage-info {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.instance-manage-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 600;
  font-size: 14px;
}

.instance-manage-tag {
  flex-shrink: 0;
  margin-inline-end: 0;
}

.instance-manage-tag-set {
  cursor: pointer;
  color: var(--ant-color-text-tertiary);
  background: var(--ant-color-fill-tertiary);
  border-color: transparent;
  transition:
    color 0.2s,
    background 0.2s;
}

.instance-manage-tag-set:hover {
  color: var(--ant-color-primary);
  background: var(--ant-color-primary-bg);
}

.instance-manage-ops {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}

.instance-manage-switch-label {
  color: var(--ant-color-text-tertiary);
  font-size: 12px;
  white-space: nowrap;
  margin-right: 4px;
}

.instance-manage-divider {
  margin: 0 4px;
  border-color: var(--ant-color-border-secondary);
}
</style>

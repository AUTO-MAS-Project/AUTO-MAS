<script setup lang="ts">
import PathPickerField from '@/components/PathPickerField.vue'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { QuestionCircleOutlined } from '@ant-design/icons-vue'
import type { ZzzOdNativeAccountField } from '@/api'
import { pickZzzGameExe } from './pickZzzGameExe'
const props = defineProps<{
  fields: ZzzOdNativeAccountField[]
  values: Record<string, string>
  loading: boolean
  saving: boolean
  selected: number | null
  save: () => Promise<boolean>
}>()
const { t } = useI18n()
const nativeAccountFields = computed(() => props.fields)
const nativeAccountValues = props.values
const nativeLoading = computed(() => props.loading)
const nativeSaving = computed(() => props.saving)
const nativeInstanceIdx = computed(() => props.selected)
const saveNativeAccount = () => props.save()
/** 运行前切换账号/多账号切换需要完整登录信息；B服实例用 B服账号名，其余用账号+密码 */
const isRequiredAccountKey = (key: string) => {
  if (nativeAccountValues.game_region === 'cn_b') {
    return key === 'bilibili_account_name'
  }
  return key === 'account' || key === 'password'
}
const selectDirectGamePath = async () => {
  const path = await pickZzzGameExe()
  if (path) nativeAccountValues.game_path = path
}
</script>
<template>
  <a-spin :spinning="nativeLoading">
    <template v-if="nativeInstanceIdx !== null">
      <a-row :gutter="24">
        <a-col v-for="f in nativeAccountFields" :key="f.key" :span="12">
          <a-form-item>
            <template #label>
              <span class="form-label">
                <span v-if="isRequiredAccountKey(f.key)" class="required-mark" aria-hidden="true"
                  >*</span
                >
                {{ f.title }}
                <a-tooltip
                  v-if="isRequiredAccountKey(f.key)"
                  :title="t('core.edit.zzzodAccountRequiredTip')"
                >
                  <QuestionCircleOutlined class="help-icon" />
                </a-tooltip>
              </span>
            </template>
            <PathPickerField
              v-if="f.key === 'game_path'"
              v-model="nativeAccountValues[f.key]"
              mode="file"
              :placeholder="t('core.edit.zzzodGamePathPlaceholder')"
              :pick-label="t('core.edit.pickFile')"
              @pick="selectDirectGamePath"
            />
            <a-input-password
              v-else-if="f.key === 'password'"
              v-model:value="nativeAccountValues[f.key]"
              :placeholder="t('core.edit.zzzodDirectPasswordPlaceholder')"
              size="large"
              class="modern-input"
            />
            <a-select
              v-else-if="(f.options?.length ?? 0) > 0"
              v-model:value="nativeAccountValues[f.key]"
              :options="f.options"
              size="large"
              class="modern-select"
            />
            <a-input
              v-else
              v-model:value="nativeAccountValues[f.key]"
              size="large"
              class="modern-input"
            />
          </a-form-item>
        </a-col>
      </a-row>
      <div class="native-save-row">
        <a-button type="primary" size="large" :loading="nativeSaving" @click="saveNativeAccount">
          {{ t('core.edit.saveSettings') }}
        </a-button>
      </div>
    </template>
    <NoData v-else :description="t('core.edit.zzzodDirectPickInstanceFirst')" />
  </a-spin>
</template>
<style scoped>
@import './zzzodFormControls.css';
.native-save-row {
  display: flex;
  justify-content: flex-start;
  margin-top: 4px;
  margin-bottom: 24px;
}
</style>

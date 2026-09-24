<script setup lang="ts">
/**
 * 原神客户端更新相关字段。通用脚本只要开关与时限（安装目录由「游戏路径」推导），
 * BetterGI 额外要选「原神游戏程序」。区服与语音都不让用户填：前者按程序文件名判定，
 * 后者跟随客户端自己的清单。
 */
import { useI18n } from 'vue-i18n'
import { message } from 'ant-design-vue'
import { FileOutlined, QuestionCircleOutlined } from '@ant-design/icons-vue'

import { isGenshinClientExe } from '@/types/script'

/** 更新字段所在 Game 段的最小形状：通用脚本没有 UpdateExe。 */
interface GenshinUpdateFields {
  IfAutoUpdate: boolean
  UpdateExe?: string
  UpdateTimeLimit?: number
}

const props = defineProps<{
  /** 配置里的 Game 段，按引用读写 */
  model: GenshinUpdateFields
  /** 所在分区整体禁用（如任务运行中锁配置） */
  disabled?: boolean
  /** 是否显示「原神游戏程序」行（BetterGI 需要；通用脚本用已有的游戏路径） */
  withExe?: boolean
}>()

const emit = defineEmits<{
  (event: 'field-change', key: keyof GenshinUpdateFields, value: unknown): void
}>()

const { t } = useI18n()

const change = <K extends keyof GenshinUpdateFields>(key: K, value: GenshinUpdateFields[K]) => {
  emit('field-change', key, value)
}

const pickExe = async () => {
  if (!window.electronAPI) {
    message.error(t('edit.filePickingUnavailableRun'))
    return
  }
  try {
    const paths = await window.electronAPI.selectFile([
      { name: t('edit.executables'), extensions: ['exe'] },
      { name: t('edit.allFiles'), extensions: ['*'] },
    ])
    const picked = paths?.[0]
    if (!picked) return
    if (!isGenshinClientExe(picked)) {
      // 只认这两个文件名：选错了不写入也不保存，免得选了别的游戏的产品
      message.error(t('edit.genshinUpdateExeRejected'))
      return
    }
    props.model.UpdateExe = picked
    change('UpdateExe', picked)
  } catch (error) {
    const msg = error instanceof Error ? error.message : String(error)
    message.error(`${t('edit.couldNotPickFile')}: ${msg}`)
  }
}
</script>

<template>
  <a-row :gutter="24">
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <span class="form-label">
            {{ t('edit.genshinUpdateAuto') }}
            <a-tooltip :title="t('edit.genshinUpdateAutoHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-select
          v-model:value="model.IfAutoUpdate"
          size="large"
          :disabled="disabled"
          @change="change('IfAutoUpdate', model.IfAutoUpdate)"
        >
          <a-select-option :value="true">{{ t('edit.yes') }}</a-select-option>
          <a-select-option :value="false">{{ t('edit.no') }}</a-select-option>
        </a-select>
      </a-form-item>
    </a-col>
    <a-col v-if="model.IfAutoUpdate" :span="12">
      <a-form-item>
        <template #label>
          <span class="form-label">
            {{ t('edit.genshinUpdateTimeLimit') }}
            <a-tooltip :title="t('edit.genshinUpdateTimeLimitHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-input-number
          v-model:value="model.UpdateTimeLimit"
          :min="1"
          :max="9999"
          size="large"
          style="width: 100%"
          :disabled="disabled"
          @blur="change('UpdateTimeLimit', model.UpdateTimeLimit)"
        />
      </a-form-item>
    </a-col>
  </a-row>

  <a-row v-if="withExe && model.IfAutoUpdate" :gutter="24">
    <a-col :span="12">
      <a-form-item>
        <template #label>
          <span class="form-label">
            {{ t('edit.genshinUpdateExe') }}
            <a-tooltip :title="t('edit.genshinUpdateExeHint')">
              <QuestionCircleOutlined class="help-icon" />
            </a-tooltip>
          </span>
        </template>
        <a-input-group compact>
          <a-input
            v-model:value="model.UpdateExe"
            size="large"
            :placeholder="t('edit.genshinUpdateExePlaceholder')"
            :disabled="disabled"
            readonly
            style="width: calc(100% - 96px)"
          />
          <a-button size="large" :disabled="disabled" @click="pickExe">
            <template #icon>
              <FileOutlined />
            </template>
            {{ t('edit.genshinUpdateExePick') }}
          </a-button>
        </a-input-group>
      </a-form-item>
    </a-col>
  </a-row>
</template>

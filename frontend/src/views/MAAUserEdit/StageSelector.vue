<template>
  <a-select
    :value="value"
    :disabled="loading"
    size="large"
    :placeholder="placeholder"
    @update:value="$emit('update:value', $event)"
  >
    <template #dropdownRender="{ menuNode: menu }">
      <v-nodes :vnodes="menu" />
      <a-divider style="margin: 4px 0" />
      <a-space style="padding: 4px 8px" size="small">
        <a-input
          ref="inputRef"
          v-model:value="customStageName"
          placeholder="输入自定义关卡，如: 11-8"
          style="flex: 1"
          size="small"
          @keyup.enter="addCustomStage"
        />
        <a-button type="text" size="small" @click="addCustomStage">
          <template #icon>
            <PlusOutlined />
          </template>
          添加关卡
        </a-button>
      </a-space>
    </template>
    <a-select-option v-for="option in options" :key="option.value" :value="option.value">
      <template v-if="option.label.includes('|')">
        <span>{{ option.label.split('|')[0] }}</span>
        <a-tag color="green" size="small" style="margin-left: 8px">
          {{ option.label.split('|')[1] }}
        </a-tag>
      </template>
      <template v-else>
        {{ option.label }}
        <a-tag
          v-if="isCustomStage(option.value)"
          color="blue"
          size="small"
          style="margin-left: 8px"
        >
          自定义
        </a-tag>
      </template>
    </a-select-option>
  </a-select>
</template>

<script setup lang="ts">
import { ref, defineComponent } from 'vue'
import { PlusOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'

// VNodes 组件定义
const VNodes = defineComponent({
  props: { vnodes: { type: Object, required: true } },
  setup(props) {
    return () => props.vnodes as any
  },
})

const props = defineProps<{
  value: string
  options: any[]
  loading: boolean
  placeholder?: string
}>()

const emit = defineEmits<{
  'update:value': [value: string]
  'add-custom-stage': [stageName: string]
}>()

const customStageName = ref('')
const inputRef = ref()

// 判断值是否为自定义关卡
const isCustomStage = (value: string) => {
  if (!value || value === '' || value === '-') return false
  // 检查是否在从API加载的关卡列表中
  const predefinedStage = props.options.find(option => option.value === value && !option.isCustom)
  return !predefinedStage
}

// 验证关卡名称格式
const validateStageName = (stageName: string): boolean => {
  if (!stageName || !stageName.trim()) {
    return false
  }
  // 简单的关卡名称验证
  const stagePattern = /^[a-zA-Z0-9\-_\u4e00-\u9fa5]+$/
  return stagePattern.test(stageName.trim())
}

// 添加自定义关卡
const addCustomStage = () => {
  if (!validateStageName(customStageName.value)) {
    message.error('请输入有效的关卡名称')
    return
  }

  const trimmedName = customStageName.value.trim()

  // 检查是否已存在
  const exists = props.options.find((option: any) => option.value === trimmedName)
  if (exists) {
    message.warning(`关卡 "${trimmedName}" 已存在`)
    return
  }

  emit('add-custom-stage', trimmedName)
  customStageName.value = ''
}
</script>

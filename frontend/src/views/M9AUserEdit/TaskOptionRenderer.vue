<template>
  <div class="task-option-renderer">
    <div v-for="(option, index) in currentOptions" :key="index" class="option-item">
      <div class="option-label">{{ option.name }}</div>
      
      <template v-if="optionDefinitions && optionDefinitions[option.name]">
        <a-radio-group
          v-if="optionDefinitions[option.name].type === 'switch'"
          v-model:value="option.index"
          @change="handleOptionChange(index)"
        >
          <a-radio
            v-for="(caseItem, caseIndex) in optionDefinitions[option.name].cases"
            :key="caseIndex"
            :value="caseIndex"
          >
            {{ caseItem.name }}
          </a-radio>
        </a-radio-group>
        
        <a-select
          v-else-if="optionDefinitions[option.name].type === 'select'"
          v-model:value="option.index"
          style="width: 100%"
          @change="handleOptionChange(index)"
        >
          <a-select-option
            v-for="(caseItem, caseIndex) in optionDefinitions[option.name].cases"
            :key="caseIndex"
            :value="caseIndex"
          >
            {{ caseItem.name }}
          </a-select-option>
        </a-select>
        
        <div
          v-else-if="optionDefinitions[option.name].type === 'input'"
          class="input-fields"
        >
          <a-form-item
            v-for="input in optionDefinitions[option.name].inputs"
            :key="input.name"
            :label="input.name"
          >
            <a-input-number
              v-if="input.pipeline_type === 'int'"
              v-model:value="option.input_values[input.name]"
              :min="0"
              style="width: 100%"
              @change="handleInputChange(index)"
            />
            <a-input
              v-else
              v-model:value="option.input_values[input.name]"
              :placeholder="input.description || input.name"
              style="width: 100%"
              @change="handleInputChange(index)"
            />
          </a-form-item>
        </div>
      </template>
      
      <div v-if="option.sub_options && option.sub_options.length > 0" class="sub-options">
        <TaskOptionRenderer
          :task-options="option.sub_options"
          :option-definitions="optionDefinitions"
          @update="handleSubOptionsUpdate(index, $event)"
        />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { M9ATaskOption } from '@/types/script'

const props = defineProps<{
  taskOptions: M9ATaskOption[]
  optionDefinitions: Record<string, any>
}>()

const emit = defineEmits<{
  update: [value: M9ATaskOption[]]
}>()

const currentOptions = ref<M9ATaskOption[]>([])

const getSubOptions = (optionDef: any, index: number): M9ATaskOption[] => {
  if (!optionDef || !optionDef.cases || optionDef.cases.length <= index) {
    return []
  }
  
  const currentCase = optionDef.cases[index]
  if (!currentCase.option || !Array.isArray(currentCase.option)) {
    return []
  }
  
  const subOpts: M9ATaskOption[] = []
  
  for (const optName of currentCase.option) {
    const optItem: M9ATaskOption = { name: optName, index: 0 }
    
    const optDef = props.optionDefinitions[optName]
    if (optDef && optDef.cases && optDef.cases.length > 0) {
      const subSubOpts = getSubOptions(optDef, 0)
      if (subSubOpts.length > 0) {
        optItem.sub_options = subSubOpts
      }
    }
    
    subOpts.push(optItem)
  }
  
  return subOpts
}

const initializeOptions = () => {
  currentOptions.value = props.taskOptions.map((opt, idx) => {
    const newOpt: M9ATaskOption = { 
      name: opt.name, 
      index: opt.index ?? 0,
      sub_options: opt.sub_options ? [...opt.sub_options] : undefined,
      input_values: opt.input_values ? { ...opt.input_values } : undefined
    }
    
    if (props.optionDefinitions && props.optionDefinitions[opt.name]) {
      const optDef = props.optionDefinitions[opt.name]
      
      if (optDef.type === 'input' && optDef.inputs) {
        if (!newOpt.input_values) {
          newOpt.input_values = {}
        }
        
        for (const input of optDef.inputs) {
          if (newOpt.input_values[input.name] === undefined && input.default !== undefined) {
            if (input.pipeline_type === 'int') {
              newOpt.input_values[input.name] = parseInt(input.default)
            } else {
              newOpt.input_values[input.name] = input.default
            }
          }
        }
      }
      
      const subOpts = getSubOptions(optDef, opt.index ?? 0)
      
      if (subOpts.length > 0) {
        if (!newOpt.sub_options || newOpt.sub_options.length === 0) {
          newOpt.sub_options = subOpts
        } else {
          const currentSubOptNames = newOpt.sub_options.map((o) => o.name)
          const newSubOptNames = subOpts.map((o) => o.name)
          
          if (JSON.stringify(currentSubOptNames) !== JSON.stringify(newSubOptNames)) {
            newOpt.sub_options = subOpts
          }
        }
      } else {
        newOpt.sub_options = []
      }
    }
    
    return newOpt
  })
}

const handleOptionChange = (index: number) => {
  if (props.optionDefinitions && props.optionDefinitions[currentOptions.value[index].name]) {
    const optDef = props.optionDefinitions[currentOptions.value[index].name]
    const subOpts = getSubOptions(optDef, currentOptions.value[index].index)
    
    if (subOpts.length > 0) {
      currentOptions.value[index].sub_options = subOpts
    } else {
      currentOptions.value[index].sub_options = []
    }
  }
  
  emit('update', currentOptions.value)
}

const handleInputChange = (index: number) => {
  emit('update', currentOptions.value)
}

const handleSubOptionsUpdate = (parentIndex: number, newSubOptions: M9ATaskOption[]) => {
  currentOptions.value[parentIndex].sub_options = newSubOptions
  emit('update', currentOptions.value)
}

watch(
  () => props.taskOptions,
  () => {
    initializeOptions()
  },
  { deep: true, immediate: true }
)

watch(
  () => props.optionDefinitions,
  () => {
    initializeOptions()
  },
  { deep: true }
)
</script>

<style scoped>
.task-option-renderer {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.option-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.option-label {
  font-weight: 500;
  color: var(--ant-color-text);
}

.sub-options {
  margin-left: 24px;
  padding-left: 16px;
  border-left: 2px solid var(--ant-color-border);
}
</style>

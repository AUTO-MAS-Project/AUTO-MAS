<template>
  <div class="task-option-renderer">
    <div v-for="(option, index) in currentOptions" :key="index" class="option-item">
      <div class="option-label">{{ getOptionLabel(option.name) }}</div>

      <template v-if="optionDefinitions && optionDefinitions[option.name]">
        <a-radio-group
          v-if="optionDefinitions[option.name].type === 'switch'"
          v-model:value="option.index"
          @change="handleOptionChange(index)"
        >
          <a-radio
            v-for="caseItem in getDisplayCases(optionDefinitions[option.name])"
            :key="getCaseIndex(optionDefinitions[option.name], caseItem)"
            :value="getCaseIndex(optionDefinitions[option.name], caseItem)"
          >
            {{ getCaseLabel(caseItem) }}
          </a-radio>
        </a-radio-group>

        <a-select
          v-else-if="['select', 'scan_select'].includes(optionDefinitions[option.name].type)"
          v-model:value="option.index"
          style="width: 100%"
          @change="handleOptionChange(index)"
        >
          <a-select-option
            v-for="(caseItem, caseIndex) in optionDefinitions[option.name].cases"
            :key="caseIndex"
            :value="caseIndex"
          >
            {{ getCaseLabel(caseItem) }}
          </a-select-option>
        </a-select>

        <div
          v-else-if="optionDefinitions[option.name].type === 'input' && option.input_values"
          class="input-fields"
        >
          <a-form-item
            v-for="input in optionDefinitions[option.name].inputs"
            :key="input.name"
            :label="getInputLabel(input)"
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

        <div v-else-if="optionDefinitions[option.name].type === 'checkbox'" class="checkbox-cases">
          <a-checkbox-group
            v-model:value="option.selected_cases"
            @change="handleCheckboxChange(index)"
          >
            <a-checkbox
              v-for="caseItem in optionDefinitions[option.name].cases"
              :key="caseItem.name"
              :value="caseItem.name"
            >
              {{ getCaseLabel(caseItem) }}
            </a-checkbox>
          </a-checkbox-group>
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
import { ref, watch } from 'vue'
import type { M9ATaskOption } from '@/types/script'

const props = defineProps<{
  taskOptions: M9ATaskOption[]
  optionDefinitions: Record<string, any>
}>()

const emit = defineEmits<{
  update: [value: M9ATaskOption[]]
}>()

const currentOptions = ref<M9ATaskOption[]>([])

const getDisplayLabel = (label: string | undefined, fallback: string | undefined) => {
  return label && !label.startsWith('$') ? label : (fallback ?? '')
}

const getOptionLabel = (optionName: string) => {
  const optionDef = props.optionDefinitions?.[optionName]
  return getDisplayLabel(optionDef?.label, optionName)
}

const getCaseLabel = (caseItem: any) => getDisplayLabel(caseItem?.label, caseItem?.name)

const getInputLabel = (input: any) => getDisplayLabel(input?.label, input?.name)

const getDisplayCases = (optionDef: any) => {
  if (!optionDef || !optionDef.cases) {
    return []
  }

  const cases = [...optionDef.cases]

  const isYesNoSwitch = cases.some(
    c => c.name === 'Yes' || c.name === 'No' || c.name === '是' || c.name === '否'
  )

  if (!isYesNoSwitch) {
    return cases
  }

  return cases.sort((a, b) => {
    const aIsYes = a.name === 'Yes' || a.name === '是'
    const bIsYes = b.name === 'Yes' || b.name === '是'
    if (aIsYes && !bIsYes) return -1
    if (!aIsYes && bIsYes) return 1
    return 0
  })
}

const getCaseIndex = (optionDef: any, caseItem: any) => {
  if (!optionDef || !optionDef.cases) {
    return 0
  }
  return optionDef.cases.findIndex((c: any) => c.name === caseItem.name)
}

const buildSubOptions = (optionNames: string[]): M9ATaskOption[] => {
  const subOpts: M9ATaskOption[] = []

  for (const optName of optionNames) {
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

const getSubOptions = (optionDef: any, index: number): M9ATaskOption[] => {
  if (!optionDef || !optionDef.cases || optionDef.cases.length <= index) {
    return []
  }

  const currentCase = optionDef.cases[index]
  if (!currentCase.option || !Array.isArray(currentCase.option)) {
    return []
  }

  return buildSubOptions(currentCase.option)
}

const getCheckboxSubOptions = (optionDef: any, selectedCases: string[] = []): M9ATaskOption[] => {
  if (!optionDef || !Array.isArray(optionDef.cases)) {
    return []
  }

  const optionNames = optionDef.cases
    .filter((caseItem: any) => selectedCases.includes(caseItem.name))
    .flatMap((caseItem: any) => (Array.isArray(caseItem.option) ? caseItem.option : []))

  return buildSubOptions(Array.from(new Set(optionNames)))
}

const getDefaultCaseNames = (optionDef: any) => {
  if (!optionDef || !Array.isArray(optionDef.cases)) {
    return []
  }
  const defaultCases = Array.isArray(optionDef.default_case)
    ? optionDef.default_case
    : typeof optionDef.default_case === 'string'
      ? [optionDef.default_case]
      : []
  return optionDef.cases
    .filter((caseItem: any) => defaultCases.includes(caseItem.name))
    .map((caseItem: any) => caseItem.name)
}

const initializeOptions = () => {
  currentOptions.value = props.taskOptions.map((opt, idx) => {
    const newOpt: M9ATaskOption = {
      name: opt.name,
      index: opt.index ?? 0,
      sub_options: opt.sub_options ? [...opt.sub_options] : undefined,
      input_values: opt.input_values ? { ...opt.input_values } : undefined,
      selected_cases: opt.selected_cases ? [...opt.selected_cases] : undefined,
    }

    if (props.optionDefinitions && props.optionDefinitions[opt.name]) {
      const optDef = props.optionDefinitions[opt.name]

      if (optDef.type === 'checkbox' && newOpt.selected_cases === undefined) {
        newOpt.selected_cases = getDefaultCaseNames(optDef)
      }

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

      const subOpts =
        optDef.type === 'checkbox'
          ? getCheckboxSubOptions(optDef, newOpt.selected_cases ?? [])
          : getSubOptions(optDef, opt.index ?? 0)

      if (subOpts.length > 0) {
        if (!newOpt.sub_options || newOpt.sub_options.length === 0) {
          newOpt.sub_options = subOpts
        } else {
          const currentSubOptNames = newOpt.sub_options.map(o => o.name)
          const newSubOptNames = subOpts.map(o => o.name)

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

const handleCheckboxChange = (index: number) => {
  if (props.optionDefinitions && props.optionDefinitions[currentOptions.value[index].name]) {
    const optDef = props.optionDefinitions[currentOptions.value[index].name]
    const subOpts = getCheckboxSubOptions(optDef, currentOptions.value[index].selected_cases ?? [])

    if (subOpts.length > 0) {
      currentOptions.value[index].sub_options = subOpts
    } else {
      currentOptions.value[index].sub_options = []
    }
  }

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

.checkbox-cases {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
</style>

import { computed, ref, watch, type Ref } from 'vue'
import type { MaaFWEmbeddedSourceItem } from '@/api'
import type { ScriptType } from '@/types/script'
import { buildMfwReuseChoices, isMfwFamily } from './scriptCreateFlow'

interface MfwCreateSourceOptions {
  selectedType: Ref<ScriptType>
  isOpen: () => boolean
  sources: () => MaaFWEmbeddedSourceItem[]
  sourcesLoading: () => boolean
  sourcesError: () => string | null
  requestSources: () => void
}

/**
 * 新建对话框 MFW 家族的「项目从哪来」：可复用的项目、当前选择，以及选中类型卡片时预取候选——
 * 读完、没出错又一个候选都没有时，第一步直接「创建并配置」，不再走只有一张卡可选的这一步。
 */
export function useMfwCreateSource({
  selectedType,
  isOpen,
  sources,
  sourcesLoading,
  sourcesError,
  requestSources,
}: MfwCreateSourceOptions) {
  /** 'new' = 选本地目录导入新项目（进引导页选目录）；否则是要复用的项目所属脚本的 id */
  const selectedMfwChoice = ref<string>('new')
  // 可复用的项目只列与入口同类型的，同一项目多个脚本并成一行
  const mfwReuseChoices = computed(() => buildMfwReuseChoices(sources(), selectedType.value))
  // 选中的源以当前列表为准：返回再进来时列表会重新拉，源可能已在运行（busy）或已被删，
  // 残留的 id 不能直接拿去提交——那会先建出脚本再被后端拒绝，留下一个没项目的空脚本。
  const selectedMfwReuse = computed(
    () =>
      mfwReuseChoices.value.find(
        choice => choice.scriptId === selectedMfwChoice.value && !choice.busy
      ) ?? null
  )
  watch(mfwReuseChoices, () => {
    if (selectedMfwChoice.value !== 'new' && !selectedMfwReuse.value) {
      selectedMfwChoice.value = 'new'
    }
  })

  // 每次打开对话框只预取一次：候选不分类型，切换 MFW 家族的卡片不必再拉
  const prefetched = ref(false)
  watch(selectedType, type => {
    if (!isOpen() || prefetched.value || !isMfwFamily(type)) return
    prefetched.value = true
    requestSources()
  })
  const skipMfwSourceStep = computed(
    () =>
      prefetched.value &&
      isMfwFamily(selectedType.value) &&
      !sourcesLoading() &&
      !sourcesError() &&
      mfwReuseChoices.value.length === 0
  )

  const resetMfwSource = () => {
    selectedMfwChoice.value = 'new'
    prefetched.value = false
  }

  return { selectedMfwChoice, mfwReuseChoices, selectedMfwReuse, skipMfwSourceStep, resetMfwSource }
}

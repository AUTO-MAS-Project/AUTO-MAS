import { ref } from 'vue'

/** 队列项的脚本下拉选项，跨组件实例保留：切换队列重挂载时先沿用上次结果，再后台刷新。 */
export const sharedScriptOptions = ref<Array<{ label: string; value: string | null }>>([])

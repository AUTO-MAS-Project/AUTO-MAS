import { defineStore } from 'pinia'
import { markRaw, ref } from 'vue'
import { ThreeBodySolver } from '@/components/three-star/physics'

/** 会话内保留积分状态与手动暂停；离开首页后再回来不自动重置或补算。 */
export const useThreeStarStore = defineStore('three-star', () => {
  const solver = markRaw(new ThreeBodySolver())
  const userPaused = ref(false)
  return { solver, userPaused }
})

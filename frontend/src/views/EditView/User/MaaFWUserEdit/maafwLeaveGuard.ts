import { ref } from 'vue'

/**
 * 用户页的路由离开守卫：`prepare` 负责提交草稿、等保存、必要时弹确认，给出能不能走。
 *
 * - 从开始离开到有结论（含确认框开着）期间 `leaving` 为真（返回按钮据此转圈）；
 * - 这期间再发起的离开（连点、又点了面包屑）等同一个结论，`prepare` 只跑一次、确认框只弹一次；
 * - 放行过一次后同一次离开（如被别的守卫重定向）不再拦，`reset()` 后下次离开照常检查。
 */
export const createMaaFWLeaveGuard = (prepare: () => Promise<boolean>) => {
  const leaving = ref(false)
  let pending: Promise<boolean> | null = null
  let approved = false

  const guard = async () => {
    if (approved) return true
    if (!pending) {
      leaving.value = true
      pending = prepare().finally(() => {
        pending = null
        leaving.value = false
      })
    }
    const result = await pending
    if (result) approved = true
    return result
  }

  const reset = () => {
    approved = false
  }

  return { leaving, guard, reset }
}

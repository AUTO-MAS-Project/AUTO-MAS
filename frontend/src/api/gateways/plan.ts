import {
  createPlanApiPlanPost,
  deletePlanApiPlanPlanIdDelete,
  getPlanApiPlanPlanIdGet,
  listPlansApiPlanGet,
  reorderPlanApiPlanOrderPatch,
  updatePlanApiPlanPlanIdPatch,
} from '../generated/sdk.gen'
import type { IndexOrderPatch, PlanCreateIn, PlanUpdateBody } from '../generated/types.gen'

export const planApi = {
  list() {
    return listPlansApiPlanGet()
  },

  create(payload: PlanCreateIn) {
    return createPlanApiPlanPost({ body: payload })
  },

  get(planId: string) {
    return getPlanApiPlanPlanIdGet({ path: { plan_id: planId } })
  },

  update(planId: string, payload: PlanUpdateBody) {
    return updatePlanApiPlanPlanIdPatch({
      path: { plan_id: planId },
      body: payload,
    })
  },

  remove(planId: string) {
    return deletePlanApiPlanPlanIdDelete({ path: { plan_id: planId } })
  },

  reorder(payload: IndexOrderPatch) {
    return reorderPlanApiPlanOrderPatch({ body: payload })
  },
}

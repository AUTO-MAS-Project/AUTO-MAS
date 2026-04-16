import { getToolsApiToolsGet, updateToolsApiToolsPatch } from '../generated/sdk.gen'
import type { ToolsConfigRead } from '../generated/types.gen'

export const toolsApi = {
  get() {
    return getToolsApiToolsGet()
  },

  update(payload: ToolsConfigRead) {
    return updateToolsApiToolsPatch({ body: payload })
  },
}

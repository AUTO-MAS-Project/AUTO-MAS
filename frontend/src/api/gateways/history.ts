import {
  getHistoryDataApiHistoryDataPost,
  searchHistoryApiHistorySearchPost,
} from '../generated/sdk.gen'
import type { HistoryDataGetIn, HistorySearchIn } from '../generated/types.gen'

export const historyApi = {
  search(payload: HistorySearchIn) {
    return searchHistoryApiHistorySearchPost({ body: payload })
  },

  getData(payload: HistoryDataGetIn) {
    return getHistoryDataApiHistoryDataPost({ body: payload })
  },
}

/**
 * 列表/详情接口的页面数据状态。
 *
 * 空数组不能同时代表「真的没有数据」和「请求失败」，两者必须由不同取值区分。
 */
export type PageDataState =
  | 'not_loaded'
  | 'loading'
  | 'loaded_fresh'
  | 'loaded_stale'
  | 'empty'
  | 'error_with_previous_data'
  | 'error_without_data'

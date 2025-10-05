/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryIndexItem } from '@/api'

export type HistoryData = {
  /**
   * 历史记录索引列表
   */
  index?: Array<HistoryIndexItem> | null
  /**
   * 公招统计数据, key为星级, value为对应的公招数量
   */
  recruit_statistics?: Record<string, number> | null
  /**
   * 掉落统计数据, 格式为 { '关卡号': { '掉落物': 数量 } }
   */
  drop_statistics?: Record<string, Record<string, number>> | null
  /**
   * 报错信息, key为时间戳, value为错误描述
   */
  error_info?: Record<string, string> | null
  /**
   * 日志内容, 仅在提取单条历史记录数据时返回
   */
  log_content?: string | null
}

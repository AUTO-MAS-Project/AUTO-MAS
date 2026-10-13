/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { HistoryIndexItem } from './HistoryIndexItem';
import type { PullCountStatistics } from './PullCountStatistics';
export type HistoryData = {
    /**
     * 历史记录索引列表
     */
    index?: (Array<HistoryIndexItem> | null);
    /**
     * 公招统计数据, key为星级, value为对应的公招数量
     */
    recruit_statistics?: (Record<string, number> | null);
    /**
     * 掉落统计数据, 格式为 { '关卡号': { '掉落物': 数量 } }
     */
    drop_statistics?: (Record<string, Record<string, number>> | null);
    /**
     * 基质统计数据, key为技能组合, value为符合武器名称
     */
    matrix_statistics?: (Record<string, string> | null);
    /**
     * MaaEnd 抽数计算统计
     */
    pull_count_statistics?: (PullCountStatistics | null);
    /**
     * 合并后的统计数据（2/3 层数字树）
     */
    data?: Record<string, any>;
    /**
     * 报错信息, key为时间戳, value为错误描述
     */
    error_info?: (Record<string, string> | null);
    /**
     * 日志内容, 仅在提取单条历史记录数据时返回
     */
    log_content?: (string | null);
    /**
     * 单条记录状态
     */
    status?: (string | null);
    /**
     * 单条记录消息
     */
    message?: (string | null);
    /**
     * 脚本类型键
     */
    type_key?: (string | null);
    /**
     * 用户名
     */
    username?: (string | null);
};


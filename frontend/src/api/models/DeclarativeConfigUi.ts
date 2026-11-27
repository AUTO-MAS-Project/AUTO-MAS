/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { UiHintsMap } from './UiHintsMap';
import type { UiTablesList } from './UiTablesList';
/**
 * 单项编辑所需的实时提示及触发器、锁使用的配置实例标识。
 */
export type DeclarativeConfigUi = {
    configUid: string;
    hints: UiHintsMap;
    tables: UiTablesList;
    i18nNamespace?: (string | null);
};


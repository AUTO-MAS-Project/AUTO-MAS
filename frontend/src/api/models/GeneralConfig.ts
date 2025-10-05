/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { GeneralConfig_Game, GeneralConfig_Info, GeneralConfig_Run, GeneralConfig_Script } from '@/api'

export type GeneralConfig = {
  /**
   * 脚本基础信息
   */
  Info?: GeneralConfig_Info | null
  /**
   * 脚本配置
   */
  Script?: GeneralConfig_Script | null
  /**
   * 游戏配置
   */
  Game?: GeneralConfig_Game | null
  /**
   * 运行配置
   */
  Run?: GeneralConfig_Run | null
}

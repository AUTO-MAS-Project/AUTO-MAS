/** 主页装饰样式；保留经典默认值，新增款式需用户主动选择。 */
export type HomeSatelliteStyle = 'classic' | 'galaxy' | 'three-star'

export const DEFAULT_HOME_SATELLITE_STYLE: HomeSatelliteStyle = 'classic'

export const normalizeHomeSatelliteStyle = (value: unknown): HomeSatelliteStyle =>
  value === 'galaxy' || value === 'three-star' ? value : DEFAULT_HOME_SATELLITE_STYLE

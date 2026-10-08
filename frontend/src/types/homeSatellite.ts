/** 主页卫星样式：原来的平面卫星（经典，默认），或可拖动的 3D 星系 */
export type HomeSatelliteStyle = 'classic' | 'galaxy'

export const DEFAULT_HOME_SATELLITE_STYLE: HomeSatelliteStyle = 'classic'

export const normalizeHomeSatelliteStyle = (value: unknown): HomeSatelliteStyle =>
  value === 'galaxy' ? 'galaxy' : DEFAULT_HOME_SATELLITE_STYLE

import { saveConfig, type FrontendConfig } from './config'
import { observeFeature } from './featureAnalytics'
import type { AnalyticsEventProps } from '@/types/analytics'

/** 资源类别来自内置枚举，绝不把包标识或显示名带入事件。 */
export const appearanceCategory = (value: unknown): 'theme' | 'mascot' | 'unknown' =>
  value === 'theme' || value === 'mascot' ? value : 'unknown'

export function saveMascotPreference(patch: Partial<FrontendConfig>) {
  const enabled = patch.desktopMascotEnabled
  const fps = patch.desktopMascotFps
  return observeFeature(
    'mascot_preference_changed',
    {
      action:
        typeof enabled === 'boolean'
          ? enabled
            ? 'enable'
            : 'disable'
          : Object.prototype.hasOwnProperty.call(patch, 'desktopMascotFps')
            ? 'fps'
            : 'configure',
      fps_preset:
        typeof fps !== 'number'
          ? 'unknown'
          : fps <= 30
            ? 'low'
            : fps <= 60
              ? 'normal'
              : fps <= 120
                ? 'high'
                : 'custom',
    },
    () => saveConfig(patch),
    () => 'success'
  )
}

export function observePreference<P extends PromiseLike<unknown>>(
  preference_kind: AnalyticsEventProps['appearance_preference_changed']['preference_kind'],
  preset_value: AnalyticsEventProps['appearance_preference_changed']['preset_value'],
  run: () => P
): P {
  return observeFeature(
    'appearance_preference_changed',
    { preference_kind, preset_value },
    run,
    () => 'success'
  )
}

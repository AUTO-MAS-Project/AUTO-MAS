import { h } from 'vue'
import { Checkbox, TypographyText } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { useConfirm } from '@/composables/useConfirm'
import {
  LIFECYCLE_LABEL_KEYS,
  lifecycleDecision,
  type InstalledPluginView,
  type LifecycleAction,
} from '../pluginCenterModel'
import { usePluginCenter } from '../usePluginCenter'

export function useInstalledActions() {
  const { t } = useI18n()
  const { confirm } = useConfirm()
  const { data, installation, runLifecycle } = usePluginCenter()

  const request = async (view: InstalledPluginView, action: LifecycleAction): Promise<boolean> => {
    if (action === 'enable' || action === 'reload') return runLifecycle(view, action)
    const decision = lifecycleDecision(action, view)
    if (decision.kind === 'direct') return runLifecycle(view, action)

    const uninstall = action === 'uninstall'
    let purgeConfig = false
    const names = decision.cascade.map(
      id => data.installed.value.find(plugin => plugin.pluginId === id)?.name ?? id
    )
    const confirmed = await confirm({
      tone: uninstall ? 'danger' : 'warning',
      title: t(
        uninstall ? 'core.plugins.uninstallConfirmTitle' : 'core.plugins.disableConfirmTitle'
      ),
      okText: t(LIFECYCLE_LABEL_KEYS[action]),
      description: h('div', [
        h(
          'p',
          t(
            uninstall
              ? 'core.plugins.uninstallConfirmContent'
              : 'core.plugins.disableConfirmContent',
            { name: view.name }
          )
        ),
        !uninstall && decision.scopes.length
          ? h(
              'p',
              t('core.plugins.disableAffected', {
                scopes: decision.scopes
                  .map(scope => t(`core.plugins.disableScope.${scope}`))
                  .join(' / '),
              })
            )
          : null,
        names.length
          ? h(
              'p',
              t(uninstall ? 'core.plugins.uninstallCascade' : 'core.plugins.disableCascade', {
                plugins: names.join(' / '),
              })
            )
          : null,
        uninstall
          ? h(Checkbox, { 'onUpdate:checked': (checked: boolean) => (purgeConfig = checked) }, () =>
              h(TypographyText, { type: 'danger' }, () => t('core.plugins.uninstallPurgeConfig'))
            )
          : null,
      ]),
    })
    return confirmed && runLifecycle(view, action, purgeConfig)
  }

  const upgrade = (view: InstalledPluginView): Promise<boolean> =>
    view.upgrade ? installation.install(view.upgrade.document) : Promise.resolve(false)

  return { request, upgrade }
}

import type { UserGetOut } from '@/api/models/UserGetOut'

/** Return enabled users in the order used by the dispatcher cursor. */
export const toRunnableUserOptions = (
  response: Pick<UserGetOut, 'order' | 'data'>
): Array<{ label: string; value: string }> => {
  const options: Array<{ label: string; value: string }> = []
  ;(response.order ?? []).forEach(item => {
    const info = response.data?.[item.uid]?.info
    if (!info || info.enabled === false) return
    options.push({ value: item.uid, label: info?.name || item.uid })
  })
  return options
}

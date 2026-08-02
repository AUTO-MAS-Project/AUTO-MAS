import type { Script, User } from '@/types/script'

const normalizeSearchValue = (value: unknown) =>
  String(value ?? '')
    .trim()
    .toLowerCase()

const includesKeyword = (values: unknown[], keyword: string) =>
  values.some(value => normalizeSearchValue(value).includes(keyword))

const matchesUser = (user: User, keyword: string) =>
  includesKeyword([user.name, user.id, user.Info.Name, user.Info.Id], keyword)

export const filterScriptsByKeyword = (scripts: Script[], rawKeyword: string): Script[] => {
  const keyword = normalizeSearchValue(rawKeyword)
  if (!keyword) return scripts

  return scripts.flatMap(script => {
    if (includesKeyword([script.name, script.id, script.type], keyword)) return [script]

    const matchingUsers = script.users.filter(user => matchesUser(user, keyword))
    return matchingUsers.length ? [{ ...script, users: matchingUsers }] : []
  })
}

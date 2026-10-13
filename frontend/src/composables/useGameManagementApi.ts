import { Service, type GameUpdateIn, type InstanceUpdateIn } from '@/api'
import { translate as t } from '@/i18n'
import { requestApi } from '@/utils/apiResult'

export function useGameManagementApi() {
  return {
    getGames: () => requestApi(() => Service.getGamesApiGamesGetPost({ gameId: null }), t('emulator.toast.loadFailed')),
    getTypes: () => requestApi(() => Service.listGameTypesApiGamesTypesPost(), t('emulator.toast.loadFailed')),
    updateGame: (body: GameUpdateIn) => requestApi(() => Service.updateGameApiGamesUpdatePost(body), t('emulator.toast.saveFailed')),
    updateDevice: (body: InstanceUpdateIn) => requestApi(() => Service.updateInstanceApiGamesInstancesUpdatePost(body), t('emulator.toast.saveFailed')),
    addGame: (type: string) => requestApi(() => Service.addGameApiGamesAddPost({ type }), t('emulator.toast.addFailed')),
    searchGames: () => requestApi(() => Service.searchGamesApiGamesSearchPost(), t('emulator.toast.searchFailed')),
    addSearchResult: (uid: string) => requestApi(() => Service.addSearchedGameApiGamesSearchAddPost({ uid }), t('emulator.toast.addFailed')),
  }
}

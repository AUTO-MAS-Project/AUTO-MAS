/* global module */
'use strict'

const experimentalAlphaIdentity = Object.freeze({
  appId: 'top.auto-mas.experimental-alpha',
  productName: 'AUTO-MAS v6 Experimental Alpha',
  executableName: 'AUTO-MAS-v6-Experimental-Alpha',
  releaseChannel: 'experimental-alpha',
  innoAppId: 'B245B0A5-70F8-4B81-9C77-0D785E6A1845',
  installDirectoryName: 'AUTO-MAS v6 Experimental Alpha',
  installerMutex: 'AUTO_MAS_V6_EXPERIMENTAL_ALPHA_INSTALLER_MUTEX',
  artifactStem: 'AUTO-MAS-v6-Experimental-Alpha',
  actionArtifactName: 'auto-mas-v6-experimental-alpha',
})

const assertExperimentalAlphaIdentity = (identity = experimentalAlphaIdentity) => {
  const requiredTextFields = [
    'appId',
    'productName',
    'executableName',
    'releaseChannel',
    'installDirectoryName',
    'installerMutex',
    'artifactStem',
    'actionArtifactName',
  ]
  for (const field of requiredTextFields) {
    if (typeof identity[field] !== 'string' || identity[field].trim().length === 0) {
      throw new TypeError(`Experimental Alpha identity field ${field} must be non-empty text`)
    }
  }
  if (!/^[0-9A-F]{8}(?:-[0-9A-F]{4}){3}-[0-9A-F]{12}$/.test(identity.innoAppId)) {
    throw new TypeError('Experimental Alpha Inno AppId must be an uppercase UUID')
  }
  if (identity.appId === 'top.auto-mas.frontend') {
    throw new Error('Experimental Alpha must not reuse the stable app identity')
  }
  if (identity.executableName === 'AUTO-MAS' || identity.artifactStem === 'AUTO-MAS') {
    throw new Error('Experimental Alpha must not reuse stable executable or artifact names')
  }
  return identity
}

assertExperimentalAlphaIdentity()

module.exports = {
  experimentalAlphaIdentity,
  assertExperimentalAlphaIdentity,
}

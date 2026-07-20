type RandomSource = () => number

const generateRandomCharacter = (charset: string, random: RandomSource): string => {
  if (!charset) return ''
  const index = Math.floor(random() * charset.length)
  return charset.charAt(index)
}

export const generateGibberishPreservingSpaces = (
  original: string,
  charset: string,
  random: RandomSource = Math.random
): string =>
  Array.from(original, character =>
    character === ' ' ? ' ' : generateRandomCharacter(charset, random)
  ).join('')

export const calculateRevealCount = (
  elapsedMs: number,
  revealDelayMs: number,
  textLength: number
): number => Math.min(textLength, Math.floor(elapsedMs / Math.max(1, revealDelayMs)))

export const getDisplayCharacter = (
  text: string,
  scrambledCharacters: string[],
  index: number,
  revealCount: number
): string => {
  const character = text[index] ?? ''
  if (index < revealCount || character === ' ') return character
  return scrambledCharacters[index] ?? ''
}

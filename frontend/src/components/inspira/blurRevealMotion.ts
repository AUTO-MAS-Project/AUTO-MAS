export const getBlurRevealInitial = (blur: string, yOffset: number) => ({
  opacity: 0,
  filter: `blur(${blur})`,
  y: yOffset,
})

export const getBlurRevealAnimate = () => ({
  opacity: 1,
  filter: 'blur(0px)',
  y: 0,
})

export const getBlurRevealContent = <T>(text: string | undefined, slotChildren: T[]) =>
  slotChildren.length > 0 ? slotChildren : text ? [text] : []

export const getBlurRevealTransition = (duration: number, delay: number, index: number) => ({
  duration,
  ease: 'easeInOut' as const,
  delay: delay * index,
})

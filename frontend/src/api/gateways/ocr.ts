import {
  checkImageAllApiOcrCheckImageAllPost,
  checkImageAnyApiOcrCheckImageAnyPost,
  checkImageApiOcrCheckImagePost,
  clickImageApiOcrClickImagePost,
  clickTextApiOcrClickTextPost,
  getScreenshotAdbApiOcrScreenshotAdbPost,
  getScreenshotApiOcrScreenshotPost,
} from '../generated/sdk.gen'
import type {
  AdbScreenshotIn,
  CheckImageAllIn,
  CheckImageAnyIn,
  CheckImageIn,
  ClickImageIn,
  ClickTextIn,
  OcrScreenshotIn,
} from '../generated/types.gen'

export const ocrApi = {
  getWindowScreenshot(payload: OcrScreenshotIn) {
    return getScreenshotApiOcrScreenshotPost({ body: payload })
  },

  getAdbScreenshot(payload: AdbScreenshotIn) {
    return getScreenshotAdbApiOcrScreenshotAdbPost({ body: payload })
  },

  checkImage(payload: CheckImageIn) {
    return checkImageApiOcrCheckImagePost({ body: payload })
  },

  checkAnyImage(payload: CheckImageAnyIn) {
    return checkImageAnyApiOcrCheckImageAnyPost({ body: payload })
  },

  checkAllImages(payload: CheckImageAllIn) {
    return checkImageAllApiOcrCheckImageAllPost({ body: payload })
  },

  clickImage(payload: ClickImageIn) {
    return clickImageApiOcrClickImagePost({ body: payload })
  },

  clickText(payload: ClickTextIn) {
    return clickTextApiOcrClickTextPost({ body: payload })
  },
}

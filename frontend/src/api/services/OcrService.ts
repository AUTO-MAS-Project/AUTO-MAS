/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
import type { ADBScreenshotIn } from '../models/ADBScreenshotIn';
import type { ADBScreenshotOut } from '../models/ADBScreenshotOut';
import type { CheckImageAllIn } from '../models/CheckImageAllIn';
import type { CheckImageAnyIn } from '../models/CheckImageAnyIn';
import type { CheckImageIn } from '../models/CheckImageIn';
import type { CheckImageOut } from '../models/CheckImageOut';
import type { ClickImageIn } from '../models/ClickImageIn';
import type { ClickOut } from '../models/ClickOut';
import type { ClickTextIn } from '../models/ClickTextIn';
import type { OCRScreenshotIn } from '../models/OCRScreenshotIn';
import type { OCRScreenshotOut } from '../models/OCRScreenshotOut';
import type { CancelablePromise } from '../core/CancelablePromise';
import { OpenAPI } from '../core/OpenAPI';
import { request as __request } from '../core/request';
export class OcrService {
    /**
     * 获取窗口截图
     * 根据窗口标题获取截图，返回Base64编码的图像数据
     *
     * Args:
     * params: 截图参数
     * - window_title: 窗口标题关键字
     * - should_preprocess: 是否预处理图片区域（默认True）
     * - aspect_ratio_width: 宽高比宽度（默认16）
     * - aspect_ratio_height: 宽高比高度（默认9）
     * - region: 自定义截图区域，格式为 (left, top, width, height)
     *
     * Returns:
     * OCRScreenshotOut: 包含Base64编码的截图和区域信息
     * @param requestBody
     * @returns OCRScreenshotOut Successful Response
     * @throws ApiError
     */
    public static getScreenshotApiOcrScreenshotPost(
        requestBody: OCRScreenshotIn,
    ): CancelablePromise<OCRScreenshotOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/screenshot',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 通过ADB获取设备截图
     * 通过 ADB 端口获取 Android 设备/模拟器截图，返回Base64编码的图像数据
     *
     * 支持两种截图方法：
     * 1. screencap PNG 方法（推荐）：速度快，直接获取 PNG 图像
     * 2. screencap raw 方法：获取原始像素数据，适用于某些不支持 PNG 的设备
     *
     * Args:
     * params: ADB 截图参数
     * - adb_path: ADB 可执行文件的路径
     * - serial: 设备序列号，格式如 "127.0.0.1:5555" 或 "emulator-5554"
     * - use_screencap: 是否使用 screencap PNG 方法（默认True）
     *
     * Returns:
     * ADBScreenshotOut: 包含Base64编码的截图和设备信息
     * @param requestBody
     * @returns ADBScreenshotOut Successful Response
     * @throws ApiError
     */
    public static getScreenshotAdbApiOcrScreenshotAdbPost(
        requestBody: ADBScreenshotIn,
    ): CancelablePromise<ADBScreenshotOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/screenshot/adb',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查是否存在指定图像
     * 截图并查找是否存在图片内的内容
     *
     * Args:
     * params: 检查图像参数
     * - window_title: 窗口标题关键字
     * - image_path: 要查找的图片路径
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * CheckImageOut: 包含查找结果和尝试次数
     * @param requestBody
     * @returns CheckImageOut Successful Response
     * @throws ApiError
     */
    public static checkImageApiOcrCheckImagePost(
        requestBody: CheckImageIn,
    ): CancelablePromise<CheckImageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/check/image',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查是否存在任意一个指定图像
     * 截图并查找是否存在列表中任意一张图片的内容
     *
     * Args:
     * params: 检查图像参数
     * - window_title: 窗口标题关键字
     * - image_paths: 要查找的图片路径列表
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * CheckImageOut: 包含查找结果和尝试次数
     * @param requestBody
     * @returns CheckImageOut Successful Response
     * @throws ApiError
     */
    public static checkImageAnyApiOcrCheckImageAnyPost(
        requestBody: CheckImageAnyIn,
    ): CancelablePromise<CheckImageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/check/image/any',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 检查是否存在所有指定图像
     * 截图并查找是否存在列表中所有图片的内容
     *
     * Args:
     * params: 检查图像参数
     * - window_title: 窗口标题关键字
     * - image_paths: 要查找的图片路径列表
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * CheckImageOut: 包含查找结果和尝试次数
     * @param requestBody
     * @returns CheckImageOut Successful Response
     * @throws ApiError
     */
    public static checkImageAllApiOcrCheckImageAllPost(
        requestBody: CheckImageAllIn,
    ): CancelablePromise<CheckImageOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/check/image/all',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 点击指定图像位置
     * 截图、查找并点击与图像一致的位置
     *
     * Args:
     * params: 点击图像参数
     * - window_title: 窗口标题关键字
     * - image_path: 要查找并点击的图片路径
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     * - threshold: 图像匹配阈值，范围 0-1，默认 0.8
     *
     * Returns:
     * ClickOut: 包含点击结果和尝试次数
     * @param requestBody
     * @returns ClickOut Successful Response
     * @throws ApiError
     */
    public static clickImageApiOcrClickImagePost(
        requestBody: ClickImageIn,
    ): CancelablePromise<ClickOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/click/image',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
    /**
     * 点击指定文字位置
     * 截图、OCR识别并点击与文字一致的位置
     *
     * Args:
     * params: 点击文字参数
     * - window_title: 窗口标题关键字
     * - text: 要查找并点击的文字内容
     * - interval: 截图间隔时间（秒），默认为 0
     * - retry_times: 重复截图次数，默认为 1
     *
     * Returns:
     * ClickOut: 包含点击结果和尝试次数
     * @param requestBody
     * @returns ClickOut Successful Response
     * @throws ApiError
     */
    public static clickTextApiOcrClickTextPost(
        requestBody: ClickTextIn,
    ): CancelablePromise<ClickOut> {
        return __request(OpenAPI, {
            method: 'POST',
            url: '/api/ocr/click/text',
            body: requestBody,
            mediaType: 'application/json',
            errors: {
                422: `Validation Error`,
            },
        });
    }
}

// ======================================================
// 切换账号OCR模式
import {check} from "./utils/tool";

const author = "彩虹QQ人";
// 图像识别资源
const pm_out = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/pm_out.png")),
    name: "pm_out.png"
};
const out_to_login = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/out_to_login.png")),
    name: "out_to_login.png"
};
const login_out_account = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/login_out_account.png")),
    name: "login_out_account.png"
};
const out_account = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/out_account.png")),
    name: "out_account.png"
};
const input_phone_or_email = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/input_phone_or_email.png")),
    name: "input_phone_or_email.png"
};
const input_password = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/input_password.png")),
    name: "input_password.png"
};
const agree = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/agree.png")),
    name: "agree.png"
};
const confirm_switch_account = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/confirm.png")),
    name: "confirm.png"
};
const input_email_username = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/input_email_username.png")),
    name: "input_email_username.png"
};
const switch_server = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/switch_server.png")),
    name: "switch_server.png"
};
const asia_server = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/asia.png")),
    name: "asia.png"
};
const europe_server = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/europe.png")),
    name: "europe.png"
};
const america_server = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/america.png")),
    name: "america.png"
};
const twhkmo_server = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/twhkmo.png")),
    name: "twhkmo.png"
};
const confirm_button = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/confirm_button.png")),
    name: "confirm_button.png"
};
const clear_login_info = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/clear_login_info.png")),
    name: "clear_login_info.png"
};
const save_login_info = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/save_login_info.png")),
    name: "save_login_info.png"
};
// 人机验证识别图片
const login_verification = {
    template: RecognitionObject.TemplateMatch(file.ReadImageMatSync("Assets/RecognitionObject/verification.png")),
    name: "verification.png"
};

// 判断temporaryAccount是否为空，如果为空则赋值‘否’
const Account = settings.temporaryAccount || "否";


// 点击区域中心
async function clickCenter(x, y, width, height) {
    let centerX = Math.round(x + width / 2);
    let centerY = Math.round(y + height / 2);
    await click(centerX, centerY);
    await sleep(500); // 确保点击后有足够的时间等待
    return { success: true, x: centerX, y: centerY };
}

// 匹配图像并点击
async function matchImgAndClick(obj, desc, timeout = 8000) {
    const script_mode = "matchImgAndClick";
    const start = Date.now();
    let retryCount = 0; // 识别次数计数
    let status = false; // 用于记录是否匹配成功
    try {
        while (Date.now() - start < timeout && !status) {
            await sleep(300);
            const ro = captureGameRegion();
            let result = ro.Find(obj.template);
            ro.dispose();
            await sleep(500); // 短暂延迟，避免过快循环
            if (result.isExist()) {
                let clickResult = await clickCenter(result.x, result.y, result.width, result.height);
                log.info(`【IMG】成功识别并点击 ${desc}| 耗时: ${Date.now() - start}ms`);
                status = true; // 设置匹配成功状态
                return { success: true, x: clickResult.x, y: clickResult.y };
            }
            // await sleep(200); // 短暂延迟，避免过快循环
            log.info(`【IMG】第${retryCount++}次识别并点击 ${desc} 失败 | 耗时: ${Date.now() - start}ms`);
        }
    } catch (error) {
        log.error(`【IMG】${script_mode}等待超时，请人工介入。===待切换账号：${settings.username}===超时原因：未找到目标 [${desc}] | 文件：${obj.name}`);
        //如果有配置通知……
        notification.error(`【IMG】${script_mode}等待超时，请人工介入。===待切换账号：${settings.username}===超时原因：未找到目标 [${desc}] | 文件：${obj.name}`);
        throw new Error(`【IMG】识别图像时发生异常: ${error.message}`);
    }
    return { success: false };
}

// 文字识别并点击
async function recognizeTextAndClick(targetText, ocrRegion, timeout = 8000) {
    let start = Date.now();
    let retryCount = 0; // 重试计数
    let status = false; // 用于记录是否匹配成功
    try {
        while (Date.now() - start < timeout && !status) {
            const ro = captureGameRegion();
            let resultList = ro.findMulti(ocrRegion);
            ro.dispose();
            await sleep(500); // 短暂延迟，避免过快循环
            for (let result of resultList) {
                if (result.text.includes(targetText)) {
                    let clickResult = await clickCenter(result.x, result.y, result.width, result.height);
                    log.info(`【OCR】成功识别并点击 ${targetText}| 耗时: ${Date.now() - start}ms`);
                    status = true; // 设置匹配成功状态
                    return { success: true, x: clickResult.x, y: clickResult.y };
                }
            }
            // await sleep(200); // 短暂延迟，避免过快循环
            log.info(`【OCR】${targetText}失败，正在进行第 ${retryCount++} 次重试...`);
        }
    } catch (error) {
        log.warn(`【OCR】经过多次尝试，仍然无法识别文字: ”${targetText}“,尝试点击默认中心位置`);
        await clickCenter(result.x, result.y, result.width, result.height);
        //如果有配置通知……
        notification.error(`【OCR】识别文字: “${targetText}”,发生异常`);
        throw new Error(`【OCR】识别文字时发生异常: ${error.message}`);
    }
    return { success: false };
}

function normalizeOcrText(text) {
    return String(text || "").replace(/\s+/g, "");
}

function levenshteinDistance(a, b) {
    const rows = a.length + 1;
    const cols = b.length + 1;
    const dp = Array.from({ length: rows }, () => Array(cols).fill(0));

    for (let i = 0; i < rows; i++) dp[i][0] = i;
    for (let j = 0; j < cols; j++) dp[0][j] = j;

    for (let i = 1; i < rows; i++) {
        for (let j = 1; j < cols; j++) {
            const cost = a[i - 1] === b[j - 1] ? 0 : 1;
            dp[i][j] = Math.min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost
            );
        }
    }

    return dp[a.length][b.length];
}

function ocrSimilarity(actual, target) {
    actual = normalizeOcrText(actual);
    target = normalizeOcrText(target);

    if (!actual || !target) return 0;
    if (actual.includes(target) || target.includes(actual)) return 1;

    let best = 1 - levenshteinDistance(actual, target) / Math.max(actual.length, target.length);
    if (actual.length > target.length) {
        for (let i = 0; i <= actual.length - target.length; i++) {
            const part = actual.substring(i, i + target.length);
            best = Math.max(best, 1 - levenshteinDistance(part, target) / target.length);
        }
    }

    return best;
}

function rectToOcrObject(rect) {
    if (!rect) return RecognitionObject.ocrThis;

    const x = rect.X != null ? rect.X : (rect.x != null ? rect.x : 0);
    const y = rect.Y != null ? rect.Y : (rect.y != null ? rect.y : 0);
    const width = rect.Width != null ? rect.Width : (rect.width != null ? rect.width : 0);
    const height = rect.Height != null ? rect.Height : (rect.height != null ? rect.height : 0);

    if (x === 0 && y === 0 && width === 0 && height === 0) {
        return RecognitionObject.ocrThis;
    }

    return RecognitionObject.Ocr(x, y, width, height);
}

function ocrMatch(target, rect = null, threshold = null) {
    const actualThreshold = threshold != null ? threshold : 0.75;
    const targetText = normalizeOcrText(target);
    const captureRegion = captureGameRegion();
    try {
        const resultList = captureRegion.findMulti(rectToOcrObject(rect));
        const texts = [];

        for (let result of resultList) {
            const text = normalizeOcrText(result.text);
            if (!text) continue;
            if (ocrSimilarity(text, targetText) >= actualThreshold) {
                return true;
            }
            texts.push(text);
        }

        return ocrSimilarity(texts.join(""), targetText) >= actualThreshold;
    } finally {
        captureRegion.dispose();
    }
}

async function waitForOcrMatch(target, rect = null, threshold = null, timeout = null) {
    const actualTimeout = timeout != null ? timeout : 10000;
    const interval = 1000;
    const start = Date.now();
    let retryCount = 0;

    while (Date.now() - start < actualTimeout) {
        if (ocrMatch(target, rect, threshold)) {
            return true;
        }

        retryCount++;
        await sleep(interval);
    }

    log.warn(`【OCR】等待文字匹配超时: ${target} | 重试次数: ${retryCount} | 耗时: ${Date.now() - start}ms`);
    return false;
}

// 账号列表 OCR 形近字符映射。先统一大小写，再处理常见的字母/数字混淆。
const accountOcrGlyphMap = Object.freeze({
    "0": "o", "o": "o",
    "1": "l", "i": "l", "l": "l", "|": "l",
    "2": "z", "z": "z",
    "5": "s", "s": "s",
    "8": "b", "b": "b",
    "＊": "*", "•": "*", "·": "*", "●": "*",
    "＠": "@", "．": ".", "。": "."
});

function normalizeAccountOcrText(text) {
    let normalized = String(text || "");
    if (typeof normalized.normalize === "function") {
        normalized = normalized.normalize("NFKC");
    }
    normalized = normalized.toLowerCase().replace(/\s+/g, "");
    return Array.from(normalized, glyph => accountOcrGlyphMap[glyph] || glyph).join("");
}
// 切换账号OCR模式
// ======================================================

(async function () {
    // ======================================================
    // Library functions

    var u = {}; // utilities 工具函数集合
    u.logi = function (message, args) { log.info("[下拉列表切换账号]" + message, args) };
    u.logw = function (message, args) { log.warn("[下拉列表切换账号]" + message, args) };
    u.loadTemplate = function (filePath, x /* 0 if omit */, y /* 0 if omit */, w /* maxWidth if omit */, h /* maxHeight if omit */) {
        return RecognitionObject.TemplateMatch(file.ReadImageMatSync(filePath), x, y, w, h);
    };
    u.findText = function (resList, text) {
        for (let i = 0; i < resList.count; i++) {
            let res = resList[i];
            if (res.text == text) {
                return res;
            }
        }
        return null;
    };
    u.matchUser = function (text, username) {
        if (typeof text !== "string" || typeof username !== "string") return false;

        const pattern = normalizeAccountOcrText(text);
        const target = normalizeAccountOcrText(username);
        if (pattern.length !== target.length) return false;
        for (let i = 0; i < pattern.length; i++) {
            const a = pattern[i];
            const b = target[i];
            if (a === '*' || b === '*') continue;
            if (a !== b) return false;
        }
        return true;
    };
    u.matchUserRelaxed = function (text, username) {
        if (typeof text !== "string" || typeof username !== "string") return false;

        // OCR 可能混淆大小写、形近字母/数字和掩码符号，先统一到映射表中的形式。
        const pattern = normalizeAccountOcrText(text).replace(/\*+/g, '*');
        const target = normalizeAccountOcrText(username).replace(/\*+/g, '*');

        // 如果规范化后没有通配符，则进行全等匹配
        if (!pattern.includes('*')) {
            return pattern === target;
        }

        // 获取前缀和后缀
        // split('*') 会将 "abc*def" 拆分为 ["abc", "def"]
        // 如果是 "*abc"，拆分为 ["", "abc"]；如果是 "abc*"，拆分为 ["abc", ""]
        const parts = pattern.split('*');
        const prefix = parts[0];
        const suffix = parts[parts.length - 1];

        // 匹配逻辑：
        // - 目标字符串必须以 prefix 开头
        // - 目标字符串必须以 suffix 结尾
        // - 目标字符串的长度必须足以容纳 prefix 和 suffix (避免重叠部分的逻辑错误)
        return (
            target.startsWith(prefix) &&
            target.endsWith(suffix) &&
            target.length >= (prefix.length + suffix.length)
        );
    };
    u.waitAndFindImage = async function (asset, internal = 500, timeout = 60000) {
        const start = Date.now();
        let lastLog = start;
        let endTime = start + timeout;
        while (Date.now() < endTime) {
            let captureRegion = captureGameRegion();
            let res = captureRegion.Find(asset);
            captureRegion.dispose();
            if (!res.isEmpty()) {
                return res;
            }
            if (Date.now() - lastLog >= 10000) {
                let elapsed = ((Date.now() - start) / 1000).toFixed(1);
                u.logw("等待匹配图像已持续 {0} 秒，仍在尝试寻找图像：{1}", elapsed, asset.Name);
                lastLog = Date.now();
            }
            await sleep(internal);
        }
        return null;
    }
    u.waitAndFindText = async function (text, x, y, w, h, internal = 500) {
        const start = Date.now();
        let lastLog = start;
        while (true) {
            let captureRegion = captureGameRegion();
            let resList = captureRegion.findMulti(RecognitionObject.ocr(x, y, w, h));
            captureRegion.dispose();
            if (typeof text === "string") {
                let textFound = u.findText(resList, text);
                if (textFound) {
                    return textFound;
                }
            } else if (text instanceof Array) {
                var textFound = null;
                for (let i = 0; i < text.length; i++) {
                    let textItem = text[i];
                    textFound = u.findText(resList, textItem);
                    if (!textFound) {
                        break;
                    }
                }
                if (textFound) {
                    return textFound;
                }
            }

            if (Date.now() - lastLog >= 10000) {
                let elapsed = ((Date.now() - start) / 1000).toFixed(1);
                u.logw("等待匹配图像已持续 {0} 秒，仍在尝试寻找文字：{1}", elapsed, text.toString());
                lastLog = Date.now();
            }
            await sleep(internal);
        }
    }

    // ======================================================
    // Setup

    const targetUser = settings.username;

    const assetLogoutIcon = u.loadTemplate("Assets/RecognitionObject/login_out_account.png", 1750, 900, 170, 180);
    const assetPaimonMenuIcon = u.loadTemplate("Assets/RecognitionObject/paimon_menu.png", 0, 0, 150, 150);

    // Check current state

    /**
     * 领取空月祝福
     */
    async function useBlessingOfTheWelkinMoon() {
        u.logi("开始尝试领取空月祝福");

        let captureRegion = captureGameRegion();
        let resList = captureRegion.findMulti(RecognitionObject.ocrThis);
        captureRegion.dispose();

        for (let i = 0; i < resList.count; i++) {
            let res = resList[i];
            if (res.text.includes("点击领取") || res.text.includes("空月祝福")) {
                res.click();
                await sleep(500);
                res.click();
                res.click();
                await sleep(500);
            }
        }

        let captureRegionGetReward = captureGameRegion();
        let resGetReward = captureRegionGetReward.findMulti(RecognitionObject.ocrThis);
        captureRegionGetReward.dispose();
        for (let i = 0; i < resGetReward.count; i++) {
            let res = resGetReward[i];
            if (res.text.includes("点击") || res.text.includes("空白") || res.text.includes("获得")) {
                res.click();
                await sleep(500);
            }
        }

        u.logi("空月祝福领取成功");
    }

    async function waitAndDetermineCurrentView() {
        u.logi("开始判断当前画面状态");
        while (true) {
            let captureRegion = captureGameRegion();
            let res = captureRegion.Find(assetLogoutIcon);
            let logoutIconFound = !res.isEmpty();

            if (logoutIconFound) {
                let resList = captureRegion.findMulti(RecognitionObject.ocr(850, 970, 220, 100));
                captureRegion.dispose();
                if (u.findText(resList, "点击进入")) {
                    u.logi("检测到目前处于登录界面");
                    return false;
                }
            }

            // 尝试领取空月祝福
            await useBlessingOfTheWelkinMoon();

            // Not in the login screen, check if is in the game main menu.
            let paimonIcon = captureRegion.Find(assetPaimonMenuIcon);
            captureRegion.dispose();
            if (!paimonIcon.isEmpty()) {
                u.logi("检测到目前处于游戏主界面");
                return true;
            }

            // Not in the main game screen either, wait and try again.
            u.logi("未检测到登出按钮或派蒙菜单图标，可能处于游戏中，等待状态变化");
            genshin.blessingOfTheWelkinMoon();
            moveMouseTo(960, 0);
            await sleep(100);
            middleButtonClick();
            genshin.returnMainUi();
            await sleep(4900);
        }
    }

    async function stateReturnToGenshinGate() {
        const assetPaimonCancelIcon = u.loadTemplate("Assets/RecognitionObject/paimon_cancel.png", 0, 0, 100, 100);

        while (true) {
            let paimonIcon = await u.waitAndFindImage(assetPaimonMenuIcon, 500, 1000);
            if (!paimonIcon) {
                u.logi("检测到派蒙菜单图标不存在，可能已开启菜单，进入登出按钮识别流程");
                break;
            }
            moveMouseTo(960, 0);
            await sleep(100);
            middleButtonClick();
            keyPress("VK_ESCAPE");
            u.logi("已按下ESC键，打开派蒙菜单");
            await sleep(1000);
        }

        // 识别派蒙菜单，点击登出按钮
        await u.waitAndFindImage(assetPaimonCancelIcon);
        // u.logi("点击登出按钮");
        click(50, 1024);

        // 退出至登录界面
        let btnExitToLogin = await u.waitAndFindText("退出至登录界面", 680, 380, 540, 340);
        // u.logi("检测到\"退出至登录界面\"按钮，点击");
        // btnExitToLogin.DrawSelf("ExitToLoginBtn");
        btnExitToLogin.Click();
    }

    async function stateLogout() {
        u.logi("开始登出");

        let btnLogout = await u.waitAndFindImage(assetLogoutIcon);
        // u.logi("识别到登出按钮，点击");
        btnLogout.DrawSelf("LogoutBtn");
        btnLogout.Click();

        const assetQuitTextButton = u.loadTemplate("Assets/RecognitionObject/out_account.png", 680, 380, 1220, 700);
        let btnQuit = await u.waitAndFindImage(assetQuitTextButton, 200);
        // u.logi("识别到退出按钮，点击");
        // btnQuit.DrawSelf("QuitBtn");
        btnQuit.Click();
    };

    async function stateChangeUser() {
        u.logi("开始切换账号");
        await u.waitAndFindText(["进入游戏", "登录其他账号"], 680, 380, 540, 340, 200);

        const assetSelectUserDropDownIcon = u.loadTemplate("Assets/RecognitionObject/caret.png", 680, 380, 1220, 700);
        let captureRegion = captureGameRegion();
        let res = captureRegion.Find(assetSelectUserDropDownIcon);
        captureRegion.dispose();
        if (res.isEmpty()) {
            u.logi("未找到下拉菜单图标，点击硬编码的坐标(960, 500)展开菜单");
            click(960, 500);
        } else {
            // u.logi("识别到下拉菜单，点击");
            // res.DrawSelf("UserDropdown");
            res.Click();
        }

        u.logi("开始从下拉列表选择账号");
        let selectedUser = null;
        const recognizedUserTexts = [];
        {
            const start = Date.now();
            // 最多识别8秒，超时后输出候选文本并明确报错。
            while (selectedUser == null && Date.now() - start <= 8000) {
                await sleep(500);

                let captureRegion = captureGameRegion();
                let resList = captureRegion.findMulti(RecognitionObject.ocr(680, 540, 540, 500));
                captureRegion.dispose();
                for (let i = 0; i < resList.count; i++) {
                    let res = resList[i];
                    const recognizedText = typeof res.text === "string" ? res.text : "";
                    if (recognizedText && !recognizedUserTexts.includes(recognizedText)) {
                        recognizedUserTexts.push(recognizedText);
                    }

                    let user = u.matchUserRelaxed(recognizedText, targetUser) || u.matchUser(recognizedText, targetUser);
                    if (user) {
                        selectedUser = res;
                        break;
                    } else {
                        u.logw("当前匹配文本：{0}", recognizedText);
                    }
                }
            }
        }

        if (selectedUser == null) {
            const candidateText = recognizedUserTexts.length > 0 ? recognizedUserTexts.join(" | ") : "未识别到任何账号文本";
            const errorMessage = `未在下拉列表中识别到目标账号，OCR候选：${candidateText}`;
            log.error(`[下拉列表切换账号]${errorMessage}`);
            notification.error(errorMessage);
            throw new Error(errorMessage);
        }

        u.logi("识别到目标账号：{0}", selectedUser.text);
        selectedUser.DrawSelf("SelectUser");
        selectedUser.Click();

        await sleep(500);
        {
            let captureRegion = captureGameRegion();
            let btnEnterGame = captureRegion.DeriveCrop(684, 598, 552, 66);
            btnEnterGame.Click();
            captureRegion.dispose();
            btnEnterGame.dispose();
            // btnEnterGame.DrawSelf("EnterGameBtn");
            // u.logi("已点击\"进入游戏\"按钮，完成账号选择。");
        }
    }

    async function stateEnterGame() {
        // u.logi("开始进入游戏，等待游戏加载。");
        let textClickToStart = await u.waitAndFindText("点击进入", 850, 970, 220, 100);
        // u.logi("已识别到\"点击进入\"文本，点击鼠标进入游戏。");
        textClickToStart.DrawSelf("ClickToStart");
        textClickToStart.Click();
    }

    // ======================================================
    // Main flow

    if (await check()) {
        log.info("当前UID与设置UID相同，无需切换账号。");
        return
    }
    if (settings.Modes == "下拉列表" && !settings.GlobalAccount) {
        await DropDownMode();
    } else if (settings.Modes == "账号+密码+OCR" && !settings.GlobalAccount) {
        await OcrMode();
    } else if (settings.Modes == "B服切换另一个账号匹配+键鼠") {
        await BilibiliMatchAndKeyboardMouseMode();
    } else if (settings.Modes == "账号+密码+OCR" && settings.GlobalAccount) {
        await GlobalOcrMode();
    } else if (settings.Modes == "下拉列表" && settings.GlobalAccount) {
        await GlobalDropDownMode();
    } else {
        log.info("尖尖哇嘎乃")
    }

    // 下拉列表模式
    async function DropDownMode() {
        const isInGame = await waitAndDetermineCurrentView();
        if (isInGame) {
            await stateReturnToGenshinGate();
            await sleep(1000);
        }
        await stateLogout();
        await sleep(500);
        await stateChangeUser();
        await sleep(500);
        await stateEnterGame();
        await sleep(20000);
        await waitAndDetermineCurrentView();

    }

    // 国际服下拉列表模式
    async function GlobalDropDownMode() {
        const script_mode = "国际服下拉列表模式";
        const page = new BvPage();
        setGameMetrics(1920, 1080, 1);
        const isInGame = await waitAndDetermineCurrentView();
        if (isInGame) {
            await stateReturnToGenshinGate();
            await sleep(1000);
        }
        await waitForOcrMatch("开始游戏");
        await matchImgAndClick(login_out_account, "登录页的右下角退出按钮");
        await waitForOcrMatch("切换账号");
        await matchImgAndClick(confirm_switch_account, "确认切换账号");
        // 检测是否弹出保存登陆记录弹框
        if (await waitForOcrMatch("退出并", new OpenCvSharp.OpenCvSharp.Rect(0, 0, 1920, 1080), 0.8, 1000)) {
            await matchImgAndClick(save_login_info, "保留登陆记录");
            await sleep(500);
            await matchImgAndClick(confirm_switch_account, "确认切换账号");
            await sleep(500);
        }
        await stateChangeUser();
        await sleep(500);
        // 换服务器操作
        if (settings.Servers && (settings.Servers !== "不切换服务器" || settings.Servers == "")) {
            await waitForOcrMatch("开始游戏");
            log.info("正在更换服务器")
            await matchImgAndClick(switch_server, "更换服务器");
            let serversMatched = true;
            if (settings.Servers == "Asia") {
                await matchImgAndClick(asia_server, "亚服");
            } else if (settings.Servers == "Europe") {
                await matchImgAndClick(europe_server, "欧服");
            } else if (settings.Servers == "America") {
                await matchImgAndClick(america_server, "美服");
            } else if (settings.Servers == "TW,HK,MO") {
                await matchImgAndClick(twhkmo_server, "台港澳");
            } else {
                log.info("尖尖哇嘎乃")
                serversMatched = false;
            }
            if (serversMatched) {
                await matchImgAndClick(confirm_button, "确认换服");
            }
        }
        await keyPress("VK_ESCAPE");
        await waitForOcrMatch("开始游戏");
        await click(960, 640);
        await page.Wait(5000);
        log.info('等待提瓦特大门加载');
        await waitForOcrMatch("点击进入");
        await click(960, 640);
        // 可能登录账号的时候出现月卡提醒，则先点击一次月卡。
        await genshin.blessingOfTheWelkinMoon();
        await page.Wait(1000);
        await genshin.returnMainUi();
        // 如果配置了通知
        notification.send("账号【" + settings.username + "】切换成功");
    }

    // OCR模式 对应：账号+密码+OCR
    async function OcrMode() {
        const script_mode = "OCR模式";
        setGameMetrics(1920, 1080, 1);
        // 如果切换账号是第一个脚本，则有可能出现月卡选项
        try {
            keyDown("VK_MENU");
            await sleep(500);
            for (let i = 0; i <= 4; i++) {
                await click(960, 864);
                await sleep(1000);
            }
        } finally {
            keyUp("VK_MENU");
        }
        await genshin.returnMainUi();

        await keyPress("VK_ESCAPE");
        await sleep(500);
        try {
            await matchImgAndClick(pm_out, "左下角退出门");
            await matchImgAndClick(out_to_login, "退出至登陆页面");
            //这一步根据 电脑配置和当前网络情况不同休眠时间不同，建议实际运行之后，如果有日志 ： 第x次 识别失败，就适当增加休眠时间
            await sleep(9000);
            await matchImgAndClick(login_out_account, "登录页的右下角退出按钮");
            await matchImgAndClick(out_account, "退出当前账号");
            await recognizeTextAndClick("登录其他账号", RecognitionObject.Ocr(300, 200, 1200, 800), 5000);
            await sleep(1000);
            await matchImgAndClick(input_phone_or_email, "填写邮箱/手机号");
            await inputText(settings.username);
            await sleep(1000);
            await matchImgAndClick(input_password, "填写密码");
            await inputText(settings.password);
            await sleep(1000);
            //按下回车登录账号，弹出用户协议对话框
            await keyPress("VK_RETURN");
            //点击回车后，等待特瓦特大门加载
            await matchImgAndClick(agree, "同意用户协议");
            //如果当天上下线次数过于频繁
            for (let i = 1; i <= 2; i++) {
                const ro = captureGameRegion();
                let verify = ro.Find(login_verification.template);
                ro.dispose();
                //等待1s避免循环速度过快
                await sleep(1000);
                if (verify.isExist()) {
                    //这里可配置通知方法
                    notification.error(`${script_mode}触发人机验证，请手动登录。===待切换账号：${settings.username}`);
                    log.error(`${script_mode}触发人机验证，请手动登录。===待切换账号：${settings.username}`);
                }
            }
            /**
             * 根据不同网络环境和电脑配置，此操作可能会将领取月卡操作取代，但是不影响使用
             * 如果发现卡在这一步，请适当延长sleep时间
             */
            await sleep(8000);
            await recognizeTextAndClick("点击进入", RecognitionObject.Ocr(862, 966, 206, 104), 5000);
            await sleep(15000);

            //可能登录账号的时候出现月卡提醒，则先点击一次月卡。
            await sleep(2000);
            keyDown("VK_MENU");
            await sleep(500);
            for (let i = 0; i <= 4; i++) {
                await click(960, 864);
                await sleep(1000);
            }
            //keyUp("VK_MENU");
            await genshin.returnMainUi();
            await sleep(1000);
            // 如果配置了通知
            notification.send("账号【" + settings.username + "】切换成功");
        } catch (error) {
            log.error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
            //如果发生错误，则发送通知
            notification.error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
            throw new Error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
        } finally {
            keyUp("VK_MENU");
        }
    }

    // B服切换匹配+键鼠模式 对应：B服切换另一个账号匹配+键鼠
    async function BilibiliMatchAndKeyboardMouseMode() {
        const script_mode = "B服切换匹配+键鼠模式";
        setGameMetrics(1920, 1080, 1);
        // 如果切换账号是第一个脚本，则有可能出现月卡选项
        try {
            keyDown("VK_MENU");
            await sleep(500);
            for (let i = 0; i <= 4; i++) {
                await click(960, 864);
                await sleep(1000);
            }
        } finally {
            keyUp("VK_MENU");
        }
        await genshin.returnMainUi();

        await keyPress("VK_ESCAPE");
        await sleep(500);
        try {
            await matchImgAndClick(pm_out, "左下角退出门");
            await matchImgAndClick(out_to_login, "退出至登陆页面");
            //这一步根据 电脑配置和当前网络情况不同休眠时间不同，建议实际运行之后，如果有日志 ： 第x次 识别失败，就适当增加休眠时间
            await sleep(7000);

            //登录其他账号
            click(1135, 478);
            await sleep(1000);

            //点击用户名
            click(963, 635);
            await sleep(500);

            //点击登录
            click(963, 635);
            await sleep(500);

            //登录其他账号
            click(1135, 478);
            await sleep(1000);

            //取消点击用户名（确保能登录）
            click(963, 400);
            await sleep(500);

            //点击登录
            click(963, 635);
            await sleep(500);

            //如果当天上下线次数过于频繁
            for (let i = 1; i <= 2; i++) {
                const ro = captureGameRegion();
                let verify = ro.Find(login_verification.template);
                ro.dispose();
                //等待1s避免循环速度过快
                await sleep(1000);
                if (verify.isExist()) {
                    //这里可配置通知方法
                    notification.error(`${script_mode}触发人机验证，请手动登录。===待切换账号：${settings.username}`);
                    log.error(`${script_mode}触发人机验证，请手动登录。===待切换账号：${settings.username}`);
                }
            }
            /**
             * 根据不同网络环境和电脑配置，此操作可能会将领取月卡操作取代，但是不影响使用
             * 如果发现卡在这一步，请适当延长sleep时间
             */
            await sleep(6500);
            await recognizeTextAndClick("点击进入", RecognitionObject.Ocr(862, 966, 206, 104), 5000);
            await sleep(12000);

            //可能登录账号的时候出现月卡提醒，则先点击一次月卡。
            await sleep(2000);
            keyDown("VK_MENU");
            await sleep(500);
            for (let i = 0; i <= 4; i++) {
                await click(960, 864);
                await sleep(1000);
            }
            //keyUp("VK_MENU");
            await genshin.returnMainUi();
            await sleep(1000);
            // 如果配置了通知
            notification.send("账号【" + settings.username + "】切换成功");
        } catch (error) {
            log.error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
            //如果发生错误，则发送通知
            notification.error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
            throw new Error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
        } finally {
            keyUp("VK_MENU");
        }
    }

    // 国际服OCR模式 对应：国际服账号+密码+OCR
    async function GlobalOcrMode() {
        const script_mode = "国际服OCR模式";
        const page = new BvPage();
        setGameMetrics(1920, 1080, 1);
        await genshin.blessingOfTheWelkinMoon();
        await genshin.returnMainUi();

        await keyPress("VK_ESCAPE");
        await sleep(500);
        try {
            await matchImgAndClick(pm_out, "左下角退出门");
            await matchImgAndClick(out_to_login, "退出至登陆页面");
            await waitForOcrMatch("开始游戏");
            await matchImgAndClick(login_out_account, "登录页的右下角退出按钮");
            await waitForOcrMatch("切换账号");
            await matchImgAndClick(confirm_switch_account, "确认切换账号");
            // 检测是否弹出保存登陆记录弹框
            if (await waitForOcrMatch("退出并", new OpenCvSharp.OpenCvSharp.Rect(0, 0, 1920, 1080), 0.8, 1000)) {
                await matchImgAndClick(save_login_info, "保留登陆记录");
                await sleep(500);
                await matchImgAndClick(confirm_switch_account, "确认切换账号");
                await sleep(500);
            }
            await recognizeTextAndClick("登录其他账号", RecognitionObject.Ocr(300, 200, 1200, 800), 8000);
            await sleep(1000);
            await matchImgAndClick(input_email_username, "输入邮箱/用户名");
            await inputText(settings.username);
            await sleep(1000);
            await matchImgAndClick(input_password, "输入密码");
            await inputText(settings.password);
            await sleep(1000);
            // 按下回车登录账号，弹出用户协议对话框
            await keyPress("VK_RETURN");
            // await matchImgAndClick(agree, "同意用户协议");
            // 当天上下线次数过于频繁弹验证码
            for (let i = 1; i <= 5; i++) {
                const ro = captureGameRegion();
                let verify = ro.Find(login_verification.template);
                ro.dispose();
                await sleep(1000);
                if (verify.isExist()) {
                    notification.error(`${script_mode}触发人机验证，请手动登录。===待切换账号：${settings.username}`);
                    log.error(`${script_mode}触发人机验证，请手动登录。===待切换账号：${settings.username}`);
                }
            }
            // 换服务器操作
            if (settings.Servers && (settings.Servers !== "不切换服务器" || settings.Servers == "")) {
                await waitForOcrMatch("开始游戏");
                log.info("正在更换服务器")
                await matchImgAndClick(switch_server, "更换服务器");
                let serversMatched = true;
                if (settings.Servers == "Asia") {
                    await matchImgAndClick(asia_server, "亚服");
                } else if (settings.Servers == "Europe") {
                    await matchImgAndClick(europe_server, "欧服");
                } else if (settings.Servers == "America") {
                    await matchImgAndClick(america_server, "美服");
                } else if (settings.Servers == "TW,HK,MO") {
                    await matchImgAndClick(twhkmo_server, "台港澳");
                } else {
                    log.info("尖尖哇嘎乃")
                    serversMatched = false;
                }
                if (serversMatched) {
                    await matchImgAndClick(confirm_button, "确认换服");
                }
            }
            await keyPress("VK_ESCAPE");
            await waitForOcrMatch("开始游戏");
            await click(960, 640);
            await page.Wait(5000);
            log.info('等待提瓦特大门加载');
            await waitForOcrMatch("点击进入");
            await click(960, 640);
            // 可能登录账号的时候出现月卡提醒，则先点击一次月卡。
            await genshin.blessingOfTheWelkinMoon();
            await page.Wait(1000);
            await genshin.returnMainUi();
            // 如果配置了通知
            notification.send("账号【" + settings.username + "】切换成功");
        } catch (error) {
            log.error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
            //如果发生错误，则发送通知
            notification.error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
            throw new Error(`${script_mode}脚本执行过程中发生错误：${error.message}`);
        } finally {
            keyUp("VK_MENU");
        }
    }
})();

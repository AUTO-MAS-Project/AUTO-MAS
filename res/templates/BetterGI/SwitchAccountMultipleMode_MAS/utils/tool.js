const commonPath = 'Assets/RecognitionObject/'
const commonMap = new Map([
    ['main_ui', {
        path: `${commonPath}`,
        name: 'paimon_menu',
        type: '.png',
    }],
])
const genshinJson = {
    width: 1920,//genshin.width,
    height: 1080,//genshin.height,
}

/**
 * 根据键值获取JSON路径
 * @param {string} key - 要查找的键值
 * @returns {any} 返回与键值对应的JSON路径值
 */
export function getJsonPath(key) {
    return commonMap.get(key); // 通过commonMap的get方法获取指定键对应的值
}

export function saveOnlyNumber(str) {
    str = str ? str : '';
    // 使用正则表达式匹配字符串中的所有数字
    // \d+ 匹配一个或多个数字
    // .join('') 将匹配到的数字数组连接成一个字符串
    // parseInt 将连接后的字符串转换为整数
    return parseInt(str.match(/\d+/g).join(''));
}

// 判断是否在主界面的函数
export const isInMainUI = () => {
    // let name = '主界面'
    let main_ui = getJsonPath('main_ui');
    // 定义识别对象
    let paimonMenuRo = RecognitionObject.TemplateMatch(
        file.ReadImageMatSync(`${main_ui.path}${main_ui.name}${main_ui.type}`),
        0,
        0,
        genshinJson.width / 3.0,
        genshinJson.width / 5.0
    );
    let captureRegion = captureGameRegion();
    let res = captureRegion.find(paimonMenuRo);
    captureRegion.Dispose()
    return !res.isEmpty();
};

export async function toMainUi() {
    let ms = 1000
    let index = 1
    await sleep(ms);
    while (!isInMainUI()) {
        await sleep(ms);
        await genshin.returnMainUi(); // 如果未启用，则返回游戏主界面
        await sleep(ms);
        if (index > 3) {
            throw new Error(`多次尝试返回主界面失败`);
        }
        index += 1
    }

}

export async function compareUid(UID = settings.uid) {
    let uid = await genshin.uid()
    let setUid = 0
    try {
        setUid = saveOnlyNumber(UID)
    } catch (e) {
        // log.warn(`UID未设置`)
    }
    let compare = uid === setUid
    if (compare) {
        log.info(`[OCR识别UID]识别结果: {uid} 与设置UID相同`, uid);
    }
    return compare
}

export async function checkUid() {
    let reJson = {
        inMainUI: false,
        isUid: false
    }
    if (isInMainUI()) {
        reJson.isUid = await compareUid()
    }
    return reJson
}

export async function check() {
    let check = false
    if (settings.uid) {
        try {
            await toMainUi();
        } catch (e) {
            log.warn("多次尝试返回主界面失败")
        }
        let checkJson = await checkUid()
        if ((!checkJson.inMainUI) && (!checkJson.isUid)) {
            //尝试直接识别
            checkJson.isUid = await compareUid()
        }
        check = checkJson.isUid
    }
    return check
}


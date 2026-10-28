/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type MaaFWConfig_Update = {
    /**
     * 项目自动更新时机：Off 不更新 / BeforeRun 运行前 / AfterRun 全部用户跑完后。 由 embedded_manager 在用户任务之外执行，耗时不计入 Run.RunTimeLimit。
     */
    AutoUpdateMode?: ('Off' | 'BeforeRun' | 'AfterRun' | null);
    /**
     * 更新渠道只有稳定版与测试版，默认稳定版，要测试版由用户手动切。 不给「跟随全局」：全局那个 Update.Channel 是 MAS 自身的发布通道， 和脚本本体的版本档位是两回事，串在一起只会让人猜。 Mirror 酱还支持 channel=alpha，**故意不开放**——那是项目方的内部 验证档，稳定性无保证，而这里更新的是用户日常在跑的脚本本体。 这两个值必须与前端 updateChannelOptions 和 schema 的 Literal 一致： 三处任一多给一档，用户选了就会 422 或被静默纠回默认值。 旧配置里的空串现在是非法值，会被 correct() 回退成 options[0]， 即 stable——这里的顺序同样不能随意调换。
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * Mirror 酱 CDK，由用户自己填。**不做全局兜底**：全局那个服务的是 AUTO-MAS 自身的更新，和脚本本体不是一回事，串在一起只会让人猜 自己在用哪个。选 Mirror 酱作为下载源时这一项必填。 （合并逻辑见 tools/embedded/update_credentials.py）
     */
    MirrorChyanCDK?: (string | null);
    /**
     * 脚本级网络代理，给这个项目的更新包下载与运行环境安装（uv / pip、 binding 源码兜底）用。与 CDK / 渠道不同，这一项**留空就跟随全局** `Update.ProxyAddress`（设置 → 其他 → 网络代理），填了就只走自己的： 代理解决的是「这台机器连不连得上」，多数人全局一份就够，个别项目 的源在别的网络才需要单独指。格式同全局项，`host:port` 不带协议时 补 `http://`（合并逻辑见 tools/embedded/update_credentials.py）。
     */
    ProxyAddress?: (string | null);
    /**
     * 更新包的下载源，由用户显式选择——**不做自动分流**。 版本检查始终走 Mirror 酱（无 CDK 也能查），但下载去哪由这一项决定： 选 Mirror 酱就必须自己填 CDK，CDK 不可用时明确报错，不悄悄换成 GitHub——用户得知道自己在从哪下载，出问题才查得动。 默认 GitHub：零配置即可用，与全局 Update.Source 的默认值一致。 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**， 不是这里的默认值。旧配置里 Source 是空串（旧默认），加载时会被 correct 成第一项并写回磁盘——GitHub 必须排在前面，否则所有既有 脚本会被静默改成 Mirror 酱，而它们并没有 CDK，每次运行都更新失败。
     */
    Source?: ('GitHub' | 'MirrorChyan' | null);
};


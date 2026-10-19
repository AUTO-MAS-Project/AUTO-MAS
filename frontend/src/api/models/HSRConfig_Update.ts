/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type HSRConfig_Update = {
    /**
     * 外部脚本（M7A / SRA）的自动更新。默认关闭：这两个是用户自己安装、 自带更新器的第三方工具，未经开启就改写它们的目录属于越界；停留在 某个旧版也是真实需求。 只有 AfterRun 一档，没有 BeforeRun：更新的收益本来就落在下一次运行 上，没有理由让当前这轮先等一个 170–750MB 的下载。想立刻更新走配置 页的手动按钮。留成枚举而非布尔，是为了日后要加档时不必做 bool→enum 迁移（MaaFW 正为此背着一个废弃字段）。 选项顺序有意义：OptionsValidator.correct() 回退的是 **options[0]**， 不是这里的默认值，Off 必须排在最前。
     */
    AutoUpdateMode?: ('Off' | 'AfterRun' | null);
    /**
     * 更新渠道，两个引擎共用。Mirror 酱还支持 alpha，**故意不开放**—— 那是项目方的内部验证档。这两个值必须与前端选项和 schema 的 Literal 一致，三处任一多给一档，用户选了就会 422 或被静默纠回默认值。
     */
    Channel?: ('stable' | 'beta' | null);
    /**
     * 下载源按引擎拆开：两者可用的源本就不同，共用一项给不出不同默认值。 版本检查恒走 Mirror 酱的免 CDK 接口（自建站没有 latest 接口，只能用 tag 拼 URL，靠这条口径补上）；这里只决定字节从哪来，且**不做自动 分流**——选了 Mirror 酱而 CDK 不可用时报明原因并跳过，不悄悄换成 GitHub，用户得知道自己在从哪下载。 M7A 没有上 AUTO-MAS 自建站，所以只有两个源，默认 GitHub。
     */
    M7ASource?: ('GitHub' | 'MirrorChyan' | null);
    /**
     * Mirror 酱 CDK，由用户自己填，**不做全局兜底**：全局那个服务的是 AUTO-MAS 自身的更新，和外部脚本不是一回事，串在一起只会让人猜自己 在用哪个。选 Mirror 酱作为下载源时这一项必填。
     */
    MirrorChyanCDK?: (string | null);
    /**
     * SRA 默认自建站：免 CDK、不限流、sha256 与 GitHub 逐字节一致，且 SRA 上游 CI 会主动往这里推送，其自带更新器也有 AUTO-MAS 这一档。
     */
    SRASource?: ('AutoSite' | 'GitHub' | 'MirrorChyan' | null);
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type M9AConfig_EmbeddedInput = {
    /**
     * 跟随来源目录（开发者模式），默认关。开着时每次运行前比一下来源目录（投影会带走的 文件的路径 + 大小 + 修改时间），变了就重新导入到这个脚本自己的私有渠道（不比版本、 不与同项目其它脚本共用版本），不做项目更新；关掉后回到 Update.Channel 的组。 见 tools/embedded/embedded_project.py「跟随来源目录」一节。
     */
    FollowSource?: (boolean | null);
    /**
     * 导入时间，仅展示；空值表示尚未导入
     */
    ImportedAt?: (string | null);
    /**
     * 投影报告（省下多少、外壳家族、排除条数与原因），JSON 字符串
     */
    Report?: (string | null);
    /**
     * 由 AUTO-MAS 内嵌一份按 interface 白名单投影的副本来运行。副本在 data/mfw/<脚本 uuid 前 12 位>/，由脚本 ID 推出、不进配置、用户不可手改； Info.Path 继续存用户选的来源目录。更新落地时同样只写白名单内的条目。 导入时来源的 interface 版本，仅展示
     */
    SourceVersion?: (string | null);
};


/* generated using openapi-typescript-codegen -- do not edit */
/* istanbul ignore file */
/* tslint:disable */
/* eslint-disable */
export type ComboBoxItem = {
    /**
     * 展示值
     */
    label: string;
    /**
     * 实际值
     */
    value: (string | null);
    /**
     * 展示文案的词表键；有值时前端优先按界面语言翻译，缺省回退 label
     */
    labelKey?: (string | null);
    /**
     * 选项类别；前端据此区分队列/脚本任务，不依赖 label 文案前缀
     */
    kind?: ('placeholder' | 'queue' | 'script' | 'fixed' | null);
    /**
     * 脚本类型键（kind=script 时给出，前端按词表显示类型名）
     */
    scriptType?: (string | null);
    /**
     * 实体名（队列名/脚本名）；kind=queue/script 时给出，前端据此拼接本地化前缀
     */
    name?: (string | null);
};


const ELEMENT_TAG = "auto-mas-ok-script-workspace";

function cloneValue(value) {
  if (value === undefined || value === null) {
    return value;
  }
  return JSON.parse(JSON.stringify(value));
}

function isRecord(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function sameValue(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

function getPath(value, path, fallback) {
  if (!isRecord(value) || !path) {
    return fallback;
  }
  if (Object.prototype.hasOwnProperty.call(value, path)) {
    return value[path];
  }

  let current = value;
  for (const segment of path.split(".").filter(Boolean)) {
    if (
      !isRecord(current) ||
      !Object.prototype.hasOwnProperty.call(current, segment)
    ) {
      return fallback;
    }
    current = current[segment];
  }
  return current === undefined ? fallback : current;
}

function setPath(value, path, nextValue) {
  const result = cloneValue(value) || {};
  if (!path) {
    return result;
  }
  if (Object.prototype.hasOwnProperty.call(result, path)) {
    result[path] = nextValue;
    return result;
  }

  const segments = path.split(".").filter(Boolean);
  let current = result;
  for (const segment of segments.slice(0, -1)) {
    if (!isRecord(current[segment])) {
      current[segment] = {};
    }
    current = current[segment];
  }
  current[segments[segments.length - 1]] = nextValue;
  return result;
}

function createElement(tagName, options = {}) {
  const element = document.createElement(tagName);
  if (options.className) {
    element.className = options.className;
  }
  if (options.text !== undefined) {
    element.textContent = options.text;
  }
  if (options.title) {
    element.title = options.title;
  }
  if (options.role) {
    element.setAttribute("role", options.role);
  }
  return element;
}

function normalizeFields(config) {
  if (Array.isArray(config.fieldSchema) && config.fieldSchema.length > 0) {
    return config.fieldSchema;
  }
  if (!Array.isArray(config.fields)) {
    return [];
  }
  return config.fields.map((field) => ({
    path: field.name,
    label: field.label || field.name,
    description: field.description || "",
    control: field.type === "bool" ? "switch" : field.type || "text",
    valueType:
      field.type === "bool"
        ? "boolean"
        : field.type === "int"
          ? "integer"
          : field.type === "float"
            ? "number"
            : field.type === "json"
              ? "object"
              : field.type === "list"
                ? "array"
                : "string",
    choices: Array.isArray(field.options)
      ? field.options.map((value) => ({ value, label: String(value) }))
      : [],
    default: field.value,
    hasDefault: field.value !== undefined,
    min: field.min,
    max: field.max,
    step: field.step,
    section: field.section,
    sectionPriority: field.sectionPriority,
    priority: field.priority,
    advanced: Boolean(field.advanced),
  }));
}

function parsePluginError(error) {
  const fallback = error instanceof Error ? error.message : String(error);
  const start = fallback.indexOf("{");
  if (start >= 0) {
    try {
      const payload = JSON.parse(fallback.slice(start));
      if (isRecord(payload)) {
        return payload;
      }
    } catch {
      // Plugin API only exposes HTTP failures as Error messages.
    }
  }
  return { message: fallback, errors: [], drafts: [] };
}

class OkScriptWorkspace extends HTMLElement {
  constructor() {
    super();
    this._connected = false;
    this._requestSerial = 0;
    this._listenerController = null;
    this.state = {
      loadingTargets: false,
      loadingConfigs: false,
      saving: false,
      targets: [],
      selectedScriptId: "",
      selectedUserId: "",
      configs: [],
      originals: {},
      drafts: {},
      selectedFilename: "",
      error: "",
      notice: "",
      validationErrors: [],
      validationDrafts: [],
      rawJson: {},
    };
  }

  connectedCallback() {
    if (this._connected) {
      return;
    }
    this._connected = true;
    this.render();
    void this.loadTargets();
  }

  disconnectedCallback() {
    this._connected = false;
    this._requestSerial += 1;
    this._listenerController?.abort();
    this._listenerController = null;
  }

  async callPlugin(path, payload) {
    const api = window.pluginAPI;
    if (!api || typeof api.call !== "function") {
      throw new Error("插件页面运行环境不可用");
    }
    const response =
      payload === undefined
        ? await api.call(path)
        : await api.call(path, payload);
    if (!isRecord(response) || response.code !== 200) {
      throw new Error(
        isRecord(response)
          ? String(response.message || "插件接口调用失败")
          : "插件接口返回无效",
      );
    }
    return response;
  }

  listen(element, type, listener) {
    element.addEventListener(type, listener, {
      signal: this._listenerController.signal,
    });
  }

  resetListeners() {
    this._listenerController?.abort();
    this._listenerController = new AbortController();
  }

  beginRequest() {
    this._requestSerial += 1;
    return this._requestSerial;
  }

  isCurrentRequest(serial) {
    return this._connected && serial === this._requestSerial;
  }

  selectedTarget() {
    return (
      this.state.targets.find(
        (target) => target.id === this.state.selectedScriptId,
      ) || null
    );
  }

  selectedConfig() {
    return (
      this.state.configs.find(
        (config) => config.filename === this.state.selectedFilename,
      ) || null
    );
  }

  changedConfigs() {
    const changed = {};
    for (const [filename, draft] of Object.entries(this.state.drafts)) {
      if (!sameValue(draft, this.state.originals[filename])) {
        changed[filename] = cloneValue(draft);
      }
    }
    return changed;
  }

  hasChanges() {
    return Object.keys(this.changedConfigs()).length > 0;
  }

  resetConfigState() {
    this.state.configs = [];
    this.state.originals = {};
    this.state.drafts = {};
    this.state.selectedFilename = "";
    this.state.validationErrors = [];
    this.state.validationDrafts = [];
    this.state.rawJson = {};
  }

  async loadTargets() {
    const serial = this.beginRequest();
    this.state.loadingTargets = true;
    this.state.error = "";
    this.state.notice = "";
    this.render();

    try {
      const response = await this.callPlugin("ok-script/workspace/targets");
      if (!this.isCurrentRequest(serial)) {
        return;
      }
      const scripts =
        isRecord(response.data) && Array.isArray(response.data.scripts)
          ? response.data.scripts
          : [];
      this.state.targets = scripts;

      const current =
        scripts.find((target) => target.id === this.state.selectedScriptId) ||
        scripts[0];
      this.state.selectedScriptId = current?.id || "";
      this.state.selectedUserId = current?.users?.some(
        (user) => user.id === this.state.selectedUserId,
      )
        ? this.state.selectedUserId
        : current?.users?.[0]?.id || "";
      this.resetConfigState();
      this.state.notice =
        scripts.length === 0 ? "未找到已保存的 ok-script 脚本" : "";
      this.state.loadingTargets = false;
      this.render();

      if (this.state.selectedScriptId && this.state.selectedUserId) {
        void this.loadConfigs();
      }
    } catch (error) {
      if (!this.isCurrentRequest(serial)) {
        return;
      }
      this.state.targets = [];
      this.resetConfigState();
      this.state.error =
        parsePluginError(error).message || "读取工作区目标失败";
      this.render();
    } finally {
      if (this.isCurrentRequest(serial)) {
        this.state.loadingTargets = false;
        this.render();
      }
    }
  }

  async loadConfigs() {
    if (!this.state.selectedScriptId || !this.state.selectedUserId) {
      return;
    }
    const serial = this.beginRequest();
    this.state.loadingConfigs = true;
    this.state.error = "";
    this.state.notice = "";
    this.resetConfigState();
    this.render();

    try {
      const response = await this.callPlugin("ok-script/configs/list", {
        script_id: this.state.selectedScriptId,
        user_id: this.state.selectedUserId,
      });
      if (!this.isCurrentRequest(serial)) {
        return;
      }
      const configs = Array.isArray(response.data) ? response.data : [];
      const originals = {};
      const drafts = {};
      for (const config of configs) {
        originals[config.filename] = cloneValue(config.currentData || {});
        drafts[config.filename] = cloneValue(config.currentData || {});
      }
      this.state.configs = configs;
      this.state.originals = originals;
      this.state.drafts = drafts;
      this.state.selectedFilename = configs[0]?.filename || "";
      this.state.notice =
        configs.length === 0
          ? String(response.message || "暂无可编辑配置文件")
          : "";
      this.render();
    } catch (error) {
      if (!this.isCurrentRequest(serial)) {
        return;
      }
      this.state.error = parsePluginError(error).message || "读取配置文件失败";
      this.render();
    } finally {
      if (this.isCurrentRequest(serial)) {
        this.state.loadingConfigs = false;
        this.render();
      }
    }
  }

  selectScript(scriptId) {
    const target =
      this.state.targets.find((item) => item.id === scriptId) || null;
    this.state.selectedScriptId = target?.id || "";
    this.state.selectedUserId = target?.users?.[0]?.id || "";
    this.state.error = "";
    this.state.notice = "";
    this.resetConfigState();
    this.render();
    if (this.state.selectedScriptId && this.state.selectedUserId) {
      void this.loadConfigs();
    }
  }

  selectUser(userId) {
    this.state.selectedUserId = userId;
    this.state.error = "";
    this.state.notice = "";
    this.resetConfigState();
    this.render();
    if (this.state.selectedScriptId && this.state.selectedUserId) {
      void this.loadConfigs();
    }
  }

  setFieldValue(filename, field, value) {
    const draft = this.state.drafts[filename] || {};
    this.state.drafts[filename] = setPath(draft, field.path, value);
    delete this.state.rawJson[`${filename}::${field.path}`];
    this.state.validationErrors = [];
    this.state.validationDrafts = [];
    this.state.error = "";
    this.render();
  }

  setJsonFieldValue(filename, field, text) {
    const key = `${filename}::${field.path}`;
    try {
      this.setFieldValue(filename, field, JSON.parse(text));
    } catch {
      this.state.rawJson[key] = text;
      this.state.validationErrors = [
        ...this.state.validationErrors.filter(
          (error) => error.path !== field.path,
        ),
        { filename, path: field.path, message: "JSON 格式无效，未写入草稿" },
      ];
      this.render();
    }
  }

  discardChanges() {
    this.state.drafts = cloneValue(this.state.originals) || {};
    this.state.validationErrors = [];
    this.state.validationDrafts = [];
    this.state.rawJson = {};
    this.state.error = "";
    this.state.notice = "已放弃未保存的配置修改";
    this.render();
  }

  async validateOrSave(mode) {
    const configs = this.changedConfigs();
    if (Object.keys(configs).length === 0) {
      this.state.notice =
        mode === "validate"
          ? "当前没有需要校验的修改"
          : "当前没有需要保存的修改";
      this.render();
      return;
    }

    const serial = this.beginRequest();
    this.state.saving = true;
    this.state.error = "";
    this.state.notice = "";
    this.state.validationErrors = [];
    this.render();
    try {
      const response = await this.callPlugin("ok-script/configs/batch-update", {
        script_id: this.state.selectedScriptId,
        user_id: this.state.selectedUserId,
        configs,
        mode,
      });
      if (!this.isCurrentRequest(serial)) {
        return;
      }
      this.state.validationDrafts = Array.isArray(response.drafts)
        ? response.drafts
        : [];
      if (mode === "commit") {
        for (const filename of Object.keys(configs)) {
          this.state.originals[filename] = cloneValue(
            this.state.drafts[filename],
          );
        }
        this.state.notice = "配置已保存";
      } else {
        this.state.notice = "配置校验通过，尚未写入";
      }
      this.render();
    } catch (error) {
      if (!this.isCurrentRequest(serial)) {
        return;
      }
      const payload = parsePluginError(error);
      this.state.validationErrors = Array.isArray(payload.errors)
        ? payload.errors
        : [];
      this.state.validationDrafts = Array.isArray(payload.drafts)
        ? payload.drafts
        : [];
      this.state.error = String(payload.message || "配置校验或保存失败");
      this.render();
    } finally {
      if (this.isCurrentRequest(serial)) {
        this.state.saving = false;
        this.render();
      }
    }
  }

  fieldErrors(filename, fieldPath) {
    return this.state.validationErrors.filter(
      (error) => error.filename === filename && error.path === fieldPath,
    );
  }

  fieldValue(filename, field) {
    const fallback = field.hasDefault ? field.default : undefined;
    return getPath(this.state.drafts[filename], field.path, fallback);
  }

  createButton(label, handler, options = {}) {
    const button = createElement("button", {
      className: options.primary
        ? "workspace-button workspace-button--primary"
        : "workspace-button",
      text: label,
    });
    button.type = "button";
    button.disabled = Boolean(options.disabled);
    this.listen(button, "click", handler);
    return button;
  }

  renderTargetSelectors(signal) {
    const panel = createElement("div", { className: "workspace-targets" });
    const target = this.selectedTarget();

    const scriptLabel = createElement("label", {
      className: "workspace-control-label",
      text: "脚本",
    });
    const scriptSelect = createElement("select", {
      className: "workspace-select",
    });
    scriptSelect.disabled =
      this.state.loadingTargets || this.state.targets.length === 0;
    const scriptPlaceholder = createElement("option", {
      text: this.state.targets.length === 0 ? "没有可用脚本" : "请选择脚本",
    });
    scriptPlaceholder.value = "";
    scriptSelect.append(scriptPlaceholder);
    for (const item of this.state.targets) {
      const label =
        item.projectLabel || item.name || item.resourceName || item.id;
      const option = createElement("option", { text: label });
      option.value = item.id;
      option.selected = item.id === this.state.selectedScriptId;
      scriptSelect.append(option);
    }
    scriptSelect.addEventListener(
      "change",
      (event) => this.selectScript(event.target.value),
      { signal },
    );
    scriptLabel.append(scriptSelect);
    panel.append(scriptLabel);

    const userLabel = createElement("label", {
      className: "workspace-control-label",
      text: "用户",
    });
    const userSelect = createElement("select", {
      className: "workspace-select",
    });
    userSelect.disabled =
      !target ||
      this.state.loadingConfigs ||
      !Array.isArray(target.users) ||
      target.users.length === 0;
    const userPlaceholder = createElement("option", {
      text: target ? "请选择用户" : "请先选择脚本",
    });
    userPlaceholder.value = "";
    userSelect.append(userPlaceholder);
    for (const user of target?.users || []) {
      const option = createElement("option", {
        text: user.enabled ? user.name : `${user.name}（已停用）`,
      });
      option.value = user.id;
      option.selected = user.id === this.state.selectedUserId;
      userSelect.append(option);
    }
    userSelect.addEventListener(
      "change",
      (event) => this.selectUser(event.target.value),
      { signal },
    );
    userLabel.append(userSelect);
    panel.append(userLabel);

    if (target) {
      const metadata = createElement("div", {
        className: "workspace-target-meta",
      });
      const resource = target.resourceName
        ? `资源：${target.resourceName}`
        : "资源：未识别";
      const root = target.rootConfigured ? "项目目录已设置" : "项目目录未设置";
      metadata.append(createElement("span", { text: resource }));
      metadata.append(createElement("span", { text: root }));
      panel.append(metadata);
    }
    return panel;
  }

  renderFileNavigation(signal) {
    const navigation = createElement("aside", {
      className: "workspace-file-nav",
    });
    navigation.append(
      createElement("h3", {
        className: "workspace-panel-title",
        text: "配置文件",
      }),
    );

    if (this.state.loadingConfigs) {
      navigation.append(
        createElement("p", {
          className: "workspace-empty",
          text: "正在读取配置文件",
        }),
      );
      return navigation;
    }
    if (this.state.configs.length === 0) {
      navigation.append(
        createElement("p", {
          className: "workspace-empty",
          text: "暂无可编辑配置文件",
        }),
      );
      return navigation;
    }

    const list = createElement("div", { className: "workspace-file-list" });
    for (const config of this.state.configs) {
      const changed = !sameValue(
        this.state.drafts[config.filename],
        this.state.originals[config.filename],
      );
      const button = createElement("button", {
        className: `workspace-file-button${config.filename === this.state.selectedFilename ? " workspace-file-button--active" : ""}`,
        title: config.filename,
      });
      button.type = "button";
      button.setAttribute(
        "aria-current",
        config.filename === this.state.selectedFilename ? "true" : "false",
      );
      const title = createElement("span", {
        className: "workspace-file-button__label",
        text: config.displayName || config.filename,
        title: config.displayName || config.filename,
      });
      button.append(title);
      const detail = createElement("span", {
        className: "workspace-file-button__detail",
        text: config.taskIndex ? `-t ${config.taskIndex}` : config.filename,
      });
      button.append(detail);
      if (changed) {
        button.append(
          createElement("span", {
            className: "workspace-change-dot",
            text: "未保存",
          }),
        );
      }
      button.addEventListener(
        "click",
        () => {
          this.state.selectedFilename = config.filename;
          this.render();
        },
        { signal },
      );
      list.append(button);
    }
    navigation.append(list);
    return navigation;
  }

  renderFieldControl(filename, field, value, signal) {
    const choices = Array.isArray(field.choices) ? field.choices : [];
    const jsonKey = `${filename}::${field.path}`;
    const isJson =
      field.control === "json" ||
      ["object", "array", "unknown"].includes(field.valueType);

    if (field.control === "switch") {
      const control = createElement("input", { className: "workspace-switch" });
      control.type = "checkbox";
      control.checked = Boolean(value);
      control.addEventListener(
        "change",
        (event) => this.setFieldValue(filename, field, event.target.checked),
        { signal },
      );
      return control;
    }

    if (field.control === "select" && choices.length > 0) {
      const control = createElement("select", {
        className: "workspace-select",
      });
      const placeholder = createElement("option", { text: "请选择" });
      placeholder.value = "";
      control.append(placeholder);
      let selectedIndex = -1;
      choices.forEach((choice, index) => {
        const option = createElement("option", {
          text: choice.label || String(choice.value),
        });
        option.value = String(index);
        option.selected = sameValue(choice.value, value);
        if (option.selected) {
          selectedIndex = index;
        }
        control.append(option);
      });
      if (selectedIndex >= 0) {
        control.value = String(selectedIndex);
      }
      control.addEventListener(
        "change",
        (event) => {
          const index = Number(event.target.value);
          if (Number.isInteger(index) && choices[index]) {
            this.setFieldValue(
              filename,
              field,
              cloneValue(choices[index].value),
            );
          }
        },
        { signal },
      );
      return control;
    }

    if (field.control === "multiselect" && choices.length > 0) {
      const control = createElement("select", {
        className: "workspace-select workspace-select--multiple",
      });
      control.multiple = true;
      const values = Array.isArray(value) ? value : [];
      choices.forEach((choice, index) => {
        const option = createElement("option", {
          text: choice.label || String(choice.value),
        });
        option.value = String(index);
        option.selected = values.some((item) => sameValue(item, choice.value));
        control.append(option);
      });
      control.addEventListener(
        "change",
        (event) => {
          const next = Array.from(event.target.selectedOptions)
            .map((option) => choices[Number(option.value)])
            .filter(Boolean)
            .map((choice) => cloneValue(choice.value));
          this.setFieldValue(filename, field, next);
        },
        { signal },
      );
      return control;
    }

    if (isJson) {
      const control = createElement("textarea", {
        className: "workspace-textarea workspace-textarea--json",
      });
      control.rows = 8;
      control.spellcheck = false;
      control.value =
        this.state.rawJson[jsonKey] ??
        (value === undefined ? "" : JSON.stringify(value, null, 2));
      control.addEventListener(
        "change",
        (event) => this.setJsonFieldValue(filename, field, event.target.value),
        { signal },
      );
      return control;
    }

    if (field.control === "textarea") {
      const control = createElement("textarea", {
        className: "workspace-textarea",
      });
      control.rows = 5;
      control.value = value ?? "";
      control.addEventListener(
        "change",
        (event) => this.setFieldValue(filename, field, event.target.value),
        { signal },
      );
      return control;
    }

    const control = createElement("input", { className: "workspace-input" });
    if (field.control === "integer" || field.control === "number") {
      control.type = "number";
      control.step = field.step ?? (field.control === "integer" ? "1" : "any");
      if (field.min !== null && field.min !== undefined) {
        control.min = field.min;
      }
      if (field.max !== null && field.max !== undefined) {
        control.max = field.max;
      }
      control.value = value ?? "";
      control.addEventListener(
        "change",
        (event) => {
          const raw = event.target.value;
          this.setFieldValue(filename, field, raw === "" ? null : Number(raw));
        },
        { signal },
      );
    } else {
      control.type = "text";
      control.value = value ?? "";
      control.addEventListener(
        "change",
        (event) => this.setFieldValue(filename, field, event.target.value),
        { signal },
      );
    }
    return control;
  }

  renderConfigForm(signal) {
    const panel = createElement("section", { className: "workspace-editor" });
    const config = this.selectedConfig();
    if (this.state.loadingConfigs) {
      panel.append(
        createElement("p", {
          className: "workspace-empty",
          text: "正在加载配置内容",
        }),
      );
      return panel;
    }
    if (!config) {
      panel.append(
        createElement("p", {
          className: "workspace-empty",
          text: "请从左侧选择一个配置文件",
        }),
      );
      return panel;
    }

    const header = createElement("div", {
      className: "workspace-editor-header",
    });
    const title = createElement("div");
    title.append(
      createElement("h3", {
        className: "workspace-editor-title",
        text: config.displayName || config.filename,
      }),
    );
    title.append(
      createElement("p", {
        className: "workspace-file-path",
        text: config.filename,
        title: config.filename,
      }),
    );
    header.append(title);
    if (config.taskIndex) {
      header.append(
        createElement("span", {
          className: "workspace-task-index",
          text: `-t ${config.taskIndex}`,
        }),
      );
    }
    panel.append(header);

    const fields = normalizeFields(config);
    if (fields.length === 0) {
      panel.append(
        createElement("p", {
          className: "workspace-empty",
          text: "该配置文件暂无可编辑字段",
        }),
      );
      return panel;
    }

    const groups = new Map();
    for (const field of fields) {
      const section = field.section || "通用配置";
      if (!groups.has(section)) {
        groups.set(section, []);
      }
      groups.get(section).push(field);
    }

    const orderedGroups = [...groups.entries()].sort(
      ([leftName, leftFields], [rightName, rightFields]) => {
        const leftPriority =
          leftFields[0]?.sectionPriority ?? Number.MAX_SAFE_INTEGER;
        const rightPriority =
          rightFields[0]?.sectionPriority ?? Number.MAX_SAFE_INTEGER;
        if (leftPriority !== rightPriority) {
          return leftPriority - rightPriority;
        }
        return leftName.localeCompare(rightName, "zh-CN");
      },
    );

    for (const [section, groupFields] of orderedGroups) {
      const group = createElement("section", {
        className: "workspace-field-group",
      });
      group.append(
        createElement("h4", {
          className: "workspace-field-group__title",
          text: section,
        }),
      );
      const grid = createElement("div", { className: "workspace-field-grid" });
      const orderedFields = [...groupFields].sort((left, right) => {
        const leftPriority = left.priority ?? Number.MAX_SAFE_INTEGER;
        const rightPriority = right.priority ?? Number.MAX_SAFE_INTEGER;
        if (leftPriority !== rightPriority) {
          return leftPriority - rightPriority;
        }
        return String(left.label || left.path).localeCompare(
          String(right.label || right.path),
          "zh-CN",
        );
      });

      for (const field of orderedFields) {
        const value = this.fieldValue(config.filename, field);
        const wide =
          field.control === "textarea" ||
          field.control === "json" ||
          ["object", "array", "unknown"].includes(field.valueType);
        const fieldRoot = createElement("label", {
          className: `workspace-field${wide ? " workspace-field--wide" : ""}`,
        });
        fieldRoot.append(
          createElement("span", {
            className: "workspace-field__label",
            text: field.label || field.path,
            title: field.path,
          }),
        );
        if (field.description) {
          fieldRoot.append(
            createElement("span", {
              className: "workspace-field__help",
              text: field.description,
            }),
          );
        }
        const control = this.renderFieldControl(
          config.filename,
          field,
          value,
          signal,
        );
        const errors = this.fieldErrors(config.filename, field.path);
        control.setAttribute(
          "aria-invalid",
          errors.length > 0 ? "true" : "false",
        );
        fieldRoot.append(control);
        for (const error of errors) {
          fieldRoot.append(
            createElement("span", {
              className: "workspace-field__error",
              text: error.message,
            }),
          );
        }
        grid.append(fieldRoot);
      }
      group.append(grid);
      panel.append(group);
    }
    return panel;
  }

  renderValidationSummary() {
    if (this.state.validationDrafts.length === 0) {
      return null;
    }
    const summary = createElement("section", {
      className: "workspace-validation-summary",
    });
    summary.append(
      createElement("h3", {
        className: "workspace-panel-title",
        text: "校验结果",
      }),
    );
    const list = createElement("ul", {
      className: "workspace-validation-list",
    });
    for (const draft of this.state.validationDrafts) {
      const count = Array.isArray(draft.changes) ? draft.changes.length : 0;
      list.append(
        createElement("li", { text: `${draft.filename}：${count} 项变更` }),
      );
    }
    summary.append(list);
    return summary;
  }

  render() {
    if (!this._connected) {
      return;
    }
    this.resetListeners();
    const signal = this._listenerController.signal;
    const root = createElement("section", { className: "ok-script-workspace" });
    const header = createElement("header", { className: "workspace-header" });
    const heading = createElement("div");
    heading.append(
      createElement("h2", {
        className: "workspace-title",
        text: this.getAttribute("title") || "ok-script 配置工作区",
      }),
    );
    const statusText = this.state.saving
      ? "保存中"
      : this.hasChanges()
        ? "有未保存修改"
        : "已保存";
    heading.append(
      createElement("p", {
        className: "workspace-status",
        text: statusText,
        role: "status",
      }),
    );
    header.append(heading);

    const actions = createElement("div", { className: "workspace-actions" });
    actions.append(
      this.createButton("刷新", () => void this.loadTargets(), {
        disabled: this.state.loadingTargets || this.state.saving,
      }),
    );
    actions.append(
      this.createButton("校验", () => void this.validateOrSave("validate"), {
        disabled: !this.hasChanges() || this.state.saving,
      }),
    );
    actions.append(
      this.createButton("放弃", () => this.discardChanges(), {
        disabled: !this.hasChanges() || this.state.saving,
      }),
    );
    actions.append(
      this.createButton("保存", () => void this.validateOrSave("commit"), {
        primary: true,
        disabled: !this.hasChanges() || this.state.saving,
      }),
    );
    header.append(actions);
    root.append(header);
    root.append(this.renderTargetSelectors(signal));

    if (this.state.error) {
      const alert = createElement("div", {
        className: "workspace-alert workspace-alert--error",
        role: "alert",
      });
      alert.append(createElement("span", { text: this.state.error }));
      alert.append(
        this.createButton("重试", () => void this.loadConfigs(), {
          disabled: this.state.loadingConfigs || this.state.saving,
        }),
      );
      root.append(alert);
    } else if (this.state.notice) {
      root.append(
        createElement("div", {
          className: "workspace-alert",
          text: this.state.notice,
          role: "status",
        }),
      );
    }

    const layout = createElement("div", { className: "workspace-layout" });
    layout.append(this.renderFileNavigation(signal));
    layout.append(this.renderConfigForm(signal));
    root.append(layout);
    const summary = this.renderValidationSummary();
    if (summary) {
      root.append(summary);
    }
    this.replaceChildren(root);
  }
}

if (!customElements.get(ELEMENT_TAG)) {
  customElements.define(ELEMENT_TAG, OkScriptWorkspace);
}

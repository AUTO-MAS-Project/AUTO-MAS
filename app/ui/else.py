class Main(QWidget):

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self, config: AppConfig, notify: Notification, crypto: CryptoHandler):
        super().__init__()

        self.config = config
        self.notify = notify
        self.crypto = crypto

        self.PASSWORD = ""
        self.if_user_list_editable = True
        self.if_update_database = True
        self.if_update_config = True
        self.user_mode_list = ["simple", "beta"]
        self.user_column = [
            "admin",
            "id",
            "server",
            "day",
            "status",
            "last",
            "game",
            "game_1",
            "game_2",
            "routine",
            "annihilation",
            "infrastructure",
            "password",
            "notes",
            "numb",
            "mode",
            "uid",
        ]
        self.userlist_simple_index = [
            0,
            1,
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            "-",
            9,
            10,
            11,
            12,
            "-",
            "-",
            "-",
        ]
        self.userlist_beta_index = [
            0,
            "-",
            "-",
            1,
            2,
            3,
            "-",
            "-",
            "-",
            4,
            5,
            "-",
            6,
            7,
            "-",
            "-",
            "-",
        ]

        # uiLoader.registerCustomWidget(PushButton)
        # uiLoader.registerCustomWidget(LineEdit)
        # uiLoader.registerCustomWidget(TextBrowser)
        # uiLoader.registerCustomWidget(TableWidget)
        # uiLoader.registerCustomWidget(TimePicker)
        # uiLoader.registerCustomWidget(SpinBox)
        # uiLoader.registerCustomWidget(CheckBox)
        # uiLoader.registerCustomWidget(HeaderCardWidget)
        # uiLoader.registerCustomWidget(BodyLabel)

        # # 导入ui配置
        # self.ui = uiLoader.load(self.config.app_path / "resources/gui/main.ui")
        # self.ui.setWindowIcon(
        #     QIcon(str(self.config.app_path / "resources/icons/AUTO_MAA.ico"))
        # )

        # # 初始化控件
        # self.main_tab: QTabWidget = self.ui.findChild(QTabWidget, "tabWidget_main")
        # self.main_tab.currentChanged.connect(self.change_config)

        # self.user_set: QToolBox = self.ui.findChild(QToolBox, "toolBox_userset")
        # self.user_set.currentChanged.connect(lambda: self.update_user_info("normal"))

        # self.user_list_simple: TableWidget = self.ui.findChild(
        #     TableWidget, "tableWidget_userlist_simple"
        # )
        # self.user_list_simple.itemChanged.connect(
        #     lambda item: self.change_user_Item(item, "simple")
        # )

        # self.user_list_beta: TableWidget = self.ui.findChild(
        #     TableWidget, "tableWidget_userlist_beta"
        # )
        # self.user_list_beta.itemChanged.connect(
        #     lambda item: self.change_user_Item(item, "beta")
        # )

        # self.user_add: PushButton = self.ui.findChild(PushButton, "pushButton_new")
        # self.user_add.setIcon(FluentIcon.ADD_TO)
        # self.user_add.clicked.connect(self.add_user)

        # self.user_del: PushButton = self.ui.findChild(PushButton, "pushButton_del")
        # self.user_del.setIcon(FluentIcon.REMOVE_FROM)
        # self.user_del.clicked.connect(self.del_user)

        # self.user_switch: PushButton = self.ui.findChild(
        #     PushButton, "pushButton_switch"
        # )
        # self.user_switch.setIcon(FluentIcon.MOVE)
        # self.user_switch.clicked.connect(self.switch_user)

        # self.read_PASSWORD: PushButton = self.ui.findChild(
        #     PushButton, "pushButton_password"
        # )
        # self.read_PASSWORD.setIcon(FluentIcon.HIDE)
        # self.read_PASSWORD.clicked.connect(lambda: self.read("key"))

        # self.refresh: PushButton = self.ui.findChild(PushButton, "pushButton_refresh")
        # self.refresh.setIcon(FluentIcon.SYNC)
        # self.refresh.clicked.connect(lambda: self.update_user_info("clear"))

        # self.run_now: PushButton = self.ui.findChild(PushButton, "pushButton_runnow")
        # self.run_now.setIcon(FluentIcon.PLAY)
        # self.run_now.clicked.connect(lambda: self.maa_starter("日常代理"))

        # self.check_start: PushButton = self.ui.findChild(
        #     PushButton, "pushButton_checkstart"
        # )
        # self.check_start.setIcon(FluentIcon.PLAY)
        # self.check_start.clicked.connect(lambda: self.maa_starter("人工排查"))

        # self.maa_path: LineEdit = self.ui.findChild(LineEdit, "lineEdit_MAApath")
        # self.maa_path.textChanged.connect(self.change_config)
        # self.maa_path.setReadOnly(True)

        # self.get_maa_path: PushButton = self.ui.findChild(
        #     PushButton, "pushButton_getMAApath"
        # )
        # self.get_maa_path.setIcon(FluentIcon.FOLDER)
        # self.get_maa_path.clicked.connect(lambda: self.read("file_path_maa"))

        # self.set_maa: PushButton = self.ui.findChild(PushButton, "pushButton_setMAA")
        # self.set_maa.setIcon(FluentIcon.SETTING)
        # self.set_maa.clicked.connect(lambda: self.maa_starter("设置MAA_全局"))

        # self.routine: SpinBox = self.ui.findChild(SpinBox, "spinBox_routine")
        # self.routine.valueChanged.connect(self.change_config)

        # self.annihilation: SpinBox = self.ui.findChild(SpinBox, "spinBox_annihilation")
        # self.annihilation.valueChanged.connect(self.change_config)

        # self.num: SpinBox = self.ui.findChild(SpinBox, "spinBox_numt")
        # self.num.valueChanged.connect(self.change_config)

        # self.if_self_start: CheckBox = self.ui.findChild(
        #     CheckBox, "checkBox_ifselfstart"
        # )
        # self.if_self_start.stateChanged.connect(self.change_config)

        # self.if_sleep: CheckBox = self.ui.findChild(CheckBox, "checkBox_ifsleep")
        # self.if_sleep.stateChanged.connect(self.change_config)

        # self.if_proxy_directly: CheckBox = self.ui.findChild(
        #     CheckBox, "checkBox_ifproxydirectly"
        # )
        # self.if_proxy_directly.stateChanged.connect(self.change_config)

        # self.if_send_mail: CheckBox = self.ui.findChild(CheckBox, "checkBox_ifsendmail")
        # self.if_send_mail.stateChanged.connect(self.change_config)

        # self.mail_address: LineEdit = self.ui.findChild(
        #     LineEdit, "lineEdit_mailaddress"
        # )
        # self.mail_address.textChanged.connect(self.change_config)

        # self.if_send_error_only: CheckBox = self.ui.findChild(
        #     CheckBox, "checkBox_ifonlyerror"
        # )
        # self.if_send_error_only.stateChanged.connect(self.change_config)

        # self.if_silence: CheckBox = self.ui.findChild(CheckBox, "checkBox_silence")
        # self.if_silence.stateChanged.connect(self.change_config)

        # self.boss_key: LineEdit = self.ui.findChild(LineEdit, "lineEdit_boss")
        # self.boss_key.textChanged.connect(self.change_config)

        # self.if_to_tray: CheckBox = self.ui.findChild(CheckBox, "checkBox_iftotray")
        # self.if_to_tray.stateChanged.connect(self.change_config)

        # self.check_update: PushButton = self.ui.findChild(
        #     PushButton, "pushButton_check_update"
        # )
        # self.check_update.setIcon(FluentIcon.UPDATE)
        # self.check_update.clicked.connect(self.check_version)

        # self.tips: TextBrowser = self.ui.findChild(TextBrowser, "textBrowser_tips")
        # self.tips.setOpenExternalLinks(True)

        # self.run_text: TextBrowser = self.ui.findChild(TextBrowser, "textBrowser_run")
        # self.wait_text: TextBrowser = self.ui.findChild(TextBrowser, "textBrowser_wait")
        # self.over_text: TextBrowser = self.ui.findChild(TextBrowser, "textBrowser_over")
        # self.error_text: TextBrowser = self.ui.findChild(
        #     TextBrowser, "textBrowser_error"
        # )
        # self.log_text: TextBrowser = self.ui.findChild(TextBrowser, "textBrowser_log")

        # self.start_time: List[Tuple[CheckBox, TimePicker]] = []
        # for i in range(10):
        #     self.start_time.append(
        #         [
        #             self.ui.findChild(CheckBox, f"checkBox_t{i + 1}"),
        #             self.ui.findChild(TimePicker, f"timeEdit_{i + 1}"),
        #         ]
        #     )
        #     self.start_time[i][0].stateChanged.connect(self.change_config)
        #     self.start_time[i][1].timeChanged.connect(self.change_config)

        # self.change_password: PushButton = self.ui.findChild(
        #     PushButton, "pushButton_changePASSWORD"
        # )
        # self.change_password.setIcon(FluentIcon.VPN)
        # self.change_password.clicked.connect(self.change_PASSWORD)

        # 初始化线程
        self.MaaManager = MaaManager(self.config)
        self.MaaManager.question.connect(lambda: self.read("question_runner"))
        self.MaaManager.update_gui.connect(self.update_board)
        self.MaaManager.update_user_info.connect(self.change_user_info)
        self.MaaManager.push_notification.connect(self.notify.push_notification)
        self.MaaManager.send_mail.connect(self.notify.send_mail)
        self.MaaManager.accomplish.connect(lambda: self.maa_ender("日常代理_结束"))
        self.MaaManager.get_json.connect(self.get_maa_config)
        self.MaaManager.set_silence.connect(self.switch_silence)

        # self.last_time = "0000-00-00 00:00"
        # self.Timer = QtCore.QTimer()
        # self.Timer.timeout.connect(self.set_theme)
        # self.Timer.timeout.connect(self.set_system)
        # self.Timer.timeout.connect(self.timed_start)
        # self.Timer.start(1000)

        # 载入GUI数据
        # self.update_user_info("normal")
        # self.update_config()

        # 启动后直接开始代理
        if self.config.content["Default"]["SelfSet.IfProxyDirectly"] == "True":
            self.maa_starter("日常代理")

    def check_PASSWORD(self) -> None:
        """检查并配置管理密钥"""

        if self.config.key_path.exists():
            return None

        while True:

            if self.read("setkey"):
                self.crypto.get_PASSWORD(self.PASSWORD)
                break
            else:
                choice = MessageBox(
                    "确认", "您没有输入管理密钥，确定要暂时跳过这一步吗？", self.ui
                )
                if choice.exec():
                    break

    def update_user_info(self, operation: str) -> None:
        """将本地数据库中的用户配置同步至GUI的用户管理界面"""

        # 读入本地数据库
        self.config.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.config.cur.fetchall()

        # 处理部分模式调整
        if operation == "clear":
            self.PASSWORD = ""
        elif operation == "read_only":
            self.if_user_list_editable = False
        elif operation == "editable":
            self.if_user_list_editable = True

        # 阻止GUI用户数据被立即写入数据库形成死循环
        self.if_update_database = False

        user_switch_list = ["转为高级", "转为简洁"]
        self.user_switch.setText(user_switch_list[self.user_set.currentIndex()])

        # 同步简洁用户配置列表
        data_simple = [_ for _ in data if _[15] == "simple"]
        self.user_list_simple.setRowCount(len(data_simple))

        for i, row in enumerate(data_simple):

            for j, value in enumerate(row):

                if self.userlist_simple_index[j] == "-":
                    continue

                # 生成表格组件
                if j == 2:
                    item = ComboBox()
                    item.addItems(["官服", "B服"])
                    if value == "Official":
                        item.setCurrentIndex(0)
                    elif value == "Bilibili":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(
                            self.change_user_CellWidget,
                            data_simple[i][16],
                            self.user_column[j],
                        )
                    )
                elif j in [4, 10, 11]:
                    item = QComboBox()
                    if j in [4, 10]:
                        item.addItems(["启用", "禁用"])
                    elif j == 11:
                        item.addItems(["启用", "禁用", "更改配置文件"])
                    if value == "y":
                        item.setCurrentIndex(0)
                    elif value == "n":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(
                            self.change_user_CellWidget,
                            data_simple[i][16],
                            self.user_column[j],
                        )
                    )
                elif j == 3 and value == -1:
                    item = QTableWidgetItem("无限")
                elif j == 5:
                    curdate = self.server_date()
                    if curdate != value:
                        item = QTableWidgetItem("今日未代理")
                    else:
                        item = QTableWidgetItem(f"今日已代理{data_simple[i][14]}次")
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                elif j == 12:
                    if self.PASSWORD == "":
                        item = QTableWidgetItem("******")
                        item.setFlags(
                            QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                        )
                    else:
                        result = self.crypto.decryptx(value, self.PASSWORD)
                        item = QTableWidgetItem(result)
                        if result == "管理密钥错误":
                            item.setFlags(
                                QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                            )
                else:
                    item = QTableWidgetItem(str(value))

                # 组件录入表格
                if j in [2, 4, 10, 11]:
                    if not self.if_user_list_editable:
                        item.setEnabled(False)
                    self.user_list_simple.setCellWidget(
                        data_simple[i][16], self.userlist_simple_index[j], item
                    )
                else:
                    self.user_list_simple.setItem(
                        data_simple[i][16], self.userlist_simple_index[j], item
                    )

        # 同步高级用户配置列表
        data_beta = [_ for _ in data if _[15] == "beta"]
        self.user_list_beta.setRowCount(len(data_beta))

        for i, row in enumerate(data_beta):

            for j, value in enumerate(row):

                if self.userlist_beta_index[j] == "-":
                    continue

                # 生成表格组件
                if j in [4, 9, 10]:
                    item = ComboBox()
                    if j == 4:
                        item.addItems(["启用", "禁用"])
                    elif j in [9, 10]:
                        item.addItems(["启用", "禁用", "修改MAA配置"])
                    if value == "y":
                        item.setCurrentIndex(0)
                    elif value == "n":
                        item.setCurrentIndex(1)
                    item.currentIndexChanged.connect(
                        partial(
                            self.change_user_CellWidget,
                            data_beta[i][16],
                            self.user_column[j],
                        )
                    )
                elif j == 3 and value == -1:
                    item = QTableWidgetItem("无限")
                elif j == 5:
                    curdate = self.server_date()
                    if curdate != value:
                        item = QTableWidgetItem("今日未代理")
                    else:
                        item = QTableWidgetItem(f"今日已代理{data_beta[i][14]}次")
                    item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                elif j == 12:
                    if self.PASSWORD == "":
                        item = QTableWidgetItem("******")
                        item.setFlags(
                            QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                        )
                    else:
                        result = self.crypto.decryptx(value, self.PASSWORD)
                        item = QTableWidgetItem(result)
                        if result == "管理密钥错误":
                            item.setFlags(
                                QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled
                            )
                else:
                    item = QTableWidgetItem(str(value))

                # 组件录入表格
                if j in [4, 9, 10]:
                    if not self.if_user_list_editable:
                        item.setEnabled(False)
                    self.user_list_beta.setCellWidget(
                        data_beta[i][16], self.userlist_beta_index[j], item
                    )
                else:
                    self.user_list_beta.setItem(
                        data_beta[i][16], self.userlist_beta_index[j], item
                    )

        # 设置列表可编辑状态
        if self.if_user_list_editable:
            self.user_list_simple.setEditTriggers(TableWidget.AllEditTriggers)
            self.user_list_beta.setEditTriggers(TableWidget.AllEditTriggers)
        else:
            self.user_list_simple.setEditTriggers(TableWidget.NoEditTriggers)
            self.user_list_beta.setEditTriggers(TableWidget.NoEditTriggers)

        # 允许GUI改变被同步到本地数据库
        self.if_update_database = True

        # 设置用户配置列表的标题栏宽度
        self.user_list_simple.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self.user_list_beta.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def update_config(self):
        """将self.config中的程序配置同步至GUI界面"""

        # 阻止GUI程序配置被立即读入程序形成死循环
        self.if_update_config = False

        self.main_tab.setCurrentIndex(
            self.config.content["Default"]["SelfSet.MainIndex"]
        )

        self.maa_path.setText(str(Path(self.config.content["Default"]["MaaSet.path"])))
        self.routine.setValue(self.config.content["Default"]["TimeLimit.routine"])
        self.annihilation.setValue(
            self.config.content["Default"]["TimeLimit.annihilation"]
        )
        self.num.setValue(self.config.content["Default"]["TimesLimit.run"])
        self.mail_address.setText(self.config.content["Default"]["SelfSet.MailAddress"])
        self.boss_key.setText(self.config.content["Default"]["SelfSet.BossKey"])

        self.if_self_start.setChecked(
            bool(self.config.content["Default"]["SelfSet.IfSelfStart"] == "True")
        )

        self.if_sleep.setChecked(
            bool(self.config.content["Default"]["SelfSet.IfSleep"] == "True")
        )

        self.if_proxy_directly.setChecked(
            bool(self.config.content["Default"]["SelfSet.IfProxyDirectly"] == "True")
        )

        self.if_send_mail.setChecked(
            bool(self.config.content["Default"]["SelfSet.IfSendMail"] == "True")
        )

        self.mail_address.setVisible(
            bool(self.config.content["Default"]["SelfSet.IfSendMail"] == "True")
        )

        self.if_send_error_only.setChecked(
            bool(
                self.config.content["Default"]["SelfSet.IfSendMail.OnlyError"] == "True"
            )
        )

        self.if_send_error_only.setVisible(
            bool(self.config.content["Default"]["SelfSet.IfSendMail"] == "True")
        )

        self.if_silence.setChecked(
            bool(self.config.content["Default"]["SelfSet.IfSilence"] == "True")
        )

        self.boss_key.setVisible(
            bool(self.config.content["Default"]["SelfSet.IfSilence"] == "True")
        )

        self.if_to_tray.setChecked(
            bool(self.config.content["Default"]["SelfSet.IfToTray"] == "True")
        )

        for i in range(10):
            self.start_time[i][0].setChecked(
                bool(self.config.content["Default"][f"TimeSet.set{i + 1}"] == "True")
            )
            time = QtCore.QTime(
                int(self.config.content["Default"][f"TimeSet.run{i + 1}"][:2]),
                int(self.config.content["Default"][f"TimeSet.run{i + 1}"][3:]),
            )
            self.start_time[i][1].setTime(time)
        self.if_update_config = True

    def update_board(self, run_text, wait_text, over_text, error_text, log_text):
        """写入数据至GUI执行界面的调度台面板"""

        self.run_text.setPlainText(run_text)
        self.wait_text.setPlainText(wait_text)
        self.over_text.setPlainText(over_text)
        self.error_text.setPlainText(error_text)
        self.log_text.setPlainText(log_text)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )

    def add_user(self):
        """添加一位新用户"""

        # 判断是否已设置管理密钥
        if not self.config.key_path.exists():
            choice = MessageBox(
                "错误",
                "请先设置管理密钥再执行添加用户操作",
                self.ui,
            )
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                return None

        # 插入预设用户数据
        set_book = [
            ["simple", self.user_list_simple.rowCount()],
            ["beta", self.user_list_beta.rowCount()],
        ]
        self.config.cur.execute(
            "INSERT INTO adminx VALUES('新用户','手机号码（官服）/B站ID（B服）','Official',-1,'y','2000-01-01','1-7','-','-','n','n','n',?,'无',0,?,?)",
            (
                self.crypto.encryptx("未设置"),
                set_book[self.user_set.currentIndex()][0],
                set_book[self.user_set.currentIndex()][1],
            ),
        )
        self.config.db.commit(),

        # 同步新用户至GUI
        self.update_user_info("normal")

    def del_user(self):
        """删除选中的首位用户"""

        # 获取对应的行索引
        if self.user_set.currentIndex() == 0:
            row = self.user_list_simple.currentRow()
        elif self.user_set.currentIndex() == 1:
            row = self.user_list_beta.currentRow()

        # 判断选择合理性
        if row == -1:
            choice = MessageBox("错误", "请选中一个用户后再执行删除操作", self.ui)
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                return None

        # 确认待删除用户信息
        self.config.cur.execute(
            "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
            (
                self.user_mode_list[self.user_set.currentIndex()],
                row,
            ),
        )
        data = self.config.cur.fetchall()
        choice = MessageBox("确认", f"确定要删除用户 {data[0][0]} 吗？", self.ui)

        # 删除用户
        if choice.exec():
            # 删除所选用户
            self.config.cur.execute(
                "DELETE FROM adminx WHERE mode = ? AND uid = ?",
                (
                    self.user_mode_list[self.user_set.currentIndex()],
                    row,
                ),
            )
            self.config.db.commit()
            if (
                self.config.app_path
                / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}"
            ).exists():
                shutil.rmtree(
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}"
                )
            # 后续用户补位
            if self.user_set.currentIndex() == 0:
                current_numb = self.user_list_simple.rowCount()
            elif self.user_set.currentIndex() == 1:
                current_numb = self.user_list_beta.rowCount()
            for i in range(row + 1, current_numb):
                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (i - 1, self.user_mode_list[self.user_set.currentIndex()], i),
                )
                self.config.db.commit()
                if (
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i}"
                ).exists():
                    (
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i}"
                    ).rename(
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i - 1}",
                    )

            # 同步最终结果至GUI
            self.update_user_info("normal")

    def switch_user(self):
        """切换用户配置模式"""

        # 获取当前用户配置模式信息
        if self.user_set.currentIndex() == 0:
            row = self.user_list_simple.currentRow()
        elif self.user_set.currentIndex() == 1:
            row = self.user_list_beta.currentRow()

        # 判断选择合理性
        if row == -1:
            choice = MessageBox("错误", "请选中一个用户后再执行切换操作", self.ui)
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                return None

        # 确认待切换用户信息
        self.config.cur.execute(
            "SELECT * FROM adminx WHERE mode = ? AND uid = ?",
            (
                self.user_mode_list[self.user_set.currentIndex()],
                row,
            ),
        )
        data = self.config.cur.fetchall()

        mode_list = ["简洁", "高级"]
        choice = MessageBox(
            "确认",
            f"确定要将用户 {data[0][0]} 转为{mode_list[1 - self.user_set.currentIndex()]}配置模式吗？",
            self.ui,
        )

        # 切换用户
        if choice.exec():
            self.config.cur.execute("SELECT * FROM adminx WHERE True")
            data = self.config.cur.fetchall()
            if self.user_set.currentIndex() == 0:
                current_numb = self.user_list_simple.rowCount()
            elif self.user_set.currentIndex() == 1:
                current_numb = self.user_list_beta.rowCount()
            # 切换所选用户
            other_numb = len(data) - current_numb
            self.config.cur.execute(
                "UPDATE adminx SET mode = ?, uid = ? WHERE mode = ? AND uid = ?",
                (
                    self.user_mode_list[1 - self.user_set.currentIndex()],
                    other_numb,
                    self.user_mode_list[self.user_set.currentIndex()],
                    row,
                ),
            )
            self.config.db.commit()
            if (
                self.config.app_path
                / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}"
            ).exists():
                shutil.move(
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}",
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[1 - self.user_set.currentIndex()]}/{other_numb}",
                )
            # 后续用户补位
            for i in range(row + 1, current_numb):
                self.config.cur.execute(
                    "UPDATE adminx SET uid = ? WHERE mode = ? AND uid = ?",
                    (i - 1, self.user_mode_list[self.user_set.currentIndex()], i),
                )
                self.config.db.commit(),
                if (
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i}"
                ).exists():
                    (
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i}"
                    ).rename(
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{i - 1}"
                    )

            self.update_user_info("normal")

    def get_maa_config(self, info):
        """获取MAA配置文件"""

        # 获取全局MAA配置文件
        if info == ["Default"]:
            shutil.copy(
                Path(self.config.content["Default"]["MaaSet.path"]) / "config/gui.json",
                self.config.app_path / "data/MAAconfig/Default",
            )
        # 获取基建配置文件
        elif info[2] == "infrastructure":
            infrastructure_path = self.read("file_path_infrastructure")
            if infrastructure_path:
                (
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[info[0]]}/{info[1]}/infrastructure"
                ).mkdir(parents=True, exist_ok=True)
                shutil.copy(
                    infrastructure_path,
                    self.config.app_path
                    / f"data/MAAconfig/{self.user_mode_list[info[0]]}/{info[1]}/infrastructure/infrastructure.json",
                )
                return True
            else:
                choice = MessageBox(
                    "错误",
                    "未选择自定义基建文件",
                    self.ui,
                )
                choice.cancelButton.hide()
                choice.buttonLayout.insertStretch(1)
                if choice.exec():
                    return False
        # 获取高级用户MAA配置文件
        elif info[2] in ["routine", "annihilation"]:
            (
                self.config.app_path
                / f"data/MAAconfig/{self.user_mode_list[info[0]]}/{info[1]}/{info[2]}"
            ).mkdir(parents=True, exist_ok=True)
            shutil.copy(
                Path(self.config.content["Default"]["MaaSet.path"]) / "config/gui.json",
                self.config.app_path
                / f"data/MAAconfig/{self.user_mode_list[info[0]]}/{info[1]}/{info[2]}",
            )

    def change_user_Item(self, item: TableWidget, mode):
        """将GUI中发生修改的用户配置表中的一般信息同步至本地数据库"""

        # 验证能否写入本地数据库
        if not self.if_update_database:
            return None

        text = item.text()
        # 简洁用户配置列表
        if mode == "simple":
            # 待写入信息预处理
            if item.column() == 3:  # 代理天数
                try:
                    text = max(int(text), -1)
                except ValueError:
                    self.update_user_info("normal")
                    return None
            if item.column() in [6, 7, 8]:  # 关卡号
                # 导入与应用特殊关卡规则
                games = {}
                with self.config.gameid_path.open(mode="r", encoding="utf-8") as f:
                    gameids = f.readlines()
                    for line in gameids:
                        if "：" in line:
                            game_in, game_out = line.split("：", 1)
                            games[game_in.strip()] = game_out.strip()
                text = games.get(text, text)
            if item.column() == 11:  # 密码
                text = self.crypto.encryptx(text)

            # 保存至本地数据库
            if text != "":
                self.config.cur.execute(
                    f"UPDATE adminx SET {self.user_column[self.userlist_simple_index.index(item.column())]} = ? WHERE mode = 'simple' AND uid = ?",
                    (text, item.row()),
                )
        # 高级用户配置列表
        elif mode == "beta":
            # 待写入信息预处理
            if item.column() == 1:  # 代理天数
                try:
                    text = max(int(text), -1)
                except ValueError:
                    self.update_user_info("normal")
                    return None
            if item.column() == 6:  # 密码
                text = self.crypto.encryptx(text)

            # 保存至本地数据库
            if text != "":
                self.config.cur.execute(
                    f"UPDATE adminx SET {self.user_column[self.userlist_beta_index.index(item.column())]} = ? WHERE mode = 'beta' AND uid = ?",
                    (text, item.row()),
                )
        self.config.db.commit()

        # 同步一般用户信息更改到GUI
        self.update_user_info("normal")

    def change_user_CellWidget(self, row, column, index):
        """将GUI中发生修改的用户配置表中的CellWidget类信息同步至本地数据库"""

        # 验证能否写入本地数据库
        if not self.if_update_database:
            return None

        # 初次开启自定义基建或选择修改配置文件时选择配置文件
        if (
            self.user_set.currentIndex() == 0
            and column == "infrastructure"
            and (
                index == 2
                or (
                    index == 0
                    and not (
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}/infrastructure/infrastructure.json"
                    ).exists()
                )
            )
        ):
            result = self.get_maa_config([0, row, "infrastructure"])
            if index == 0 and not result:
                index = 1

        # 初次开启自定义MAA配置或选择修改MAA配置时调起MAA配置任务
        if (
            self.user_set.currentIndex() == 1
            and column in ["routine", "annihilation"]
            and (
                index == 2
                or (
                    index == 0
                    and not (
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[self.user_set.currentIndex()]}/{row}/{column}/gui.json"
                    ).exists()
                )
            )
        ):
            self.MaaManager.get_json_path = [
                self.user_set.currentIndex(),
                row,
                column,
            ]
            self.maa_starter("设置MAA_用户")

        # 服务器
        if self.user_set.currentIndex() == 0 and column == "server":
            server_list = ["Official", "Bilibili"]
            self.config.cur.execute(
                f"UPDATE adminx SET server = ? WHERE mode = 'simple' AND uid = ?",
                (server_list[index], row),
            )
        # 其它(启用/禁用)
        elif index in [0, 1]:
            index_list = ["y", "n"]
            self.config.cur.execute(
                f"UPDATE adminx SET {column} = ? WHERE mode = ? AND uid = ?",
                (
                    index_list[index],
                    self.user_mode_list[self.user_set.currentIndex()],
                    row,
                ),
            )
        self.config.db.commit()

        # 同步用户组件信息修改到GUI
        self.update_user_info("normal")

    def change_user_info(self, modes, uids, days, lasts, notes, numbs):
        """将代理完成后发生改动的用户信息同步至本地数据库"""

        for index in range(len(uids)):
            self.config.cur.execute(
                "UPDATE adminx SET day = ? WHERE mode = ? AND uid = ?",
                (days[index], modes[index], uids[index]),
            )
            self.config.cur.execute(
                "UPDATE adminx SET last = ? WHERE mode = ? AND uid = ?",
                (lasts[index], modes[index], uids[index]),
            )
            self.config.cur.execute(
                "UPDATE adminx SET notes = ? WHERE mode = ? AND uid = ?",
                (notes[index], modes[index], uids[index]),
            )
            self.config.cur.execute(
                "UPDATE adminx SET numb = ? WHERE mode = ? AND uid = ?",
                (numbs[index], modes[index], uids[index]),
            )
        self.config.db.commit()

        # 同步用户信息更改至GUI
        self.update_user_info("normal")

    def change_config(self):
        """将GUI中发生修改的程序配置同步至self.config变量"""

        # 验证能否写入self.config变量
        if not self.if_update_config:
            return None

        # 验证MAA路径
        if Path(self.config.content["Default"]["MaaSet.path"]) != Path(
            self.maa_path.text()
        ):
            if (Path(self.maa_path.text()) / "MAA.exe").exists() and (
                Path(self.maa_path.text()) / "config/gui.json"
            ).exists():
                self.config.content["Default"]["MaaSet.path"] = str(
                    Path(self.maa_path.text())
                )
                self.get_maa_config(["Default"])
            else:
                choice = MessageBox(
                    "错误",
                    "该路径下未找到MAA.exe或MAA配置文件，请重新设置MAA路径！",
                    self.ui,
                )
                if choice.exec():
                    pass

        self.config.content["Default"][
            "SelfSet.MainIndex"
        ] = self.main_tab.currentIndex()
        self.config.content["Default"]["TimeLimit.routine"] = self.routine.value()
        self.config.content["Default"][
            "TimeLimit.annihilation"
        ] = self.annihilation.value()
        self.config.content["Default"]["TimesLimit.run"] = self.num.value()
        self.config.content["Default"]["SelfSet.MailAddress"] = self.mail_address.text()
        self.config.content["Default"]["SelfSet.BossKey"] = self.boss_key.text()

        if self.if_sleep.isChecked():
            self.config.content["Default"]["SelfSet.IfSleep"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfSleep"] = "False"

        if self.if_self_start.isChecked():
            self.config.content["Default"]["SelfSet.IfSelfStart"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfSelfStart"] = "False"

        if self.if_proxy_directly.isChecked():
            self.config.content["Default"]["SelfSet.IfProxyDirectly"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfProxyDirectly"] = "False"

        if self.if_send_mail.isChecked():
            self.config.content["Default"]["SelfSet.IfSendMail"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfSendMail"] = "False"

        if self.if_send_error_only.isChecked():
            self.config.content["Default"]["SelfSet.IfSendMail.OnlyError"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfSendMail.OnlyError"] = "False"

        if self.if_silence.isChecked():
            self.config.content["Default"]["SelfSet.IfSilence"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfSilence"] = "False"

        if self.if_to_tray.isChecked():
            self.config.content["Default"]["SelfSet.IfToTray"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfToTray"] = "False"

        for i in range(10):
            if self.start_time[i][0].isChecked():
                self.config.content["Default"][f"TimeSet.set{i + 1}"] = "True"
            else:
                self.config.content["Default"][f"TimeSet.set{i + 1}"] = "False"
            time = self.start_time[i][1].getTime().toString("HH:mm")
            self.config.content["Default"][f"TimeSet.run{i + 1}"] = time

        # 将配置信息同步至本地JSON文件
        self.config.save_config()

        # 同步程序配置至GUI
        self.update_config()

    def set_theme(self):
        """手动更新主题色到组件"""

        self.user_list_simple.setStyleSheet("QTableWidget::item {}")
        self.user_list_beta.setStyleSheet("QTableWidget::item {}")

    def read(self, operation):
        """弹出对话框组件进行读入"""

        class InputMessageBox(MessageBoxBase):
            """输入对话框"""

            def __init__(self, parent, title: str, content: str, mode: str):
                super().__init__(parent)
                self.title = SubtitleLabel(title)

                if mode == "明文":
                    self.input = LineEdit()
                elif mode == "密码":
                    self.input = PasswordLineEdit()

                self.input.setPlaceholderText(content)
                self.input.setClearButtonEnabled(True)

                # 将组件添加到布局中
                self.viewLayout.addWidget(self.title)
                self.viewLayout.addWidget(self.input)

        # 读入PASSWORD
        if operation == "key":

            choice = InputMessageBox(self.ui, "请输入管理密钥", "管理密钥", "密码")
            if choice.exec() and choice.input.text() != "":
                self.PASSWORD = choice.input.text()
                self.update_user_info("normal")

        elif operation == "oldkey":

            choice = InputMessageBox(
                self.ui, "请输入旧的管理密钥", "旧管理密钥", "密码"
            )
            if choice.exec() and choice.input.text() != "":
                self.PASSWORD = choice.input.text()
                return True
            else:
                return False

        elif operation == "newkey":

            choice = InputMessageBox(
                self.ui, "请输入新的管理密钥", "新管理密钥", "密码"
            )
            if choice.exec() and choice.input.text() != "":
                return choice.input.text()
            else:
                return None

        elif operation == "setkey":

            choice = InputMessageBox(
                self.ui,
                "未检测到管理密钥，请设置您的管理密钥",
                "管理密钥",
                "密码",
            )
            if choice.exec() and choice.input.text() != "":
                self.PASSWORD = choice.input.text()
                return True
            else:
                return False

        # 读入选择
        elif operation == "question_runner":
            choice = MessageBox(
                self.MaaManager.question_title,
                self.MaaManager.question_info,
                None,
            )
            if choice.exec():
                self.MaaManager.question_choice = "Yes"
            else:
                self.MaaManager.question_choice = "No"

        # 读入MAA文件目录
        elif operation == "file_path_maa":
            file_path = QFileDialog.getExistingDirectory(self.ui, "选择MAA文件夹")
            if file_path:
                self.maa_path.setText(file_path)

        # 读入自定义基建文件目录
        elif operation == "file_path_infrastructure":
            file_path, _ = QFileDialog.getOpenFileName(
                self.ui, "选择自定义基建文件", "", "JSON 文件 (*.json)"
            )
            return file_path

    def set_system(self):
        """设置系统相关配置"""

        # 同步系统休眠状态
        if self.config.content["Default"]["SelfSet.IfSleep"] == "True":
            # 设置系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(
                self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED
            )
        elif self.config.content["Default"]["SelfSet.IfSleep"] == "False":
            # 恢复系统电源状态
            ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)

        # 同步开机自启
        if (
            self.config.content["Default"]["SelfSet.IfSelfStart"] == "True"
            and not self.is_startup()
        ):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                winreg.KEY_SET_VALUE,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
            )
            winreg.SetValueEx(
                key, self.config.app_name, 0, winreg.REG_SZ, self.config.app_path_sys
            )
            winreg.CloseKey(key)
        elif (
            self.config.content["Default"]["SelfSet.IfSelfStart"] == "False"
            and self.is_startup()
        ):
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                winreg.KEY_SET_VALUE,
                winreg.KEY_ALL_ACCESS | winreg.KEY_WRITE | winreg.KEY_CREATE_SUB_KEY,
            )
            winreg.DeleteValue(key, self.config.app_name)
            winreg.CloseKey(key)

    def is_startup(self):
        """判断程序是否已经开机自启"""

        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )

        try:
            value, _ = winreg.QueryValueEx(key, self.config.app_name)
            winreg.CloseKey(key)
            return True
        except FileNotFoundError:
            winreg.CloseKey(key)
            return False

    def timed_start(self):
        """定时启动代理任务"""

        # 获取定时列表
        time_set = [
            self.config.content["Default"][f"TimeSet.run{_ + 1}"]
            for _ in range(10)
            if self.config.content["Default"][f"TimeSet.set{_ + 1}"] == "True"
        ]
        # 按时间调起代理任务
        curtime = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        if (
            curtime[11:16] in time_set
            and curtime != self.last_time
            and not self.MaaManager.isRunning()
        ):
            self.last_time = curtime
            self.maa_starter("日常代理")

    def switch_silence(self, mode, emulator_path, boss_key):
        """切换静默模式"""

        if mode == "启用":
            self.Timer.timeout.disconnect()
            self.Timer.timeout.connect(self.set_theme)
            self.Timer.timeout.connect(self.set_system)
            self.Timer.timeout.connect(self.timed_start)
            self.Timer.timeout.connect(
                lambda: self.set_silence(emulator_path, boss_key)
            )
        elif mode == "禁用":
            self.Timer.timeout.disconnect()
            self.Timer.timeout.connect(self.set_theme)
            self.Timer.timeout.connect(self.set_system)
            self.Timer.timeout.connect(self.timed_start)

    def set_silence(self, emulator_path, boss_key):
        """设置静默模式"""

        windows = self.get_window_info()
        if any(emulator_path in _ for _ in windows):
            try:
                pyautogui.hotkey(*boss_key)
            except pyautogui.FailSafeException as e:
                # 执行日志记录，暂时缺省
                pass

    def get_window_info(self):
        """获取当前窗口信息"""

        def callback(hwnd, window_info):
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd):
                _, pid = win32process.GetWindowThreadProcessId(hwnd)
                process = psutil.Process(pid)
                window_info.append((win32gui.GetWindowText(hwnd), process.exe()))
            return True

        window_info = []
        win32gui.EnumWindows(callback, window_info)
        return window_info

    def maa_starter(self, mode):
        """启动MaaManager线程运行任务"""

        # 检查MAA路径是否可用
        if (
            not (
                Path(self.config.content["Default"]["MaaSet.path"]) / "MAA.exe"
            ).exists()
            and (
                Path(self.config.content["Default"]["MaaSet.path"]) / "config/gui.json"
            ).exists()
        ):
            choice = MessageBox("错误", "您还未正确配置MAA路径！", self.ui)
            choice.cancelButton.hide()
            choice.buttonLayout.insertStretch(1)
            if choice.exec():
                return None

        self.maa_running_set(f"{mode}_开始")

        # 配置参数
        self.MaaManager.mode = mode
        self.config.cur.execute("SELECT * FROM adminx WHERE True")
        data = self.config.cur.fetchall()
        self.MaaManager.data = [list(row) for row in data]

        # 启动执行线程
        self.MaaManager.start()

    def maa_ender(self, mode):
        """中止MAA线程"""

        self.switch_silence("禁用", "", [])

        self.MaaManager.requestInterruption()
        self.MaaManager.wait()

        self.maa_running_set(mode)

    def maa_running_set(self, mode):
        """处理MAA运行过程中的GUI组件变化"""

        if "开始" in mode:

            self.MaaManager.accomplish.disconnect()
            self.user_add.setEnabled(False)
            self.user_del.setEnabled(False)
            self.user_switch.setEnabled(False)
            self.set_maa.setEnabled(False)

            self.update_user_info("read_only")

            if mode == "日常代理_开始":
                self.MaaManager.accomplish.connect(
                    lambda: self.maa_ender("日常代理_结束")
                )
                self.check_start.setEnabled(False)
                self.run_now.clicked.disconnect()
                self.run_now.setText("结束运行")
                self.run_now.clicked.connect(lambda: self.maa_ender("日常代理_结束"))

            elif mode == "人工排查_开始":
                self.MaaManager.accomplish.connect(
                    lambda: self.maa_ender("人工排查_结束")
                )
                self.run_now.setEnabled(False)
                self.check_start.clicked.disconnect()
                self.check_start.setText("中止排查")
                self.check_start.clicked.connect(
                    lambda: self.maa_ender("人工排查_结束")
                )

            elif mode == "设置MAA_全局_开始" or mode == "设置MAA_用户_开始":
                self.MaaManager.accomplish.connect(
                    lambda: self.maa_ender("设置MAA_结束")
                )
                self.run_now.setEnabled(False)
                self.check_start.setEnabled(False)

        elif "结束" in mode:

            shutil.copy(
                self.config.app_path / "data/MAAconfig/Default/gui.json",
                Path(self.config.content["Default"]["MaaSet.path"]) / "config",
            )
            self.user_add.setEnabled(True)
            self.user_del.setEnabled(True)
            self.user_switch.setEnabled(True)
            self.set_maa.setEnabled(True)

            self.update_user_info("editable")

            if mode == "日常代理_结束":

                self.check_start.setEnabled(True)
                self.run_now.clicked.disconnect()
                self.run_now.setText("立即执行")
                self.run_now.clicked.connect(lambda: self.maa_starter("日常代理"))

            elif mode == "人工排查_结束":

                self.run_now.setEnabled(True)
                self.check_start.clicked.disconnect()
                self.check_start.setText("开始排查")
                self.check_start.clicked.connect(lambda: self.maa_starter("人工排查"))

            elif mode == "设置MAA_结束":

                self.run_now.setEnabled(True)
                self.check_start.setEnabled(True)

    def server_date(self):
        """获取当前的服务器日期"""

        dt = datetime.datetime.now()
        if dt.time() < datetime.datetime.min.time().replace(hour=4):
            dt = dt - datetime.timedelta(days=1)
        return dt.strftime("%Y-%m-%d")

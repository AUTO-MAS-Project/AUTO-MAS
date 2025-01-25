class Main(QWidget):

    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self, config: AppConfig, notify: Notification, crypto: CryptoHandler):
        super().__init__()

        self.config = config
        self.notify = notify
        self.crypto = crypto

        

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
        # self.run_now.clicked.connect(lambda: self.maa_starter("自动代理"))

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

        # self.if_sleep: CheckBox = self.ui.findChild(CheckBox, "checkBox_IfAllowSleep")
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
        self.MaaManager.accomplish.connect(lambda: self.maa_ender("自动代理_结束"))
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
            self.maa_starter("自动代理")



    # def update_config(self):
    #     """将self.config中的程序配置同步至GUI界面"""

    #     # 阻止GUI程序配置被立即读入程序形成死循环
    #     self.if_update_config = False

    #     self.main_tab.setCurrentIndex(
    #         self.config.content["Default"]["SelfSet.MainIndex"]
    #     )

    #     self.maa_path.setText(str(Path(self.config.content["Default"]["MaaSet.path"])))
    #     self.routine.setValue(self.config.content["Default"]["TimeLimit.routine"])
    #     self.annihilation.setValue(
    #         self.config.content["Default"]["TimeLimit.annihilation"]
    #     )
    #     self.num.setValue(self.config.content["Default"]["TimesLimit.run"])
    #     self.mail_address.setText(self.config.content["Default"]["SelfSet.MailAddress"])
    #     self.boss_key.setText(self.config.content["Default"]["SelfSet.BossKey"])

    #     self.if_self_start.setChecked(
    #         bool(self.config.content["Default"]["SelfSet.IfSelfStart"] == "True")
    #     )

    #     self.if_sleep.setChecked(
    #         bool(self.config.content["Default"]["SelfSet.IfAllowSleep"] == "True")
    #     )

    #     self.if_proxy_directly.setChecked(
    #         bool(self.config.content["Default"]["SelfSet.IfProxyDirectly"] == "True")
    #     )

    #     self.if_send_mail.setChecked(
    #         bool(self.config.content["Default"]["SelfSet.IfSendMail"] == "True")
    #     )

    #     self.mail_address.setVisible(
    #         bool(self.config.content["Default"]["SelfSet.IfSendMail"] == "True")
    #     )

    #     self.if_send_error_only.setChecked(
    #         bool(
    #             self.config.content["Default"]["SelfSet.IfSendMail.OnlyError"] == "True"
    #         )
    #     )

    #     self.if_send_error_only.setVisible(
    #         bool(self.config.content["Default"]["SelfSet.IfSendMail"] == "True")
    #     )

    #     self.if_silence.setChecked(
    #         bool(self.config.content["Default"]["SelfSet.IfSilence"] == "True")
    #     )

    #     self.boss_key.setVisible(
    #         bool(self.config.content["Default"]["SelfSet.IfSilence"] == "True")
    #     )

    #     self.if_to_tray.setChecked(
    #         bool(self.config.content["Default"]["SelfSet.IfToTray"] == "True")
    #     )

    #     for i in range(10):
    #         self.start_time[i][0].setChecked(
    #             bool(self.config.content["Default"][f"TimeSet.set{i + 1}"] == "True")
    #         )
    #         time = QtCore.QTime(
    #             int(self.config.content["Default"][f"TimeSet.run{i + 1}"][:2]),
    #             int(self.config.content["Default"][f"TimeSet.run{i + 1}"][3:]),
    #         )
    #         self.start_time[i][1].setTime(time)
    #     self.if_update_config = True



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
            self.config.content["Default"]["SelfSet.IfAllowSleep"] = "True"
        else:
            self.config.content["Default"]["SelfSet.IfAllowSleep"] = "False"

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

        
            def get_maa_config(self, info):
                """获取MAA配置文件"""

                # 获取全局MAA配置文件
                if info == ["Default"]:
                    shutil.copy(
                        Path(self.config.content["Default"]["MaaSet.path"])
                        / "config/gui.json",
                        self.config.app_path / "data/MAAconfig/Default",
                    )
                # 获取基建配置文件
         
                # 获取高级用户MAA配置文件
                elif info[2] in ["routine", "annihilation"]:
                    (
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[info[0]]}/{info[1]}/{info[2]}"
                    ).mkdir(parents=True, exist_ok=True)
                    shutil.copy(
                        Path(self.config.content["Default"]["MaaSet.path"])
                        / "config/gui.json",
                        self.config.app_path
                        / f"data/MAAconfig/{self.user_mode_list[info[0]]}/{info[1]}/{info[2]}",
                    )

    def set_theme(self):
        """手动更新主题色到组件"""

        self.user_list_simple.setStyleSheet("QTableWidget::item {}")
        self.user_list_beta.setStyleSheet("QTableWidget::item {}")

    
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

            if mode == "自动代理_开始":
                self.MaaManager.accomplish.connect(
                    lambda: self.maa_ender("自动代理_结束")
                )
                self.check_start.setEnabled(False)
                self.run_now.clicked.disconnect()
                self.run_now.setText("结束运行")
                self.run_now.clicked.connect(lambda: self.maa_ender("自动代理_结束"))

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

            if mode == "自动代理_结束":

                self.check_start.setEnabled(True)
                self.run_now.clicked.disconnect()
                self.run_now.setText("立即执行")
                self.run_now.clicked.connect(lambda: self.maa_starter("自动代理"))

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

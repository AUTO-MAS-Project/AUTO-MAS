#   <AUTO_MAA:A MAA Multi Account Management and Automation Tool>
#   Copyright © <2024> <DLmaster361>

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   DLmaster_361@163.com

import sqlite3
import subprocess
import atexit
import datetime
import time
import os
from termcolor import colored

#资源回收
def cleanup():
    if os.path.exists("state/BEGIN"):
        os.remove("state/BEGIN")

DATABASE="data/data.db"

#设置回调函数
atexit.register(cleanup)
while True:
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM timeset WHERE True")
    timeset=cur.fetchall()
    cur.close()
    db.close()
    timeset=[list(row) for row in timeset]
    timeset=[timeset[i][0] for i in range(len(timeset))]
    for i in range(60):
        #展示当前信息
        curtime=datetime.datetime.now().strftime("%H:%M")
        os.system('cls')
        if len(timeset)!=0:
            print(colored("设定时间："+'，'.join(timeset),'green'))
        print(colored("当前时间："+curtime,'green'))
        print(colored("运行日志：",'green'))
        if os.path.exists("state/running"):
            print(colored("正在运行代理",'yellow'))
        elif os.path.exists("log.txt"):
            with open("log.txt",'r',encoding="utf-8") as f:
                linex=f.read()
                print(colored(linex,'light_green'))
        else:
            print(colored("暂无",'light_green'))
        #定时执行
        if (curtime in timeset) and not os.path.exists("state/running"):
            with open("state/BEGIN","w",encoding="utf-8") as f:
                print("BEGIN",file=f)
            run=subprocess.Popen(["run.exe"])
            runpid=run.pid
            while True:
                if os.path.exists("state/END"):
                    os.system('taskkill /F /T /PID '+str(runpid))
                    os.remove("state/END")
                    break
                time.sleep(1)
            os.remove("state/BEGIN")
        time.sleep(1)
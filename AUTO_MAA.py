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
import datetime
import time
import os
from termcolor import colored

DATABASE="data/data.db"
db=sqlite3.connect(DATABASE)
cur=db.cursor()
cur.execute("SELECT * FROM timeset WHERE True")
timeset=cur.fetchall()
timeset=[list(row) for row in timeset]
while True:
    curtime=datetime.datetime.now().strftime("%H:%M")
    print(colored("当前时间："+curtime,'green'))
    timenew=[]
    timenew.append(curtime)
    if timenew in timeset:
        print(colored("开始执行",'yellow'))
        maa=subprocess.Popen(["run.exe"])
        maapid=maa.pid
        while True:
            if os.path.exists("OVER"):
                os.system('taskkill /F /T /PID '+str(maapid))
                os.remove("OVER")
                print(colored("执行完毕",'yellow'))
                break
    time.sleep(1)
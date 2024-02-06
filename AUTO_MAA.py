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
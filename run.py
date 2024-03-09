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

import os
import subprocess
import atexit
import sqlite3
import datetime
import time
import json
from termcolor import colored

#执行MAA任务
def runmaa(id,tel,game,num=3):
    #配置MAA运行参数
    with open(setpath,"r",encoding="utf-8") as f:
        data=json.load(f)
    data["Configurations"]["Default"]["Start.AccountName"]=tel[:3]+"****"+tel[7:]
    data["Configurations"]["Default"]["MainFunction.Stage1"]="Annihilation"
    data["Configurations"]["Default"]["Fight.RemainingSanityStage"]=game
    data["Configurations"]["Default"]["Fight.UseRemainingSanityStage"]="True"
    data["Configurations"]["Default"]["GUI.CustomStageCode"]="True"
    with open(setpath,"w",encoding="utf-8") as f:
        json.dump(data,f)
    #开始运行
    for i in range(num):
        global idnew,idold,idfail,idall,logx,logi
        #创建MAA任务
        maa=subprocess.Popen([maapath])
        maapid=maa.pid
        #等待MAA启动
        idsuccess=idnew+idold
        idwait=[idx for idx in idall if not idx in idsuccess+idfail+[id]]
        os.system('cls')
        if i==0:
            print(colored("正在代理：",'white')+colored(id,'blue'))
        else:
            print(colored("正在代理：",'white')+colored(id,'light_blue'))
        print(colored("等待代理：",'white')+colored('，'.join(idwait),'yellow'))
        print(colored("代理成功：",'white')+colored('，'.join(idsuccess),'green'))
        print(colored("代理失败：",'white')+colored('，'.join(idfail),'red'))
        print(colored("运行日志：",'white')+colored("等待MAA初始化",'light_green'))
        time.sleep(60)
        #监测MAA运行状态
        while True:
            #打印基本信息
            os.system('cls')
            if i==0:
                print(colored("正在代理：",'white')+colored(id,'blue'))
            else:
                print(colored("正在代理：",'white')+colored(id,'light_blue'))
            print(colored("等待代理：",'white')+colored('，'.join(idwait),'yellow'))
            print(colored("代理成功：",'white')+colored('，'.join(idsuccess),'green'))
            print(colored("代理失败：",'white')+colored('，'.join(idfail),'red'))
            print(colored("运行日志：",'white'))
            #读取并保存MAA日志
            with open(logpath,'r',encoding='utf-8') as f:
                logs=f.readlines()[-1:-10:-1]
                print(colored(''.join(logs[::-1]),'light_green'))
                log=''.join(logs)
                logx[logi]=log
                logi=(logi+1) % len(logx)
            #判断MAA程序运行状态
            if ("任务已全部完成！" in log):
                return True
            elif ("请检查连接设置或尝试重启模拟器与 ADB 或重启电脑" in log) or ("已停止" in log) or ("MaaAssistantArknights GUI exited" in log) or timeout():
                os.system('taskkill /F /T /PID '+str(maapid))
                break
            time.sleep(10)
    return False

#检查是否超时
def timeout():
    global logx
    log0=logx[0]
    for i in range(len(logx)):
        if logx[i]!=log0:
            return False
    return True

#更新已完成用户的数据
def updata(id):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE admin=?",(id,))
    info=cur.fetchall()
    cur.execute("UPDATE adminx SET day=? WHERE admin=?",(info[0][2]-1,id))
    db.commit()
    cur.execute("UPDATE adminx SET last=? WHERE admin=?",(curdate,id))
    db.commit()
    cur.close()
    db.close()
    return 0

#资源回收
def cleanup():
    if os.path.exists("state/RUNNING"):
        os.remove("state/RUNNING")

#读取运行情况
if os.path.exists("state/RUNNING"):
    exit()
#标记当前正在运行
with open("state/RUNNING","w",encoding="utf-8") as f:
    print("RUNNING",file=f)
#设置回调函数
atexit.register(cleanup)
#获取PATH与用户数据
DATABASE="data/data.db"
db=sqlite3.connect(DATABASE)
cur=db.cursor()
cur.execute("SELECT * FROM pathset WHERE True")
path=cur.fetchall()
path=str(path[0][0])
setpath=path+"/config/gui.json"
logpath=path+"/debug/gui.log"
maapath=path+"/MAA.exe"
cur.execute("SELECT * FROM adminx WHERE True")
data=cur.fetchall()
data=[list(row) for row in data]
cur.close()
db.close()
#开始执行
curdate=datetime.date.today().strftime('%Y-%m-%d')
begintime=datetime.datetime.now().strftime("%H:%M")
idnew=[]
idold=[]
idfail=[]
idall=[data[i][0] for i in range(len(data))]
LOGXLEN=60
logx=['' for i in range(LOGXLEN)]
logi=0
for i in range(len(data)):
    if data[i][3]=='y' and data[i][4]!=curdate and data[i][2]>0:
        book=runmaa(data[i][0],data[i][1],data[i][5])
        if book:
            updata(data[i][0])
            idnew.append(data[i][0])
        else:
            idfail.append(data[i][0])
for i in range(len(data)):
    if data[i][3]=='y' and data[i][4]==curdate and data[i][2]>0:
        book=runmaa(data[i][0],data[i][1],data[i][5])
        if book:
            idold.append(data[i][0])
        else:
            idall.remove(data[i][0])
endtime=datetime.datetime.now().strftime("%H:%M")
with open("log.txt","w",encoding="utf-8") as f:
    print("任务开始时间："+begintime+"，结束时间："+endtime,file=f)
    print("已完成数："+str(len(idnew))+"，未完成数："+str(len(idfail))+"，重复执行数："+str(len(idold)),file=f)
    if len(idfail)!=0:
        print("代理未完成的用户：",file=f)
    for i in range(len(idfail)):
        print(idfail[i],file=f)
if os.path.exists("state/BEGIN"):
    with open("state/END","w",encoding="utf-8") as f:
        print("END",file=f)
exit()
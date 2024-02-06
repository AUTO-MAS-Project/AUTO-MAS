import os
import subprocess
import sqlite3
import datetime
import time
import json
from termcolor import colored

#判断MAA程序运行状态
def ifoff():
    while True:
        time.sleep(10)
        with open(logpath,'r',encoding='utf-8') as f:
            logs=f.readlines()[-1:-10:-1]
            log=''.join(logs)
            print(colored('\n'.join(logs[::-1]),"green"))
            if "任务已全部完成！" in log:
                return True
            elif ("请检查连接设置或尝试重启模拟器与 ADB 或重启电脑" in log) or ("已停止" in log):
                return False

#执行MAA任务
def runmaa(tel,game,num=2):
    #配置MAA运行参数
    with open(setpath,"r",encoding="utf-8") as f:
        data = json.load(f)
    data["Configurations"]["Default"]["Start.AccountName"]=tel[:3]+"****"+tel[7:]
    week=str(datetime.datetime.now().strftime('%A'))
    if week=="Monday":
        data["Configurations"]["Default"]["MainFunction.Stage1"]="Annihilation"
    else:
        data["Configurations"]["Default"]["MainFunction.Stage1"]=game
    with open(setpath,"w",encoding="utf-8") as f:
        json.dump(data,f)
    #开始运行
    for i in range(num):
        maa=subprocess.Popen([maapath])
        maapid=maa.pid
        time.sleep(60)
        if ifoff():
            return True
        else:
            os.system('taskkill /F /T /PID '+str(maapid))
    return False

#更新已完成用户的数据
def updata(id):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE admin='%s'" %(id))
    info=cur.fetchall()
    cur.execute("UPDATE adminx SET day=%d WHERE admin='%s'" %(info[0][2]-1,id))
    db.commit()
    cur.execute("UPDATE adminx SET last='%s' WHERE admin='%s'" %(curdate,id))
    print("upcurdate")
    db.commit()
    cur.close()
    db.close()
    return 0

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
curdate=datetime.date.today()
curdate=curdate.strftime('%Y-%m-%d')
idnew=[]
idold=[]
idfail=[]
for i in range(len(data)):
    if data[i][3]=='y' and data[i][4]!=curdate and data[i][2]>0:
        book=runmaa(data[i][1],data[i][5])
        if book:
            updata(data[i][0])
            idnew.append(data[i][0])
            print(colored("已完成"+data[i][0]+"今日的代理","yellow"))
        else:
            idfail.append(data[i][0])
            print(colored("异常中止"+data[i][0]+"的代理","red"))
for i in range(len(data)):
    if data[i][3]=='y' and data[i][4]==curdate and data[i][2]>0:
        book=runmaa(data[i][1],data[i][5])
        if book:
            idold.append(data[i][0])
            print(colored("已重复完成"+data[i][0]+"今日的代理","yellow"))
with open("log.txt","w", encoding="utf-8") as f:
    print("任务结束，已完成数："+str(len(idnew))+"，未完成数："+str(len(idfail))+"，重复执行数："+str(len(idold)),file=f)
    if len(idfail)!=0:
        print("代理未完成的用户：",file=f)
    for i in range(len(idfail)):
        print(idfail[i],file=f)
with open("OVER","w", encoding="utf-8") as f:
    print("OVER",file=f)
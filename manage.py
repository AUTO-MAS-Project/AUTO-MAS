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
import datetime
import msvcrt
import sys
import os
import hashlib
import random
import secrets
from Crypto.Cipher import AES
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Util.Padding import pad,unpad

#读入密码
def readpass(text):
    sys.stdout=sys.__stdout__
    sys.stdout.write(text)
    sys.stdout.flush()
    p=''
    while True:
        typed=msvcrt.getch()
        if len(p)!=0:
            if typed==b'\r':
                sys.stdout.write('\b*')
                sys.stdout.flush()
                break
            elif typed==b'\b':
                p=p[:-1]
                sys.stdout.write('\b \b')
                sys.stdout.flush()
            else:
                p+=typed.decode("utf-8")
                sys.stdout.write('\b*'+typed.decode("utf-8"))
                sys.stdout.flush()
        elif typed!=b'\r' and typed!=b'\b':
            p+=typed.decode("utf-8")
            sys.stdout.write(typed.decode("utf-8"))
            sys.stdout.flush()
    print('')
    return p

#配置密钥
def getPASSWORD(PASSWORD):
    #生成RSA密钥对
    key=RSA.generate(2048)
    public_key_local=key.publickey()
    private_key=key
    #保存RSA公钥
    with open('data/key/public_key.pem','wb') as f:
        f.write(public_key_local.exportKey())
    #生成密钥转换与校验随机盐
    PASSWORDsalt=secrets.token_hex(random.randint(32,1024))
    with open("data/key/PASSWORDsalt.txt","w",encoding="utf-8") as f:
        print(PASSWORDsalt,file=f)
    verifysalt=secrets.token_hex(random.randint(32,1024))
    with open("data/key/verifysalt.txt","w",encoding="utf-8") as f:
        print(verifysalt,file=f)
    #将管理密钥转化为AES-256密钥
    AES_password=hashlib.sha256((PASSWORD+PASSWORDsalt).encode("utf-8")).digest()
    #生成AES-256密钥校验哈希值并保存
    AES_password_verify=hashlib.sha256(AES_password+verifysalt.encode("utf-8")).digest()
    with open("data/key/AES_password_verify.bin","wb") as f:
        f.write(AES_password_verify)
    #AES-256加密RSA私钥并保存密文
    AES_key=AES.new(AES_password,AES.MODE_ECB)
    private_key_local=AES_key.encrypt(pad(private_key.exportKey(),32))
    with open("data/key/private_key.bin","wb") as f:
        f.write(private_key_local)

#加密
def encryptx(note):
    #读取RSA公钥
    with open('data/key/public_key.pem','rb') as f:
        public_key_local=RSA.import_key(f.read())
    #使用RSA公钥对数据进行加密
    cipher=PKCS1_OAEP.new(public_key_local)
    encrypted=cipher.encrypt(note.encode("utf-8"))
    return encrypted

#解密
def decryptx(note,PASSWORD):
    #读入RSA私钥密文、盐与校验哈希值
    with open("data/key/private_key.bin","rb") as f:
        private_key_local=f.read().strip()
    with open("data/key/PASSWORDsalt.txt","r",encoding="utf-8") as f:
        PASSWORDsalt=f.read().strip()
    with open("data/key/verifysalt.txt","r",encoding="utf-8") as f:
        verifysalt=f.read().strip()
    with open("data/key/AES_password_verify.bin","rb") as f:
        AES_password_verify=f.read().strip()
    #将管理密钥转化为AES-256密钥并验证
    AES_password=hashlib.sha256((PASSWORD+PASSWORDsalt).encode("utf-8")).digest()
    AES_password_SHA=hashlib.sha256(AES_password+verifysalt.encode("utf-8")).digest()
    if AES_password_SHA!=AES_password_verify:
        return "管理密钥错误"
    else:
        #AES解密RSA私钥
        AES_key=AES.new(AES_password,AES.MODE_ECB)
        private_key_pem=unpad(AES_key.decrypt(private_key_local),32)
        private_key=RSA.import_key(private_key_pem)
        #使用RSA私钥解密数据
        decrypter=PKCS1_OAEP.new(private_key)
        note=decrypter.decrypt(note)
        return note.decode("utf-8")

#修改管理密钥
def changePASSWORD():
    #获取用户信息
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE True")
    data=cur.fetchall()
    cur.close()
    db.close()
    data=[list(row) for row in data]
    global PASSWORD
    #验证管理密钥
    PASSWORDold=readpass("请输入旧管理密钥：")
    if len(data)==0:
        print("当前无用户，验证自动通过")
        PASSWORDnew=readpass("请输入新管理密钥：")
        getPASSWORD(PASSWORDnew)
        PASSWORD=PASSWORDnew
        return "管理密钥修改成功"
    while decryptx(data[0][6],PASSWORDold)=="管理密钥错误":
            print("管理密钥错误")
            PASSWORDold=readpass("请输入旧管理密钥：")
    print("验证通过")
    #修改管理密钥
    PASSWORDnew=readpass("请输入新管理密钥：")
    #使用旧管理密钥解密
    for i in range(len(data)):
        data[i][6]=decryptx(data[i][6],PASSWORDold)
    #使用新管理密钥重新加密
    getPASSWORD(PASSWORDnew)
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    for i in range(len(data)):
        cur.execute("UPDATE adminx SET password=? WHERE admin=?",(encryptx(data[i][6]),data[i][0]))
        db.commit()
    cur.close()
    db.close()
    PASSWORD=PASSWORDnew
    return "管理密钥修改成功"

#添加用户
def add():
    adminx=input("用户名：")
    #用户名重复验证
    while search(adminx,0)=="":
        print("该用户已存在，请重新输入")
        adminx=input("用户名：")
    numberx=input("手机号码：")
    dayx=int(input("代理天数："))
    gamex=input("关卡号：")
    passwordx=readpass("密码：")
    passwordx=encryptx(passwordx)
    #应用更新
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("INSERT INTO adminx VALUES(?,?,?,'y','2000-01-01',?,?)",(adminx,numberx,dayx,gamex,passwordx))
    db.commit()
    cur.close()
    db.close()
    return "操作成功"

#删除用户信息
def delete(id):
    #检查用户是否存在
    if search(id,0)!="":
        return "未找到"+id
    #应用更新
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("DELETE FROM adminx WHERE admin=?",(id,))
    db.commit()
    cur.close()
    db.close()
    return "成功删除"+id

#检索用户信息与配置
def search(id,book):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    #处理启动时间查询
    if id=="time":
        cur.execute("SELECT * FROM timeset WHERE True")
        timex=cur.fetchall()
        timex=[list(row) for row in timex]
        cur.close()
        db.close()
        if len(timex)==0:
            return "启动时间未设置"
        else:
            for i in range(len(timex)):
                print(timex[i][0])
            return ""
    #处理MAA路径查询
    if id=="maa":
        cur.execute("SELECT * FROM pathset WHERE True")
        pathx=cur.fetchall()
        if len(pathx)>0:
            cur.close()
            db.close()
            return pathx[0][0]
        else:
            cur.close()
            db.close()
            return "MAA路径未设置"
    #处理用户查询与全部信息查询
    if id=="all":
        cur.execute("SELECT * FROM adminx WHERE True")
    else:
        cur.execute("SELECT * FROM adminx WHERE admin=?",(id,))
    data=cur.fetchall()
    #处理全部信息查询时的MAA路径与启动时间查询
    if id=="all":
        cur.execute("SELECT * FROM pathset WHERE True")
        pathx=cur.fetchall()
        if len(pathx)>0:
            print("\nMAA路径："+pathx[0][0])
        else:
            print("\nMAA路径未设置")
        cur.execute("SELECT * FROM timeset WHERE True")
        timex=cur.fetchall()
        timex=[list(row) for row in timex]
        if len(timex)==0:
            print("\n启动时间未设置")
        else:
            print("启动时间：",end='')
            for i in range(len(timex)):
                print(timex[i][0],end='    ')
            print('')
    cur.close()
    db.close()
    data=[list(row) for row in data]
    if len(data)>0:
        #转译执行情况、用户状态，对全部信息查询与无输出查询隐去密码
        curdate=datetime.date.today()
        curdate=curdate.strftime('%Y-%m-%d')
        for i in range(len(data)):
            if data[i][4]==curdate:
                data[i][4]="今日已执行"
            else:
                data[i][4]="今日未执行"
            if data[i][3]=='y':
                data[i][3]="启用"
            else:
                data[i][3]="禁用"
            if id=="all" or book==0:
                data[i][6]="******"
            else:
                #解密
                global PASSWORD
                if PASSWORD==0 or decryptx(data[i][6],PASSWORD)=="管理密钥错误":
                    PASSWORD=readpass("请输入管理密钥：")
                data[i][6]=decryptx(data[i][6],PASSWORD)
        #制表输出
        if book==1:
            print('')
            print(unit("用户名",15),unit("手机号码",12),unit("代理天数",8),unit("状态",4),unit("执行情况",10),unit("关卡",10),unit("密码",25))
            for i in range(len(data)):
                print(unit(data[i][0],15),unit(data[i][1],12),unit(data[i][2],8),unit(data[i][3],4),unit(data[i][4],10),unit(data[i][5],10),unit(data[i][6],25))
        return ""
    elif id=="all":
        return "\n当前没有用户记录"
    else:
        return "未找到"+id

#续期
def renewal(readxx):
    #提取用户名与续期时间
    for i in range(len(readxx)):
        if readxx[i]==' ':
            id=readxx[:i]
            dayp=int(readxx[i+1:])
            break
    #检查用户是否存在
    if search(id,0)!="":
        return "未找到"+id
    #应用更新
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE admin=?",(id,))
    data=cur.fetchall()
    cur.execute("UPDATE adminx SET day=? WHERE admin=?",(data[0][2]+dayp,id))
    db.commit()
    cur.close()
    db.close()
    return '成功更新'+id+'的代理天数至'+str(data[0][2]+dayp)+'天'

#用户状态配置
def turn(id,t):
    #检查用户是否存在
    if search(id,0)!="":
        return "未找到"+id
    #应用更新
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("UPDATE adminx SET status=? WHERE admin=?",(t,id))
    db.commit()
    cur.close()
    db.close()
    if t=='y':
        return '已启用'+id
    else:
        return '已禁用'+id

#修改刷取关卡
def gameid(readxx):
    #提取用户名与修改值
    for i in range(len(readxx)):
        if readxx[i]==' ':
            id=readxx[:i]
            gamep=readxx[i+1:]
            break
    #检查用户是否存在
    if search(id,0)!="":
        return "未找到"+id
    #导入与应用特殊关卡规则
    games={}
    with open('data/gameid.txt',encoding='utf-8') as f:
        gameids=f.readlines()
        for i in range(len(gameids)):
            for j in range(len(gameids[i])):
                if gameids[i][j]=='：':
                    gamein=gameids[i][:j]
                    gameout=gameids[i][j+1:]
                    break
            games[gamein]=gameout.strip()
    if gamep in games:
        gamep=games[gamep]
    #应用更新
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("UPDATE adminx SET game=? WHERE admin=?",(gamep,id))
    db.commit()
    cur.close()
    db.close()
    return '成功更新'+id+'的关卡为'+gamep

#设置MAA路径
def setpath(pathx):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM pathset WHERE True")
    pathold=cur.fetchall()
    if len(pathold)>0:
        cur.execute("UPDATE pathset SET path=? WHERE True",(pathx,))
    else:
        cur.execute("INSERT INTO pathset VALUES(?)",(pathx,))
    db.commit()
    cur.close()
    db.close()
    return "MAA路径已设置为"+pathx

#设置启动时间
def settime(book,timex):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    #检查待操作对象存在情况
    cur.execute("SELECT * FROM timeset WHERE True")
    timeold=cur.fetchall()
    timeold=[list(row) for row in timeold]
    timenew=[]
    timenew.append(timex)
    #添加时间设置
    if book=='+':
        if timenew in timeold:
            cur.close()
            db.close()
            return "已存在"+timex
        else:
            cur.execute("INSERT INTO timeset VALUES(?)",(timex,))
            db.commit()
            cur.close()
            db.close()
            return "已添加"+timex
    #删除时间设置
    elif book=='-':
        if timenew in timeold:
            cur.execute("DELETE FROM timeset WHERE time=?",(timex,))
            db.commit()
            cur.close()
            db.close()
            return "已删除"+timex
        else:
            cur.close()
            db.close()
            return "未找到"+timex

#统一制表单元
def unit(x,m):
    #字母与连接符占1位，中文占2位
    x=str(x)
    n=0
    for i in x:
        if 'a'<=i<='z' or 'A'<=i<='Z' or '0'<=i<='9' or i=='_' or i=='-':
            n+=1
    return '    '+x+' '*(m-2*len(x)+n)

#初期检查
DATABASE="data/data.db"
PASSWORD=0
if not os.path.exists(DATABASE):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    db.execute("CREATE TABLE adminx(admin text,number text,day int,status text,last date,game text,password byte)")
    db.execute("CREATE TABLE pathset(path text)")
    db.execute("CREATE TABLE timeset(time text)")
    readx=input("首次启动，请设置MAA路径：")
    cur.execute("INSERT INTO pathset VALUES(?)",(readx,))
    db.commit()
    cur.close()
    db.close()
    PASSWORD=readpass("请设置管理密钥（密钥与数据库绑定）：")
    getPASSWORD(PASSWORD)

#初始界面
print("Good evening!")
print(search("all",1))

#主程序
while True:
    read=input()
    if len(read)==0:
        print("无法识别的输入")
    elif read[0]=='+' and len(read)==1:
        print(add())
    elif read[0]=='-' and len(read)==1:
        os._exit(0)
    elif read[0]=='/':
        print(setpath(read[1:]))
    elif read[0]=='*' and len(read)==1:
        print(changePASSWORD())
    elif read[0]==':' and (read[1]=='+' or read[1]=='-'):
        print(settime(read[1],read[2:]))
    else:
        if read[-1]=='?' and read[-2]==' ':
            print(search(read[:-2],1))
        elif read[-1]=='+' and read[-2]==' ':
            print(renewal(read[:-2]))
        elif read[-1]=='-' and read[-2]==' ':
            print(delete(read[:-2]))
        elif read[-1]=='~' and read[-2]==' ':
            print(gameid(read[:-2]))
        elif (read[-1]=='y' or read[-1]=='n') and read[-2]==' ':
            print(turn(read[:-2],read[-1]))
        else:
            print("无法识别的输入")
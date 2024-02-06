import sqlite3
import datetime
import os

#添加用户
def add():
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    adminx=input("用户名：")
    #用户名重复验证
    while search(adminx,0)=="":
        print("该用户已存在，请重新输入")
        adminx=input("用户名：")
    numberx=input("手机号码：")
    dayx=int(input("代理天数："))
    gamex=input("关卡号：")
    passwordx=input("密码：")
    #应用更新
    cur.execute("INSERT INTO adminx(admin,number,day,status,last,game,password) VALUES('%s','%s',%d,'y','2000-01-01','%s','%s')" %(adminx,numberx,dayx,gamex,passwordx))
    db.commit()
    cur.close()
    db.close()
    return "操作成功"

#删除用户信息
def delete(id):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    #检查用户是否存在
    cur.execute("SELECT * FROM adminx WHERE admin='%s'" %(id))
    data=cur.fetchall()
    if len(data)==0:
        return "未找到"+id
    #应用更新
    cur.execute("DELETE FROM adminx WHERE admin='%s'" %(id))
    db.commit()
    cur.close()
    db.close()
    return "成功删除"+id

#检索用户信息与配置
def search(id,book):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    #处理MAA路径查询
    if id=="maa":
        cur.execute("SELECT * FROM setting WHERE True")
        pathx=cur.fetchall()
        if len(pathx)>0:
            return pathx[0][0]
        else:
            return "MAA路径未设置"
    #处理用户查询与全部信息查询
    if id=="all":
        cur.execute("SELECT * FROM adminx WHERE True")
    else:
        cur.execute("SELECT * FROM adminx WHERE admin='%s'" %(id))
    data=cur.fetchall()
    if id=="all":
        cur.execute("SELECT * FROM setting WHERE True")
        pathx=cur.fetchall()
        if len(pathx)>0:
            print("\nMAA路径："+pathx[0][0])
        else:
            print("\nMAA路径未设置")
    cur.close()
    db.close()
    data=[list(row) for row in data]
    if len(data)>0:
        #转译执行情况、用户状态，对全部信息查询隐去密码
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
            if id=="all":
                data[i][6]="******"
        #制表输出
        if book==1:
            print('')
            print(unit("用户名",15),unit("手机号码",12),unit("代理天数",8),unit("状态",4),unit("执行情况",10),unit("关卡",10),unit("密码",25))
            for i in range(len(data)):
                print(unit(data[i][0],15),unit(data[i][1],12),unit(data[i][2],8),unit(data[i][3],4),unit(data[i][4],10),unit(data[i][5],10),unit(data[i][6],25))
        return ""
    elif id=="all":
        return "当前没有用户记录"
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
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE admin='%s'" %(id))
    data=cur.fetchall()
    if len(data)==0:
        return "未找到"+id
    #应用更新
    cur.execute("UPDATE adminx SET day=%d WHERE admin='%s'" %(data[0][2]+dayp,id))
    db.commit()
    cur.close()
    db.close()
    return '成功更新'+id+'的代理天数至'+str(data[0][2]+dayp)+'天'

#用户状态配置
def turn(id,t):
    #检查用户是否存在
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE admin='%s'" %(id))
    data=cur.fetchall()
    if len(data)==0:
        return "未找到"+id
    #应用更新
    if t=='y' or t=='n':
        cur.execute("UPDATE adminx SET status='%s' WHERE admin='%s'" %(t,id))
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
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM adminx WHERE admin='%s'" %(id))
    data=cur.fetchall()
    if len(data)==0:
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
    cur.execute("UPDATE adminx SET game='%s' WHERE admin='%s'" %(gamep,id))
    db.commit()
    cur.close()
    db.close()
    return '成功更新'+id+'的关卡为'+gamep

#设置MAA路径
def setpath(pathx):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    cur.execute("SELECT * FROM setting WHERE True")
    pathold=cur.fetchall()
    if len(pathold)>0:
        cur.execute("UPDATE setting SET path='%s' WHERE True" %(pathx))
    else:
        cur.execute("INSERT INTO setting(path) VALUES('%s')" %(pathx))
    db.commit()
    cur.close()
    db.close()
    return "MAA路径已设置为"+pathx

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
if not os.path.exists(DATABASE):
    db=sqlite3.connect(DATABASE)
    cur=db.cursor()
    db.execute("CREATE TABLE adminx(admin text,number text,day int,status text,last date,game text,password text)")
    db.execute("CREATE TABLE setting(path text)")
    readx=input("首次启动，请设置MAA路径：")
    cur.execute("INSERT INTO setting(path) VALUES('%s')" %(readx))
    db.commit()
    cur.close()
    db.close()

#初始界面
print("Good evening!")
print(search("all",1))

#主程序
while True:
    read=input()
    if len(read)==0:
        print("无法识别的输入")
    elif read[0]=='+':
        print(add())
    elif read[0]=='-':
        exit()
    elif read[0]=='/':
        print(setpath(read[1:]))
    else:
        if read[-1]=='?':
            print(search(read[:-2],1))
        elif read[-1]=='+':
            print(renewal(read[:-2]))
        elif read[-1]=='-':
            print(delete(read[:-2]))
        elif read[-1]=='~':
            print(gameid(read[:-2]))
        elif read[-1]=='y' or read[-1]=='n':
            print(turn(read[:-2],read[-1]))
        else:
            print("无法识别的输入")
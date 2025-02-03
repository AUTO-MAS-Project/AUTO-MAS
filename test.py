import requests
from serverchan_sdk import sc_send

# 发送消息
sendkey = "SCT53272TqVLN4TlrrKmgcmKI1nnoQHmb"
title = "测试标题"
desp = "这是消息内容"
options = {"tags": "服务器报警|图片"}  # 可选参数

content = f'{title}\n{desp}'
data = {
    "msgtype": "text",
    "text": {
        "content": content
    }
}
response = requests.post(url='https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=2c9218cb-c086-42d9-9f0a-a8859e10cc0a'
                         , json=data)
print(isinstance(response.json(), dict))



"""
{"errcode":0,"errmsg":"ok"}
"""

"""
{'code': 0, 'message': '', 'data': {'pushid': '191226387', 'readkey': 'SCTUReMFXaCBsZi', 'error': 'SUCCESS', 'errno': 0}}
"""
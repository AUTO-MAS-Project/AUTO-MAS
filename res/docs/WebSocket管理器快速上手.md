# WebSocket 绠＄悊鍣ㄥ揩閫熶笂鎵?

杩欎唤鏂囨。闈㈠悜浜屾寮€鍙戣€咃紝鐩爣鏄敤鏈€灏戜唬鐮侀€氳繃 `ws_client_manager` 鍒涘缓骞剁鐞嗭細

- 姝ｅ悜杩炴帴锛堝悗绔富鍔ㄨ繛澶栭儴 WS 鏈嶅姟锛?
- 鍙嶅悜杩炴帴锛堝閮ㄥ鎴风杩炲叆鍚庣 WS 璺敱锛?

绠＄悊鍣ㄥ叆鍙ｄ綅浜庯細`app.utils.websocket.ws_client_manager`

---

## 1. 姝ｅ悜杩炴帴锛歰penws

閫傜敤鍦烘櫙锛氫綘鐭ラ亾鐩爣鏈嶅姟鍣ㄥ湴鍧€锛岄渶瑕佸悗绔富鍔ㄥ彂璧疯繛鎺ャ€?

```python
from app.utils.websocket import ws_client_manager

async def open_outbound_ws():
    client = await ws_client_manager.openws(
        name="MyOutbound",                 # 瀹㈡埛绔敮涓€鍚嶇О
        url="ws://127.0.0.1:5140/ws",     # 鐩爣 WS 鍦板潃
        ping_interval=15.0,
        ping_timeout=30.0,
        reconnect_interval=5.0,
        max_reconnect_attempts=-1,          # -1 琛ㄧず鏃犻檺閲嶈繛
    )

    # 鍙€夛細鍙戦€佽璇?
    await ws_client_manager.send_auth(
        name="MyOutbound",
        token="your-token",
        auth_type="auth",
    )

    # 鍙€夛細鍙戦€佷笟鍔℃秷鎭?
    await ws_client_manager.send_message(
        "MyOutbound",
        {"id": "Client", "type": "command", "data": {"hello": "world"}},
    )

    return client
```

---

## 2. 鍙嶅悜杩炴帴锛歰penwsr

### 澹版槑寮忓姩鎬佸弽鍚戦€氶亾锛堟帹鑽愶級

鐜板湪鍚庣鎻愪緵缁熶竴鍔ㄦ€佸叆鍙ｏ細`/api/ws/{channel_name}`銆?

浣犲彧闇€瑕佸厛澹版槑閫氶亾锛屽鎴风杩炴帴鍒板搴旇矾寰勫悗锛岃矾鐢变細鑷姩璋冪敤 `openwsr` 鎺ョ锛?

```python
from app.utils.websocket import ws_client_manager

# 鍚姩闃舵鎵ц涓€娆?
ws_client_manager.register_reverse_channel(
    name="123123",
    ping_interval=15.0,
    ping_timeout=30.0,
    auth_token="optional-token",
)
```

鐒跺悗璁╁閮ㄥ鎴风杩炴帴锛?

- `ws://<host>:<port>/api/ws/123123`

娉ㄦ剰锛?

- 鍙湁宸插０鏄庨€氶亾浼氳鏀捐锛涙湭澹版槑浼氳鎷掔粷銆?
- `wsdev` 涔熷凡鏀逛负鍚屾牱鐨勫０鏄庡紡鍐欐硶锛屽叆鍙ｄ负 `/api/ws/wsdev`銆?

濡傛灉浣犻渶瑕佸湪涓氬姟浠ｇ爜閲屾嬁鍒拌閫氶亾瀵瑰簲鐨勪細璇濆疄渚嬶紝鍙洿鎺ョ瓑寰咃細

```python
session = await ws_client_manager.wait_for_reverse_session("123123", timeout=10)

# session 鍙洿鎺ュ彂閫佹秷鎭?
await session.send_json({"id": "Client", "type": "command", "data": {"ok": True}})
```

---

## 3. 甯哥敤绠＄悊鎿嶄綔

```python
# 鏄惁瀛樺湪
ws_client_manager.has_client("MyOutbound")

# 璇诲彇缁熶竴浼氳瘽瀵硅薄锛堟鍚?鍙嶅悜閮藉彲锛?
session = ws_client_manager.get_session("MyOutbound")

# 鍒楀嚭鎵€鏈夎繛鎺ョ姸鎬?
clients = ws_client_manager.list_clients()

# 鏂紑杩炴帴
await ws_client_manager.disconnect_client("MyOutbound")

# 鍒犻櫎瀹㈡埛绔紙绯荤粺瀹㈡埛绔笉鍙垹闄わ級
await ws_client_manager.remove_client("MyOutbound")
```

---

## 3.1 WS 绠＄悊鍣ㄦ柟娉曟€昏

浠ヤ笅涓?`WSClientManager` 褰撳墠鍏叡鏂规硶锛屾寜鍔熻兘鍒嗙粍锛?

- 鍙嶅悜閫氶亾澹版槑锛?
- `register_reverse_channel(name, ping_interval=15.0, ping_timeout=30.0, auth_token=None, on_message=None, on_connect=None, on_disconnect=None, overwrite=True)`
- `unregister_reverse_channel(name)`
- `is_reverse_channel_registered(name)`
- `get_reverse_channel_config(name)`
- `list_reverse_channels()`
- 浼氳瘽绛夊緟涓庢煡璇細
- `wait_for_reverse_session(name, timeout=None)`
- `get_client(name)`
- `get_session(name)`
- `has_client(name)`
- `is_system_client(name)`
- `list_clients()`
- 姝ｅ悜/鍙嶅悜杩炴帴鎺у埗锛?
- `create_client(name, url, ping_interval=15.0, ping_timeout=30.0, reconnect_interval=5.0, max_reconnect_attempts=-1)`
- `openws(name, url, ping_interval=15.0, ping_timeout=30.0, reconnect_interval=5.0, max_reconnect_attempts=-1)`
- `openwsr(name, websocket, ping_interval=15.0, ping_timeout=30.0, auth_token=None, on_message=None, on_connect=None, on_disconnect=None)`
- `connect_client(name)`
- `disconnect_client(name)`
- `remove_client(name)`
- 娑堟伅鐩稿叧锛?
- `send_message(name, message)`
- `send_auth(name, token, auth_type="auth", extra_data=None)`
- `get_message_history(name=None)`
- `clear_message_history(name=None)`
- 璋冭瘯杩炴帴缁存姢锛?
- `add_debug_connection(ws)`
- `remove_debug_connection(ws)`
- 鍏朵粬宸ュ叿锛?
- `http_to_ws_url(http_url)`
- `init_system_client_koishi()`
- `update_system_client_koishi()`

---

## 4. 鏈€浣冲疄璺?

- `name` 淇濇寔鍏ㄥ眬鍞竴锛屽缓璁娇鐢ㄤ笟鍔″墠缂€锛堝 `Order-WS`銆乣Notify-WS`锛夈€?
- 灏介噺閫氳繃 `ws_client_manager.send_message/send_auth` 缁熶竴鍙戦€侊紝渚夸簬鍘嗗彶璁板綍涓庤皟璇曢〉鑱斿姩銆?
- 鍙嶅悜璺敱涓紭鍏堜娇鐢?`session.wait_closed()`锛岄伩鍏嶅嚱鏁版彁鍓嶈繑鍥炲鑷寸敓鍛藉懆鏈熶笉涓€鑷淬€?
- 绯荤粺淇濈暀鍚嶇О锛堝 `Main`銆乣Koishi`锛変笉瑕佺敤浜庢櫘閫氫笟鍔¤繛鎺ャ€?

---

## 5. 涓庣幇鏈変唬鐮佸鐓?

浣犲彲浠ョ洿鎺ュ弬鑰冭繖涓や釜瀹炵幇锛?

- 涓诲弽鍚戣繛鎺ュ叆鍙ｏ細`app/api/core.py` 涓?`/api/core/ws`
- 绠＄悊鍣ㄥ疄鐜帮細`app/utils/websocket.py` 涓?`WSClientManager.openws/openwsr`

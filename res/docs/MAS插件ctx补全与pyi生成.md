# MAS 閹绘帊娆?ctx 鐞涖儱鍙忔稉?pyi 閻㈢喐鍨氶幐鍥у础

> 閻楀牊婀伴敍姝?.0
> 閻㈢喐鏅ラ弮銉︽埂閿?026-03-27
> 闁倻鏁ら懠鍐ㄦ纯閿涙UTO-MAS 閹绘帊娆㈠鈧崣鎴︽▉濞堢绱欓崥搴ｎ伂 + VS Code/Pylance閿?

## 1. 閻╊喗鐖?

閺堫剚鏋冨锝囨暏娴滃氦顕╅弰搴窗

- 婵″倷缍嶉悽鐔稿灇閹绘帊娆㈠鈧崣鎴犳暏閻?`.pyi` 缁鐎烽幓鎰仛閺傚洣娆㈤敍?
- 娣囶喗鏁兼潏鎾冲毉閻╊喖缍嶉崥搴礉婵″倷缍嶉柌宥嗘煀閻㈢喐鍨氶敍?
- 閹绘帊娆㈡禒锝囩垳闁插苯顩ф担鏇熺垼濞?`ctx` 閹靛秷鍏橀懢宄扮繁鐞涖儱鍙忔稉搴ｎ劮閸氬秵褰佺粈鐚寸幢
- 鐢瓕顫嗛垾婊勭梾閺堝藟閸忋劉鈧繄娈戦幒鎺撶叀閺傜懓绱￠妴?

## 2. 瑜版挸澧犵€圭偟骞囧鍌濐潔

瑜版挸澧犻崥搴ｎ伂瀹告彃鍞寸純顔炬晸閹存劕娅掗敍?

- 娴狅絿鐖滄担宥囩枂閿涙瓪app/core/plugins/dev_stub_generator.py`
- 閻㈢喐鍨氶崙鑺ユ殶閿涙瓪generate_plugin_context_stubs()`
- 瀵偓閸欐垶膩瀵繐绱戦崗绛圭窗`AUTO_MAS_DEV`

瑜版挸澧犳妯款吇鏉堟挸鍤惄顔肩秿閿涘牆鍑＄拫鍐╂殻閿涘绱?

- `plugins/_generated/`

閻㈢喐鍨氶弬鍥︽閸栧懏瀚敍?

- `plugins/_generated/__init__.pyi`
- `plugins/_generated/context.pyi`
- `plugins/_generated/runtime_api.pyi`
- `plugins/_generated/cache_store.pyi`

## 3. 婵″倷缍嶉柌宥嗘煀閻㈢喐鍨?pyi

### 3.1 閸涙垝鎶ょ悰灞惧閸斻劎鏁撻幋鎰剁礄閹恒劏宕橀敍?

閸︺劑銆嶉惄顔界壌閻╊喖缍嶉幍褑顢戦敍?

```powershell
d:/Dev/AUTO-MAS/.venv/Scripts/python.exe -c "from app.core.plugins.dev_stub_generator import generate_plugin_context_stubs; print(generate_plugin_context_stubs())"
```

閹存劕濮涢崥搴濈窗鏉堟挸鍤敍?

- `output_dir`閿涙氨鏁撻幋鎰窗瑜?
- `changed_files`閿涙碍婀板▎鈩冩箒閸欐ɑ娲块惃鍕瀮娴?
- `unchanged_files`閿涙碍婀板▎鈩冩￥閸欐ɑ娲块惃鍕瀮娴?

### 3.2 閸氼垰濮╅崥搴ｎ伂閺冩儼鍤滈崝銊ф晸閹?

鐠佸墽鐤嗛悳顖氼暔閸欐﹢鍣洪崥搴℃儙閸斻劌鎮楃粩顖ょ窗

```powershell
$env:AUTO_MAS_DEV = "1"
d:/Dev/AUTO-MAS/.venv/Scripts/python.exe main.py
```

瑜?`AUTO_MAS_DEV` 娑?`1/true/yes/on`閿涘牅绗夐崠鍝勫瀻婢堆冪毈閸愭瑱绱氶弮璁圭礉閸氬海顏崥顖氬З濞翠胶鈻兼导姘冲殰閸斻劍澧界悰灞肩濞嗭紕鏁撻幋鎰┾偓?

### 3.3 娴ｈ法鏁ら崥搴ｎ伂閹恒儱褰涢幍瀣З闁插秴缂?

閹恒儱褰涢敍?

- `POST /api/plugins/dev/rebuild_ctx_stub`

鐠囧瓨妲戦敍?

- 瀵偓閸欐垶膩瀵繋绗呴崣顖滄纯閹恒儴鐨熼悽顭掔幢
- 闂堢偛绱戦崣鎴災佸蹇撳讲娴?`force=true` 瀵搫鍩楃憴锕€褰傞妴?

## 4. 閹绘帊娆㈡稉顓烆洤娴ｆ洘瀣侀崚鎷屗夐崗?

閹恒劏宕橀崷銊﹀絻娴犳湹鑵戞稉?`ctx` 閺勬儳绱￠弽鍥ㄦ暈缁鐎烽敍鍫濈磻閸欐垶婀＄猾璇茬€风€电厧鍙嗛敍澶涚窗

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.plugins.context import PluginContext


async def setup(ctx: "PluginContext") -> None:
    cache = ctx.cache.register(
        cache_name="test_cache",
        backend="json",
        limit=10,
        limit_mode="count",
    )
    cache.set("test_cache", {"1": "2"})
    ctx.logger.info(f"缂傛挸鐡ㄩ崘娆忓弳閹存劕濮? {cache.get('test_cache')}")
```

鏉╂瑦鐗遍崣顖欎簰閼惧嘲绶遍敍?

- `ctx.runtime` / `ctx.runtime_api` 閻ㄥ嫭鏌熷▔鏇狀劮閸氬秵褰佺粈鐚寸幢
- `ctx.cache.register(...)` 閸欏倹鏆熼幓鎰仛閿?
- 閻╃鍙ч弬瑙勭《 docstring 閹绘劗銇氶妴?

## 5. 鐢瓕顫嗛梻顕€顣介幒鎺撶叀

### 5.1 閹存垶鏁兼禍鍡楁倵缁旑垯鍞惍渚婄礉娴ｅ棙褰佺粈鐑樼梾閺囧瓨鏌?

閹稿銆庢惔蹇擃槱閻炲棴绱?

1. 闁插秵鏌婇幍褑顢戞稉鈧▎?`generate_plugin_context_stubs()`閿?
2. 绾喛顓?`plugins/_generated/*.pyi` 閻ㄥ嫪鎱ㄩ弨瑙勬闂傛潙鍑￠弴瀛樻煀閿?
3. 閸?VS Code 閹笛嗩攽 `Python: Restart Language Server`閵?

### 5.2 閺堝琚崹瀣垼濞夈劋绲炬潻妯绘Ц濞屄に夐崗?

濡偓閺屻儵銆嶉敍?

1. 閹绘帊娆㈤弬鍥︽閺勵垰鎯侀崘娆庣啊 `ctx: "PluginContext"`閿?
2. `TYPE_CHECKING` 娑撳顕遍崗銉ㄧ熅瀵板嫭妲搁崥锕€褰茬憴锝嗙€介敍?
3. 瑜版挸澧犲銉ょ稊閸栭缚袙闁插﹤娅掗弰顖氭儊閺勵垶銆嶉惄?`.venv`閿?
4. 閺勵垰鎯佺拠顖氭躬閸忔湹绮崥灞芥倳瀹搞儰缍旈崠鐑樺ⅵ瀵偓娴滃棙褰冩禒鑸垫瀮娴犺翰鈧?

### 5.3 閻㈢喐鍨氭径杈Е娴兼艾濂栭崫宥勫瘜濞翠胶鈻奸崥?

娑撳秳绱伴妴鍌氱秼閸撳秷顔曠拋鈩冩Ц閿?

- 閼奉亜濮╅悽鐔稿灇婢惰精瑙︽禒鍛邦唶瑜版洘妫╄箛?warning閿?
- 娑撳秹妯嗛弬顓炴倵缁旑垱婀囬崝鈥虫儙閸斻劋绗岄幓鎺嶆閸旂姾娴囬妴?

## 6. 缂佸瓨濮㈠楦款唴

- 娴犲懎婀鈧崣鎴犲箚婢у啫鎯庨悽銊ㄥ殰閸斻劎鏁撻幋鎰剁幢
- 閹恒儱褰涙笟褌绻氶悾娆愬閸斻劑鍣稿楦垮厴閸旀冻绱濇笟澶哥艾韫囶偊鈧喎鍩涢弬甯幢
- 瑜?`PluginContext/RuntimeAPI/Cache` 鐎电懓顦婚弬瑙勭《閸欐ɑ娲块崥搴礉閹笛嗩攽娑撯偓濞嗭繝鍣稿鍝勮嫙绾喛顓?IDE 閹绘劗銇氶弰顖氭儊閸氬本顒為妴?


婵″倹鐏夋担鐘虫Ц閹靛濮╅惄瀛樺复鐠?main.py閿涘牅绗夐弰顖滄暠 Electron 閹峰鎹ｉ敍澶涚礉闁絼绗夋导姘冲殰閸斻劍鏁為崗銉ュ綁闁插繈鈧倹顒濋弮鎯邦嚞閸忓牐顔曠純顔惧箚婢у啫褰夐柌蹇撳晙閸氼垰濮╅敍?
PowerShell: $env:AUTO_MAS_DEV="1" 閸氬骸鍟€鏉╂劘顢戦崥搴ｎ伂閵

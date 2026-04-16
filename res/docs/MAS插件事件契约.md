# MAS 閹绘帊娆㈡禍瀣╂婵傛垹瀹?

> 閻楀牊婀伴敍姝?.2
> 閻㈢喐鏅ラ弮銉︽埂閿?026-04-15
> 闁倻鏁ら懠鍐ㄦ纯閿涙UTO-MAS 閹绘帊娆㈡禍瀣╂閹崵鍤庨敍鍦梫entBus閿涘绗屾禒璇插缂傛牗甯撴禍瀣╂

## 1. 閻╊喗鐖ｆ稉搴″斧閸?

閺堫剙顨栫痪锔炬暏娴滃海绮烘稉鈧幓鎺嶆娴滃娆㈤惃鍕嚒閸氬秲鈧胶绮ㄩ弸鍕嫲鐟欙箑褰傜拠顓濈疅閿涘瞼鈥樻穱婵撶窗

- 閹绘帊娆㈤崣顖欎簰缁嬪啿鐣惧☉鍫ｅ瀭娴滃娆㈤敍灞肩瑝娓氭繆绂嗛崘鍛壋鐎圭偟骞囩紒鍡氬Ν閿?
- 娴犺濮熼悽鐔锋嚒閸涖劍婀￠敍鍧盿sk / script閿涘褰茬憴鍌涚ゴ閵嗕礁褰叉潻鍊熼嚋閿?
- 閺傛澘顤冪€涙顔岄弮鏈电箽閹镐礁鎮滈崥搴″悑鐎瑰箍鈧?

閺嶇绺鹃崢鐔峰灟閿?

- 鐎涙顔屾潻钘夊娴兼ê鍘涢敍灞肩瑝閸嬫氨鐗崸蹇撶础缁夊娅庨敍?
- 娴犺濮熺痪褌绨ㄦ禒鑸垫杹閸?`data` 娑擃叏绱濋懘姘拱缁狙傜皑娴犳湹绻氶幐浣瑰楠炲啿鍚嬬€圭櫢绱?
- 閹绘帊娆㈡径鍕倞韫囧懘銆忕€瑰綊鏁婇敍灞肩瑝閼宠棄娲滈幓鎺嶆瀵倸鐖堕梼璇差敚娑撶粯绁︾粙瀣ㄢ偓?

## 2. 闁氨鏁?Envelope

閹碘偓閺堝绨ㄦ禒璺烘綆閸栧懎鎯堟禒銉ょ瑓妞よ泛鐪扮€涙顔岄敍?

- `event: string`閿涙矮绨ㄦ禒璺烘倳閿?
- `event_version: string`閿涙艾顨栫痪锔惧閺堫剨绱濊ぐ鎾冲閸ュ搫鐣炬稉?`1`閿?
- `source: string`閿涙碍娼靛┃鎰侀崸妤嬬礄瀵ら缚顔呴敍姝歝ore.task_manager`閿涘绱?
- `timestamp: string`閿涙SO8601 閺冨爼妫跨€涙顑佹稉灞傗偓?

娴犺濮熺痪褌绨ㄦ禒璁圭礄`task.*`閿涘绗熼崝鈥崇摟濞堢數绮烘稉鈧弨鎯ф躬閿?

- `data: object`

閼存碍婀扮痪褌绨ㄦ禒璁圭礄`script.*`閿涘娣幐浣规＆閺堝鍚嬬€瑰湱绮ㄩ弸鍕剁礉鐎涙顔岄崣顖氭躬妞よ泛鐪伴惄瀛樺复鐠囪褰囬妴?

## 3. 閺嶅洤鍣禍瀣╂濞撳懎宕?

### 3.1 娴犺濮熼悽鐔锋嚒閸涖劍婀℃禍瀣╂

- `task.start`閿涙矮鎹㈤崝鈥冲灥婵瀵茬€瑰本鍨氶獮璺虹磻婵澧界悰灞炬鐟欙箑褰傞妴?
- `task.progress`閿涙矮鎹㈤崝鈥冲彠闁款喚濮搁幀浣稿絺閻㈢喎褰夐崠鏍ㄦ鐟欙箑褰傞敍鍫滅伐婵″倽鍓奸張顒傚Ц閹降鈧胶鍌ㄥ鏇樷偓浣哥暚閹存劖鏆熼崣妯哄閿涘鈧?
- `task.log`閿涙艾缍嬮崜宥堝壖閺堫剚妫╄箛妤€褰傞悽鐔告箒閺佸牆褰夐崠鏍ㄦ鐟欙箑褰傞妴?
- `task.exit`閿涙矮鎹㈤崝锟犫偓鈧崙铏圭埠娑撯偓閺€璺哄經娴滃娆㈤敍鍫熷灇閸?/ 婢惰精瑙?/ 閸欐牗绉烽敍澶堚偓?

### 3.2 閼存碍婀伴悽鐔锋嚒閸涖劍婀℃禍瀣╂

- `script.start`
- `script.success`
- `script.error`
- `script.cancelled`
- `script.exit`

鐠囧瓨妲戦敍姝歴cript.exit` 娑撶儤鏁归崣锝勭皑娴犺绱濆楦款唴閹绘帊娆㈡导妯哄帥閻╂垵鎯夌€瑰啫浠涚紒鐔剁婢跺嫮鎮婇妴?

## 4. 鐟欙箑褰傜拠顓濈疅閿涘牆鐤勯悳鏉款嚠姒绘劧绱?

### 4.1 `task.progress` 閸欘垵鍏樻径姘偧鐟欙箑褰?

`task.progress` 閺勵垪鈧粎濮搁幀浣告彥閻撗傜皑娴犲灈鈧繐绱濇稉宥嗘Ц閳ユ粈绔村▎鈩冣偓褌绨ㄦ禒鍨涒偓婵勨偓鍌欐崲閸斺剝澧界悰宀冪箖缁嬪鑵戝В蹇旑偧閻樿埖鈧礁褰夐崠鏍厴閸欘垵鍏樼憴锕€褰傞妴?

### 4.2 `task.log` 娑?`task.progress` 閻ㄥ嫭妫╄箛妤勭箖濠?

瑜版挸澧犵€圭偟骞囩€靛厜鈧粍妫ら幇蹇庣疅閺冦儱绻旈垾婵嗕粵鏉╁洦鎶ら敍姘秼瑜版挸澧犻弮銉ョ箶娑撹櫣鈹栭幋鏍︾矌缁岃櫣娅ч敍鍫濐洤閹广垼顢戦敍澶嬫閿涘奔绗夐崣鎴︹偓浣割嚠鎼存梹妫╄箛妤€褰夐崠鏍︾皑娴犺绱濋崙蹇撶毌閸ｎ亜锛愰妴?

### 4.3 `task.start` 閹垮秳缍旈崗銉ュ經

`task.start` 閸栧懎鎯堥崣顖涙惙娴ｆ粌鍙嗛崣锝忕礄婵″倸浠犲銏犵秼閸撳秳鎹㈤崝掳鈧礁浠犲銏犲弿闁劋鎹㈤崝鈽呯礆閿涘本褰冩禒璺哄讲閻╁瓨甯撮幑顔筋劃鐟欙箑褰?API 鐠嬪啰鏁ら妴?

### 4.4 闂冪喎鍨稉搴ゅ壖閺堫剝鐦戦崚顐㈢摟濞堥潧顤冨?

娑撶儤鏁幐浣瑰絻娴犺埖瀵滈崗铚傜秼閼存碍婀伴柊宥囩枂缁儳鍣潻鍥ㄦ姢閿涘牅绶ユ俊鍌椻偓婊€绮庤ぐ鎾崇┛闁?娑撳婀€娑撳啰绮ㄩ弶鐔告閹笛嗩攽閳ユ繐绱氶敍灞兼崲閸斺€茬瑢閼存碍婀版禍瀣╂閺傛澘顤冩禒銉ょ瑓閸忕厧顔愮€涙顔岄敍?

- `queue_name`閿涙岸妲﹂崚妤€鎮曠粔甯礄閸欘垯璐熺粚鐚寸礆閿?
- `task.exit.data.scripts`閿涙矮鎹㈤崝鈥冲敶閼存碍婀伴幗妯款洣閺佹壆绮嶉敍?
- `task.exit.data.final_script_*`閿涙矮鎹㈤崝鈩冩暪閸欙絾妞傞懘姘拱娑撳﹣绗呴弬鍥风幢
- `script.*.data.queue_id / queue_name`閿涙俺鍓奸張顑跨皑娴犳湹绗傞惃鍕Е閸掓ぞ绗傛稉瀣瀮閵?

## 5. Payload 缁€杞扮伐

### 5.1 task.start

```json
{
  "event": "task.start",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:45+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "queue_name": "濮ｅ繑妫╂潪顔款嚄",
    "script_total": 3,
    "scripts": [
      {
        "script_id": "script-001",
        "script_name": "閺冦儱鐖舵禒璇插",
        "status": "缁涘绶?
      }
    ],
    "primary_script_id": null,
    "primary_script_name": null,
    "actions": {
      "stop_task": {
        "api": "/api/dispatch/stop",
        "method": "POST",
        "body": {
          "taskId": "task-001"
        }
      },
      "stop_all_tasks": {
        "api": "/api/dispatch/stop",
        "method": "POST",
        "body": {
          "taskId": "ALL"
        }
      }
    }
  }
}
```

### 5.2 task.progress

```json
{
  "event": "task.progress",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:50+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "queue_name": "濮ｅ繑妫╂潪顔款嚄",
    "current_script_index": 0,
    "current_script_id": "script-001",
    "current_script_name": "閺冦儱鐖舵禒璇插",
    "script_total": 3,
    "script_completed": 1,
    "user_total": 12,
    "user_completed": 4,
    "current_script": {
      "script_id": "script-001",
      "script_name": "閺冦儱鐖舵禒璇插",
      "status": "鏉╂劘顢?,
      "current_user_index": 1,
      "user_count": 4
    }
  }
}
```

### 5.3 task.log

```json
{
  "event": "task.log",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:51+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "queue_name": "濮ｅ繑妫╂潪顔款嚄",
    "script_id": "script-001",
    "script_name": "閺冦儱鐖舵禒璇插",
    "script_status": "鏉╂劘顢?,
    "current_script_index": 0,
    "log": "...鐎瑰本鏆ｉ弮銉ョ箶...",
    "log_tail": "...閺堫偄鐔弮銉ョ箶...",
    "log_length": 12345,
    "truncated_for_tail": true
  }
}
```

### 5.4 task.exit

```json
{
  "event": "task.exit",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:24:20+08:00",
  "data": {
    "task_id": "task-001",
    "mode": "AutoProxy",
    "queue_id": "queue-001",
    "queue_name": "濮ｅ繑妫╂潪顔款嚄",
    "scripts": [
      {
        "script_id": "script-001",
        "script_name": "閺冦儱鐖舵禒璇插",
        "status": "鐎瑰本鍨?
      }
    ],
    "final_script_id": "script-001",
    "final_script_name": "閺冦儱鐖舵禒璇插",
    "final_script_status": "鐎瑰本鍨?,
    "result": "success",
    "error": null,
    "summary": "娴犺濮熼幗妯款洣..."
  }
}
```

### 5.5 script.exit

```json
{
  "event": "script.exit",
  "event_version": "1",
  "source": "core.task_manager",
  "timestamp": "2026-03-22T01:23:59+08:00",
  "task_id": "task-001",
  "script_id": "script-001",
  "script_name": "閺冦儱鐖舵禒璇插",
  "mode": "AutoProxy",
  "status": "鐎瑰本鍨?,
  "error": null,
  "result": "script.success",
  "data": {
    "queue_id": "queue-001",
    "queue_name": "濮ｅ繑妫╂潪顔款嚄"
  }
}
```

## 6. 閹绘帊娆㈡笟褍鐤勭捄闈涚紦鐠?

- 娴犺濮熺紒鏉戝鏉╁€熼嚋閿涙氨鏁?`task_id` 娴ｆ粈璐熸稉濠氭暛閿涘瞼娲冮崥?`task.start` / `task.progress` / `task.log` / `task.exit`閵?
- 閼存碍婀扮紒鏉戝閺€璺哄經閿涙矮绱崗鍫㈡磧閸?`script.exit`閿涘本瀵?`result` 閸嬫艾鍨庨弨顖氼槱閻炲棎鈧?
- 缁儳鍣懘姘拱鐟欙箑褰傞敍姘喘閸忓牅浜?`script.exit` + `script_name/script_id` 鏉╁洦鎶ら敍娌梩ask.exit` 閸欘垳绮ㄩ崥?`scripts` 娑?`final_script_name` 閸嬫矮鎹㈤崝鈩冩暪閸欙絽鍨介弬顓溾偓?
- 娴滃娆㈡径鍕倞鐎瑰綊鏁婇敍姘槱閻炲棗鍤遍弫鏉垮敶闁劌绨查幑鏇″箯瀵倸鐖堕敍宀勪缉閸忓秳绱堕幘顓炲煂閹崵鍤庨妴?
- 缂傛挸鐡ㄩ柊宥呮値娴滃娆㈤敍姘紦鐠侇喕濞囬悽?`ctx.cache` 鐎甸€涚皑娴犳儼顓搁弫鑸偓浣稿箵闁插秶顒烽崥宥冣偓浣虹叚閺堢喓濮搁幀浣镐粵閺堫剙婀撮幐浣风畽閸栨牓鈧?

缁€杞扮伐閿涘牊甯归懡鎰剁礆閿?

- `counter:task.progress`閿涙俺顔囪ぐ鏇⌒曢崣鎴烆偧閺佸府绱?
- `last:task.progress`閿涙矮绻氱€涙ɑ娓堕崥搴濈閺夆€虫彥閻撗嶇幢
- `task:<task_id>:summary`閿涙艾婀?`task.exit` 閺€璺哄經閸愭瑥鍙嗛幗妯款洣閵?

## 7. 閸忕厧顔愰幀褌绗岄崡鍥╅獓缁涙牜鏆?

- 閺傛澘顤冪€涙顔岄崣顏囨嫹閸旂媴绱濇稉宥呭灩闂勩倖妫﹂張澶婄摟濞堢绱?
- 閺冦垺婀佹禍瀣╂鐠囶厺绠熸穱婵囧瘮娑撳秴褰夐敍?
- 閹绘帊娆㈡惔鏂款嚠閺堫亞鐓＄€涙顔岀€圭懓绻婇敍鍫濇嫹閻ｃ儱宓嗛崣顖ょ礆閿涘矂浼╅崗宥団€栫紓鏍垳娑撱儲鐗哥€涙顔岄崗銊╂肠閵?

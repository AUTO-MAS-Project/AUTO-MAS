# Banner Watch source evidence

Live checks were run on 2026-11-20. Both sweeps completed all eight sources
without an exception:

| Sweep | First verified_at | Last verified_at | Counts |
| --- | --- | --- | --- |
| 1 | `2026-11-20T03:59:36Z` | `2026-11-20T03:59:54Z` | Endfield 8, Wuthering Waves 12, Arknights 2, Blue Archive 16, Princess Connect 7, Azur Lane 8, Girls' Frontline 2 12, Resonance 14 |
| 2 | `2026-11-20T04:00:09Z` | `2026-11-20T04:00:26Z` | Endfield 8, Wuthering Waves 12, Arknights 2, Blue Archive 16, Princess Connect 7, Azur Lane 8, Girls' Frontline 2 12, Resonance 14 |

## Observation shape

Every adapter returns a list of JSON-friendly observations with these keys:

```text
game, server, title, kind, start_mode, starts_at, ends_at, end_kind,
confirmed_open_at, official_url, verified_at, published_at, official_id,
article_id, source_anchor, revision, cancelled, replaces, related,
publication_order
```

`official_id` is populated only where the source itself supplies a pool ID.
`article_id` is the news, moment, opus, or post ID. `published_at` and
`publication_order` come from the authoritative absolute source timestamp,
never list position. `revision` is a digest of article/pool content and source
timestamps, so reaction and view counters do not create false corrections.

## Routes and exact live samples

| Game | Discovery and verification route | Exact sample |
| --- | --- | --- |
| Endfield | [bulletin API](https://web-news.hypergryph.com/api/bulletin?lang=zh-cn&code=endfield_web&page=1&pageSize=30&tabs%5B%5D=notices) and per-CID detail API | [7204](https://endfield.hypergryph.com/news/7204): `「烟火邀星河」特许寻访说明`, published `2026-11-04T10:00:00Z`, starts `2026-11-05T04:00:00Z`, end unknown. |
| Endfield version evidence | [6094](https://endfield.hypergryph.com/news/6094) version text | `「月映申领」开放`, article ID `6094`, kind `weapon`, starts `2026-11-05T04:00:00Z`, end unknown because it closes after three `特许寻访`. The same-named `「月映申领」限时特卖说明` post, CID `5971`, is excluded as pool evidence. |
| Wuthering Waves | [article menu](https://media-cdn-mingchao.kurogame.com/akiwebsite/website2.0/json/G152/zh/ArticleMenu.json) and JSON article detail | [4609](https://mc.kurogames.com/main/news/detail/4609): `灼霜｜武器活动唤取`, `赝作的矮星｜武器活动唤取`, `雪色所映千般未来｜角色活动唤取`, and `予明日以谎言｜角色活动唤取`, all `after_maintenance`, published `2026-04-30T02:00:00Z`, end unknown. Prose saying an item can be obtained from a convene is not emitted as another pool. |
| Arknights | [news list](https://ak.hypergryph.com/news) and Next.js detail data | [1457](https://ak.hypergryph.com/news/1457): published `2026-08-29T03:00:00Z`, starts `2026-09-04T04:00:00Z`, ends `2026-09-17T19:59:00Z`. Live newest pool: `[限定寻访·庆典]【将雪投火】限时寻访即将开启`, starts `2026-11-01T04:00:00Z`, ends `2026-11-14T19:59:00Z`. |
| Blue Archive | [official TapTap topic](https://www.taptap.cn/app/316964/topic?type=official), official Bilibili UID `3493265644980448`, and [supplied opus](https://www.bilibili.com/opus/1168392597461270533) | TapTap live update: four 11/12 reruns end `2026-11-26T05:59:00Z`; the separate `老师，维护更新已结束` post at `2026-11-12T08:45:00Z` is attached through `confirmed_open_at` and `related`. The [11/19 preview](https://www.taptap.cn/moment/871772133179523691) yields four 11/26 pool names as `tbd`, with no invented time. |
| Blue Archive replay | Reduced genuine Bilibili opus fixture | Published `2026-02-12T06:00:00Z`; exactly three independently anchored pools start `2026-02-14T06:00:00Z` and end `2026-02-28T05:59:00Z`. |
| Princess Connect | Verified [Sina official profile](https://www.sina.cn/media/6603867494), with official Bilibili UID `353840826` and opus `1259278024604385281` recorded as the alternate identity | `精选扭蛋｜纳娜` is confirmed by the 11/13 post at `2026-11-13T06:05:00Z`; `自选复刻附奖扭蛋｜限定角色` and `白金扭蛋｜★3必得` are retained. The 11/19 `21:30~待定` maintenance post is not emitted as a pool. TapTap `768909398603991311` remains a replay fixture but is not live discovery. |
| Azur Lane | [official TapTap topic](https://www.taptap.cn/app/31597/topic?type=official) and moment detail | [871814659823372045](https://www.taptap.cn/moment/871814659823372045): three permanent build additions, all `after_maintenance`, `starts_at=null`, `ends_at=null`, `end_kind=permanent`. The 10/22 limited-build sample is also `after_maintenance`; its `10:00~16:00` maintenance window is not used as the pool start. |
| Girls' Frontline 2 | [news list API](https://gf2-web-preregister-api.sunborngame.com/website/news_list/4?page=1&limit=50) and [article detail API](https://gf2-web-preregister-api.sunborngame.com/website/news/2225) | Articles 2225-2228 produce eight named current pools: four `定向采购` and four `军备提升`. They are confirmed at `2026-11-03T03:00:00Z` and end `2026-11-24T00:59:00Z`. |
| Resonance | [official TapTap topic](https://www.taptap.cn/app/226568/topic?type=official) and [update post](https://www.taptap.cn/moment/872109359222491961) | Three independent sections: `特设招募｜天鳞至理` ends `2026-12-16T04:00:00Z`; `专列招募｜原罪抱拥` and `常驻招募｜那由他` end `2026-12-02T04:00:00Z`. `常驻` is `standard`; `关注我们` and the gift section are excluded. |

## Boundaries and known limitations

- TapTap collection inspects at most four official-topic pages and at most 24
  candidate detail posts per adapter. This is recurring discovery, not a claim
  that a static page is exhaustive.
- The Sina profile currently exposes a static latest-100 post page. Older posts
  require a future historical route; the adapter applies the normal 270-day
  sweep cutoff after reading that page.
- Blue Archive's Bilibili feed is optional because it can return an empty or
  challenge response. TapTap is the required recurring route. If the required
  TapTap route or a required detail fails, the adapter raises rather than
  returning the Bilibili subset.
- Blue Archive correction aliases `片雨让白昼` and `春阴映白浪` map to the later
  pool names `骤雨让白昼` and `花阴映白浪`, preserving one anchor per actual
  pool. Both source moment IDs remain in `related`.
- A pool with no absolute end is `end_kind=unknown`. Permanent/maintenance
  additions are `end_kind=permanent`. No adapter infers cancellation from
  absence, and no adapter treats a maintenance start as a pool start.
- A required list/detail failure raises `BannerSourceError`; partial records are
  not published as a successful sweep. This lets the caller retain failure
  state instead of clearing an outage.
- HTTP/TLS verification is never disabled. No alternate route changes TLS
  policy.


## Integration and telemetry

Source adapters depend on public HTTP and return normalized observations. Calendar
subscriptions, versioned claims and delivery remain in the host calendar
component and use the existing notification dispatcher. Codex handoff requires
explicit confirmation in the desktop renderer.

There are no new analytics events. The recurring fetch and outbox attempts are
internal reliability activity with local diagnostics. Subscription choices and
reviewed analysis requests describe personal preferences and may include user
inventory or team information. The feature has no separate analytics use case,
and its acceptance relies on observed delivery and local replay receipts.

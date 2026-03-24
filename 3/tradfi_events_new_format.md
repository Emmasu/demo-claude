# TradFi Combo Event Tracking — New Format

---

## Event: pageview

### `page_name = TradingbotCreateTradfiComboPageView`

| Attribute | Type | 属性值示例 | 应埋点平台 | 事件截图 | Link | Tag标签 | 备注 |
|---|---|---|---|---|---|---|---|
| type | STRING | manual | WEB, IOS, ANDROID | | | Trading Bot | |

> **⚠️ Issue:** The second sub-row "来到TradfiCombo Details页面" is listed under the same event name but represents a different page. It is missing both an event name and an attribute variable name. Suggested new event: `TradingbotTradFiComboDetailsPageView`. Attribute name and values (`my bot`, `asset`) need to be confirmed.

---

## Event: click

### `page_name = TradingbotTradFiClick`

| Attribute | Type | 属性值示例 | 应埋点平台 | 事件截图 | Link | Tag标签 | 备注 |
|---|---|---|---|---|---|---|---|
| button_name | STRING | createGrid, createManually, createAuto, confirmCreateGrid, confirmCreateManually, confirmCreateAuto, clickGuide, closeCombo, helpGuide | WEB, IOS, ANDROID | | | Trading Bot | 点击TradfiCombo修改弹窗确认按钮对应的 button_name 值缺失，需补充 |
| create_type | STRING | 创建类型 | WEB, IOS, ANDROID | | | Trading Bot | 仅在 confirmCreate 系列按钮触发时携带 |

> **⚠️ Issues:**
> - "进入Tutorial" has two states: `曝光show` and `点击click` — consider splitting into a separate **expose** event and keeping only `clickGuide` here.
> - "点击TradfiCombo修改弹窗确认按钮" has no `button_name` value defined — needs to be filled in.

---

## Event: server

### `page_name = TradingBotComboCreateResult`

| Attribute | Type | 属性值示例 | 应埋点平台 | 事件截图 | Link | Tag标签 | 备注 |
|---|---|---|---|---|---|---|---|
| bot_id | STRING | | SERVER | | | Trading Bot | 匹配业务数据 |
| leverage | NUMBER | | SERVER | | | Trading Bot | 杠杆倍数 |
| create_type | STRING | auto, manual, grid, copy | SERVER | | | Trading Bot | 需区分 dailypick 传的 copy / auto / manual |
| block_source | STRING | create_entry | SERVER | | | Trading Bot | 交易站模块资源位，主入口 |
| is_success | INT | 1 | SERVER | | | Trading Bot | 创建成功为 1 |

---

## Summary of Issues to Resolve

| # | Event | Issue |
|---|---|---|
| 1 | TradingbotCreateTradfiComboPageView | "来到TradfiCombo Details页面" missing event name — suggest `TradingbotTradFiComboDetailsPageView` |
| 2 | TradingbotCreateTradfiComboPageView | Details 页面 attribute variable name is blank — needs to be defined |
| 3 | TradingbotTradFiClick | "点击TradfiCombo修改弹窗确认按钮" missing `button_name` value |
| 4 | TradingbotTradFiClick | "进入Tutorial" has both expose and click states — consider splitting into two events |
| 5 | All events | Screenshot and Link columns are empty — need to be filled in |

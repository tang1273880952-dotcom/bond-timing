# 股债估值仪表盘

本仓库通过 GitHub Actions 获取市场估值数据，使用 GitHub Pages 发布单一的股债估值仪表盘。

网页地址：https://tang1273880952-dotcom.github.io/bond-timing/

## 页面内容

- 新增资金观察方向：中证500、10年国债ETF、30年国债ETF、标普500。
- 历史估值走势：中证500、科创100、北证50。
- 用不同颜色区分相对低估、中性和相对高估；最新行情日期以各卡片显示为准。

## 更新与发布

- `.github/workflows/deploy.yml`：更新中国股债估值数据和发布仪表盘。
- `.github/workflows/update-us.yml`：独立更新标普500相关数据和重新发布。
- `scripts/build_pages.py`：构建只含仪表盘的最小 GitHub Pages 发布目录，不发布测试、脚本或原始行情缓存。

首页“刷新数据”会重新读取已发布的最新快照，不会直接启动 GitHub Actions，也不保证行情源当天已有新数据。

## 不要删除的行情缓存

- `data/csi500_erp_daily.csv`：中证500真实日度 ERP 历史缓存。
- `data/csi500_erp_monthly.csv`：中证500月度历史分位样本。
- `data/csi500_index_close_daily.csv`：中证500实际收盘点位。
- `data/bse50_daily.csv`、`data/star100_daily.csv`：北证50及科创100历史估值。
- `data/china_yields_daily.csv`：国债收益率历史缓存。

这些缓存用于增量更新，不直接包含在 Pages 发布包中。网页读取 `data/latest.json`、`data/us_latest.json`，更新状态在对应 `status.json` 文件中。

## 计算口径

ERP = 100 / 指数滚动市盈率 TTM − 国债10年期收益率（标普500使用美国10年期国债收益率）。
参考分位由各自真实历史样本计算，每月使用上一个完整月份的行情修正。
10年、30年国债ETF为收益率代理判断，不等于ETF实时价格或未来回报。
绿色代表相对较便宜，不代表确定的交易信号。

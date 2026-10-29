# 股债估值与A股筛选

本仓库由 GitHub Actions 更新市场数据，并通过 GitHub Pages 发布两个静态网页：

- 首页：中证500、中国10年/30年国债收益率代理、北证50、科创100、标普500估值观察。
- `/a-share/`：A股估值初筛、财务验证、PB历史走势与云端观察池。

## 更新与发布

- `.github/workflows/deploy.yml`：中国股债估值数据更新和首页发布；行情计算与单纯网页发布分离。
- `.github/workflows/update-us.yml`：美股数据单独更新，并发布最新静态网页。
- `.github/workflows/ashare-fast.yml`：A股大范围PE/PB轻量初筛。
- `.github/workflows/ashare.yml`：对候选股票进行财报和历史PB深度验证。
- `.github/workflows/portfolio.yml`：仓库所有者通过GitHub Issue更新云端持仓。

所有 Pages 发布都调用 `python scripts/build_pages.py "$RUNNER_TEMP/pages-site"`。
仅上传网页所需的18个资源和 `.nojekyll`，不上传脚本、测试、仓库历史和历史行情缓存。

## 数据文件不能随意删除

- `data/csi500_erp_daily.csv`：中证500真实日度ERP历史缓存。
- `data/csi500_erp_monthly.csv`：供10年水平分位参考使用的真实月度样本。
- `data/csi500_index_close_daily.csv`：中证500指数实际收盘点位。
- `data/bse50_daily.csv`、`data/star100_daily.csv`：北证50、科创100真实指数估值历史。
- `data/china_yields_daily.csv`：首次完整下载后增量刷新的国债收益率缓存。

以上缓存是加速日后更新的必要文件，不会进入公开的Pages发布包。
`data/latest.json`、`data/us_latest.json` 为已核验页面快照；`status.json` 记录同步状态。

## 准确性原则

ERP = 100 / 指数滚动市盈率TTM − 中国10年国债收益率（标普500使用美国10年国债收益率）。
估值参考分位采用对应历史样本；水平线在每个新的自然月根据上个完成月份修正。
不同资产的评分公式不同，不能简单地把最高分视为最优资产。债券ETF模块仍是债券收益率代理，
不是ETF实际复权价格或实际未来回报。

**注意隐私**：GitHub Pages是公开网页。网站发布的 `a-share/data/holdings.json`
也可以被任何知道网址的人读取；不要在公开持仓文件中加入账户、姓名、资金账号等敏感信息。

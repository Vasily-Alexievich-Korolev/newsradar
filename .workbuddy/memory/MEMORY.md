# NewsRadar 项目记忆

## 用户偏好
- eco_data 宏观经济数据更新后，需 git commit + push 到远程仓库 (newsradar/main)
- 远程地址：git@github.com:Vasily-Alexievich-Korolev/newsradar.git

## 技术约定
- Git remote 名为 `newsradar`，非 `origin`
- CSV 文件使用 UTF-8 BOM 编码 (utf-8-sig)
- 月度数据格式：时间列为 YYYYMM 或 YYYY-MM

## 数据源
- 宏观经济月度指标通过 akshare 抓取（CPI/PPI/PMI/M1/M2/工业增加值/社融）
- 每日指标（北向资金/融资融券/国债收益率等）各自独立 fetcher

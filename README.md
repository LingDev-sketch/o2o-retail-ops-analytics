# O2O即时零售运营数据质量监控与自动化分析平台

这是一个面向 **即时零售 / O2O运营 / 业务数据分析** 岗位的项目作品。项目模拟把运营同学原本依赖 Excel、Power Query、手工筛选和日报透视的流程，迁移为一个轻量级 Python + Streamlit 分析工具。

## 项目亮点

- 使用 Python Pandas 清洗并关联订单、门店、商品、库存、促销等多张业务表。
- 使用 Streamlit 搭建运营分析页面，支持日期、城市、品类筛选。
- 使用 Plotly 展示 GMV、订单量、门店排名、商品排名、促销 uplift 等图表。
- 使用 YAML 配置异常规则，模拟客户定制化指标和异常监控逻辑。
- 输出异常门店清单，支持 GMV 下滑、订单下滑、缺货率过高、退款率异常等问题定位。
- 提供 SQL 示例，覆盖多表关联、窗口函数、CTE、促销效果分析和异常门店识别。

## 业务场景

即时零售运营团队通常需要持续关注：

- GMV、订单量、客单价、退款率、缺货率
- 门店销售排名、区域表现、异常门店
- 高销量低库存商品、滞销商品、库存风险
- 促销活动前后 GMV 变化和商品 uplift

本项目将这些分析流程整合到一个可交互页面中，减少重复手工处理，提高异常排查效率。

## 项目结构

```text
o2o_retail_ops_analytics/
  app.py
  generate_data.py
  requirements.txt
  config/
    rules.yaml
  data/
    orders.csv
    stores.csv
    products.csv
    inventory.csv
    promotions.csv
  sql/
    o2o_analysis_examples.sql
```

## 运行方式

```powershell
python -m pip install -r requirements.txt
python generate_data.py
python -m streamlit run app.py
```

## 数据表说明

- `orders.csv`：订单明细，包含订单日期、门店、商品、GMV、订单状态、是否促销、退款标记。
- `stores.csv`：门店维表，包含城市、区域、门店类型、开店日期。
- `products.csv`：商品维表，包含品牌、品类、成本价、销售价。
- `inventory.csv`：库存明细，包含门店、商品、库存数量、安全库存。
- `promotions.csv`：促销配置，包含促销商品、活动日期和折扣力度。

## 可写入简历的项目描述

**O2O即时零售运营分析工具｜Python + Streamlit + SQL**

基于即时零售业务场景，围绕订单、库存、促销、门店等数据，搭建轻量级运营分析工具，用于替代传统 Excel 手工统计流程，支持运营人员进行指标监控、异常排查和促销复盘。

- 使用 Python Pandas 对订单、库存、商品、门店、促销等多表数据进行清洗、关联与指标计算。
- 使用 SQL 完成 GMV、订单量、客单价、缺货率、退款率、促销订单占比等核心指标统计，并通过窗口函数识别连续下滑门店。
- 使用 Streamlit 搭建运营分析页面，支持按日期、城市、门店、品类等维度筛选查看经营表现。
- 设计 YAML 异常规则配置，实现 GMV 下滑、缺货率过高、退款率异常、库存不足等问题的自动识别。
- 输出异常门店及异常商品清单，辅助运营人员定位销售波动、库存不足和促销效果不佳等问题。
- 使用 Plotly 展示销售趋势、品类贡献、门店排名、促销前后对比等图表，提高分析结果可读性。

## 面试讲法

这个项目不是单纯做一个 BI 看板，而是模拟把运营同学原本依赖 Excel / Power Query 的分析流程迁移到 Python + Streamlit 工具里。项目把异常判断规则放在 YAML 配置文件中，后续如果客户新增指标或调整阈值，可以优先修改配置，减少重复改代码。

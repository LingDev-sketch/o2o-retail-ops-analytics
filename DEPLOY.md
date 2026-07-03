# 部署成公开 URL

## 推荐方式：Streamlit Community Cloud

1. 注册或登录 Streamlit Community Cloud。
2. 把本项目上传到一个 GitHub 仓库。
3. 在 Streamlit Cloud 新建应用，选择该仓库。
4. Main file path 填写：

```text
app.py
```

5. 部署完成后会得到一个公开访问 URL，可放在 BOSS 直聘项目链接里。

## 需要上传的文件

```text
app.py
generate_data.py
requirements.txt
README.md
resume_project.md
config/rules.yaml
data/orders.csv
data/stores.csv
data/products.csv
data/inventory.csv
data/promotions.csv
sql/o2o_analysis_examples.sql
.streamlit/config.toml
```

## 如果部署后没有数据

在 Streamlit Cloud 的应用后台打开终端，运行：

```bash
python generate_data.py
```

本项目已经包含生成后的 `data/*.csv`，正常情况下不需要重新生成。

## BOSS 项目链接说明

项目名称建议写：

```text
O2O即时零售运营分析工具
```

项目描述建议写：

```text
基于订单、门店、商品、库存、促销等模拟业务数据，使用 Python + Pandas + Streamlit 搭建即时零售运营分析工具，支持 GMV、订单量、客单价、退款率、缺货率等核心指标监控，并通过 YAML 配置异常规则，自动识别 GMV 下滑、缺货率过高、退款率异常等门店问题。
```

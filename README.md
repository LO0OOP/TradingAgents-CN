# TradingAgents-CN

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/Version-v1.1.0-green.svg)](./VERSION)
[![Upstream](https://img.shields.io/badge/上游-hsliuping%2FTradingAgents--CN-orange.svg)](https://github.com/hsliuping/TradingAgents-CN)

---

## 📖 项目简介

**TradingAgents-CN** 是一个多智能体股票分析平台，上游项目为 [hsliuping/TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN)。本项目在其基础上持续维护增强，支持 **A股 / 港股 / 美股** 的投资分析与学习研究。

**核心能力**：多智能体股票分析（市场 / 基本面 / 新闻 / 社媒分析师 → 多空辩论 → 交易决策 → 风险管理）、自选股管理、智能股票筛选、模拟交易、批量分析、多 LLM 提供商、多数据源（Tushare / AKShare / BaoStock / 腾讯）、报告导出（Markdown / Word / PDF）。

**技术栈**：FastAPI + Vue 3 + Element Plus + MongoDB + Redis + Docker。

---

## 🎯 版本说明

### v1.1.0（当前版本）

- 修复批量任务重复执行：禁用前端自动重试、延长请求超时、新增失败任务手动重试
- 分析报告页 / 报告列表优化：展示批量任务名、分析深度、分析模型，以及买入 / 卖出 / 持有决策标签
- 修复按股票名称搜索报告漏报的问题
- 分析模型展示去除类名前缀，仅显示模型名
- 其他 Bug 修复与稳定性优化

### v1.0.1

第一个稳定版。

### v0.1.0

初始版本。

---

## 🚀 快速开始

### Docker 部署

```bash
docker compose up -d --build
```

- 前端页面：http://localhost:3000
- 后端 API 文档：http://localhost:8000/docs

### 本地开发

```bash
.\start_dev.ps1 backend     # 启动后端（端口 8000）
.\start_dev.ps1 frontend    # 启动前端（端口 3000）
```

---

## ⚠️ 免责声明

本工具仅用于数据分析与学习研究，不构成任何投资建议。分析结果由 AI 生成，仅供参考；投资有风险，决策需谨慎。

## 🙏 致谢

感谢上游项目 [hsliuping/TradingAgents-CN](https://github.com/hsliuping/TradingAgents-CN) 及其源项目 [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) 提供的基础框架。

## 📄 许可证

本项目采用混合许可证，详见 [LICENSE](./LICENSE) 与 [COPYRIGHT](./COPYRIGHT.md)。

---

<div align="center">

**🌟 如果这个项目对你有帮助，请给我们一个 Star！**

</div>
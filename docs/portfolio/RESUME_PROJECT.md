# Resume Project Description

## 中文简历版

**Tomato Agent｜基于 DeepSeek 的证据驱动 Tool Calling Agent**

- 设计并实现 9 个 Pydantic Typed Tools 与 Registry-driven Function Calling，覆盖结构化数据查询、7 天株高预测、View-level RGB 分析、知识 RAG、历史案例检索和规则化可靠性评估。
- 构建 Evidence-driven Workflow：RequestContract、Evidence Planner/Store、冲突分析、FULL/PARTIAL/ABSTAIN、Claim Provenance、调用预算、参数修复与重复调用处理。
- 建立 12,168 条 Plant Case 与 1,001 条 View Case 的历史记忆，加入混合检索、跨实体过滤、Temporal Leakage Guard 与 OOD 检测。
- 完成真实 `deepseek-flash` Known-10 开发集评测：Tool Selection F1 96.67%、Argument Accuracy 100%、Evidence Grounding/Provenance 100%、人工 PASS 8/10；同时保留严格自动 PASS 5/10 与 Bad Case 修复边界。

## English resume version

**Tomato Agent — Evidence-driven Tool-calling Agent with RAG & Historical Memory**

- Built a registry-driven function-calling layer with 9 Pydantic-typed tools for structured data, t+7 growth prediction, View-level CV, knowledge RAG, historical retrieval, and rule-based reliability.
- Implemented controlled evidence workflows with RequestContract, planning/store, conflict analysis, FULL/PARTIAL/ABSTAIN resolution, claim provenance, call budgets, argument repair, and duplicate-call handling.
- Built historical memory over 12,168 Plant and 1,001 View cases with hybrid similarity, cross-entity filters, temporal-leakage guards, and OOD diagnostics.
- Evaluated real `deepseek-flash` behavior on a 10-case known development set: 96.67% tool-selection F1, 100% argument accuracy, 100% evidence grounding/provenance, and 8/10 human PASS; documented the stricter 5/10 automatic score and unresolved holdout boundary.

## 100 字介绍

Tomato Agent 是一个证据驱动的大模型 Agent 原型。系统通过 9 个 Typed Tools 调度番茄数据、机器学习预测、View-level RGB、知识 RAG 与历史案例记忆，并使用结构化工作流完成证据聚合、可靠性、冲突、拒答和 Claim Provenance。项目包含真实 DeepSeek Function Calling 评测、Trace、Bad Case 与离线回放 Demo。

## 200 字介绍

面向番茄水肥与生长分析场景，构建了一个不依赖 LLM 直接“猜数值”的证据驱动 Agent：结构化数据、株高预测、View-level RGB、知识检索和历史案例分别由专业工具完成，LLM 负责意图理解与多工具调度。系统包含 9 个 Pydantic Typed Tools、4 条受控工作流、RequestContract、Evidence Store、模型—案例冲突分析、FULL/PARTIAL/ABSTAIN、Scope Safety 与 Claim Provenance；历史记忆覆盖 12,168 个 Plant Cases 和 1,001 个 View Cases，并加入时间泄漏保护与 OOD 检测。真实 `deepseek-flash` Known-10 开发评测获得 96.67% Tool Selection F1、100% Argument Accuracy 和 8/10 人工 PASS，同时保留 5/10 严格自动 PASS 与 48-case Holdout 未运行的限制。

## 面试表述边界

不要宣称生产级水肥控制、100% 决策准确率、Plant-level RGB、跨季泛化已解决、因果推理或 Holdout 已通过。应说明使用 AI 编程工具协作完成工程，并能独立解释、运行、测试和修改 Registry、Workflow、Evidence 与 Evaluation 的核心路径。

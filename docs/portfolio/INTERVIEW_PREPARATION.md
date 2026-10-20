# Interview Preparation

## 一分钟项目介绍

我做了一个番茄领域的证据驱动 Agent，但重点不是农业聊天，而是 Agent 工程。LLM 不直接预测株高或生成灌溉量，而是通过 9 个 Pydantic Typed Tools 调用结构化数据、机器学习、View-level RGB、知识 RAG 和历史案例记忆。系统使用 4 条受控工作流，把 ToolResult 统一成 Evidence，再完成冲突分析、可靠性、FULL/PARTIAL/ABSTAIN 和 Claim Provenance。真实 `deepseek-flash` 在 10 条已知开发案例上达到 96.67% Tool Selection F1、100% 参数准确率和 8/10 人工 PASS；严格自动 PASS 只有 5/10，这暴露了 required-tool 和状态契约问题，我又通过 RequestContract 做了离线修复。项目现在提供零联网 Replay Demo、真实 Trace、测试与 Bad Case 文档。

## 三分钟项目介绍

项目源于番茄水肥研究，但我把它重构成了一个可评测的 Agent Foundation。数据侧已有 canonical plant/sensor tables、锁定的 t+7 株高模型、Frozen ResNet18 View-level 表示、知识 RAG，以及 12,168 条 Plant/1,001 条 View 历史案例。

Agent 接收到问题后，Structured Router 决定 intent 和 workflow，RequestContract 只记录用户真实请求，Evidence Planner 明确必需/可选证据。模型只能从 Tool Registry 暴露的 9 个 schema 中选择工具；Pydantic 校验参数，Executor 限制工具预算、修复次数并识别重复调用。ToolResult 进入 EvidenceNormalizer/Store，随后检查 RAG relevance、evidence completeness、ML–case conflict 和 scope。最后 Claim 必须绑定 Evidence ID，并构建 Claim→Evidence→Tool→Source 的 provenance graph；状态由 deterministic resolver 输出 FULL、PARTIAL 或 ABSTAIN。

我没有只用 Mock 自测。V1.4.4 在用户授权下用 `deepseek-flash` 跑了 10 条已知开发案例，41 次 API 调用，Tool Selection F1 96.67%、参数准确率 100%、grounding/provenance 100%，人工 PASS 8/10。但严格自动 PASS 只有 5/10：一类问题是 required reliability 未调用，另一类是模型主动添加未请求限制导致 false PARTIAL。V1.4.5 增加 RequestContract 和独立 required-tool evaluator 后，Known-10 离线回归 10/10；我没有把它冒充新的在线结果，48 条独立 Holdout 也保持 NOT_RUN。这个项目最能体现的是：工具合同、证据工程、Agent 状态和真实 LLM 评测，而不是“做了一个会聊天的页面”。

## 深度技术问答

### 1. Function Calling 的核心是什么？

模型生成的是结构化调用意图，不是直接执行代码。工程层用 Registry 将合法名称映射到 callable，用 Pydantic 验证参数，再把结构化 ToolResult 返回给模型继续推理。安全边界在应用侧，而不是模型“承诺正确”。

### 2. 多轮 Responses 风格调用如何管理上下文？

Provider 传输层保持无状态；Orchestrator 显式携带前序响应项、function call 与 function output。应用状态保存预算、Trace、已执行指纹和 Evidence，避免依赖服务端隐式会话。

### 3. Structured Output 和 Tool Schema 有什么区别？

Tool Schema 约束调用名称和参数；Structured Output 约束 Router、Evidence Plan 或 Final Answer 的结果形状。两者都要验证，但失败恢复不同：工具参数可局部修复，最终答案还需 Evidence/Scope 二次检查。

### 4. 为什么用 Pydantic？

它同时提供运行时校验、JSON Schema 和一致的错误信息。`schemas/tools.py` 的同一个模型服务 CLI、Provider schema 与执行器，减少三套合同漂移。

### 5. Router 如何避免随意路由？

Router 输出受枚举和 schema 限制，后续 RequestContract 与 Workflow Registry 再校验。即使 Router 选择不完美，未知 workflow/tool 也不会被执行。

### 6. Argument Repair 如何工作？

首次校验失败后，只把 canonical schema、原始参数和 validation error 交给 repair prompt；修复次数有上限并写入 Trace。超过预算返回结构化错误，不无限重试。

### 7. 未知 Tool Name 为什么危险，如何修复？

名字错误会导致任务表面规划成功但无法执行。早期 Bad Case 来自 Prompt 中工具合同与 Registry 漂移；修复后 Provider schema 由 Registry 导出，执行器再次做精确查找，并允许一次有边界的 plan repair。

### 8. Duplicate Tool Call 如何处理？

以 canonical name 和规范化参数做 fingerprint。相同调用可复用已有结果或阻断，并分别记录 attempted calls、actual executions、reused results，避免重复成本被统计掩盖。

### 9. RAG 的召回与相关性如何分离？

RAG Adapter 先调用现有 KnowledgeRepository 返回候选；Relevance Gate 再判断候选能否支持当前 claim。检索成功不等于答案充分，高盐案例就是“有候选但无可接受证据”。

### 10. Hybrid Historical Retrieval 是什么？

Case Memory 用标准化状态/环境特征和可用的视觉表示形成相似度，再结合 scope、year/treatment、跨实体和最小相似度过滤。结果包含真实 outcome，不是知识文本。

### 11. Case Memory 与长期对话 Memory 有何不同？

这里的 Memory 是只读历史实验案例库，不是用户聊天摘要。每条 Case 有时间、entity、scope、输入特征和观察到的未来 outcome，可被审计和防泄漏。

### 12. Temporal Leakage Guard 怎么做？

查询指定 cutoff；候选 case_date 和其 outcome_date 必须符合历史可用性，`historical_only` 禁止把查询之后的信息作为相似案例证据，还可排除同一实体。

### 13. Agent State 里有什么？

包含 query、route、RequestContract、Evidence Plan、tool calls/results、预算、warnings、evidence completeness、reliability、final answer 和 trace identifiers。它不是把所有中间文本塞进一个字符串。

### 14. 为什么固定 Workflow 而不是完全自由 ReAct？

农业任务有明确证据依赖和拒答边界。固定 workflow 能声明 required evidence、fallback 和 status；模型仍负责自然语言解析与工具参数。T=工具自由度，W=证据约束，两者组合比纯自由循环更可测。

### 15. Retry、Timeout 和 Budget 如何配合？

Provider 有网络 retry/timeout，Agent 另有 provider-call、tool-call 和 repair budget。网络重试不应无限增加业务工具调用；所有层级的计数都进入 Trace。

### 16. Trace 记录什么？

request/trace/tool-call ID、工具名、参数摘要、来源（model/workflow/fallback）、校验与修复、延迟、status/error code、scope 和 evidence count。默认不记录完整 embedding 或大传感器数组。

### 17. Claim Grounding 如何验证？

每个可验证 claim 持有 `support_evidence_ids`。Assembler 检查 ID 存在、证据类型与 claim 类型语义匹配，并生成 provenance edge。缺失支持会删 claim 或降级状态。

### 18. FULL / PARTIAL / ABSTAIN 如何判定？

不是看语气。Resolver 读取 RequestContract：所有请求子任务完成为 FULL；有可用答案但缺 required evidence 为 PARTIAL；主要问题没有可支持证据为 ABSTAIN。

### 19. Reliability 为什么不是概率？

当前没有校准集。HIGH/MEDIUM/LOW/UNKNOWN 是规则化政策，组合 scope match、critical features、domain、evidence completeness 和 model–case agreement，输出中明确 `statistically_calibrated=false`。

### 20. Agent Evaluation 为什么不能只看最终答案？

同一答案可能由错误工具或泄漏数据得到。因此分层评估 intent、tool precision/recall、参数、执行率、required tools、evidence registration/grounding、scope safety、status consistency、人工可用性和成本。

### 21. Mock 和真实 LLM 各自发现什么？

Mock 适合稳定验证 contract 与 regression；真实 LLM 才会暴露工具别名、参数变体、过度保守、漏调用与自然语言状态漂移。V1.4.4 的 false PARTIAL 就不是普通 unit test 能发现的。

### 22. 如何分析 Latency 和 Token Cost？

按 case 记录 provider calls、input/output/cached tokens、p50/p95 latency 和估算成本。综合任务 6 次 provider calls、约 12.36 秒，说明减少无效循环比换一个更大模型更重要。

### 23. 为什么选择 DeepSeek 但保持 Provider 解耦？

DeepSeek 用于实际成本可控的 Function Calling 验证；工具、workflow 和 evidence 不依赖其 SDK 类型。Provider 层只负责结构化请求/响应转换，未来可换 OpenAI-compatible 或本地模型。

### 24. 当前系统最大的局限是什么？

不是模型参数，而是证据：公开 Sensor 跨季偏移、RGB View shortcut、无局部根区映射、无真实灌溉/施肥事件和最优标签；在线只测过 10 个已知开发案例，独立 holdout 未运行。

### 25. 如果下一步只有一周，会做什么？

先完成仓库授权/CI，再在明确授权下运行 V1.4.5 Known-10 在线回归；达到门槛后一次性开启 48-case holdout。不会先加 Multi-Agent 或复杂 UI，因为当前证据是评测泛化而非能力数量最缺。

## 失败案例复盘模板

面试时按“现象 → 可观测证据 → 定位层 → 最小修复 → 回归指标 → 未解决边界”回答。三个完整实例见 [Engineering Decisions](ENGINEERING_DECISIONS.md)：invalid tool name、evidence missing、false PARTIAL。

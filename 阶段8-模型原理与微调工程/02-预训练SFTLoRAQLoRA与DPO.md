# 预训练、SFT、LoRA、QLoRA 与 DPO

## 一、方法选型

| 方法 | 解决问题 | 资源成本 | 适合阶段 |
|---|---|---:|---|
| 预训练 | 学习通用语言和领域分布 | 极高 | 了解原理，不作为本路线实践 |
| Continued Pretraining | 注入领域语料和术语 | 高 | 有大量高质量无标注语料时 |
| SFT | 学习任务格式、行为和工具调用模式 | 中 | 首选实践方法 |
| LoRA | 只训练低秩适配器 | 低 | 单卡或有限资源 |
| QLoRA | 量化基座后训练 LoRA | 更低 | 显存受限的实验 |
| DPO | 根据偏好对优化输出 | 中 | 有成对偏好数据时 |

## 二、SFT

SFT 数据通常是：

```json
{"messages":[
  {"role":"system","content":"你是运维分析助手。"},
  {"role":"user","content":"分析 pay-api 的错误率。"},
  {"role":"assistant","content":"请提供时间窗口和环境，我会先执行只读查询。"}
]}
```

Agent 场景还应覆盖：工具选择、参数格式、工具失败恢复、拒绝越权和人工审批边界。不要只用“漂亮答案”训练，否则模型可能学会语言风格，却不会稳定调用工具。

## 三、LoRA 与 QLoRA

LoRA 冻结基座参数，只训练低秩矩阵 $A$ 和 $B$：

$$
W'=W+\Delta W=W+BA
$$

这样可以显著降低训练参数和显存。QLoRA 在低比特量化的基座上训练 LoRA 适配器，训练后通常保存 adapter，而不是复制完整基座模型。

需要理解的参数：

- `r`：低秩维度；
- `lora_alpha`：缩放系数；
- `lora_dropout`：适配器 dropout；
- `target_modules`：注入 LoRA 的层；
- 学习率、batch、序列长度和训练步数。

## 四、DPO

DPO 使用偏好数据：同一个输入对应 chosen 和 rejected 输出。它比完整 RLHF 流程简单，但仍然依赖稳定的偏好标准和高质量数据。DPO 不应该被当作“自动让模型更聪明”的开关。

## 五、微调与 RAG 的边界

- 知识经常变化：优先 RAG；
- 需要固定回答风格或输出格式：考虑 SFT；
- 需要稳定工具调用协议：SFT + 结构化约束 + Tool 评测；
- 需要调整偏好：考虑 DPO；
- 需要降低成本：先做模型路由、缓存、量化和上下文优化。

## 六、练习

1. 将 20 条 Tool Calling 样本转换为 SFT 格式。
2. 对比全参数微调、LoRA 和 QLoRA 的显存与训练时间。
3. 为 10 条样本构造 chosen/rejected 偏好对，并说明判定标准。
4. 记录微调前后工具准确率和安全拒答率。

## 资料依据

- [PEFT Documentation](https://huggingface.co/docs/peft/index)
- [TRL Documentation](https://huggingface.co/docs/trl/index)
- [LoRA Paper](https://arxiv.org/abs/2106.09685)
- [QLoRA Paper](https://arxiv.org/abs/2305.14314)
- [DPO Paper](https://arxiv.org/abs/2305.18290)

# 阶段 8：模型原理与微调工程

目标：理解现代大语言模型的核心原理，并能完成一次小规模、可评测、可部署的参数高效微调实验。

> 定位：阶段 8 是进阶阶段，不是 Agent 应用开发的前置条件。应用型 Agent 工程师重点掌握原理、选型和微调工程闭环；不建议把从零预训练大模型作为学习目标。

## 适合什么时候学习

- 需要做领域模型适配或私有化部署；
- 需要理解模型能力、上下文和推理成本的来源；
- 目标岗位包含 LLM 算法、模型工程、推理优化或训练平台；
- 已经有可复现的 Agent 评测集，能够判断微调是否真的带来收益。

## 学习文档

- [01 - Transformer、Tokenizer 与语言模型基础](01-Transformer-Tokenizer与语言模型基础.md)
- [02 - 预训练、SFT、LoRA、QLoRA 与 DPO](02-预训练SFTLoRAQLoRA与DPO.md)
- [03 - 微调数据、实验设计与评测](03-微调数据实验设计与评测.md)
- [04 - 量化、推理与模型服务](04-量化推理与模型服务.md)
- [05 - 阶段 8 综合实践：领域模型适配实验](05-阶段8综合实践-领域模型适配实验.md)

## 推荐顺序

```text
01 原理
  -> 02 微调方法
  -> 03 数据与评测
  -> 04 量化与推理
  -> 05 综合实践
```

## 阶段边界

本阶段不要求：

- 从零训练数十亿参数模型；
- 自己实现完整分布式训练框架；
- 一开始深入 RLHF 的全部算法细节；
- 用微调替代 RAG、Tool Calling、Workflow 或权限控制。

## 最终产出

选择一个小型开源指令模型，使用经过脱敏和版本化的数据完成 LoRA 或 QLoRA 实验，并输出：

- 基线模型与微调模型对比；
- 训练配置、数据集版本和硬件信息；
- Agent 任务评测结果；
- 显存、吞吐、延迟和成本记录；
- 失败案例、适用边界和回滚方案。

## 资料依据

- [Hugging Face Transformers](https://huggingface.co/docs/transformers/index)
- [Hugging Face PEFT](https://huggingface.co/docs/peft/index)
- [Hugging Face TRL](https://huggingface.co/docs/trl/index)
- [Hugging Face Quantization](https://huggingface.co/docs/transformers/main/en/quantization/overview)
- [PyTorch Transformer Tutorial](https://pytorch.org/tutorials/beginner/transformer_tutorial.html)

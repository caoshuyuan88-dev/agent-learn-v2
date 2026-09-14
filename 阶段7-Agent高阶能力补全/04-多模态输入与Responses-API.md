# 多模态输入与 Responses API

## 一、学习目标

- 理解 Chat Completions 与 Responses API 的定位差异；
- 处理图片、PDF 或其他文件输入；
- 将多模态输入纳入 Token、成本、权限和评测；
- 让工具调用和多模态分析处于同一条可观测链路中。

## 二、Responses API 的工程关注点

Responses API 面向更统一的模型响应和工具交互模型。实际接入时不要只替换 endpoint，还要核对：

- 输入和输出对象结构；
- 对话状态如何保存；
- 工具定义和工具结果格式；
- 流式事件类型；
- 结构化输出约束；
- 模型、版本和能力矩阵；
- 失败、超时和重试语义。

代码应固定 SDK 版本，并以当前官方文档和目标模型能力为准。

## 三、多模态输入分层

```text
文本输入
  -> 图片 / 音频 / 视频 / 文档输入
  -> 模型内容理解
  -> 结构化提取
  -> 工具或工作流处理
```

输入文件必须经过：

- MIME 类型和大小校验；
- 病毒扫描或内容安全检查；
- 租户权限校验；
- 临时存储和过期清理；
- PII 和敏感信息策略；
- Trace 中的文件元数据记录，避免直接记录原始敏感内容。

## 四、示例：图片输入

下面是概念性示例，具体字段以当前 OpenAI SDK 文档为准：

```python
from openai import OpenAI

client = OpenAI()

response = client.responses.create(
    model="gpt-5",
    input=[
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "识别截图中的错误信息，并输出 JSON。"},
                {
                    "type": "input_image",
                    "image_url": "https://example.com/incident.png",
                },
            ],
        }
    ],
)

print(response.output_text)
```

不要把外部 URL 直接交给模型而不做访问控制。生产系统应使用受保护的文件代理或短期签名 URL。

## 五、结构化提取

多模态输出进入业务流程前，必须经过 schema 校验：

```python
from pydantic import BaseModel, Field


class IncidentImageFinding(BaseModel):
    service: str
    error_code: str | None = None
    severity: str = Field(pattern="^(low|medium|high|critical)$")
    evidence: list[str]
```

模型输出不等于事实。需要保留原始文件引用、页码或图像区域等证据，并对关键结果做人工复核或二次校验。

## 六、文档和 PDF

建议把文档处理拆成独立步骤：

```text
上传
  -> 类型 / 大小 / 安全检查
  -> 文本和版面提取
  -> 页码与来源保留
  -> 模型结构化分析
  -> Pydantic 校验
  -> RAG / Workflow / 报告
```

对于扫描 PDF，OCR 错误应作为评测维度；不能只测最终答案，还要测字段提取准确率和来源定位准确率。

## 七、评测与观测

新增字段：

```text
input_modalities
file_id
mime_type
file_size
page_count
model_vision_capability
extraction_latency
extraction_error
```

评测至少包含：清晰图片、低分辨率图片、空白文件、恶意文件、越权文件、超大文件、中文文档和无答案文档。

## 资料依据

- [OpenAI Responses API migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [OpenAI Images and Vision](https://developers.openai.com/api/docs/guides/images-vision)

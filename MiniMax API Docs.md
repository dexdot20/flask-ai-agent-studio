> ## Documentation Index
> Fetch the complete documentation index at: https://platform.minimax.io/docs/llms.txt
> Use this file to discover all available pages before exploring further.

# Compatible Anthropic API

> Call MiniMax models using the Anthropic SDK

To meet developers' needs for the Anthropic API ecosystem, our API now supports the Anthropic API format. With simple configuration, you can integrate MiniMax capabilities into the Anthropic API ecosystem.

## Quick Start

### 1. Install Anthropic SDK

<CodeGroup>
  ```bash Python theme={null}
  pip install anthropic
  ```

  ```bash Node.js theme={null}
  npm install @anthropic-ai/sdk
  ```
</CodeGroup>

### 2. Configure Environment Variables

```bash theme={null}
export ANTHROPIC_BASE_URL=https://api.minimax.io/anthropic
export ANTHROPIC_API_KEY=${YOUR_API_KEY}
```

### 3. Call API

```python Python theme={null}
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="MiniMax-M2.7",
    max_tokens=1000,
    system="You are a helpful assistant.",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": "Hi, how are you?"
                }
            ]
        }
    ]
)

for block in message.content:
    if block.type == "thinking":
        print(f"Thinking:\n{block.thinking}\n")
    elif block.type == "text":
        print(f"Text:\n{block.text}\n")
```

### 4. Important Note

In multi-turn function call conversations, the complete model response (i.e., the assistant message) must be append to the conversation history to maintain the continuity of the reasoning chain.

* Append the full `response.content` list to the message history (includes all content blocks: thinking/text/tool\_use)

## Supported Models

When using the Anthropic SDK, the `MiniMax-M2.7` `MiniMax-M2.7-highspeed` `MiniMax-M2.5` `MiniMax-M2.5-highspeed` `MiniMax-M2.1` `MiniMax-M2.1-highspeed` `MiniMax-M2` model is supported:

| Model Name             | Context Window | Description                                                                                                                                   |
| :--------------------- | :------------- | :-------------------------------------------------------------------------------------------------------------------------------------------- |
| MiniMax-M2.7           | 204,800        | **Beginning the journey of recursive self-improvement** (output speed approximately 60 tps)                                                   |
| MiniMax-M2.7-highspeed | 204,800        | **M2.7 Highspeed: Same performance, faster and more agile (output speed approximately 100 tps)**                                              |
| MiniMax-M2.5           | 204,800        | **Peak Performance. Ultimate Value. Master the Complex (output speed approximately 60 tps)**                                                  |
| MiniMax-M2.5-highspeed | 204,800        | **M2.5 highspeed: Same performance, faster and more agile (output speed approximately 100 tps)**                                              |
| MiniMax-M2.1           | 204,800        | **Powerful Multi-Language Programming Capabilities with Comprehensively Enhanced Programming Experience (output speed approximately 60 tps)** |
| MiniMax-M2.1-highspeed | 204,800        | **Faster and More Agile (output speed approximately 100 tps)**                                                                                |
| MiniMax-M2             | 204,800        | **Agentic capabilities, Advanced reasoning**                                                                                                  |

<Note>
  For details on how tps (Tokens Per Second) is calculated, please refer to [FAQ > About APIs](/faq/about-apis#q-how-is-tps-tokens-per-second-calculated-for-text-models).
</Note>

<Note>
  The Anthropic API compatibility interface currently only supports the
  `MiniMax-M2.7` `MiniMax-M2.7-highspeed` `MiniMax-M2.5` `MiniMax-M2.5-highspeed` `MiniMax-M2.1` `MiniMax-M2.1-highspeed` `MiniMax-M2` model. For other models, please use the standard MiniMax API
  interface.
</Note>

## Compatibility

### Supported Parameters

When using the Anthropic SDK, we support the following input parameters:

| Parameter            | Support Status  | Description                                                                                                                                         |
| :------------------- | :-------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------- |
| `model`              | Fully supported | supports `MiniMax-M2.7` `MiniMax-M2.7-highspeed` `MiniMax-M2.5` `MiniMax-M2.5-highspeed` `MiniMax-M2.1` `MiniMax-M2.1-highspeed` `MiniMax-M2` model |
| `messages`           | Partial support | Supports text and tool calls, no image/document input                                                                                               |
| `max_tokens`         | Fully supported | Maximum number of tokens to generate                                                                                                                |
| `stream`             | Fully supported | Streaming response                                                                                                                                  |
| `system`             | Fully supported | System prompt                                                                                                                                       |
| `temperature`        | Fully supported | Range (0.0, 1.0], controls output randomness, recommended value: 1                                                                                  |
| `tool_choice`        | Fully supported | Tool selection strategy                                                                                                                             |
| `tools`              | Fully supported | Tool definitions                                                                                                                                    |
| `top_p`              | Fully supported | Nucleus sampling parameter                                                                                                                          |
| `metadata`           | Fully Supported | Metadata                                                                                                                                            |
| `thinking`           | Fully Supported | Reasoning Content                                                                                                                                   |
| `top_k`              | Ignored         | This parameter will be ignored                                                                                                                      |
| `stop_sequences`     | Ignored         | This parameter will be ignored                                                                                                                      |
| `service_tier`       | Ignored         | This parameter will be ignored                                                                                                                      |
| `mcp_servers`        | Ignored         | This parameter will be ignored                                                                                                                      |
| `context_management` | Ignored         | This parameter will be ignored                                                                                                                      |
| `container`          | Ignored         | This parameter will be ignored                                                                                                                      |

### Messages Field Support

| Field Type           | Support Status  | Description                      |
| :------------------- | :-------------- | :------------------------------- |
| `type="text"`        | Fully supported | Text messages                    |
| `type="tool_use"`    | Fully supported | Tool calls                       |
| `type="tool_result"` | Fully supported | Tool call results                |
| `type="thinking"`    | Fully supported | Reasoning Content                |
| `type="image"`       | Not supported   | Image input not supported yet    |
| `type="document"`    | Not supported   | Document input not supported yet |

## Examples

### Streaming Response

```python Python theme={null}
import anthropic

client = anthropic.Anthropic()

print("Starting stream response...\n")
print("=" * 60)
print("Thinking Process:")
print("=" * 60)

stream = client.messages.create(
    model="MiniMax-M2.7",
    max_tokens=1000,
    system="You are a helpful assistant.",
    messages=[
        {"role": "user", "content": [{"type": "text", "text": "Hi, how are you?"}]}
    ],
    stream=True,
)

reasoning_buffer = ""
text_buffer = ""

for chunk in stream:
    if chunk.type == "content_block_start":
        if hasattr(chunk, "content_block") and chunk.content_block:
            if chunk.content_block.type == "text":
                print("\n" + "=" * 60)
                print("Response Content:")
                print("=" * 60)

    elif chunk.type == "content_block_delta":
        if hasattr(chunk, "delta") and chunk.delta:
            if chunk.delta.type == "thinking_delta":
                # Stream output thinking process
                new_thinking = chunk.delta.thinking
                if new_thinking:
                    print(new_thinking, end="", flush=True)
                    reasoning_buffer += new_thinking
            elif chunk.delta.type == "text_delta":
                # Stream output text content
                new_text = chunk.delta.text
                if new_text:
                    print(new_text, end="", flush=True)
                    text_buffer += new_text

print("\n")
```

## Important Notes

<Warning>
  1. The Anthropic API compatibility interface currently only supports the `MiniMax-M2.7` `MiniMax-M2.7-highspeed` `MiniMax-M2.5` `MiniMax-M2.5-highspeed` `MiniMax-M2.1` `MiniMax-M2.1-highspeed` `MiniMax-M2` model

  2. The `temperature` parameter range is (0.0, 1.0], values outside this range will return an error

  3. Some Anthropic parameters (such as `thinking`, `top_k`, `stop_sequences`, `service_tier`, `mcp_servers`, `context_management`, `container`) will be ignored

  4. Image and document type inputs are not currently supported
</Warning>


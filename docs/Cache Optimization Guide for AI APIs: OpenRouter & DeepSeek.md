# Cache Optimization Guide for AI APIs: OpenRouter & DeepSeek

## Introduction

Prompt caching significantly reduces inference costs by storing and reusing repeated prompt prefixes across requests. This document consolidates technical details from OpenRouter's prompt caching and DeepSeek's KV cache implementations to help developers maximize cache hits in their applications.

## 1. OpenRouter Prompt Caching

### Overview
OpenRouter enables prompt caching on supported providers and models, with most providers automatically enabling it. Some providers (e.g., Anthropic) require explicit `cache_control` settings.

### Key Features

#### Provider Sticky Routing
- **Purpose**: Maximizes cache hit rates by routing subsequent requests to the same provider endpoint after a cached request.
- **How it works**:
  - After a request uses prompt caching, OpenRouter remembers which provider served your request.
  - Subsequent requests for the same model are routed to the same provider.
  - Sticky routing only activates when the provider's cache read pricing is cheaper than regular prompt pricing.
  - Falls back to next-best provider if sticky provider becomes unavailable.
  - Overridden by manual `provider.order` specifications.
- **Granularity**: Account-level, per model, per conversation. Conversations are identified by hashing the first system/developer message and first non-system message.

#### Cache Inspection
Cache usage metrics are available via:
1. Activity page detail button
2. `/api/v1/generation` API endpoint
3. `prompt_tokens_details` object in API responses

**Example Usage Object:**
```json
{
  "usage": {
    "prompt_tokens": 10339,
    "completion_tokens": 60,
    "total_tokens": 10399,
    "prompt_tokens_details": {
      "cached_tokens": 10318,
      "cache_write_tokens": 0
    }
  }
}
```

**Key fields:**
- `cached_tokens`: Tokens read from cache (cache hit)
- `cache_write_tokens`: Tokens written to cache (first request establishing cache)

### Provider-Specific Implementations

#### OpenAI
- **Cache writes**: No cost
- **Cache reads**: 0.25x or 0.50x original input pricing
- **Minimum prompt size**: 1024 tokens
- **Configuration**: Automatic, no additional setup required

#### Grok
- **Cache writes**: No cost
- **Cache reads**: 0.25x original input pricing
- **Configuration**: Automatic

#### Moonshot AI
- **Configuration**: Automatic, no additional setup

#### Groq
- **Cache writes**: No cost
- **Cache reads**: 0.5x original input pricing
- **Configuration**: Automatic (currently Kimi K2 models)

#### Anthropic Claude
- **Cache writes (5-minute TTL)**: 1.25x original input pricing
- **Cache writes (1-hour TTL)**: 2x original input pricing
- **Cache reads**: 0.1x original input pricing

**Supported models**: Claude Opus 4.6/4.5/4.1/4, Sonnet 4.6/4.5/4/3.7, Haiku 4.5/3.5

**Minimum cacheable prompt lengths:**
- 4096 tokens: Claude Opus 4.6, Claude Opus 4.5, Claude Haiku 4.5
- 2048 tokens: Claude Sonnet 4.6, Claude Haiku 3.5
- 1024 tokens: Claude Sonnet 4.5, Claude Opus 4.1, Claude Opus 4, Claude Sonnet 4, Claude Sonnet 3.7

**Cache TTL Options:**
- **5 minutes (default)**: `"cache_control": { "type": "ephemeral" }`
- **1 hour**: `"cache_control": { "type": "ephemeral", "ttl": "1h" }`

**Two implementation approaches:**
1. **Automatic caching**: Add `cache_control` at top-level of request (only works with Anthropic provider directly)
2. **Explicit cache breakpoints**: Place `cache_control` on individual content blocks (works across all Anthropic-compatible providers including Bedrock and Vertex AI)

#### Google Gemini
- **Implicit Caching**: Automatically enabled on supported models
- **Pricing Changes**: Cached requests charged at reduced rates
- **Supported Models**: Gemini 2.5 Flash, Gemini 2.5 Pro, etc.

## 2. DeepSeek Context Caching (KV Cache)

### Overview
DeepSeek's Context Caching on Disk Technology is enabled by default for all users. Each request triggers hard disk cache construction, with overlapping prefixes in subsequent requests counting as cache hits.

### How It Works
- Only repeated **prefix** parts trigger cache hits
- Cache matches identical message sequences from the beginning of conversations
- Few-shot learning significantly benefits from context caching due to repeated prefixes

**Example 1: Financial Report Analysis**
```json
// First Request
messages: [
    {"role": "system", "content": "You are an experienced financial report analyst..."},
    {"role": "user", "content": "<financial report content>\n\nPlease summarize the key information."}
]

// Second Request (cache hit on prefix)
messages: [
    {"role": "system", "content": "You are an experienced financial report analyst..."},
    {"role": "user", "content": "<financial report content>\n\nPlease analyze the profitability."}
]
```

**Example 2: Conversation Continuation**
```json
// First Request
messages: [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "What is the capital of China?"}
]

// Second Request (cache hit on initial messages)
messages: [
    {"role": "system", "content": "You are a helpful assistant"},
    {"role": "user", "content": "What is the capital of China?"},
    {"role": "assistant", "content": "The capital of China is Beijing."},
    {"role": "user", "content": "What is the capital of the United States?"}
]
```

**Example 3: Few-Shot Learning (4-shot example)**
```json
// First Request
messages: [    
    {"role": "system", "content": "You are a history expert..."},
    {"role": "user", "content": "In what year did Qin Shi Huang unify the six states?"},
    {"role": "assistant", "content": "Answer: 221 BC"},
    {"role": "user", "content": "Who was the founder of the Han Dynasty?"},
    {"role": "assistant", "content": "Answer: Liu Bang"},
    {"role": "user", "content": "Who was the last emperor of the Tang Dynasty?"},
    {"role": "assistant", "content": "Answer: Li Zhu"},
    {"role": "user", "content": "Who was the founding emperor of the Ming Dynasty?"},
    {"role": "assistant", "content": "Answer: Zhu Yuanzhang"},
    {"role": "user", "content": "Who was the founding emperor of the Qing Dynasty?"}
]

// Second Request (cache hit on first 4 rounds)
messages: [    
    {"role": "system", "content": "You are a history expert..."},
    {"role": "user", "content": "In what year did Qin Shi Huang unify the six states?"},
    {"role": "assistant", "content": "Answer: 221 BC"},
    {"role": "user", "content": "Who was the founder of the Han Dynasty?"},
    {"role": "assistant", "content": "Answer: Liu Bang"},
    {"role": "user", "content": "Who was the last emperor of the Tang Dynasty?"},
    {"role": "assistant", "content": "Answer: Li Zhu"},
    {"role": "user", "content": "Who was the founding emperor of the Ming Dynasty?"},
    {"role": "assistant", "content": "Answer: Zhu Yuanzhang"},
    {"role": "user", "content": "When did the Shang Dynasty fall?"}
]
```

### Cache Metrics in API Response
DeepSeek API includes two fields in the `usage` section:
1. `prompt_cache_hit_tokens`: Number of tokens in input that resulted in cache hit (0.1 yuan per million tokens)
2. `prompt_cache_miss_tokens`: Number of tokens in input that did not result in cache hit (1 yuan per million tokens)

### Technical Limitations
1. **Storage unit**: 64 tokens minimum; content < 64 tokens not cached
2. **Best-effort basis**: No guarantee of 100% cache hit rate
3. **Cache construction time**: Takes seconds to build
4. **Automatic cleanup**: Unused caches cleared within hours to days
5. **Prefix matching only**: Only matches from the beginning of conversations

## 3. Implementation Guidelines for Maximum Cache Hits

### General Principles
1. **Maintain consistent conversation prefixes**: Keep system messages and initial user prompts identical across requests
2. **Structure conversations for prefix reuse**: Place static content (instructions, context, examples) at the beginning
3. **Batch similar requests**: Group requests with shared prefixes to benefit from sticky routing

### OpenRouter-Specific Strategies
1. **Enable provider sticky routing**: Let OpenRouter optimize routing automatically (unless explicit provider order needed)
2. **Monitor cache metrics**: Regularly check `cached_tokens` vs `cache_write_tokens` ratio
3. **Configure Anthropic carefully**: Choose between automatic (top-level) vs explicit (per-block) cache control based on provider constraints
4. **Optimize TTL settings**: Use 1-hour TTL for extended sessions to avoid repeated cache writes
5. **Respect minimum token requirements**: Ensure prompts meet provider-specific thresholds

### DeepSeek-Specific Strategies
1. **Design for prefix matching**: Structure conversations so variable content comes after static prefix
2. **Leverage few-shot learning**: Place examples at the beginning where they can be cached
3. **Minimize prefix changes**: Avoid altering system messages or initial user prompts
4. **Batch processing**: Process multiple similar queries in sequence to benefit from cache hits

## 4. Code Examples

### OpenRouter Request with Cache Control (Anthropic)
```json
{
  "model": "claude-3-5-sonnet-20241022",
  "messages": [
    {"role": "user", "content": "Large document content here..."}
  ],
  "cache_control": {
    "type": "ephemeral",
    "ttl": "1h"
  }
}
```

### DeepSeek Request Structure for Cache Hits
```python
# Example Python structure
messages = [
    # Static prefix (cached)
    {"role": "system", "content": "You are an expert analyst..."},
    {"role": "user", "content": "Static context data..."},
    
    # Variable content (not cached if prefix changes)
    {"role": "user", "content": "Variable query..."}
]
```

## 5. Cost Implications

### OpenRouter Pricing Model
- **Cache writes**: Typically free (except Anthropic: 1.25x-2x)
- **Cache reads**: 0.1x-0.5x original input pricing
- **Monitoring**: Check `cache_discount` field in responses

### DeepSeek Pricing Model
- **Cache hit tokens**: 0.1 yuan per million tokens
- **Cache miss tokens**: 1 yuan per million tokens
- **10x cost difference** between hit and miss tokens

## 6. Troubleshooting Cache Hit Issues

### Common Problems & Solutions

**Problem: Low cache hit rate on OpenRouter**
- Check if provider sticky routing is active
- Verify consistent conversation prefixes
- Monitor `cached_tokens` in usage details
- Ensure minimum token requirements are met

**Problem: No cache hits on DeepSeek**
- Verify prefix matching: only identical beginnings are cached
- Check if content > 64 tokens (minimum cacheable unit)
- Ensure requests are sequential with overlapping prefixes
- Account for cache construction delay (seconds)

**Problem: Inconsistent cache behavior**
- Review provider-specific limitations
- Check for explicit provider order overrides
- Verify cache TTL settings (especially for Anthropic)
- Monitor system message changes between requests

### Debugging Steps
1. **Inspect API responses**: Check `prompt_tokens_details` (OpenRouter) or `prompt_cache_hit_tokens` (DeepSeek)
2. **Review request structure**: Ensure identical prefixes across requests
3. **Check provider settings**: Verify automatic caching is enabled where applicable
4. **Monitor pricing**: Compare cache read vs write costs to validate savings

## 7. Best Practices Summary

### Architectural Recommendations
1. **Separate static and dynamic content**: Place invariant instructions, context, and examples at conversation start
2. **Design for conversation reuse**: Structure applications to maximize prefix overlap
3. **Implement request batching**: Group similar operations to benefit from warm caches
4. **Monitor cache efficiency**: Track hit rates and adjust application logic accordingly

### Provider Selection Guidance
1. **High-volume, consistent prompts**: Choose providers with automatic caching (OpenAI, DeepSeek)
2. **Complex conversations with large contexts**: Consider Anthropic with explicit cache control
3. **Cost-sensitive applications**: DeepSeek offers 10x cost difference between hit/miss tokens
4. **Multi-provider flexibility**: OpenRouter provides sticky routing across providers

### Implementation Checklist
- [ ] Identify static content that can form conversation prefixes
- [ ] Structure requests to place variable content after static prefixes
- [ ] Configure appropriate cache control settings per provider
- [ ] Implement monitoring for cache hit rates
- [ ] Optimize based on actual cache performance metrics
- [ ] Consider TTL settings for extended sessions
- [ ] Test with representative workload patterns

## References
1. [OpenRouter Prompt Caching Documentation](https://openrouter.ai/docs/guides/best-practices/prompt-caching)
2. [DeepSeek Context Caching Documentation](https://api-docs.deepseek.com/guides/kv_cache)
3. [OpenAI Prompt Caching](https://platform.openai.com/docs/guides/prompt-caching)
4. [Anthropic Prompt Caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)

---

*Document created: 2026-04-15 | For developer reference: Cache optimization for AI API cost reduction*
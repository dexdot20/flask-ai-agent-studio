# OpenRouter API: Inner Monologue (Reasoning) & Tool Calling Entegrasyon Rehberi

OpenRouter'ın güncel API'sinde Claude 3.7 Sonnet, DeepSeek R1 gibi modellerin yanıt vermeden önce kendi kendine konuştuğu "Thinking / Reasoning" (içsel düşünme) metinlerini almak ve bunu **Tool Calling (Fonksiyon Çağrısı)** yaparken kesintiye uğramadan devam ettirmek standartlaştırılmıştır.

Modelin tool kullanmadan önceki düşüncelerini okumak ve tool'dan dönen sonucu verdikten sonra modelin bağlamdan kopmamasını sağlamak için aşağıdaki adımlar izlenmelidir.

### 1. İsteği (Request) Gönderirken Düşünmeyi Aktif Etme

Modele gönderilen ilk istekte ana gövdeye `reasoning` parametresi eklenmelidir.
*(Not: Anthropic modelleri için token limiti belirtmek zorunludur. DeepSeek, Gemini gibi modeller için `effort` kullanılabilir.)*

```json
{
  "model": "anthropic/claude-3.7-sonnet",
  "messages":[
    {
      "role": "user",
      "content": "Ankara'da hava nasıl? Buna göre bana ne giyeceğimi adım adım düşünerek söyle."
    }
  ],
  "tools":[
    {
      "type": "function",
      "function": {
        "name": "get_weather",
        "description": "Belirtilen şehrin hava durumunu getirir.",
        "parameters": {
          "type": "object",
          "properties": {
            "location": { "type": "string" }
          },
          "required": ["location"]
        }
      }
    }
  ],
  "reasoning": {
    "max_tokens": 2000 // Anthropic modelleri için max_tokens zorunludur.
    // Diğer modeller (örn. Gemini, Qwen vb.) için: "effort": "high" kullanılabilir.
  }
}
```

### 2. Yanıtı (Response) Okuma ve İçsel Konuşmayı Alma

Model bir Tool çağırmaya karar verdiğinde API yanıtı döner. Düşünme süreci, standart API yanıtının içinde iki şekilde yer alır:

1. **`message.reasoning` (String):** Modelin kendi kendine konuştuğu düz metin (Frontend'de kullanıcıya "Model Düşünüyor..." diye göstermek için bunu kullanın).
2. **`message.reasoning_details` (Array):** Düşünme sürecinin yapılandırılmış (JSON) hali. (Bir sonraki *tool_result* isteğinde, modelin düşüncesini unutmaması için sisteme geri beslenmesi **şarttır**).

**Örnek 1. Adım API Yanıtı:**
```json
{
  "choices":[
    {
      "message": {
        "role": "assistant",
        "content": null,
        "tool_calls":[
          {
            "id": "call_123",
            "type": "function",
            "function": { "name": "get_weather", "arguments": "{\"location\": \"Ankara\"}" }
          }
        ],
        "reasoning": "Kullanıcı Ankara'daki hava durumunu ve ne giyeceğini soruyor. Önce hava durumunu öğrenmeliyim, bunun için get_weather aracını kullanacağım. Sonuca göre bir kıyafet önereceğim...",
        "reasoning_details":[
          {
            "type": "reasoning.text",
            "text": "Kullanıcı Ankara'daki hava durumunu ve ne giyeceğini soruyor. Önce hava durumunu öğrenmeliyim, bunun için get_weather aracını kullanacağım. Sonuca göre bir kıyafet önereceğim...",
            "id": "reasoning-text-1",
            "format": "anthropic-claude-v1",
            "index": 0
          }
        ]
      }
    }
  ]
}
```

### 3. Tool Sonucunu Gönderirken Düşünceyi Koruma (Preserving Reasoning) - EN ÖNEMLİ KISIM

Model tool çağırdığında düşünme sürecini "dondurur". Siz fonksiyonu kendi sunucunuzda çalıştırıp sonucu modele (2. istek olarak) geri gönderirken, **modelin önceki düşünce adımlarını unutmaması için** bir önceki adımda dönen `reasoning_details` dizisini **hiç değiştirmeden** assistant mesajına eklemelisiniz.

**Tool Sonucunu (Weather API cevabını) İçeren 2. İstek:**
```json
{
  "model": "anthropic/claude-3.7-sonnet",
  "messages":[
    {
      "role": "user",
      "content": "Ankara'da hava nasıl? Buna göre bana ne giyeceğimi adım adım düşünerek söyle."
    },
    {
      "role": "assistant",
      "tool_calls":[
        {
          "id": "call_123",
          "type": "function",
          "function": { "name": "get_weather", "arguments": "{\"location\": \"Ankara\"}" }
        }
      ],
      // VURUCU NOKTA: Bir önceki yanıttan gelen reasoning_details dizisini BURAYA YAPIŞTIRIYORUZ
      "reasoning_details":[
        {
          "type": "reasoning.text",
          "text": "Kullanıcı Ankara'daki hava durumunu ve ne giyeceğini soruyor. Önce hava durumunu öğrenmeliyim...",
          "id": "reasoning-text-1",
          "format": "anthropic-claude-v1",
          "index": 0
        }
      ]
    },
    {
      "role": "tool",
      "tool_call_id": "call_123",
      "content": "{\"temperature\": 12, \"condition\": \"Rüzgarlı ve Parçalı Bulutlu\"}"
    }
  ],
  "tools": [ /* ... Aynı tool objeleri ... */ ]
}
```
*Bu yapıyı kurguladığınızda model 2. istekte: "Ah evet, ben en son tool çağırıp şunu düşünüyordum, şimdi tool cevabı gelmiş, kaldığım yerden düşünmeye ve nihai cevabı üretmeye devam edeyim" diyerek reasoning sürecini başarılı şekilde tamamlar.*

### 4. Streaming (Akış) Kullanılıyorsa Dikkat Edilecekler

Eğer API'yi `stream: true` ile kullanıyorsanız, "Thinking" metinleri `content` içinde değil, `reasoning_details` içinde chunk'lar halinde gelir.

Gelen veriyi parse ederken şu mantığı kurmalısınız:

```javascript
// Gelen Stream chunk'larını dinlerken:
const delta = chunk.choices[0].delta;

// Eğer model DÜŞÜNÜYORSA (Inner Monologue aktıyorsa):
if (delta.reasoning_details && delta.reasoning_details.length > 0) {
    for (const detail of delta.reasoning_details) {
        if (detail.type === 'reasoning.text' && detail.text) {
             process.stdout.write(detail.text); // UI'daki "Düşünülüyor..." kutusuna yazdır
        }
    }
} 
// Eğer model NİHAİ CEVABI (Tool sonrası veya direk cevap) veriyorsa:
else if (delta.content) {
    process.stdout.write(delta.content); // Normal sohbet balonuna yazdır
}
```

### Özet Geliştirici Check-List'i:
- [ ] İlk istekte Root Payload içine `reasoning` ayarlarını ekle.
- [ ] Backend'de, OpenRouter'dan dönen ilk yanıtın içindeki `message.reasoning` alanını Frontend'e aktar ki kullanıcı görsün.
- [ ] `message.reasoning_details` array'ini bir değişkende/veritabanında (veya session'da) tut.
- [ ] Tool fonksiyonunu çalıştırıp sonucu geri yollarken, sakladığın `message.reasoning_details` array'ini `assistant` mesaj rolünün içine ekleyerek geri gönder.

***

Hazırladığım bu rehber, OpenRouter'ın resmi güncellemelerine ve aslında sizin de sorunuzun en başında belirttiğiniz güncel dokümantasyon linklerine dayanmaktadır. Yazılımcınıza rehberle birlikte bu linkleri de iletmeniz, teknik detayları (özellikle tipleri ve yapıları) doğrudan kaynaktan teyit etmesi için çok faydalı olacaktır.

İlgili kaynaklar ve içerikleri şunlardır:

**1. Reasoning Yanıt Objesi ve API Referansı (En Temel Kaynak)**
*   **Link:** [https://openrouter.ai/docs/api/reference/responses/reasoning](https://openrouter.ai/docs/api/reference/responses/reasoning)
*   **İçeriği:** API'den dönen `reasoning` (string) ve `reasoning_details` (array) objelerinin tam yapısını, JSON formatını ve `reasoning.text`, `reasoning.signature` gibi alt tiplerini gösterir.

**2. Reasoning (Düşünme) Modelleri İçin En İyi Uygulamalar (Preserving Reasoning)**
*   **Link:** [https://openrouter.ai/docs/guides/best-practices/reasoning-tokens](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens)
*   **İçeriği:** Rehberde bahsettiğim **"Düşünceyi Koruma (Preserving Reasoning)"** mantığının anlatıldığı yerdir. Modelin tool kullanımından sonra konseptten kopmaması için `reasoning_details`'in bir sonraki isteğe nasıl ekleneceğini (Anthropic modellerindeki zorunluluğu) açıklar.

**3. İstek (Request) Gönderirken Reasoning Parametreleri**
*   **Link:**[https://openrouter.ai/docs/guides/routing/model-variants/thinking](https://openrouter.ai/docs/guides/routing/model-variants/thinking)
*   **İçeriği:** İsteği başlatırken payload içine eklenen `"reasoning"` objesini açıklar. Anthropic için `max_tokens`, OpenAI/Gemini gibi modeller için `effort: "high" | "medium" | "low"` parametrelerinin nasıl kullanılacağını gösterir.

**4. Duyuru ve Genel Mimari Mantığı**
*   **Link:**[https://openrouter.ai/announcements/reasoning-tokens-for-thinking-models](https://openrouter.ai/announcements/reasoning-tokens-for-thinking-models)
*   **İçeriği:** OpenRouter'ın eskiden yaşanan tool calling + reasoning çakışmalarını çözdüğü, bu yeni standartlaştırılmış API yapısını duyurduğu ve o1, o3, R1, Sonnet 3.7 gibi modellerin bu yapıya nasıl entegre edildiğini anlattığı resmi blog/duyuru yazısıdır.
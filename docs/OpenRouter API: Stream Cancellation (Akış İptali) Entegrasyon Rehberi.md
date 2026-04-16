# OpenRouter API: Stream Cancellation (Akış İptali) Entegrasyon Rehberi

OpenRouter API'sinde streaming (akış) kullanırken, kullanıcı arayüzünde bir "Durdur" (Stop Generating) butonuna basılması veya sayfanın kapatılması gibi durumlarda modelin işlem yapmasını ve API maliyetinin yazılmasını durdurmak mümkündür.

Bu işlem, ağ bağlantısının `AbortController` kullanılarak kesilmesi (abort) yöntemiyle yapılır. **Desteklenen sağlayıcılarda (providers), bağlantı koptuğu anda modelin arkadaki çalışması anında durdurulur ve sadece o ana kadar üretilen token'lar için ücretlendirilirsiniz**.

### 1. Sağlayıcı (Provider) Destek Durumu

Her AI sağlayıcısı bağlantı koparıldığında arkada çalışan süreci durdurmayı (ve faturalandırmayı kesmeyi) desteklemez. Eğer desteklenmeyen bir modelde stream'i durdurursanız, frontend'de veri akışı dursa bile arka planda model çalışmaya devam eder ve **tam yanıtın faturası size yansıtılır**.

**Destekleyen Sağlayıcılar (Anında Durur ve Faturalandırma Kesilir):**
*   OpenAI, Azure, Anthropic
*   DeepSeek, XAI, Cohere
*   Fireworks, AnyScale, Together, Lepton, OctoAI, Novita, DeepInfra
*   Hyperbolic, Infermatic, Avian, Cloudflare, SFCompute, Nineteen, Liquid, Friendli, Chutes, Mancer, Recursal

**Şu An DESTEKLENMEYEN Sağlayıcılar (Tam Fatura Yansır):**
*   Google, Google AI Studio, AWS Bedrock
*   Groq, Perplexity, Mistral, HuggingFace
*   Replicate, Modal, Minimax, AI21, Featherless
*   SambaNova, Alibaba, Nebius vb. (Diğer küçük sağlayıcılar)

*(Not: Eğer uygulamanızda maliyet optimizasyonu çok önemliyse, kullanıcı "Durdur" dediğinde arkada çalışmaya devam etmemesi için yukarıdaki desteklenen sağlayıcılardan (Örn: Anthropic, OpenAI, DeepSeek) birini tercih ettiğinize emin olun.)*

### 2. Uygulama: AbortController Kullanımı

Bağlantıyı iptal etmek için standart JavaScript/TypeScript `AbortController` yapısını HTTP isteğinize veya SDK fonksiyonunuza `signal` olarak bağlamanız gerekir.

**TypeScript SDK / Fetch Örneği:**

```typescript
import { OpenRouter } from '@openrouter/sdk';

const openRouter = new OpenRouter({
  apiKey: 'SİZİN_API_ANAHTARINIZ',
});

// 1. Controller'ı oluşturun
const controller = new AbortController();

async function startStreaming() {
    try {
        const stream = await openRouter.chat.send({
            model: 'anthropic/claude-3.7-sonnet', // İptali destekleyen bir model
            messages:[{ role: 'user', content: 'Bana çok uzun bir hikaye yaz' }],
            stream: true,
        }, {
            // 2. Sinyali API isteğine bağlayın
            signal: controller.signal,
        });

        for await (const chunk of stream) {
            const content = chunk.choices?.[0]?.delta?.content;
            if (content) {
                console.log(content); // UI'a yazdır
            }
        }
    } catch (error) {
        // 4. İptal durumunu yakalayın
        if (error.name === 'AbortError') {
            console.log('Akış kullanıcı veya sistem tarafından iptal edildi.');
            // Burada faturanın kesildiğinden ve bağlantının kapandığından emin olabilirsiniz.
        } else {
            console.error('Bilinmeyen bir akış hatası:', error);
        }
    }
}

// 3. Herhangi bir DOM eventinde (Örn: "Durdur" butonuna tıklanınca) akışı kesin:
document.getElementById('stopButton').addEventListener('click', () => {
    controller.abort(); 
});
```

### 3. Akış Sırasında Oluşabilecek Hataları Yakalama (Mid-Stream Errors)

Kullanıcı akışı iptal etmese bile, bazen bağlantı sırasında sağlayıcı tarafında hata oluşabilir. OpenRouter hataları iki şekilde gönderir:

**A. Token Gönderilmeden Önceki Hatalar:** (Örn: Yanlış API Key, Yetersiz Bakiye)
Standart HTTP 400, 401, 402, 502 gibi status kodları ve JSON hatası olarak düşer. (Normal `try/catch` mekanizması çalışır).

**B. Token Gönderimi Başladıktan Sonraki Hatalar (Mid-Stream):**
Eğer model cevap yazmaya başladıktan sonra arkada bir şeyler patlarsa (HTTP Status çoktan `200 OK` olduğu için), hata stream'in içine bir *chunk* olarak enjekte edilir.
Bu durumda chunk içinde `error` objesi bulunur ve stream'i bitiren `finish_reason` değeri `"error"` olur.

Bu durumu SDK içerisinde şu şekilde kontrol etmelisiniz:

```typescript
for await (const chunk of stream) {
    // Akış ortasında (Mid-Stream) hata kontrolü
    if ('error' in chunk) {
        console.error(`Akış sırasında hata oluştu: ${chunk.error.message}`);
        if (chunk.choices?.[0]?.finish_reason === 'error') {
            console.log('Akış hata sebebiyle OpenRouter tarafından zorla kapatıldı.');
        }
        return; // İşlemi durdur
    }

    // Sorun yoksa veriyi basmaya devam et
    const content = chunk.choices?.[0]?.delta?.content;
    // ...
}
```

### Özet Geliştirici Check-List'i:
- [ ] UI tarafına "Yanıtı Durdur / Stop" butonu eklenecek.
- [ ] API isteği atılırken bir `AbortController` örneği oluşturulup `signal` parametresine bağlanacak.
- [ ] Stop butonuna basıldığında (veya kullanıcı chat sayfasından ayrıldığında/sekme kapattığında) `controller.abort()` tetiklenecek.
- [ ] Hata yakalama bloğunda (catch), `error.name === 'AbortError'` koşulu kontrol edilerek, bunun teknik bir hata olmadığı, kullanıcının isteği ile iptal edildiği (graceful shutdown) yönetilecek.
- [ ] Uygulama maliyetlerini optimize etmek için `Google`, `Mistral`, `Groq` gibi sağlayıcılarda `abort()` atılsa dahi paranın tam çekileceği product / iş birimine bildirilecek.

***

**Kaynak Doküman Linki (Yazılımcı için):**
*   [OpenRouter API: Streaming - Stream Cancellation](https://openrouter.ai/docs/api/reference/streaming#stream-cancellation)
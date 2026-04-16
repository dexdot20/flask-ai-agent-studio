


# DeepSeek API: Stream Cancellation (Akış İptali) Teknik Rehberi

## 1. DeepSeek API'de Akış İptali Destekleniyor mu?
**Evet.** Doğrudan DeepSeek'in kendi API'si (`api.deepseek.com`), OpenAI uyumlu (OpenAI-compatible) bir REST mimarisi üzerine inşa edildiği için standart HTTP soket kapatma / akış iptali (Stream Cancellation) işlemlerini yerel olarak destekler. 

İstemci (client) tarafında bağlantı kesildiğinde veya `AbortController` tetiklendiğinde, DeepSeek sunucuları TCP/IP seviyesindeki bu kopukluğu anında algılar ve arka plandaki LLM metin üretimini (inference) derhal durdurur.

## 2. Faturalandırma ve Maliyet Yönetimi
Doğrudan DeepSeek API'si kullanıldığında akışın iptal edilmesi maliyet optimizasyonu açısından kritik bir öneme sahiptir:
*   **Anında Kesinti:** Bağlantı koptuğu saniye itibarıyla sunucu tarafındaki yük durdurulur.
*   **Kullanım Kadar Öde:** Faturanıza sadece iptal anına kadar sunucudan size başarıyla iletilmiş olan "Output (Çıktı)" token'ları ve gönderdiğiniz "Input (Girdi)" token'ları yansır. Üretilmeyen kısım için hiçbir ücret ödemezsiniz.
*   **Uygulama Senaryosu:** Özellikle `deepseek-reasoner` (R1) gibi uzun düşünme (thinking) süreleri olan veya çok uzun çıktılar üreten modellerde, kullanıcı "Durdur" butonuna bastığında API maliyetinin israf olmasını %100 oranında engeller.

## 3. Entegrasyon Örnekleri

DeepSeek API'si OpenAI SDK'ları ile tam uyumlu olduğu için, iptal işlemleri standart web ve Node.js API'leri kullanılarak yapılır.

### A. JavaScript / TypeScript (Tarayıcı & Node.js)
Eğer frontend uygulamanızda doğrudan `fetch` kullanıyorsanız veya Node.js arka planında OpenAI SDK'sını DeepSeek Base URL'i ile yönlendirdiyseniz, bir `AbortController` nesnesi kullanmalısınız.

**Node.js / TypeScript SDK (OpenAI Paketi ile) Örneği:**
```typescript
import OpenAI from 'openai';

// DeepSeek API'sine yönlendirilmiş OpenAI istemcisi
const deepseek = new OpenAI({
  baseURL: 'https://api.deepseek.com',
  apiKey: 'SİZİN_DEEPSEEK_API_KEY_İNİZ'
});

// 1. Controller oluştur
const controller = new AbortController();

async function streamDeepSeek() {
  try {
    const stream = await deepseek.chat.completions.create({
      model: 'deepseek-chat', // veya deepseek-reasoner
      messages:[{ role: 'user', content: 'Bana çok detaylı bir hikaye anlat.' }],
      stream: true
    }, {
      // 2. Sinyali isteğe bağla
      signal: controller.signal
    });

    for await (const chunk of stream) {
      const content = chunk.choices[0]?.delta?.content;
      if (content) process.stdout.write(content);
    }
  } catch (error: any) {
    // 4. İptal durumunu yakala
    if (error.name === 'AbortError') {
      console.log('\n[SİSTEM] Akış kullanıcı tarafından durduruldu. Faturalandırma kesildi.');
    } else {
      console.error('Bilinmeyen API Hatası:', error);
    }
  }
}

// 3. UI üzerinde bir "Stop" butonuna basıldığında akışı kes:
// document.getElementById('stopButton').addEventListener('click', () => {
//     controller.abort();
// });
```

### B. Python (Asyncio) Modeli
Python tarafında, asenkron olarak çalışan `AsyncOpenAI` istemcisi kullanıldığında, çalışan `asyncio.Task` iptal edildiğinde (cancel) bağlantı kapatılır ve DeepSeek sunucusundaki işlem sonlandırılır.

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key="SİZİN_DEEPSEEK_API_KEY_İNİZ",
    base_url="https://api.deepseek.com"
)

async def stream_deepseek():
    try:
        stream = await client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": "Kuantum fiziğini detaylıca anlat."}],
            stream=True
        )
        
        async for chunk in stream:
            # Reasoner modeli için düşünme token'larını da destekler
            content = chunk.choices[0].delta.content or ""
            print(content, end="", flush=True)
            
    except asyncio.CancelledError:
        print("\n[SİSTEM] Görev iptal edildi. DeepSeek API bağlantısı kapatıldı.")
        raise

async def main():
    # Akışı başlatan görevi (task) oluştur
    task = asyncio.create_task(stream_deepseek())
    
    # 3 saniye sonra kullanıcının "Durdur" butonuna bastığını simüle et
    await asyncio.sleep(3)
    task.cancel()
    
    try:
        await task
    except asyncio.CancelledError:
        pass # İptal edildiğinde programın çökmemesi için geçiştir

asyncio.run(main())
```

## 4. Mimari ve Proxy Uyarıları (Önemli)
DeepSeek API'sini doğrudan frontend'den çağırmak güvenlik (API key ifşası) nedeniyle önerilmez. Genellikle istekler kendi Backend'iniz üzerinden (Reverse Proxy) geçirilir.

Eğer arada kendi sunucunuz varsa, **istemci ile sunucunuz arasındaki bağlantı koptuğunda, sunucunuzun da DeepSeek API'sine giden bağlantıyı kopardığından kesinlikle emin olmalısınız.** 

*   **Node.js/Express Proxy Örneği:** Frontend'den gelen istek `req.on('close', ...)` veya `req.on('aborted', ...)` event'leri ile dinlenmeli ve bu event tetiklendiğinde arka planda DeepSeek'e giden `fetch` veya `SDK` isteği yukarıdaki `controller.abort()` metodu ile manual olarak iptal edilmelidir.
*   **Hata Yapılırsa Ne Olur?** Eğer frontend bağlantıyı keser ama backend'iniz DeepSeek'i dinlemeye devam ederse, kullanıcı sayfadan çıkmış olsa bile DeepSeek modeli arka planda üretmeye devam eder ve siz boş yere API faturası ödersiniz.

## 5. UI/UX Tarafında "Bitiş" Yönetimi
Bağlantı aniden kesildiği için DeepSeek API, normalde akışın sonunda gönderdiği `finish_reason: "stop"` ibaresini gönderemez. 
Yazılım ekibiniz, `AbortError` yakalandığında arayüzdeki "Yazıyor..." animasyonunu durduracak ve o ana kadar üretilen metni kalıcı hale getirecek (veritabanına kaydedecek vb.) manuel bir kapanış mekanizması (graceful degradation) geliştirmelidir.
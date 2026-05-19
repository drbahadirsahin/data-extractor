# LLM Gateway hazırlığı

Bu gateway, masaüstü uygulamaya OpenRouter API key gömmeden LLM çağrısı yapmak için tasarlanmıştır.

## Mimari

1. Masaüstü uygulama `https://<gateway-domain>/v1/chat/completions` adresine istek gönderir.
2. Gateway isteği doğrular, model ve token sınırlarını uygular.
3. Gateway OpenRouter'a kendi sunucu secret'ı ile istek gönderir.
4. OpenRouter yanıtı masaüstü uygulamaya geri döner.

Masaüstü paketinde OpenRouter API key bulunmaz. Gateway de istek gövdesini loglamaz; klinik metinler uygulama loglarına veya gateway loglarına yazılmamalıdır.

## İlk hedef

`early.10` sürümü yalnızca hazırlık sürümüdür:

- `gateway/cloudflare-worker.js` gateway iskeletini içerir.
- Masaüstü uygulama `llm_gateway` sağlayıcısını tanır.
- Varsayılan masaüstü ayarı henüz gateway'e çevrilmez.

Gateway yayına alındıktan sonra `early.11` ile `app_config.json` içindeki `llm.base_url` gateway adresine çevrilecek.

## Cloudflare Worker kurulumu

Gateway klasöründe:

```bash
cd gateway
cp wrangler.toml.example wrangler.toml
```

Gerekirse `wrangler.toml` içindeki `name`, `DEFAULT_MODEL` ve `MAX_TOKENS` değerlerini düzenleyin.

Secret değerlerini dosyaya yazmayın. Bunları Cloudflare secret olarak kaydedin:

```bash
wrangler secret put OPENROUTER_API_KEY
wrangler secret put CLIENT_TOKEN
```

`CLIENT_TOKEN` erken test için basit gateway erişim kontrolüdür. Final mimaride bunun yerine kullanıcı/proje bazlı aktivasyon ve merkezi rate limit mekanizması tercih edilmelidir. Bu token OpenRouter key değildir; sızsa bile OpenRouter secret'ı açığa çıkmaz, ancak gateway kullanımını kötüye kullanmaya izin verebilir.

Deploy:

```bash
wrangler deploy
```

Sağlık kontrolü:

```bash
curl https://<gateway-domain>/health
```

LLM test isteği:

```bash
curl https://<gateway-domain>/v1/chat/completions \
  -H "Authorization: Bearer <CLIENT_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen/qwen3.5-9b",
    "messages": [{"role": "user", "content": "Sadece JSON döndür: {\"ok\": true}"}],
    "temperature": 0,
    "max_tokens": 256
  }'
```

## Masaüstü ayarı

Gateway hazır olduğunda uygulama ayarı şu şekle çevrilecek:

```json
"llm": {
  "provider": "llm_gateway",
  "base_url": "https://<gateway-domain>/v1",
  "model": "qwen/qwen3.5-9b",
  "temperature": 0,
  "max_tokens": 8192,
  "timeout_seconds": 120,
  "gateway_client_token_secret_name": "llm_gateway_client_token",
  "use_json_schema": true
}
```

Eğer gateway tarafında geçici olarak `CLIENT_TOKEN` zorunlu tutulmayacaksa `gateway_client_token_secret_name` alanı olmadan da çalışır. Final üründe açık gateway bırakılmamalıdır.

## Sürüm planı

1. `early.10`: Gateway kodu ve masaüstü `llm_gateway` desteği.
2. Gateway'i test domaininde yayına alma.
3. `early.11`: Masaüstü varsayılan LLM endpoint'ini gateway domainine çevirme.
4. `early.12`: Rate limit, kullanım ölçümü, hata mesajları ve merkezi gateway log politikasını sıkılaştırma.

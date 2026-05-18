LLM Extractor macOS ilk açılış notu
====================================

Bu erken sürüm Apple Developer ID ile imzalanıp notarize edilmemiştir.
Bu nedenle macOS ilk açılışta uygulamayı engelleyebilir.

Önerilen ilk açılış:

1. Zip dosyasını açın.
2. LLMExtractor-...-macos-arm64 klasörünü silmeden bırakın.
3. LLMExtractor.app üzerine sağ tıklayın.
4. Aç seçeneğini tıklayın.
5. macOS tekrar sorarsa Aç seçeneğini onaylayın.

Eğer macOS "uygulama hasarlı" veya "doğrulanamadı" benzeri bir uyarı verirse,
Terminal uygulamasında şu komutu çalıştırın. Komuttaki APP_YOLU yerine
LLMExtractor.app dosyasının gerçek yolunu yazın veya uygulamayı Terminal
penceresine sürükleyip bırakın:

xattr -dr com.apple.quarantine APP_YOLU

Not:
Uygulamayı tek başına /Applications içine taşımak yerine, zipten çıkan klasörün
içinde çalıştırmanız önerilir. Bu erken sürüm taşınabilir veri klasörünü aynı
paket klasörü içinde tutacak şekilde tasarlanmıştır.

Uygulama açılır gibi olup pencere göstermeden kapanırsa şu log dosyasını
kontrol edin:

LLMExtractor-...-macos-arm64/.llm_extractor_data/llm_extractor.log

Uygulamayı .app dosyasını tek başına başka bir yere taşıyarak çalıştırdıysanız
log şu konumda olabilir:

~/Library/Application Support/LLMExtractor/llm_extractor.log

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

Eğer macOS "uygulama hasarlı" veya "doğrulanamadı" benzeri bir uyarı verirse
veya uygulama güncellemeyi indirip tekrar aynı sürümle açılıyorsa, Terminal
uygulamasında şu komutu çalıştırın. Komuttaki KLASOR_YOLU yerine zipten çıkan
LLMExtractor-...-macos-arm64 klasörünün gerçek yolunu yazın veya bu klasörü
Terminal penceresine sürükleyip bırakın:

xattr -dr com.apple.quarantine KLASOR_YOLU

Örnek:

xattr -dr com.apple.quarantine "$HOME/Downloads/LLMExtractor-0.1.0-early.8-macos-arm64"

Bu komut yalnızca .app dosyasına değil, zipten çıkan üst klasörün tamamına
uygulanmalıdır. Aksi halde macOS uygulamayı geçici App Translocation konumundan
çalıştırabilir ve otomatik güncelleme kalıcı klasöre yazılamaz.

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

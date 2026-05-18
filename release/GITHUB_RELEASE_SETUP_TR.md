# Erken sürüm dağıtım hattı

Bu proje için önerilen dağıtım modeli:

1. Kaynak kod GitHub repository içinde tutulur.
2. GitHub Actions macOS ve Windows paketlerini üretir.
3. GitHub Releases paketleri ve `update_manifest.json` dosyasını barındırır.
4. Uygulama açılışta manifest dosyasını okuyup uygun platform paketini indirir.

## İlk kurulum

GitHub üzerinde yeni bir repository oluşturun. Açık kaynak/public repository en düşük maliyetli seçenektir. Private repository de çalışır, ancak Actions dakika ve artifact depolama limitleri GitHub planınıza göre uygulanır.

Yerelde proje klasöründe:

```bash
git init
git add .
git commit -m "Prepare early release packaging"
git branch -M main
git remote add origin https://github.com/OWNER/REPO.git
git push -u origin main
```

Bu proje için repository adı:

```text
drbahadirsahin/data-extractor
```

## Güncelleme manifest adresi

`app_config.json` içindeki `release.updates.manifest_url` alanı, yayınlanan son release içindeki manifest dosyasını göstermelidir:

```json
"manifest_url": "https://github.com/drbahadirsahin/data-extractor/releases/latest/download/update_manifest.json"
```

Bu değer kullanıcıya dağıtılacak build üretilmeden önce ayarlanmalıdır.

## Release üretme

GitHub arayüzünde:

1. Repository sayfasını açın.
2. `Actions` sekmesine gidin.
3. `Build portable release` workflow'unu seçin.
4. `Run workflow` ile örneğin `v0.1.0-early.1` tag değerini girin.

Workflow tamamlandığında GitHub Releases altında şu dosyalar oluşur:

- `LLMExtractor-<version>-windows-x64.zip`
- `LLMExtractor-<version>-macos-arm64.zip`
- `LLMExtractor-<version>-macos-x64.zip`
- `update_manifest.json`

Alternatif olarak tag push ederek de release başlatabilirsiniz:

```bash
git tag v0.1.0-early.1
git push origin v0.1.0-early.1
```

## Sürüm yükseltme

Yeni sürüm için:

1. `app_config.json` içindeki `release.version` değerini yükseltin.
2. Değişiklikleri commit edip GitHub'a gönderin.
3. Yeni tag ile workflow'u çalıştırın.

Uygulama açılışta `update_manifest.json` dosyasındaki sürüm daha yeniyse kullanıcıya güncelleme sunar.

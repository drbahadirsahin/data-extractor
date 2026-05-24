# Veri Giriş Modu Tasarımı

Bu doküman `codex/data-entry-mode` branch'i için geliştirme notudur. Amaç, mevcut belge/Excel çıkarım uygulamasını aşamalı olarak offline-first REDCap veri giriş arayüzüne dönüştürmektir. `main` branch public release hattı olarak kalır; bu mod olgunlaşana kadar release'e alınmaz.

## Hedef İş Akışı

1. Kullanıcı proje bazlı REDCap API token ile bağlanır.
2. Server tarafındaki `tc_hash` external module zorunlu kabul edilir.
3. Uygulama aktif kullanıcı/DAG context bilgisini alır.
4. Kullanıcının erişebildiği kayıtların server manifest'i indirilir.
5. Lokal SQLite cache ile server manifest karşılaştırılır.
6. Server'da daha yeni olan kayıtlar lokale çekilir.
7. Lokalde gönderilmemiş değişiklikler varsa kullanıcıya gösterilir.
8. Kullanıcı formları lokal verilerle açar, manuel veri girer/düzenler.
9. Değişiklikler outbox/pending queue'ya yazılır.
10. Gönderimde conflict kontrolü yapılır; güvenli olanlar REDCap API/external module ile server'a aktarılır.

## Yerel Depolama

İlk teknik tercih SQLite'tır. Nedenleri:

- Büyük REDCap projelerinde JSON dosyalarına göre daha hızlı ve daha kontrollü sorgulanır.
- Kayıt, alan, pending change, sync state ve TC hash eşlemesini ayrı ama ilişkili tablolarda tutabilir.
- İleride form UI, filtreleme, arama ve dynamic query alanları için lokal sorgu altyapısı sağlar.
- Tek dosya olduğu için taşınabilir uygulama modeliyle uyumludur.

İlk şema `data_entry_store.py` içinde oluşturuldu.

Ana tablolar:

- `redcap_data_values`: REDCap'in `redcap_data` tablosuna yakın lokal veri tablosu.
- `redcap_data`: `redcap_data_values` üzerinden view. Dynamic SQL alanları için REDCap'e benzer kolon adları sağlar.
- `record_sync_state`: kayıt bazlı remote/local son değişiklik ve dirty/conflict durumu.
- `pending_changes`: lokalde yapılmış ama server'a gönderilmemiş değişiklikler.
- `identity_hash_map`: serverdaki hashed T.C. kimlik numarası ile `record` eşlemesi.
- `project_context`: proje, kullanıcı ve aktif DAG context cache'i.
- `metadata_cache`: metadata/data dictionary/form/event/choice gibi proje sabitleri.
- `dynamic_query_cache`: serverdan çözümlenmiş dynamic SQL seçenekleri için kısa ömürlü cache.

## REDCap Veri Şekli

REDCap normalde veriyi `redcap_data` tablosunda şu yapıda tutar:

```text
project_id, event_id, record, field_name, value, instance
```

Lokal tablo da bu alanları korur. Ek kolonlar sadece sync için tutulur:

```text
dag_unique_name, remote_updated_at, local_updated_at, source, dirty
```

Bu sayede:

- Form renderer alan değerlerini REDCap'e yakın bir veri modelinden okuyabilir.
- Repeating form/event ve longitudinal yapı sonradan daha doğal desteklenir.
- Basit dynamic SQL alanları lokal `redcap_data` view'ı ile çözümlenebilir.
- Çözülemeyen veya güvenlik/context gerektiren dynamic SQL alanları server endpoint'ine bırakılır.

## T.C. Kimlik Hash Eşlemesi

Server tarafında gerçek T.C. kimlik numarası tutulmamalı veya masaüstüne gönderilmemelidir. External module zaten hashed unique T.C. kimlik numarası ile kayıtları eşleştiriyor. Lokal tarafta tutulacak yapı:

```text
project_id, tc_hash, record, dag_unique_name, remote_updated_at, last_synced_at
```

Bu tablo şu amaçlarla kullanılacak:

- Belge/Excel veya manuel giriş sırasında T.C. hash ile mevcut kayıt bulma.
- Yeni kayıt oluşturma öncesi duplicate kontrolü.
- Offline form ekranında gerçek T.C. numarasını tekrar taşımadan kayıt eşleme.

## Dynamic SQL Alanları

Dynamic Query / SQL alanları için iki katmanlı yaklaşım önerilir:

1. Basit SQL'ler lokal `redcap_data` view'ı üzerinden çözülebilir.
2. REDCap'e özel fonksiyon, user/DAG context, permission veya karmaşık join gerektiren SQL'ler serverdaki external module endpoint'i ile çözümlenmelidir.

Önerilen server endpoint:

```text
content=externalModule
prefix=tc_hash
action=get-dynamic-query-options
field_name=...
record=...
event_id=...
instance=...
format=json
returnFormat=json
```

Response önerisi:

```json
{
  "field_name": "mr_tarih_secimi",
  "record": "12",
  "options": [
    {"value": "2026-01-02", "label": "2026-01-02"}
  ],
  "context_hash": "..."
}
```

## Gerekli External Module Endpointleri

Mevcut:

- `get-api-user-context`
- `set-api-user-dag`
- `lookup-record-by-tc`
- `create-record-by-tc`

Yeni veri giriş modu için önerilen ek endpointler:

### `get-sync-manifest`

Aktif token/DAG için kullanıcının erişebildiği kayıtların minimal listesini döndürür.

```json
{
  "project_id": "17",
  "dag": "marmara",
  "records": [
    {"record": "1", "remote_updated_at": "2026-05-24T10:12:00Z"}
  ],
  "identity_hash_updated_at": "2026-05-24T10:12:00Z"
}
```

### `get-record-data`

Belirli kayıtların `redcap_data` şekline yakın satırlarını döndürür.

```json
{
  "project_id": "17",
  "records": [
    {
      "record": "1",
      "remote_updated_at": "2026-05-24T10:12:00Z",
      "rows": [
        {
          "project_id": "17",
          "event_id": "",
          "record": "1",
          "field_name": "hasta_ad",
          "value": "AB",
          "instance": ""
        }
      ]
    }
  ]
}
```

### `get-identity-hash-map`

Aktif token/DAG için `tc_hash -> record` eşlemesini döndürür.

```json
{
  "project_id": "17",
  "rows": [
    {
      "tc_hash": "...",
      "record": "1",
      "dag_unique_name": "marmara",
      "remote_updated_at": "2026-05-24T10:12:00Z"
    }
  ]
}
```

### `get-dynamic-query-options`

Dynamic SQL alanlarını server context'iyle çözer.

### `submit-record-changes`

İlk aşamada mevcut REDCap API import kullanılabilir. Ancak conflict kontrolünü ve server-side validation özetini tek noktadan almak için ileride external module üzerinden batch değişiklik endpoint'i daha iyi olabilir.

## Conflict Mantığı

Her kayıt için iki zaman damgası tutulur:

- `remote_updated_at`: serverdan en son bilinen kayıt değişiklik zamanı.
- `local_updated_at`: lokalde son değişiklik zamanı.

Kurallar:

- Server daha yeni, local dirty değil: kayıt yeniden çekilir.
- Server daha yeni, local dirty: conflict.
- Local dirty, server aynı: kullanıcıya gönderim önerilir.
- İki taraf da aynı: unchanged.

İlk SQLite iskeleti `compare_remote_manifest()` ile bu ayrımı yapmaya başladı.

## Geliştirme Sırası

1. SQLite şema ve store testleri.
2. External module sync client endpoint parserları.
3. İlk proje açılışında read-only sync: manifest + changed records + identity hash map.
4. Read-only kayıt tarayıcı.
5. REDCap metadata'dan form renderer.
6. Manual edit -> pending changes.
7. Submit + conflict resolver.
8. Dynamic SQL seçenek çözümleyici.

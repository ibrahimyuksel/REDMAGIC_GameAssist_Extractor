# REDMAGIC GameAssist 15.5 APK Bulut Çıkarıcı

Bu paket, 6,99 GB'lık LtiRom ROM arşivini **GitHub Actions'ın bulut sunucusunda** işler ve mevcutsa yalnızca `GameAssist15_5.apk` dosyasını çıktı olarak verir. Yerel bilgisayara ROM indirmez.

## Kaynak ve kapsam

- Cihaz: REDMAGIC Astra, NP05J / PQ84P01.
- Kaynak: https://github.com/jawadaboumehsen/LtiRom/releases/tag/global-fifteen
- ZIP: dört sıralı parça `.zip.00` ... `.zip.03` (bunlar bağımsız ZIP arşivleri değil, tek ZIP'in ardışık bayt parçalarıdır).
- ZIP SHA-256: `7b5829860343f297c5ea7d636fb39b4768a2ac3b4c184d8ad9e353d04d0ab383`.
- GameAssist tahmini sürümü: `15.5.001.2603051437`.
- ROM formatı: Android recovery ZIP (`system.transfer.list` ve `system.new.dat.br`), EROFS sistemi.

## Kurulum

1. GitHub hesabında **yeni, boş bir private repository** oluştur: `redmagic-apk-extractor`.
2. Paketteki `.github/workflows/extract_gameassist.yml` ve `scripts/restore_sdat_stream.py` dosyalarını **aynı yolları koruyarak** repoya yükle. İstersen `tests` klasörünü de ekle.
3. GitHub'da **Actions** sekmesini aç. `Extract REDMAGIC GameAssist 15.5` iş akışını seç.
4. **Run workflow** -> **Run workflow** ile başlat.
5. Başarılıysa ilgili işlem sayfasının **Artifacts** kısmında `REDMAGIC-GameAssist15_5-APK` artefaktını indir.
6. ZIP içinde `GameAssist15_5.apk`, `SHA256SUMS.txt`, `EXTRACTION_INFO.txt` bulunur.

## Teknik akış

1. Dört ayrı ROM parçasını indirip SHA-256 ile doğrular.
2. Parçaları tek ZIP'e ekler (ayrı bir birleştirme kopyası oluşturmaz).
3. `system.transfer.list` bilgisiyle Brotli sistem verisini akış olarak `system.img` dosyasına yazar.
4. EROFS dosya sistemini salt okunur bağlar.
5. Beklenen yoldaki GameAssist APK'sını kopyalar; APK ZIP yapısını kontrol eder.
6. Yalnızca küçük APK ve kimlik bilgilerini `upload-artifact` ile sunar.

## Sınırlamalar

- **Bu iş akışı henüz gerçek 7 GB ROM üzerinde çalıştırılmadı.** Kaynak ROM'un APK'yi gerçekten içerdiği ayrıca doğrulanmalıdır.
- Sistem imajının EROFS olması repo yapılandırmasından çıkarıldı; sürüm değişmişse mount işlemi başarısız olabilir.
- Standard GitHub Linux runner'ı yaklaşık **14 GB SSD** sunar. İş akışı kullanılmayan SDK'ları silerek alan açar. Disk limiti veya internet sorunu nedeniyle iş başarısız olabilir.
- GitHub Actions kullanımı hesap/plan limitlerine tabidir. Özel repo Actions dakikalarını tüketebilir.
- ROM üçüncü taraf geliştirici tarafından yayımlanmış özel ROM'dur. OEM GameAssist'in orijinal sürümü ve imzası mutlaka ayrıca doğrulanmalıdır.
- İçerik yalnızca kişisel teknik inceleme amacıyla çıkarılmalıdır. Başka cihazlara kurmayın; Samsung'da çalışacağı varsayılmamalıdır.
- Sadece APK bulunması Hunt GPU algoritmasının APK içinde olduğunu kanıtlamaz. DEX çağrıları ve ilgili grafik sistemi ayrıca incelenmelidir.

## Sorun olursa

GitHub Actions'da kırmızı olan adımı ve son 20-30 satırlık hata çıktısını paylaş. Özellikle mount veya kaynak dosya bulunamadı hataları ayrıca değerlendirilmelidir.

## Kaynaklar

- https://github.com/jawadaboumehsen/LtiRom/blob/main/GAMEASSIST_PLUGIN_FRAMEWORK.md
- https://github.com/jawadaboumehsen/LtiRom/blob/main/scripts/internal/build_flashable_zip.sh
- https://github.com/xpirt/sdat2img

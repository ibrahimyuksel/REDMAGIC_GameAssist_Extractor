# ROM Dosya Gezgini v2 — Türkçe Kullanım

GitHub üzerinde **Actions > ROM Dosya Gezgini v2 - Seçmeli Dosya Çıkarma > Run workflow** yolunu açın.
**Run workflow** düğmesi GitHub'ın kendi arayüzüne aittir; bu düğmenin İngilizce olması GitHub dil ayarına bağlıdır. Açılan işlem formumuz Türkçedir.

## Formdaki alanlar

1. **rom_baglantisi** — ROM'un doğrudan HTTPS indirme bağlantısı. ZIP, parçalı ZIP, TAR, TAR.GZ veya desteklenen ham sistem imajları. İndirme GitHub bulut sunucusuna yapılır; bilgisayarınıza büyük ROM indirilmez.
2. **aranacak_dosyalar** — Çıkarmak istediğiniz dosya adları. Örnek: `GameAssist15_5.apk`, `*.apk` veya `GameAssist*.apk,libgame*.so`. Birden çok arama virgülle ayrılır.
3. **islem_turu** — **Dosyaları çıkar** seçilen dosyaları getirir. **Yalnızca listele** ise `FILE_LIST.csv` hazırlar; tüm içerik listesi için aranacak dosyalar alanını boş bırakabilirsiniz.
4. **zip_parca_sayisi** — Normal ZIP için `1`. `.zip.00` ile `.zip.03` arasındaki dört parçalı dosya için `4`. Bağlantı olarak ilk parça veya temel `.zip` adresi kullanılır.
5. **taranacak_bolumler** — Varsayılan `system`. `all` tüm bölümleri, `none` sadece dış arşivi tarar. İstenen alt küme de yazılabilir: `system,system_ext,product,vendor,odm`.
6. **rom_sha256** — ROM'un SHA-256 sağlama toplamı varsa girin; isteğe bağlı.
7. **azami_dosya_sayisi** — En fazla kaç dosya çıkarılacağı; varsayılan `20`, üst sınır `30`.

**Run workflow** ile işlemi başlatın. İşlem sayfasındaki **Artifacts > ROM-Explorer-v2-Sonuclar** bağlantısından sonucu indirin. Sonuç ZIP'i `REPORT.json`, `FILE_LIST.csv` ve eşleşen dosyaların bulunduğu `selected/` dizinini içerir. İşlem hata verse bile mümkünse rapor yüklenir.

## Desteklenen kaynaklar

- Tek ZIP, art arda gelen `.zip.00`, `.zip.01` vb. parçalı ZIP; TAR, TAR.GZ/TGZ.
- Android tam blok OTA: `system.transfer.list` + `system.new.dat.br` (veya diğer seçilen bölümler), EROFS veya ext4 salt-okunur bağlanabiliyorsa.
- ZIP içerisindeki tam `system.img` ve desteklenen diğer `partition.img` imajları; bağlanabilir ham `.img` / `.erofs` dosyaları.

**Henüz desteklenmeyenler:** `payload.bin`, artımlı OTA, Android sparse imajları, şifreli arşivler, üreticiye özel kaplar ve web oturumu gerektiren indirme bağlantıları.

**Sınırlar:** Kaynak en fazla 14 GiB, tek çıkarılan dosya en fazla 500 MiB, toplam çıktı en fazla 750 MiB, bir işlemde en fazla 30 çıkarılan dosya ve en fazla 200.000 envanter satırı. GitHub Actions disk, süre ve kullanım kotaları da geçerlidir.

**Örnek:** LtiRom ROM'un doğrudan `.zip.00` dosya bağlantısı, `zip_parca_sayisi=4`, `aranacak_dosyalar=GameAssist15_5.apk`, `taranacak_bolumler=system`, `islem_turu=Dosyaları çıkar`.

**Güvenlik:** Yalnızca güvendiğiniz HTTPS bağlantılarını kullanın. GitHub Actions giriş alanlarında parola, oturum çerezi veya özel erişim anahtarı bulundurmayın.

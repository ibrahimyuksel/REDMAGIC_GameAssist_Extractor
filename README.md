# REDMAGIC ROM Dosya Gezgini ve Secmeli Cikarici

Bu GitHub Actions is akisi, yaklasik **6,99 GB REDMAGIC Astra LtiRom ROM** dosyasini **GitHub bulutunda** isler. Bilgisayara ROM indirilmez. Uc mod bulunur:

| Mod | Islev | Cikti |
| --- | --- | --- |
| `browse` (varsayilan) | `system` bolumundeki **tum normal dosyalari** listeler; anahtar kelimeyle GitHub Actions sonucunda filtreli onizleme | `REDMAGIC-ROM-File-Index` (aranabilir HTML + JSON + CSV + Markdown) |
| `extract` | `selected_paths` alanindaki dosyalari ad veya glob kalibiyla cikarir | `REDMAGIC-Selected-Files` (dosyalar ve SHA-256 listesi) |
| `gameassist` | Daha once **basariyla test edilmis** GameAssist15_5.apk cikarimini aynen yapar | `REDMAGIC-GameAssist15_5-APK` |

## Kullanim (bilgisayara 7 GB indirmeden)

1. [Actions > Extract REDMAGIC GameAssist 15.5](../../actions/workflows/extract_gameassist.yml) sayfasini ac.
2. **Run workflow** tusuna bas; `mode = browse` olarak birak. `search` icine ornegin `GameAssist,GameSpace,Hunt` gir (virgulle ayrilan kelimelerden herhangi biri eslesir).
3. Islem tamamlaninca ilgili calistirma sayfasindaki **Summary** altinda dosya adlari ve byte boyutlari gorunur (en fazla ilk 100 eslesme).
4. Tum dosyalar icin **Artifacts > REDMAGIC-ROM-File-Index** arsivini indir. Icinde `rom-file-browser.html` bulunur; tarayicida acip filtrele, dosyalari sec, **Secili yollari kopyala** dugmesine bas. Bu katalog kucuktur, 7 GB'lik ROM degildir.
5. **Run workflow** ekranina don, `mode = extract` sec ve kopyaladigin yolları `selected_paths` alanina yapistir.
6. Yeni calistirmanin **Artifacts > REDMAGIC-Selected-Files** arsivinde sadece sectigin dosyalar, `SHA256SUMS.txt` ve `selected-files.json` bulunur.

### Ornek `selected_paths`

Tek dosya:

```text
app/GameAssist15_5/GameAssist15_5.apk
```

Birden cok dosya veya kalip (virgulle ayrilir):

```text
app/GameAssist15_5/GameAssist15_5.apk, *hunt*.so, *GameSpace*.apk
```

Kalip eslesmeleri **buyuk/kucuk harfe duyarsizdir**. Kalip klasor adi icermiyorsa tum klasorlerdeki dosya adlari taranir. Girilen her kalibin en az bir dosyayla eslesmesi gerekir. Seçim toplamda **30 dosya / 768 MiB** ile sinirlidir; fazla secim hata verir ve dosya cikarilmaz.

### Eski GameAssist akisi

`mode = gameassist` secilirse daha onceki tek APK cikarma akisi kullanilir. 9 Ekim 2026'daki [basarili run](../../actions/runs/37957281779) icin `GameAssist15_5.apk` yaklasik 94 MiB olmustur. Dosyanin diger cihazlarda calisacagi anlamina gelmez.

## Kaynak ve dogrulama

- Cihaz: **REDMAGIC Astra**, `NP05J / PQ84P01`.
- Kaynak: <https://github.com/jawadaboumehsen/LtiRom/releases/tag/global-fifteen>
- ROM 4 ardarda gelen parca: `.zip.00`, `.zip.01`, `.zip.02`, `.zip.03` (ayri ayri ZIP degildir).
- ZIP SHA-256: `7b5829860343f297c5ea7d636fb39b4768a2ac3b4c184d8ad9e353d04d0ab383`.
- `system.transfer.list` + `system.new.dat.br` akisa acilir; `system.img` olusturulur, EROFS salt okunur baglanir.
- `GameAssist` beklenen surum: `15.5.001.2603051437` (**APK paket metadata ile bagimsiz teyit edilmedi**).

## Sinirlamalar

- **Yalnizca `system` bolumu** taranir; `product`, `vendor`, `odm`, `system_ext` bolumleri henuz ekli degildir. ROM'un ZIP iceriginde bulunsa bile diger bolum dosyalarini listelemez.
- `browse` ve `extract` farkli Action calistirmalaridir. Her calistirma ROM'u **bulutta yeniden indirir**. Bilgisayara indirilen tek sey secilen kucuk sonuc arsividir. Bakinmak icin indirilen HTML indeks dosyasi ROM degildir.
- GitHub Actions zaman/disk/kota sinirlari, upstream ROM baglantilari ve 7 gunluk artifact suresi gecerlidir.
- Orijinal `gameassist` modu gercek ROM'da basarili olmustur. Yeni `browse`/`extract` modlarinin mantigi kucuk test dosya sisteminde dogrulanmistir; gercek ROM uzerinde ayrica calistirilmalari gerekir.
- OEM lisanslari ve sistem bagimliliklari nedeniyle dosyalarin baska bir telefonda yuklenmesi veya REDMAGIC Hunt modunun diger cihazda calismasi garanti degildir.

## Gelistirme/test (ROM indirmeden)

```bash
python3 tests/test_restore_sdat_stream.py
python3 -m unittest discover -s tests -p 'test_rom_browser.py' -v
```

## Teknik kaynaklar

- <https://github.com/jawadaboumehsen/LtiRom/blob/main/GAMEASSIST_PLUGIN_FRAMEWORK.md>
- <https://github.com/xpirt/sdat2img>
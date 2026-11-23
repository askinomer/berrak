# Berrak

**Disleksi ve DEHB için Türkçe okuma asistanı.**

Kullanıcı bir konu yazar. Berrak internette Türkçe kaynakları arar, bilgiyi yapay zekâ ile
sadeleştirir ve okunması kolay bir sayfa olarak sunar. Kendi metnini yapıştırıp sadeleştirmek de mümkün.

Proje, LangFlow hackathon'undaki [ReadAid](https://lablab.ai/ai-hackathons/langflow-hackathon/alpha/readaid-ai-dyslexia-and-adhd-readability-content)
fikrinden ilham alır ve onu Türkçe için yeniden tasarlar. Tamamen **ücretsiz** servislerle çalışır.

---

## Özellikler

| Özellik | Açıklama |
|---|---|
| Türkçe arama | Tavily (ücretsiz plan) veya anahtar gerektirmeyen DuckDuckGo |
| Sadeleştirme | Gemini ücretsiz katmanı, disleksi/DEHB kurallarına göre yazılmış Türkçe sistem prompt'u |
| 3 okuma seviyesi | İlkokul (≤8 kelime/cümle), Ortaokul (≤12), Lise/Yetişkin (≤15) |
| Okunabilirlik ölçümü | Türkçe için geliştirilmiş **Ateşman formülü**, sadeleştirme öncesi/sonrası karşılaştırma |
| Heceleme modu | Uzun kelimelerin heceleri iki renkle gösterilir (Türkçe hece kurallarıyla) |
| Yazı tipleri | Lexend, Atkinson Hyperlegible, OpenDyslexic, Verdana. Türkçe karakter desteği test edildi, sayfaya gömülü |
| Görünüm ayarları | Yazı boyutu, satır aralığı, harf aralığı, 5 renk teması (krem, açık mavi, açık yeşil, gri-beyaz, koyu) |
| DEHB desteği | "Kısaca" özeti, bölüm bölüm odak modu, ilerleme çubuğu, okuma süresi, "Okudum" işaretleri, okuma cetveli |
| Sesli okuma | Tarayıcının Türkçe sesiyle; okunan paragraf vurgulanır |
| Doğruluk | Her bilgi kaynağa bağlanır ([1], [2]), kaynaklar sayfanın sonunda listelenir |
| İndirme | Sonuç tek bir HTML dosyası olarak indirilebilir, internetsiz açılır |
| Demo modu | API anahtarı olmadan hazır örnek içerik (sunum için yedek) |

## Nasıl çalışır?

```
Kullanıcı konusu
      │
      ▼
[İsteğe bağlı] Gemini: konuyu 3 arama sorgusuna böler  ("Kapsamlı arama")
      │
      ▼
Tavily / DuckDuckGo: Türkçe kaynakları bulur, metinlerini alır
      │
      ▼
Gemini: kurallara göre sadeleştirir → yapılandırılmış JSON
        (başlık, kısaca, bölümler, sözlük, akılda kalsın)
      │
      ▼
Ateşman skoru hesaplanır  →  HTML sayfası üretilir  →  Streamlit'te gösterilir
```

ReadAid'de model doğrudan HTML yazıyordu. Berrak'ta model **JSON** üretir, HTML'i program oluşturur.
Bunun üç faydası var: görünüm her seferinde tutarlı olur, kullanıcı ayarları yeni bir yapay zekâ çağrısı
olmadan değişir ve model çıktısı güvenli şekilde işlenir (zararlı HTML sayfaya giremez).

## Kurulum

Python 3.10 veya üstü gerekir.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Tarayıcıda `http://localhost:8501` açılır.

### Ücretsiz API anahtarları

1. **Gemini (zorunlu):** <https://aistudio.google.com/apikey> adresinden Google hesabıyla anahtar al. Kredi kartı gerekmez.
2. **Tavily (isteğe bağlı):** <https://app.tavily.com> adresinden kayıt ol. Ayda 1.000 ücretsiz arama verir.
   Boş bırakırsan DuckDuckGo kullanılır (anahtar gerekmez ama sonuçlar daha kısa olur).

Anahtarları uygulamanın kenar çubuğuna yazabilir veya `.streamlit/secrets.toml.example` dosyasını
`secrets.toml` olarak kopyalayıp içine kaydedebilirsin.

### Kota ipuçları
- Aynı konu 24 saat boyunca önbellekten gelir, tekrar kredi harcamaz.
- "Kapsamlı arama" açıkken bir konu 3 Tavily kredisi harcar, kapalıyken 1.
- Gemini bir modelde kota hatası verirse sıradaki modele otomatik geçilir. Model listesi kenar çubuğundaki **Gelişmiş** bölümünden değiştirilebilir.

## Canlı test

Gerçek servislerle 5 konu ve 1 yapıştırılmış metin denemek için:

```bash
python canli_test.py
```

Kurulumu da yapan tek komut (macOS ve Linux): `bash canli_test_calistir.sh`. Betik Python 3.10+ bulur, proje
klasöründe bir sanal ortam (`.venv`) kurar, anahtar kayıtlı değilse sorar ve `.streamlit/secrets.toml`'a kaydeder,
sonra testi çalıştırır.

Betik ayrıca bir **seviye deneyi** yapar: "Fotosentez nedir?" konusunun aynı kaynaklarını üç okuma seviyesinde
ayrı ayrı sadeleştirir. Kaynaklar sabit tutulduğu için fark yalnızca seviyeden gelir. Toplam 8 deneme yapılır.

Betik anahtarları ortam değişkenlerinden (`GEMINI_API_KEY`, `TAVILY_API_KEY`) veya `.streamlit/secrets.toml`
dosyasından okur. Sonuçlar `canli_test_sonuclari/` klasörüne yazılır:

- `…-sonuclar.json`: her deneme için süre, kullanılan model, kaynaklar ve şu ölçümler:
  - sadeleştirme öncesi ve sonrası **Ateşman** puanı ile ortalama cümle uzunluğu
    (kaynak metindeki menü ve başlık gibi kısa satırlar ölçüme katılmaz)
  - **kural uyumu:** seviye sınırını aşan cümleler, 3 cümleden uzun paragraflar, bölüm sayısı
  - **kaynak gösterme:** [1], [2] gibi kaynak numarası taşıyan metin oranı, var olmayan kaynağa verilen numaralar
  - **sayı kontrolü:** çıktıdaki 2+ basamaklı sayıların (yıl, yüzde vb.) kaynak metinlerde geçip geçmediği
- `…-konu-seviye.html`: üretilen sayfaların kendisi. İnternetsiz açılır; sunumda bağlantı koparsa yedek olarak kullanılabilir.
- `…-sonuclar.zip`: yukarıdakilerin hepsi tek dosyada.

Anahtarlar sonuç dosyalarına yazılmaz. Tüm test yaklaşık 3 dakika sürer ve ücretsiz kotanın küçük bir kısmını kullanır
(Tavily'de yaklaşık 8 kredi).

## İnternette yayınlama (Streamlit Community Cloud, ücretsiz)

1. Projeyi GitHub'da bir repoya yükle. `secrets.toml` dosyası `.gitignore` sayesinde yüklenmez.
2. <https://share.streamlit.io> adresine GitHub hesabınla gir, **Create app** de, repoyu ve `app.py` dosyasını seç.
3. **Advanced settings → Secrets** alanına anahtarları yaz:
   ```toml
   GEMINI_API_KEY = "…"
   TAVILY_API_KEY = "…"
   ```
4. **Deploy** de. Birkaç dakika sonra `https://….streamlit.app` adresinde açılır.

Kayıtlı anahtarlar sunucuda kalır; ziyaretçilerin tarayıcısına gönderilmez. Yine de bağlantıyı herkese açık
paylaşırsan ziyaretçiler senin ücretsiz kotanı kullanır. Bu yüzden bağlantıyı sadece hocanla ve sınıfla paylaş.

## Proje yapısı

```
app.py                  Streamlit arayüzü
canli_test.py           Gerçek servislerle uçtan uca deneme betiği
berrak/
  search.py             Tavily + DuckDuckGo araması
  prompts.py            Türkçe sadeleştirme kuralları ve seviye ayarları
  llm.py                Gemini istemcisi, JSON şeması, model yedekleme
  readability.py        Heceleme, Ateşman formülü, cümle analizi
  render.py             Erişilebilir HTML sayfası, temalar, yazı tipleri
  pipeline.py           Arama → sadeleştirme → ölçüm akışı
  evaluation.py         Kural uyumu, kaynak gösterme ve sayı kontrolü ölçümleri
  demo.py               Anahtarsız demo içeriği
  assets/fonts/         Gömülü yazı tipleri (OFL lisanslı)
tests/test_berrak.py    Modül testleri (heceleme, Ateşman, model yedekleme, HTML güvenliği, SDK istekleri)
tests/test_app.py       Arayüz ve canlı test betiği testleri
```

Testleri çalıştırmak için: `pip install pytest && python -m pytest`

Testler internete çıkmaz. Gemini ve Tavily isteklerinin doğru biçimde oluşturulduğu, gerçek SDK'lar
kullanılarak ama HTTP katmanı sahte bir sunucuyla değiştirilerek denenir.

## Sadeleştirme kuralları (özet)

Tam liste `berrak/prompts.py` dosyasında. Kaynaklar: British Dyslexia Association *Dyslexia Style Guide*,
W3C *Making Content Usable for People with Cognitive and Learning Disabilities*, sade dil ilkeleri.

- Bir cümlede tek fikir, seviyeye göre en fazla 8 / 12 / 15 kelime
- Etken çatı ("yapılmaktadır" yerine "yapılır")
- **Türkçeye özgü:** uzun ek zincirlerini ve "-dığı için", "-masına rağmen" gibi iç içe yan cümleleri kırmak
- Ağır ve eski kelimeleri sadeleştirmek, yabancı terimleri açıklamak
- Kalın vurgu (italik, altı çizili, büyük harf yok)
- Önemli bilgi en başta, kısa bölümler, en fazla 3 cümlelik paragraflar
- Sadece kaynaktaki bilgiyi kullanmak, sayı ve tarihleri korumak

## Okunabilirlik ölçümü

Ateşman (1997) formülü: `198,825 − 40,175 × (hece/kelime) − 2,610 × (kelime/cümle)`

| Puan | Zorluk |
|---|---|
| 90–100 | Çok kolay |
| 70–89 | Kolay |
| 50–69 | Orta güçlükte |
| 30–49 | Zor |
| 0–29 | Çok zor |

Türkçede hece sayısı ünlü sayısına eşit olduğu için formül otomatik ve güvenilir şekilde hesaplanabilir.

## Sınırlamalar

- Yapay zekâ hata yapabilir. Bu yüzden her bilgi kaynağa bağlanır ve kaynaklar gösterilir.
- Heceleme kuralı Türkçe kelimelerde doğrudur. Bazı yabancı kökenli kelimelerde TDK yazımından farklı bölebilir.
- Sesli okuma kalitesi tarayıcıya bağlıdır. Türkçe ses en iyi Chrome ve Edge'de çalışır.
- Ücretsiz kotalar ödev, demo ve küçük kullanıcı testleri için yeterlidir; geniş çaplı yayın için yetmez.
- **Berrak tanı koymaz.** Yalnızca okumayı kolaylaştırır.

## Geliştirme fikirleri

- Gerçek kullanıcılarla okuma süresi ve anlama testi
- PDF yükleyip sadeleştirme
- Tarayıcı eklentisi: herhangi bir web sayfasını tek tıkla sadeleştirme
- Kullanıcının zorlandığı konulara göre kişisel okuma önerileri

## Lisans

Kod: MIT. Yazı tipleri: SIL Open Font License (lisans dosyaları `berrak/assets/fonts/` içinde).

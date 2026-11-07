<p align="center">
  <img src="docs/logo.svg" width="72" alt="">
</p>

<h1 align="center">Kondis</h1>

<p align="center">
  Kişisel antrenörler ve butik salonlar için açık kaynak antrenör paneli.<br>
  Programı sen yazarsın, öğrencin uygulama indirmeden linkten açıp setlerini girer.
</p>

<p align="center">
  <a href="https://github.com/harunnkcnn/kondis/actions/workflows/ci.yml"><img src="https://github.com/harunnkcnn/kondis/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/license-AGPL--3.0-2f7bff" alt="AGPL-3.0">
  <img src="https://img.shields.io/badge/Django-6.1-0f1726" alt="Django 6.1">
  <img src="https://img.shields.io/badge/dil-TR%20%7C%20EN-0f1726" alt="TR | EN">
</p>

<p align="center"><b>Türkçe</b> · <a href="README.en.md">English</a></p>

---

![Antrenör paneli: bugün kim çalıştı, kimin paketi bitiyor](docs/screenshots/dashboard.png)

## Neden Kondis?

Türkiye'de PT'lerin çoğu öğrenci programını hâlâ WhatsApp'tan fotoğraf, Excel ve not defteriyle yürütüyor. Paket ne zaman bitiyor, öğrenci bu hafta geldi mi, geçen hafta squat'ta kaç kaldırdı... hepsi akılda tutulmaya çalışılıyor.

Kondis bunu tek bir panelde topluyor:

- **Öğrenciye uygulama indirtmezsin.** Her öğrencinin kendine özel, istediğin an yenileyebileceğin bir linki var. WhatsApp'tan gönderirsin, telefonda açar, setini girer.
- **Paket ve seans takibi.** "12 PT seansı", "3 aylık üyelik" gibi paketler; biten, bitmek üzere olan ve seansı kalmayanlar ana ekranda.
- **Kim ortadan kayboldu?** Bir haftadır antrenman girmeyen öğrenciler tek tıkla WhatsApp'la listede.
- **Veri senin.** Kendi sunucunda, kendi bilgisayarında ya da ucuz bir VPS'te çalışır. Abonelik yok, reklam yok, izleme yok.

## Özellikler

**Antrenör tarafı**
- Bugün ekranı: bugün antrenman yapanlar, yenilenecek paketler, bir haftadır sessiz olanlar
- Öğrenci kartı: hedef, notlar (sakatlık vb.), kilo grafiği, son antrenmanlar, en iyi kaldırışlar (tahmini 1RM, Epley)
- Program yazma: günlere bölünmüş program, haftanın gününe sabitleme ya da sıralı rotasyon (A, B, C, A...)
- Hazır şablonlar: Full Body 3x, Upper/Lower, Push/Pull/Legs; yüklenir, sonra istediğin gibi düzenlenir
- Türkçe ve İngilizce isimli 55 egzersizlik kütüphane + kendi egzersizlerin
- Paketler: tarih aralığı, seans sayısı (ya da sınırsız), ücret; "Seans düş" ile tek tıkla seans kullanımı

**Öğrenci tarafı (telefon)**
- Bugünün antrenmanını kendisi önerir (haftanın gününe ya da son yapılan güne göre)
- Her egzersizde hedef, dinlenme süresi, antrenörün ipucu ve **geçen seferki setler**
- Ağırlık ve tekrar alanları son değerlerle dolu gelir; setler sayfa yenilenmeden eklenir
- Set numarası, yüke göre renklenen bir plaka diski olarak görünür (100+ kırmızı, 60+ mavi, 40+ sarı, 20+ yeşil)
- Antrenman sonunda kilo ve antrenöre not; yeni rekorlar özet ekranında

| Antrenman | Program | Öğrenci kartı |
|---|---|---|
| ![](docs/screenshots/portal-workout.png) | ![](docs/screenshots/program.png) | ![](docs/screenshots/client.png) |

## Hızlı başlangıç

### Docker ile (önerilen)

```bash
git clone https://github.com/harunnkcnn/kondis.git
cd kondis
cp .env.example .env          # KONDIS_SECRET_KEY ve alan adını düzenle
docker compose up -d --build
docker compose exec web python manage.py createsuperuser
```

`http://localhost:8000` adresini aç ve oluşturduğun kullanıcıyla giriş yap.

### Docker'sız (geliştirme)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
export KONDIS_DEBUG=1
python manage.py migrate
python manage.py seed_demo          # isteğe bağlı: örnek antrenör ve 5 öğrenci
python manage.py runserver
```

Demo girişi: `demo` / `kondis-demo-2026`

## Yayına alma

| Değişken | Ne işe yarar | Varsayılan |
|---|---|---|
| `KONDIS_SECRET_KEY` | Oturum imzalama anahtarı. Uzun ve rastgele olsun. | *(zorunlu)* |
| `KONDIS_ALLOWED_HOSTS` | Virgülle ayrılmış alan adları | `localhost,127.0.0.1` |
| `KONDIS_CSRF_TRUSTED_ORIGINS` | `https://` ile tam adres | *(boş)* |
| `KONDIS_BASE_URL` | Öğrenci linklerinde kullanılan adres | istek adresi |
| `KONDIS_DATABASE_URL` | `sqlite:///...` ya da `postgres://...` | `data/kondis.sqlite3` |
| `KONDIS_LANGUAGE` | Varsayılan dil (`tr` / `en`) | `tr` |
| `KONDIS_TIME_ZONE` | Saat dilimi | `Europe/Istanbul` |
| `KONDIS_SECURE_COOKIES` | HTTPS'te `1` | `1` |
| `KONDIS_HSTS_SECONDS` | HSTS süresi (HTTPS'ten eminsen) | `0` |

Öğrenci linkleri ve oturumlar için **HTTPS kullan**. Caddy, Nginx ya da Cloudflare Tunnel önüne konabilir. Tüm veri tek bir klasörde durur (`./data`); yedeklemek için o klasörü kopyalamak yeter. PostgreSQL için `KONDIS_DATABASE_URL` yeterli.

## Mimari

```
coaching/
  models.py      Öğrenci, Paket, Egzersiz, Program > Gün > Hareket, Antrenman > Set
  services.py    HTTP'den bağımsız iş mantığı: 1RM, rekorlar, ana ekran, şablonlar
  views.py       Antrenör paneli (her sorgu giriş yapan antrenöre göre filtrelenir)
  portal.py      Öğrenci ekranı (link anahtarıyla erişim)
templates/       Django şablonları + htmx
locale/tr/       Türkçe çeviriler
```

- **Django 6.1 + htmx**: ayrı bir frontend build adımı yok, JavaScript bağımlılığı tek dosya.
- **SQLite varsayılan**, PostgreSQL destekli. Tek antrenör ya da küçük bir salon için SQLite fazlasıyla yeterli.
- Arayüz tamamen el yazımı CSS; koyu tema, telefon öncelikli, klavyeyle gezilebilir.

## Güvenlik

- Öğrenci linki 192 bit rastgele bir anahtar içerir; antrenör istediği an yeni link üretip eskisini geçersiz kılabilir.
- Öğrenci sayfaları `noindex`, `no-store` ve sınırlı `Referrer-Policy` ile sunulur.
- Her antrenör yalnızca kendi öğrencilerini görür; öğrenci yalnızca kendi antrenmanına set ekleyebilir. Bu kurallar testlerle korunur.
- Tüm formlarda CSRF koruması açık, yayında güvenli çerezler varsayılan.

Bir açık bulursan lütfen herkese açık issue yerine [SECURITY.md](SECURITY.md)'deki adrese yaz.

## Sürümler

**Community** (bu repo, AGPL-3.0): tek antrenör, sınırsız öğrenci, yukarıdaki tüm özellikler.

**Pro** (lisanslı, ayrı paket): birden fazla antrenör ve salon sahibi görünümü, ödeme ve borç takibi, WhatsApp hatırlatmaları, programı logolu PDF olarak paylaşma, ölçü ve fotoğraf takibi. Kurulum aynı; Pro paketi lisans anahtarıyla eklenir. Bilgi için GitHub üzerinden iletişime geç.

## Katkı

Hata bildirimleri ve pull request'ler açık. Başlamadan önce:

```bash
KONDIS_DEBUG=1 python manage.py test
```

Yeni bir metin eklediysen `locale/tr/LC_MESSAGES/django.po` dosyasına Türkçesini ekle (`python manage.py makemessages -l tr`, GNU gettext gerekir).

## Lisans

[AGPL-3.0](LICENSE). Kendi sunucunda kullanabilir, değiştirebilir ve paylaşabilirsin. Değiştirilmiş bir sürümü başkalarına ağ üzerinden hizmet olarak sunarsan, o sürümün kaynak kodunu da aynı lisansla açman gerekir.

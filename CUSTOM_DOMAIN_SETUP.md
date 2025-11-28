# 🌐 Custom Domain Kurulumu - Cumhuriyet Kütüphanesi

Railway'de custom domain ekleyerek web adresinizi "cumhuriyet-kutuphanesi" gibi güzel bir link yapabilirsiniz.

## 📋 Adımlar

### 1. Railway Dashboard'dan Custom Domain Ekleme

1. **Railway Dashboard'a gidin:** https://railway.app
2. **fantastic-encouragement** projesine gidin
3. **web** service'ine tıklayın
4. **Settings** → **Networking** bölümüne gidin
5. **Custom Domain** bölümünde **Add Domain** butonuna tıklayın

### 2. Domain Seçenekleri

#### Seçenek A: Ücretsiz Subdomain (Önerilen)
Railway ücretsiz subdomain sağlar:
- `cumhuriyet-kutuphanesi.up.railway.app`
- `cal-kutuphane.up.railway.app`
- `kutuphane-cal.up.railway.app`

#### Seçenek B: Kendi Domain'iniz (Ücretli)
Kendi domain'iniz varsa (örn: `cumhuriyetkutuphanesi.com`):
1. Domain'inizin DNS ayarlarına gidin
2. Railway'in verdiği CNAME kaydını ekleyin
3. Railway'de domain'i doğrulayın

### 3. Railway CLI ile Domain Ekleme (Alternatif)

```bash
# Railway'de domain eklemek için (eğer CLI destekliyorsa)
railway domain add cumhuriyet-kutuphanesi.up.railway.app
```

## 🔧 Mevcut Domain

**Şu anki domain:**
- `web-production-8d80.up.railway.app`

**Önerilen yeni domain:**
- `cumhuriyet-kutuphanesi.up.railway.app` (Railway dashboard'dan eklenebilir)

## 📝 Notlar

- Railway'in otomatik domain'i değiştirilemez
- Custom domain eklemek için Railway dashboard kullanılmalı
- Ücretsiz plan için Railway subdomain kullanılabilir
- Kendi domain'iniz için DNS ayarları gerekir

## 🎯 Sonuç

Custom domain eklendikten sonra:
- ✅ Güzel bir URL: `cumhuriyet-kutuphanesi.up.railway.app`
- ✅ Site içeriğinde "Cumhuriyet Anadolu Lisesi Kütüphanesi" adı zaten kullanılıyor
- ✅ Manifest.json'da "Cumhuriyet Anadolu Lisesi Kütüphane Sistemi" adı var


# 🌐 Domain Kurulum Rehberi - Cumhuriyet Kütüphanesi

## ✅ Yapılan Güncellemeler

1. **Site Başlığı Güncellendi:**
   - Tarayıcı sekmesinde: "Cumhuriyet Anadolu Lisesi Kütüphanesi"
   - Manifest.json: "Cumhuriyet Kütüphanesi" (kısa ad)

2. **Mevcut Domain:**
   - `web-production-8d80.up.railway.app`

## 🎯 Custom Domain Ekleme (Railway Dashboard)

Railway'de daha güzel bir domain için:

### Adım 1: Railway Dashboard
1. https://railway.app → **fantastic-encouragement** projesi
2. **web** service → **Settings** → **Networking**

### Adım 2: Custom Domain Ekle
1. **Custom Domain** bölümünde **Add Domain** tıklayın
2. Domain adını girin (örn: `cumhuriyet-kutuphanesi`)
3. Railway otomatik olarak `.up.railway.app` ekler

### Sonuç:
- ✅ Yeni domain: `cumhuriyet-kutuphanesi.up.railway.app`
- ✅ Eski domain de çalışmaya devam eder

## 📝 Alternatif: Kendi Domain'iniz

Kendi domain'iniz varsa (örn: `cumhuriyetkutuphanesi.com`):

1. **Domain sağlayıcınızın DNS ayarlarına gidin**
2. **CNAME kaydı ekleyin:**
   - Name: `@` veya `www`
   - Value: Railway'in verdiği CNAME değeri
3. **Railway'de domain'i doğrulayın**

## 🔗 Mevcut Durum

- **Site Adı:** Cumhuriyet Anadolu Lisesi Kütüphanesi ✅
- **Domain:** `web-production-8d80.up.railway.app`
- **Site Başlığı:** Tarayıcı sekmesinde "Cumhuriyet Anadolu Lisesi Kütüphanesi" görünüyor ✅

## 💡 Öneriler

1. **Railway Dashboard'dan custom domain ekleyin** (en kolay)
2. **Domain adı önerileri:**
   - `cumhuriyet-kutuphanesi.up.railway.app`
   - `cal-kutuphane.up.railway.app`
   - `kutuphane-cal.up.railway.app`

## ✅ Tamamlanan

- [x] Site başlığı güncellendi
- [x] Manifest.json güncellendi
- [x] Domain kurulum rehberi eklendi
- [ ] Custom domain eklendi (Railway dashboard'dan yapılacak)


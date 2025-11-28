# 🌐 Railway Domain Değiştirme - Cumhuriyet Kütüphanesi

## 🎯 Hedef
`web-production-8d80.up.railway.app` → `cumhuriyet-kutuphanesi.up.railway.app`

## 📋 Adımlar (Railway Dashboard)

### Yöntem 1: Service Adını Değiştir (Önerilen)

1. **Railway Dashboard'a gidin:** https://railway.app
2. **fantastic-encouragement** projesine gidin
3. **web** service'ine tıklayın
4. **Settings** sekmesine gidin
5. **Service Name** bölümünde:
   - Mevcut: `web`
   - Yeni: `cumhuriyet-kutuphanesi` yazın
   - **Save** butonuna tıklayın

6. Railway otomatik olarak yeni domain oluşturacak:
   - `cumhuriyet-kutuphanesi-production-xxxx.up.railway.app`

### Yöntem 2: Custom Domain Ekle (Alternatif)

1. **Railway Dashboard'a gidin:** https://railway.app
2. **fantastic-encouragement** projesine gidin
3. **web** service → **Settings** → **Networking**
4. **Custom Domain** bölümünde **Add Domain** tıklayın
5. Domain adını girin: `cumhuriyet-kutuphanesi`
6. Railway otomatik olarak `.up.railway.app` ekler

### Sonuç:
- ✅ Yeni domain: `cumhuriyet-kutuphanesi.up.railway.app`
- ✅ Eski domain (`web-production-8d80.up.railway.app`) bir süre daha çalışır, sonra kaldırılabilir

## ⚠️ Önemli Notlar

1. **Service adı değişikliği:**
   - Service adını değiştirmek deployment'ı yeniden başlatabilir
   - Environment variables korunur
   - Kod değişmez

2. **Domain değişikliği:**
   - Eski domain bir süre daha çalışır
   - Yeni domain aktif olana kadar eski domain'i kullanabilirsiniz
   - DNS propagation birkaç dakika sürebilir

3. **Railway CLI:**
   - Domain değiştirme CLI ile yapılamaz
   - Sadece Railway Dashboard'dan yapılabilir

## 🔧 Alternatif: Service Yeniden Adlandırma

Eğer service adını değiştirmek istemiyorsanız:

1. **Yeni bir service oluşturun:**
   - Railway Dashboard → **New Service**
   - Service adı: `cumhuriyet-kutuphanesi`
   - Aynı GitHub repo'yu bağlayın

2. **Eski service'i silin:**
   - `web` service'ini silebilirsiniz (isteğe bağlı)

## 📝 Hızlı Adımlar

1. Railway Dashboard → https://railway.app
2. Proje → fantastic-encouragement
3. Service → web
4. Settings → Service Name → `cumhuriyet-kutuphanesi`
5. Save
6. Yeni domain: `cumhuriyet-kutuphanesi-production-xxxx.up.railway.app`

## ✅ Kontrol

Domain değişikliğinden sonra:
- Yeni domain'i test edin
- Eski domain'in hala çalıştığını kontrol edin
- Environment variables'ların korunduğunu doğrulayın


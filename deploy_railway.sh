#!/bin/bash
# Railway Deployment Script
# Bu script Railway'e deploy etmek için gerekli adımları yapar

echo "🚂 Railway Deployment Başlatılıyor..."

# Railway projesi link edildi mi kontrol et
if ! railway status &>/dev/null; then
    echo "❌ Railway projesi link edilmemiş!"
    echo "Railway projesini link ediyorum..."
    railway link --project 234e220e-b72a-4d70-96a6-784726111b9e
fi

# Environment variables kontrol et
echo "📋 Environment variables kontrol ediliyor..."
railway variables | grep -q "SECRET_KEY" || railway variables --set "SECRET_KEY=e7b56f6ca6963f3c9f34f047ecacc877fa0b9b1815121aecfe53269bbd5c1975"
railway variables | grep -q "FLASK_ENV" || railway variables --set "FLASK_ENV=production"

# Deployment başlat
echo "🚀 Deployment başlatılıyor..."
railway up --detach

echo "✅ Deployment başlatıldı!"
echo "📊 Deployment durumunu kontrol etmek için: railway deployment list"
echo "📝 Logları görmek için: railway logs"


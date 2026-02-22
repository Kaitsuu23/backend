# Proxy Setup Guide

Panduan untuk setup proxy agar dapat resolusi tinggi (720p, 1080p).

## 🎯 Kenapa Perlu Proxy?

YouTube membatasi Railway IP, hanya return format 360p. Dengan proxy, kita bisa bypass restriction ini.

## 🔧 Option 1: Pakai Proxy Gratis (Tidak Reliable)

### 1. Cari Free Proxy

Website untuk cari proxy gratis:
- https://free-proxy-list.net/
- https://www.sslproxies.org/
- https://www.proxy-list.download/HTTPS

### 2. Update proxy_config.py

Edit file `backend/proxy_config.py`:

```python
FREE_PROXIES = [
    'http://123.45.67.89:8080',
    'http://98.76.54.32:3128',
    'socks5://11.22.33.44:1080',
]
```

**Note:** Free proxy sering mati, perlu update terus.

---

## 💰 Option 2: Pakai Proxy Berbayar (Recommended)

### Rekomendasi Provider:

#### 1. **Bright Data (Luminati)** - Paling Reliable
- Website: https://brightdata.com/
- Harga: ~$500/month (residential proxy)
- Trial: 7 hari gratis
- Best for: Production

#### 2. **Smartproxy**
- Website: https://smartproxy.com/
- Harga: $12.5/GB (residential)
- Trial: 3 hari money-back
- Good for: Medium traffic

#### 3. **Webshare**
- Website: https://www.webshare.io/
- Harga: $2.99/month (10 proxies)
- Free tier: 10 proxies gratis
- Good for: Testing

#### 4. **ProxyScrape**
- Website: https://proxyscrape.com/
- Harga: $5/month (premium)
- Free tier: Available
- Good for: Budget

### Setup Paid Proxy:

#### A. Via Environment Variable (Railway)

1. Di Railway dashboard → Variables
2. Tambah variable:
   ```
   PROXY_URL=http://username:password@proxy.example.com:8080
   ```
3. Reload web app

#### B. Via Code

Edit `backend/proxy_config.py`:

```python
PAID_PROXY = 'http://username:password@proxy.example.com:8080'
```

---

## 🧪 Test Proxy

### 1. Test di Local

```bash
cd backend
export PROXY_URL='http://your-proxy:port'
python main.py
```

### 2. Test Endpoint

```bash
curl "http://localhost:8000/info?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ"
```

Lihat apakah `video_formats` sekarang ada 720p, 1080p, dll.

---

## 🔄 Proxy Rotation (Advanced)

Untuk traffic tinggi, pakai multiple proxies:

Edit `proxy_config.py`:

```python
FREE_PROXIES = [
    'http://proxy1:8080',
    'http://proxy2:8080',
    'http://proxy3:8080',
]

def get_proxy():
    import random
    return random.choice(FREE_PROXIES)
```

---

## 🐛 Troubleshooting

### Proxy Timeout

Increase timeout di `proxy_config.py`:

```python
def get_ydl_proxy_opts():
    proxy = get_proxy()
    if proxy:
        return {
            'proxy': proxy,
            'socket_timeout': 60,  # Increase to 60 seconds
        }
    return {}
```

### Proxy Authentication Failed

Format proxy harus benar:
- HTTP: `http://username:password@host:port`
- SOCKS5: `socks5://username:password@host:port`

### Still Getting 360p Only

1. Cek proxy masih aktif (test di browser)
2. Coba proxy lain
3. Cek Railway logs untuk error message

---

## 💡 Tips

1. **Residential Proxy > Datacenter Proxy** - YouTube lebih susah detect
2. **Rotate Proxies** - Jangan pakai 1 proxy terus
3. **Monitor Usage** - Paid proxy biasanya limited by bandwidth
4. **Test Locally First** - Sebelum deploy, test di local dulu

---

## 🆓 Free Proxy Trial

Beberapa provider kasih trial gratis:

1. **Webshare** - 10 proxies gratis selamanya
   - Daftar: https://www.webshare.io/
   - Get proxy list
   - Add ke `FREE_PROXIES`

2. **Bright Data** - 7 hari trial
   - Daftar: https://brightdata.com/
   - Pilih residential proxy
   - Copy credentials

3. **Smartproxy** - 3 hari money-back
   - Daftar: https://smartproxy.com/
   - Pilih residential proxy
   - Test dalam 3 hari

---

## 📊 Expected Results

Setelah setup proxy dengan benar:

**Before (No Proxy):**
```json
{
  "video_formats": [
    {"resolution": "360p", "format_id": "18"}
  ]
}
```

**After (With Proxy):**
```json
{
  "video_formats": [
    {"resolution": "1080p", "format_id": "137"},
    {"resolution": "720p", "format_id": "136"},
    {"resolution": "480p", "format_id": "135"},
    {"resolution": "360p", "format_id": "18"}
  ]
}
```

---

## 🚀 Quick Start (Webshare Free)

1. Daftar di https://www.webshare.io/
2. Verify email
3. Dashboard → Proxy → Proxy List
4. Copy proxy (format: `ip:port:username:password`)
5. Convert ke format: `http://username:password@ip:port`
6. Add ke Railway Variables:
   ```
   PROXY_URL=http://username:password@ip:port
   ```
7. Reload Railway
8. Test!

---

**Good luck!** 🎉

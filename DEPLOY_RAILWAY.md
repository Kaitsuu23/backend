# Deploy ke Railway

Panduan deploy backend YouTube Downloader ke Railway.

## 🚀 Quick Start (5 menit)

### 1. Persiapan

1. Buat akun di [Railway.app](https://railway.app/)
2. Login dengan GitHub
3. Install Railway CLI (optional):
   ```bash
   npm install -g @railway/cli
   ```

### 2. Deploy via Web (Paling Mudah)

#### A. Push ke GitHub (Jika Belum)

```bash
# Di folder project
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/yt_downloader.git
git push -u origin main
```

#### B. Deploy di Railway

1. Buka [Railway.app](https://railway.app/)
2. Klik **"New Project"**
3. Pilih **"Deploy from GitHub repo"**
4. Pilih repository `yt_downloader`
5. Railway akan auto-detect Python project
6. Klik **"Deploy"**

#### C. Configure Root Directory

Karena backend ada di subfolder:

1. Di Railway dashboard, klik project Anda
2. Klik **Settings**
3. Di bagian **"Root Directory"**, isi: `backend`
4. Save

#### D. Add Environment Variables (Optional)

Di **Variables** tab, tambahkan jika perlu:
```
PORT=8000
PYTHON_VERSION=3.11
```

### 3. Deploy via CLI

```bash
# Login
railway login

# Link project
cd backend
railway init

# Deploy
railway up

# Get URL
railway domain
```

### 4. Get Backend URL

Setelah deploy selesai:

1. Di Railway dashboard, klik project
2. Klik **Settings** → **Networking**
3. Klik **Generate Domain**
4. Copy URL (contoh: `your-app.up.railway.app`)

### 5. Update Flutter Config

Edit `lib/config.dart`:

```dart
class AppConfig {
  static const String backendUrl = 'https://your-app.up.railway.app';
}
```

## 🔧 Troubleshooting

### Build Failed

**Cek:**
- Root directory sudah diset ke `backend`?
- File `requirements.txt` ada?
- File `Procfile` atau `railway.json` ada?

**Fix:**
```bash
# Pastikan semua file ada
ls backend/
# Harus ada: main.py, requirements.txt, Procfile, railway.json
```

### FFmpeg Not Found

Railway sudah include FFmpeg via `nixpacks.toml`. Jika masih error:

1. Cek file `nixpacks.toml` ada
2. Pastikan ada baris: `nixPkgs = ["python311", "ffmpeg"]`

### Port Error

Railway otomatis set `$PORT` environment variable. Pastikan di `main.py`:

```python
if __name__ == "__main__":
    import uvicorn
    import os
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
```

### YouTube Block

Sama seperti PythonAnywhere, YouTube bisa block. Solusi sudah ada di `main.py` dengan:
- User-Agent spoofing
- Player client configuration
- HTTP headers

## 💰 Pricing

**Trial:**
- $5 credit gratis untuk new account
- Cukup untuk testing ~1 bulan

**Hobby Plan:**
- $5/month
- 500 hours execution
- 8GB RAM
- 100GB bandwidth

**Pro Plan:**
- $20/month
- Unlimited execution
- Better resources

## 📊 Monitoring

Di Railway dashboard:

1. **Deployments** - Lihat deployment history
2. **Metrics** - CPU, Memory, Network usage
3. **Logs** - Real-time logs
4. **Settings** - Configuration

## 🔄 Update Code

### Via Git

```bash
# Update code
git add .
git commit -m "Update backend"
git push

# Railway auto-deploy on push
```

### Via CLI

```bash
cd backend
railway up
```

## 🌐 Custom Domain (Optional)

1. Di Railway dashboard → Settings → Networking
2. Klik **Custom Domain**
3. Masukkan domain Anda
4. Update DNS records sesuai instruksi

## 🔐 Environment Variables

Tambahkan di Railway dashboard → Variables:

```
YOUTUBE_API_KEY=your_key_here  # Optional
MAX_FILE_SIZE=500000000        # 500MB
ALLOWED_ORIGINS=*              # CORS
```

## 📝 Files Needed

```
backend/
├── main.py              # FastAPI app
├── requirements.txt     # Dependencies
├── Procfile            # Start command
├── railway.json        # Railway config
├── nixpacks.toml       # Build config (FFmpeg)
└── runtime.txt         # Python version
```

## ✅ Checklist

- [ ] Akun Railway dibuat
- [ ] Code di-push ke GitHub
- [ ] Project di-deploy di Railway
- [ ] Root directory diset ke `backend`
- [ ] Domain generated
- [ ] Backend accessible
- [ ] Flutter config updated
- [ ] Test download works

## 🆘 Support

- [Railway Docs](https://docs.railway.app/)
- [Railway Discord](https://discord.gg/railway)
- [Railway Status](https://status.railway.app/)

---

**Estimated Setup Time:** 5-10 minutes

**Difficulty:** ⭐⭐ (Easy)

**Cost:** $5 trial credit (free for ~1 month)

# 🚀 Railway.com Deployment Guide - Telegram AI Teacher Bot

## 📋 Prerequisites

1. **Railway Account**: Sign up at [railway.app](https://railway.app)
2. **GitHub Account**: (Optional but recommended)
3. **Telegram Bot Token**: From @BotFather
4. **MongoDB Database**: Railway provides this

---

## 🎯 Quick Deploy Steps

### Method 1: Using Railway CLI (Fastest)

**Step 1: Install Railway CLI**
```bash
npm i -g @railway/cli
```

**Step 2: Login to Railway**
```bash
railway login
```

**Step 3: Initialize Project**
```bash
cd railway_deploy
railway init
```

**Step 4: Add MongoDB**
```bash
railway add --database mongodb
```

**Step 5: Set Environment Variables**
```bash
railway variables set TELEGRAM_BOT_TOKEN=8114005473:AAEdWNELI89j9qOr6oHoV8Hre7BfB74qI4w
railway variables set OWNER_TELEGRAM_ID=1938325440
railway variables set OWNER_CONTACT=@Fx_squad_trader2
railway variables set EMERGENT_LLM_KEY=sk-emergent-0A85439BdEe95B25eB
railway variables set DB_NAME=telegram_study_bot
```

**Step 6: Deploy**
```bash
railway up
```

---

### Method 2: Using Railway Dashboard (Easy)

**Step 1: Create New Project**
1. Go to [railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo" or "Empty Project"

**Step 2: Add MongoDB**
1. Click "+ New" button
2. Select "Database"
3. Choose "MongoDB"
4. Railway will create MongoDB and set `MONGO_URL` automatically

**Step 3: Upload Files**

If using Empty Project:
1. Click "+ New"
2. Select "Empty Service"
3. Click on the service
4. Go to "Settings" → "Source"
5. Upload these files:
   - `telegram_bot.py`
   - `Dockerfile`
   - `requirements.txt`
   - `.env` (create from .env.example)

**Step 4: Set Environment Variables**

Go to "Variables" tab and add:

```
TELEGRAM_BOT_TOKEN=8114005473:AAEdWNELI89j9qOr6oHoV8Hre7BfB74qI4w
OWNER_TELEGRAM_ID=1938325440
OWNER_CONTACT=@Fx_squad_trader2
EMERGENT_LLM_KEY=sk-emergent-0A85439BdEe95B25eB
DB_NAME=telegram_study_bot
```

**Note**: `MONGO_URL` is automatically set by Railway when you add MongoDB.

**Step 5: Deploy**

Railway will automatically deploy when you push code or upload files.

---

### Method 3: Using GitHub (Recommended for Updates)

**Step 1: Create GitHub Repository**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin <your-repo-url>
git push -u origin main
```

**Step 2: Connect to Railway**
1. Go to Railway Dashboard
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your repository
5. Railway auto-detects Dockerfile

**Step 3: Add MongoDB**
1. Click "+ New"
2. Database → MongoDB

**Step 4: Set Environment Variables**
(Same as Method 2, Step 4)

**Step 5: Deploy**
Automatic on git push!

---

## 📁 Files Included

```
railway_deploy/
├── telegram_bot.py          # Main bot code
├── Dockerfile              # Docker configuration
├── requirements.txt        # Python dependencies  
├── .env.example           # Environment variables template
├── railway.json           # Railway configuration (JSON)
├── railway.toml           # Railway configuration (TOML)
└── README_RAILWAY_DEPLOY.md  # This file
```

---

## ⚙️ Environment Variables Explained

| Variable | Description | Example |
|----------|-------------|----------|
| `MONGO_URL` | MongoDB connection (Auto-set by Railway) | `mongodb://...` |
| `DB_NAME` | Database name | `telegram_study_bot` |
| `TELEGRAM_BOT_TOKEN` | From @BotFather | `8114005473:AAE...` |
| `OWNER_TELEGRAM_ID` | Your Telegram user ID | `1938325440` |
| `OWNER_CONTACT` | Your Telegram username | `@Fx_squad_trader2` |
| `EMERGENT_LLM_KEY` | AI key for Gemini | `sk-emergent-...` |

---

## 🔍 Verify Deployment

**Step 1: Check Logs**
```bash
railway logs
```

Or in Dashboard: Click service → "Deployments" → View logs

**Step 2: Look for Success Messages**
```
✅ Bot is now running and ready to receive messages!
Owner ID: 1938325440
```

**Step 3: Test Bot**
Send `/start` to your Telegram bot

---

## 🛠️ Troubleshooting

### Bot Not Starting?

**Check logs:**
```bash
railway logs
```

**Common Issues:**

1. **Missing Environment Variables**
   - Solution: Add all required variables in Railway dashboard

2. **MongoDB Connection Failed**
   - Solution: Make sure MongoDB plugin is added
   - Check `MONGO_URL` is set automatically

3. **Invalid Bot Token**
   - Solution: Get new token from @BotFather
   - Update `TELEGRAM_BOT_TOKEN` variable

4. **Build Failed**
   - Solution: Check Dockerfile and requirements.txt
   - View build logs in Railway

### Bot Stops After Some Time?

**Solution**: Railway free tier has limitations
- Upgrade to Hobby plan ($5/month)
- Or use Railway credits

---

## 💰 Railway Pricing

**Free Tier:**
- $5 free credits/month
- Good for testing
- May sleep after inactivity

**Hobby Plan ($5/month):**
- No sleeping
- 24/7 uptime
- Better for production

---

## 📊 Monitoring

**View Metrics:**
1. Go to Railway Dashboard
2. Click your service
3. Go to "Metrics" tab

**Monitor:**
- CPU usage
- Memory usage  
- Network traffic
- Request count

---

## 🔄 Updates & Redeployment

**If using GitHub:**
```bash
git add .
git commit -m "Update bot"
git push
```
Railway auto-deploys!

**If using CLI:**
```bash
railway up
```

**If using Dashboard:**
1. Upload new files
2. Railway redeploys automatically

---

## 📱 Managing Textbooks

**Upload via Dashboard:**

You'll need to deploy the React dashboard separately for textbook management.

**Alternative - Direct MongoDB:**

1. Use Railway's MongoDB client
2. Or use MongoDB Compass
3. Connect with `MONGO_URL` from Railway

---

## 🆘 Support

**Railway Support:**
- Discord: https://discord.gg/railway
- Docs: https://docs.railway.app

**Bot Issues:**
- Check logs: `railway logs`
- View bot code: `telegram_bot.py`

---

## ✅ Deployment Checklist

- [ ] Railway account created
- [ ] MongoDB added to project  
- [ ] All environment variables set
- [ ] Files uploaded or repo connected
- [ ] Deployment successful (check logs)
- [ ] Bot responding to `/start`
- [ ] Owner approval system working
- [ ] AI responses working
- [ ] Image analysis working
- [ ] Graph generation working

---

## 🎉 Success!

Your Telegram AI Teacher Bot is now live on Railway!

**Features Working:**
- ✅ AI Chat with reasoning
- ✅ Mathematical graph generation
- ✅ Image analysis
- ✅ Page extraction from textbooks
- ✅ Homework & assignments
- ✅ Voice responses (English/Amharic)
- ✅ 24/7 availability

**Next Steps:**
1. Test all features
2. Upload textbooks via MongoDB
3. Share bot with students
4. Monitor usage in Railway dashboard

**Bot Link:** `t.me/YourBotUsername`

---

**Made with ❤️ for Education**

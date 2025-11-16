# Railway Deployment Guide

This guide walks you through deploying the WhatsApp Message Memory system to Railway.app.

## Prerequisites

- GitHub account with this repository pushed
- Railway account (sign up at [railway.app](https://railway.app))
- Supabase project with tables set up
- Whapi.cloud API credentials
- OpenAI API key

## Architecture Overview

The deployment consists of three services:
1. **Web Service**: FastAPI webhook receiver (receives WhatsApp messages)
2. **Worker Service**: RQ background worker (processes media, transcriptions, PDFs)
3. **Redis**: Message queue connecting web and worker

## Step 1: Create Railway Project

1. Go to [railway.app/new](https://railway.app/new)
2. Click "Deploy from GitHub repo"
3. Authorize Railway to access your GitHub account
4. Select the `message_memory` repository

## Step 2: Add Redis Service

1. In your Railway project dashboard, click "+ New"
2. Select "Database" → "Add Redis"
3. Railway will automatically create a Redis instance and set the `REDIS_URL` environment variable

## Step 3: Configure Environment Variables

In your Railway project, go to the service settings and add these variables:

### Required Variables

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-anon-key
WHAPI_TOKEN=your-whapi-token
WHAPI_API_URL=https://gate.whapi.cloud
OPENAI_API_KEY=sk-your-openai-api-key
MEDIA_BUCKET_NAME=whatsapp-media
```

### Auto-Generated Variables

These are set automatically by Railway:
- `REDIS_URL` - Set by Redis service
- `PORT` - Set by Railway for web service

## Step 4: Deploy Web Service

1. Railway will detect the `Procfile` and ask which process to run
2. For the first service, select "web"
3. Railway will:
   - Build using NIXPACKS (detects `pyproject.toml` and `uv`)
   - Install dependencies
   - Start the FastAPI server with `uvicorn app.main:app --host 0.0.0.0 --port $PORT`

4. Once deployed, Railway provides a public URL like `https://your-app.up.railway.app`

## Step 5: Deploy Worker Service

1. In your Railway project, click "+ New"
2. Select "GitHub Repo" → Select the same `message_memory` repository
3. In service settings:
   - Name: `message-worker` (or similar)
   - Select "worker" from the Procfile processes
4. Add the same environment variables as the web service (or use Railway's "Add Variables from Service" feature)
5. Deploy

The worker will start processing jobs from the Redis queue.

## Step 6: Configure Whapi Webhook

1. Get your Railway web service URL: `https://your-app.up.railway.app`
2. In Whapi dashboard, set webhook URL to: `https://your-app.up.railway.app/webhook`
3. Test by sending a WhatsApp message

## Step 7: Verify Deployment

### Check Web Service

```bash
curl https://your-app.up.railway.app/health
```

Expected response:
```json
{"status": "healthy"}
```

### Check Logs

1. In Railway dashboard, click on each service
2. Go to "Deployments" → "View Logs"
3. You should see:
   - **Web**: `INFO: Uvicorn running on http://0.0.0.0:PORT`
   - **Worker**: `INFO: Worker started, queue: whatsapp-messages`

### Test with WhatsApp Message

1. Send a text message to your WhatsApp number
2. Check worker logs for: `INFO: Processing message {id} of type text`
3. Verify in Supabase that the message was stored

## Monitoring and Maintenance

### View Logs

Railway provides real-time logs for each service:
- Web service: HTTP requests, webhook events
- Worker service: Job processing, media downloads, transcriptions

### Metrics

Railway dashboard shows:
- CPU usage
- Memory usage
- Request count
- Deployment history

### Scaling

**Auto-scaling** (Hobby Plan and above):
- Railway can auto-scale based on traffic
- Go to Service Settings → Scaling

**Manual scaling**:
- Adjust `numReplicas` in `railway.json`
- Recommended: 1 web replica, 1-2 worker replicas

### Cost Optimization

**Estimated costs** (as of 2024):

| Component | Usage | Cost |
|-----------|-------|------|
| Web service | 1 replica, ~512MB RAM | $5/month |
| Worker service | 1 replica, ~512MB RAM | $5/month |
| Redis | Shared instance | $5/month |
| **Total** | | **~$15/month** |

**Tips to reduce costs**:
- Use Railway's $5 free tier credit
- Scale down to 1 worker during low-traffic periods
- Monitor logs to optimize retry intervals

## Troubleshooting

### Worker not processing jobs

**Check**:
1. Verify `REDIS_URL` is set in worker service
2. Check worker logs for connection errors
3. Ensure both web and worker use the same Redis instance

**Fix**: In Railway dashboard, link Redis to both services

### Webhook not receiving messages

**Check**:
1. Verify Railway web service is deployed and running
2. Test `/health` endpoint
3. Check Whapi webhook configuration

**Fix**: Update Whapi webhook URL to Railway domain

### PDF parsing fails

**Check**:
1. Verify `OPENAI_API_KEY` is set correctly
2. Check worker logs for OpenAI API errors
3. Monitor OpenAI usage limits

**Fix**: Check OpenAI account billing and rate limits

### Out of memory errors

**Symptoms**: Service crashes with `OOM` in logs

**Fix**:
1. Go to Service Settings → Resources
2. Increase memory allocation (Railway Hobby plan: up to 8GB)
3. Or optimize processing (reduce concurrent jobs)

## Updating the Application

### Deploy New Changes

Railway auto-deploys on git push:

```bash
git add .
git commit -m "Update feature"
git push origin main
```

Railway will:
1. Detect the push
2. Rebuild services
3. Deploy with zero downtime (rolling update)

### Manual Redeploy

In Railway dashboard:
1. Go to service → Deployments
2. Click "⋯" → "Redeploy"

## Environment-Specific Configuration

### Staging Environment

Create a separate Railway project for staging:
1. Deploy same repo to new project
2. Use separate Supabase project
3. Use test Whapi number

### Production Best Practices

1. **Enable health checks**: Railway uses `/health` endpoint
2. **Set restart policy**: Already configured in `railway.json`
3. **Monitor error rates**: Check logs daily during initial deployment
4. **Set up alerts**: Use Railway webhooks + Discord/Slack for deployment notifications
5. **Database backups**: Supabase handles this automatically

## Additional Resources

- [Railway Documentation](https://docs.railway.app/)
- [Railway Discord](https://discord.gg/railway)
- [Supabase Dashboard](https://app.supabase.com/)
- [Whapi Documentation](https://whapi.cloud/docs)

## Support

If you encounter issues:
1. Check Railway service logs
2. Verify all environment variables are set
3. Test `/health` endpoint
4. Review Supabase and OpenAI usage
5. Check Whapi webhook delivery logs

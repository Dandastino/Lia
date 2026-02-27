# Deployment Guide for Lia

## Production Checklist

### Backend Deployment

#### 1. Environment Configuration
- [ ] Set all required environment variables on production server
- [ ] Use strong `JWT_SECRET_KEY` (generate with `openssl rand -hex 32`)
- [ ] Use environment-specific database (not localhost)
- [ ] Enable SSL/TLS for database connections

#### 2. Database
- [ ] Create production PostgreSQL database for Lia
- [ ] Run migration scripts
- [ ] Set up database backups
- [ ] Configure user permissions (separate read/write privileges if possible)

#### 3. LiveKit
- [ ] Set up LiveKit instance (self-hosted or cloud)
- [ ] Configure CORS for frontend domain
- [ ] Test voice quality and latency

#### 4. API Security
- [ ] Enable CORS only for your frontend domain
- [ ] Implement rate limiting
- [ ] Use HTTPS only
- [ ] Set secure cookie flags
- [ ] Enable CSRF protection if needed

#### 5. Deployment Options

**Option A: Docker**
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "server:app"]
```

**Option B: Traditional Server (Gunicorn + Nginx)**
```bash
# Install
pip install gunicorn

# Run with Gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 server:app

# Nginx reverse proxy
upstream lia_backend {
    server 127.0.0.1:5000;
}

server {
    listen 443 ssl http2;
    server_name api.lia.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    location / {
        proxy_pass http://lia_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

**Option C: Cloud Platforms**
- AWS Lambda + RDS
- Google Cloud Run + Cloud SQL
- Azure App Service + Azure SQL
- Heroku (with PostgreSQL add-on)

### Frontend Deployment

#### 1. Build
```bash
npm run build
```

#### 2. Environment Configuration
- [ ] Update `VITE_API_URL` to production backend URL
- [ ] Verify API endpoint is HTTPS

#### 3. Deployment Options

**Option A: Static Hosting**
- AWS S3 + CloudFront
- Google Cloud Storage + Cloud CDN
- Azure Static Web Apps
- Vercel
- Netlify

**Option B: Traditional Server (Nginx)**
```nginx
server {
    listen 443 ssl http2;
    server_name lia.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    
    root /var/www/lia-frontend/dist;
    
    location / {
        try_files $uri /index.html;
    }
    
    # API proxy (optional)
    location /api {
        proxy_pass https://api.lia.example.com;
    }
}
```

### Connector-Specific Setup

#### PostgreSQL/MySQL External Connectors
- [ ] Database credentials stored securely (environment variables, secrets manager)
- [ ] Network access configured (firewall rules)
- [ ] Connection pooling configured for performance
- [ ] SSL/TLS required for database connections

#### HubSpot Connector
- [ ] Create OAuth app in HubSpot
- [ ] Store API key securely (AWS Secrets Manager, Azure Key Vault, etc.)
- [ ] Test API rate limits
- [ ] Monitor sync logs for failures

#### Salesforce Connector
- [ ] Create Connected App in Salesforce
- [ ] Store credentials securely
- [ ] Test OAuth token refresh
- [ ] Monitor API usage

#### Dynamics 365 Connector
- [ ] Register app in Azure AD
- [ ] Generate client secret
- [ ] Assign appropriate permissions
- [ ] Test token refresh

### Monitoring & Logging

#### Backend Monitoring
- [ ] Set up application logging (CloudWatch, Stackdriver, etc.)
- [ ] Monitor sync_logs table for errors
- [ ] Set up alerts for failed syncs
- [ ] Track API response times
- [ ] Monitor database connections

#### Health Checks
```bash
# Add health check endpoint
GET /health -> 200 OK
```

#### Log Levels
```python
# Production: INFO/WARNING
# Development: DEBUG
```

### Security Checklist

- [ ] All credentials in environment variables
- [ ] No secrets in version control (.gitignore enforced)
- [ ] HTTPS everywhere
- [ ] Strong database passwords
- [ ] Regular backups
- [ ] Database encryption at rest
- [ ] Rate limiting on API endpoints
- [ ] Input validation on all endpoints
- [ ] CORS configured strictly
- [ ] JWT tokens have expiration
- [ ] Dependent on secrets manager (not local files)

### Backup & Recovery

```bash
# PostgreSQL backup
pg_dump -U postgres lia_db > backup_$(date +%Y%m%d).sql

# Restore
psql -U postgres lia_db < backup_20240101.sql

# Automated backup (cron)
0 2 * * * pg_dump -U postgres lia_db | gzip > /backups/lia_db_$(date +\%Y\%m\%d).sql.gz
```

### Performance Optimization

- [ ] Database query optimization (add indexes)
- [ ] Connection pooling (PgBouncer for PostgreSQL)
- [ ] Caching for frequently accessed data
- [ ] CDN for frontend assets
- [ ] Compress API responses (gzip)
- [ ] Load balancing for multiple backend instances

### Disaster Recovery Plan

1. **RTO (Recovery Time Objective)**: Target recovery time
2. **RPO (Recovery Point Objective)**: Acceptable data loss timeframe
3. **Backup frequency**: Daily at minimum
4. **Testing**: Test recovery procedures monthly

## Scaling Considerations

### Horizontal Scaling
- Run multiple backend instances behind load balancer
- Ensure statelessness (JWT auth, no session stored locally)
- Use connection pooling for database

### Vertical Scaling
- Increase server resources (CPU, RAM)
- Optimize queries
- Add database indexes

### Database Scaling
- Read replicas for reporting/analytics
- Sharding for very large datasets (by organization_id)
- Query optimization and caching

## Post-Deployment

- [ ] Run smoke tests
- [ ] Verify all connectors working
- [ ] Test end-to-end user flow
- [ ] Monitor error rates
- [ ] Get user feedback
- [ ] Document any issues/fixes

## Rollback Plan

If deployment fails:
```bash
# Git rollback
git revert <commit>
git push

# Docker rollback
docker pull lia:previous_tag
docker run -d lia:previous_tag

# Database rollback
# Restore from most recent backup
psql lia_db < backup_20240101.sql
```


#!/bin/bash
# Deploy all services to Railway

set -e

echo "🚀 Deploying Agent Memory Commons to Railway"
echo "=============================================="
echo ""

# Check if logged in
if ! railway whoami &>/dev/null; then
    echo "❌ Not logged in to Railway. Run: railway login"
    exit 1
fi

# Check if project is linked
if ! railway status &>/dev/null; then
    echo "📦 No Railway project linked. Creating new project..."
    railway init
fi

echo "✅ Railway CLI ready"
echo ""

# Deploy API service
echo "1️⃣  Deploying Laravel API..."
cd api
railway up --service=api || railway up
cd ..
echo ""

# Deploy Trading service
echo "2️⃣  Deploying Python Trading Bot..."
cd trading
railway up --service=trading || railway up
cd ..
echo ""

# Deploy Frontend
echo "3️⃣  Deploying React Frontend..."
cd frontend
railway up --service=frontend || railway up
cd ..
echo ""

echo "=============================================="
echo "✅ Deployment complete!"
echo ""
echo "Next steps:"
echo "  1. Set environment variables:"
echo "     railway variables"
echo ""
echo "  2. Add PostgreSQL:"
echo "     railway add --service postgres"
echo ""
echo "  3. Add Redis:"
echo "     railway add --service redis"
echo ""
echo "  4. Check deployment status:"
echo "     railway status"
echo ""
echo "  5. View logs:"
echo "     railway logs"

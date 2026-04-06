#!/bin/bash
# Monitor Railway deployments in real-time

set -e

echo "📊 Railway Deployment Monitor"
echo "=============================="
echo ""

PROJECT="hopeful-presence"

# Function to get service status
check_service() {
    local service=$1
    echo "🔍 Checking $service..."

    cd "$service" 2>/dev/null || return

    # Get deployment status
    STATUS=$(railway service status 2>/dev/null | grep "Status:" | awk '{print $2}')
    DEPLOYMENT=$(railway service status 2>/dev/null | grep "Deployment:" | awk '{print $2}')

    if [ -n "$STATUS" ]; then
        case $STATUS in
            SUCCESS)
                echo "  ✅ $service: RUNNING"
                ;;
            BUILDING)
                echo "  🔨 $service: BUILDING..."
                ;;
            DEPLOYING)
                echo "  🚀 $service: DEPLOYING..."
                ;;
            FAILED)
                echo "  ❌ $service: FAILED"
                echo "     View logs: cd $service && railway logs"
                ;;
            *)
                echo "  ⚠️  $service: $STATUS"
                ;;
        esac
    else
        echo "  ⚪ $service: Not deployed"
    fi

    cd - > /dev/null
}

# Monitor loop
echo "Starting monitor (Ctrl+C to stop)..."
echo ""

while true; do
    clear
    echo "📊 Railway Deployment Monitor - $(date '+%H:%M:%S')"
    echo "=============================="
    echo ""

    check_service "api"
    echo ""
    check_service "trading"
    echo ""
    check_service "frontend"
    echo ""

    echo "=============================="
    echo "Commands:"
    echo "  railway logs            - View logs"
    echo "  railway open            - Open dashboard"
    echo "  railway service status  - Detailed status"
    echo ""

    sleep 10
done

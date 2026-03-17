#!/bin/bash
# Test script to verify Docker build with environment variables

set -e

echo "🧪 Testing Docker Build with Environment Variables"
echo "=================================================="

# Test 1: Build with .env.production file
echo ""
echo "Test 1: Building with .env.production file..."
if [ -f .env.production ]; then
  echo "✓ .env.production file exists"
  docker build -t data-entry-app-test:env-file .
  echo "✓ Build successful with .env.production"
else
  echo "⚠ .env.production file not found. Create it first:"
  echo "  cp env.production.example .env.production"
  echo "  # Then edit .env.production with your credentials"
fi

# Test 2: Build with build args
echo ""
echo "Test 2: Building with build arguments..."
if [ -n "$VITE_SUPABASE_URL" ] && [ -n "$VITE_SUPABASE_ANON_KEY" ]; then
  docker build \
    --build-arg VITE_SUPABASE_URL="$VITE_SUPABASE_URL" \
    --build-arg VITE_SUPABASE_ANON_KEY="$VITE_SUPABASE_ANON_KEY" \
    -t data-entry-app-test:build-args .
  echo "✓ Build successful with build args"
else
  echo "⚠ Environment variables not set. To test with build args:"
  echo "  export VITE_SUPABASE_URL='https://your-project.supabase.co'"
  echo "  export VITE_SUPABASE_ANON_KEY='your-key'"
  echo "  ./test-build.sh"
fi

# Test 3: Verify the built image
echo ""
echo "Test 3: Verifying built image..."
if docker images | grep -q "data-entry-app-test"; then
  echo "✓ Image created successfully"
  echo ""
  echo "To test the image locally:"
  echo "  docker run -p 3000:3000 data-entry-app-test:env-file"
  echo ""
  echo "Then open http://localhost:3000 in your browser"
else
  echo "⚠ No test image found"
fi

echo ""
echo "✅ Testing complete!"


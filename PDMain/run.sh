#!/bin/bash

# Paws Pendragon Local Development Runner
# Usage: ./run.sh from the project directory, or from Git Bash anywhere

PROJECT_DIR="C:/Users/exoki/OneDrive/Documents/Claude/Projects/Paws Pendragon"

echo "🐾 Paws Pendragon Local Bot Runner"
echo "=================================="
echo ""

# Navigate to project directory
cd "$PROJECT_DIR" || exit 1
echo "📁 Working directory: $(pwd)"
echo ""

# Install/update dependencies
echo "📦 Installing dependencies..."
pip install -q -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Failed to install dependencies"
    exit 1
fi
echo "✅ Dependencies ready"
echo ""

# Check for .env file
if [ ! -f .env ]; then
    echo "⚠️  .env file not found!"
    echo "   Copy .env.example to .env and fill in your test bot token:"
    echo "   DISCORD_TOKEN=your_test_bot_token_here"
    echo "   GUILD_ALLOWLIST=your_test_guild_id"
    exit 1
fi

echo "🚀 Starting Paws Pendragon..."
echo "=================================="
echo ""

# Run the bot
python bot.py

# If we get here, bot shut down
echo ""
echo "=================================="
echo "🛑 Bot stopped"

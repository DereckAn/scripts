#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Toggle Natural Scroll
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 🖱️

# Documentation:
# @raycast.description Toggle natural scroll on/off
# @raycast.author dereckan
# @raycast.authorURL https://raycast.com/dereckan

# Check current state
current=$(defaults read -g com.apple.swipescrolldirection 2>/dev/null || echo "1")

echo "Current state: $current"

if [ "$current" = "1" ]; then
    defaults write -g com.apple.swipescrolldirection -bool false
    echo "Natural scrolling: OFF"
else
    defaults write -g com.apple.swipescrolldirection -bool true
    echo "Natural scrolling: ON"
fi

# Force the system to reload mouse/trackpad settings
echo "Reloading input settings..."
# Restart mouse/trackpad handling processes
killall cfprefsd 2>/dev/null || true
# Send notification to update preferences
/usr/bin/killall -HUP SystemUIServer 2>/dev/null || true

# Show new state
new_state=$(defaults read -g com.apple.swipescrolldirection 2>/dev/null)
echo "New state: $new_state"
echo "Settings reloaded!"
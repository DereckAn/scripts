#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Toggle Natural Scroll
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 🖱️

# Documentation:
# @raycast.description Turn on and off the natural scroll of the mac
# @raycast.author dereckan
# @raycast.authorURL https://raycast.com/dereckan

echo "Starting natural scroll toggle..."

# Read current state
current=$(defaults read -g com.apple.swipescrolldirection 2>/dev/null)
exit_code=$?

echo "Current setting read result: exit_code=$exit_code, value=$current"

if [ $exit_code -ne 0 ] || [ -z "$current" ]; then
    echo "Setting not found, defaulting to 1 (enabled)"
    current=1
fi

echo "Current natural scrolling state: $current"

if [ "$current" -eq 1 ]; then
    echo "Disabling natural scrolling..."
    defaults write -g com.apple.swipescrolldirection -bool false
    if [ $? -eq 0 ]; then
        echo "✅ Natural scrolling DISABLED"
    else
        echo "❌ Failed to disable natural scrolling"
        exit 1
    fi
else
    echo "Enabling natural scrolling..."
    defaults write -g com.apple.swipescrolldirection -bool true
    if [ $? -eq 0 ]; then
        echo "✅ Natural scrolling ENABLED"
    else
        echo "❌ Failed to enable natural scrolling"
        exit 1
    fi
fi

# Verify the change
new_state=$(defaults read -g com.apple.swipescrolldirection 2>/dev/null)
echo "New state: $new_state"

echo "Script completed successfully!"



#!/usr/bin/osascript

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Toggle Natural Scroll
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 🖱️

# Documentation:
# @raycast.description Toggle natural scroll and apply changes immediately
# @raycast.author dereckan
# @raycast.authorURL https://raycast.com/dereckan

try
	-- Get current state
	set currentState to do shell script "defaults read -g com.apple.swipescrolldirection 2>/dev/null || echo '1'"
	set currentState to currentState as integer
	
	log "Current natural scrolling state: " & currentState
	
	if currentState = 1 then
		-- Disable natural scrolling
		do shell script "defaults write -g com.apple.swipescrolldirection -bool false"
		set resultMessage to "Natural scrolling DISABLED"
	else
		-- Enable natural scrolling
		do shell script "defaults write -g com.apple.swipescrolldirection -bool true"
		set resultMessage to "Natural scrolling ENABLED"
	end if
	
	-- Force reload of preferences
	do shell script "killall cfprefsd 2>/dev/null || true"
	
	-- Add a brief delay to ensure the setting is written
	delay 0.5
	
	-- Method 1: Restart System Preferences if it's running
	tell application "System Events"
		if (name of processes) contains "System Preferences" then
			tell application "System Preferences" to quit
			delay 0.5
		end if
	end tell
	
	-- Method 2: Apply changes through both Mouse and Trackpad settings
	-- First try Mouse settings
	tell application "System Preferences"
		activate
		set current pane to pane "Mouse"
		delay 1.5
	end tell
	
	tell application "System Events"
		tell process "System Preferences"
			try
				-- Look for Natural scrolling checkbox and double-click it
				click checkbox "Natural scrolling" of window 1
				delay 0.3
				click checkbox "Natural scrolling" of window 1
				delay 0.5
			end try
		end tell
	end tell
	
	-- Now try Trackpad settings
	tell application "System Preferences"
		set current pane to pane "Trackpad"
		delay 1.5
	end tell
	
	tell application "System Events"
		tell process "System Preferences"
			try
				-- Click on "Scroll & Zoom" tab if it exists
				click button "Scroll & Zoom" of window 1
				delay 0.5
				-- Look for Natural scrolling checkbox and double-click it
				click checkbox "Natural scrolling" of window 1
				delay 0.3
				click checkbox "Natural scrolling" of window 1
				delay 0.5
			end try
		end tell
	end tell
	
	-- Close System Preferences
	tell application "System Preferences" to quit
	
	-- Final step: Additional delay to ensure changes are applied
	delay 1
	
	log "✅ " & resultMessage
	return resultMessage & " - Settings applied and refreshed!"
	
on error errMsg
	-- Close System Preferences if there was an error
	try
		tell application "System Preferences" to quit
	end try
	log "❌ Error: " & errMsg
	return "Error: " & errMsg
end try
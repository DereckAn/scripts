#!/usr/bin/osascript

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Toggle Natural Scroll (Simple)
# @raycast.mode fullOutput

# Optional parameters:
# @raycast.icon 🖱️

# Documentation:
# @raycast.description Simple toggle for natural scroll
# @raycast.author dereckan
# @raycast.authorURL https://raycast.com/dereckan

try
	-- Get current state
	set currentState to do shell script "defaults read -g com.apple.swipescrolldirection 2>/dev/null || echo '1'"
	set currentState to currentState as integer
	
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
	
	-- Wait a moment
	delay 0.5
	
	-- Try to disconnect and reconnect mouse/trackpad by restarting related processes
	do shell script "launchctl stop com.apple.mouse.daemon 2>/dev/null || true"
	do shell script "launchctl start com.apple.mouse.daemon 2>/dev/null || true"
	
	-- Alternative method: restart HID processes
	do shell script "sudo launchctl stop com.apple.hidd 2>/dev/null || sudo launchctl kickstart system/com.apple.hidd 2>/dev/null || true"
	
	return resultMessage & " - Please test your mouse scroll!"
	
on error errMsg
	return "Completed with potential issues: " & errMsg
end try
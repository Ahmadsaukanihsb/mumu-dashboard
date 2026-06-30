--[[
    Roblox Auto-Join Monitor Script
    Dashboard Roblox - Auto join private/public server when kicked/leave
    
    CARA PAKAI:
    1. Inject script ini ke Roblox via executor (Synapse, Krnl, dll)
    2. Script akan otomatis monitor dan rejoin saat kena kick atau leave
    3. Edit konfigurasi di bawah sesuai kebutuhan

    KONFIGURASI:
    - PLACE_ID: ID game Roblox
    - SERVER_CODE: Kode private server (kosongkan untuk public server)
    - REJOIN_DELAY: Delay detik sebelum rejoin
]]

-- ======= KONFIGURASI =======
local PLACE_ID = 4483381587           -- Ganti dengan Place ID game kamu
local SERVER_CODE = ""                 -- Kode private server ("" untuk public)
local REJOIN_DELAY = 3                -- Delay dalam detik sebelum rejoin
local MAX_RETRIES = 5                 -- Maksimal percobaan rejoin
-- =============================

local Players = game:GetService("Players")
local TeleportService = game:GetService("TeleportService")
local RunService = game:GetService("RunService")
local HttpService = game:GetService("HttpService")
local StarterGui = game:GetService("StarterGui")

local LocalPlayer = Players.LocalPlayer
local isRejoining = false

-- Notifikasi di Roblox
local function notify(title, text, duration)
    pcall(function()
        StarterGui:SetCore("SendNotification", {
            Title = title,
            Text = text,
            Duration = duration or 5
        })
    end)
end

-- Fungsi untuk join ulang
local function rejoin()
    if isRejoining then return end
    isRejoining = true

    notify("Auto-Join", "Rejoining in " .. REJOIN_DELAY .. "s...", REJOIN_DELAY)

    for attempt = 1, MAX_RETRIES do
        local success, err = pcall(function()
            if SERVER_CODE ~= "" then
                -- Private server
                TeleportService:TeleportToPrivateServer(PLACE_ID, SERVER_CODE, {LocalPlayer})
            else
                -- Public server
                TeleportService:Teleport(PLACE_ID, LocalPlayer)
            end
        end)

        if success then
            isRejoining = false
            return
        end

        warn("Auto-Join: Attempt " .. attempt .. " failed: " .. tostring(err))
        notify("Auto-Join", "Retry " .. attempt .. "/" .. MAX_RETRIES, 2)

        if attempt < MAX_RETRIES then
            task.wait(REJOIN_DELAY)
        end
    end

    isRejoining = false
    notify("Auto-Join", "Max retries reached!", 5)
end

-- Event: Kena kick
LocalPlayer.OnKick:Connect(function(msg)
    notify("KICKED", "Kicked: " .. tostring(msg), 3)
    warn("Kicked: " .. tostring(msg))
    task.wait(REJOIN_DELAY)
    rejoin()
end)

-- Event: Pemain dihapus (left/removed)
Players.PlayerRemoving:Connect(function(player)
    if player == LocalPlayer then
        notify("LEFT", "You left the game. Rejoining...", 3)
        task.wait(REJOIN_DELAY)
        rejoin()
    end
end)

-- Event: Teleport gagal
TeleportService.TeleportInitFailed:Connect(function(player, teleportState, errorMessage)
    if player == LocalPlayer then
        notify("TELEPORT FAILED", errorMessage, 3)
        task.wait(REJOIN_DELAY)
        rejoin()
    end
end)

-- Monitoring loop
task.spawn(function()
    while task.wait(15) do
        if LocalPlayer and LocalPlayer.Parent then
            -- Still connected
        end
    end
end)

notify("Auto-Join", "Monitor active! Ready to rejoin on kick/leave.", 5)
print("Auto-Join Monitor aktif - Place ID: " .. PLACE_ID)
print("Server: " .. (SERVER_CODE ~= "" and "Private" or "Public"))

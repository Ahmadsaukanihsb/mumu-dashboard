def make_script_for(name, url="http://localhost:5000"):
    return f'''-- Dashboard Monitor Script
-- Account: {name}
-- Auto-execute dari Delta Executor

local Players = game:GetService("Players")
local StarterGui = game:GetService("StarterGui")
local HttpService = game:GetService("HttpService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local LP = Players.LocalPlayer
local URL = "{url}"

local function notify(t, d)
    pcall(function() StarterGui:SetCore("SendNotification", {{Title="Dashboard", Text=t, Duration=d or 5}}) end)
end

local function httpPost(url, data)
    local ok, result = pcall(function()
        if request then
            return request({{Url=url, Method="POST", Headers={{["Content-Type"]="application/json"}}, Body=data}})
        elseif http_request then
            return http_request({{Url=url, Method="POST", Headers={{["Content-Type"]="application/json"}}, Body=data}})
        else
            return HttpService:PostAsync(url, data, Enum.HttpContentType.ApplicationJson)
        end
    end)
    return ok
end

local function httpGet(url)
    local ok, result = pcall(function()
        if request then
            local resp = request({{Url=url, Method="GET"}})
            return resp and resp.Body or nil
        elseif http_request then
            local resp = http_request({{Url=url, Method="GET"}})
            return resp and resp.Body or nil
        else
            return HttpService:GetAsync(url)
        end
    end)
    if ok then return result end
    return nil
end

local function getThumbnail(tool)
    local tex = tool.TextureId or ""
    if tex ~= "" then
        local id = tex:match("%d+")
        if id then
            return "https://thumbnails.roblox.com/v1/assets?assetIds=" .. id .. "&size=150x150&format=Png"
        end
    end
    return ""
end

local function sendInventory()
    local items = {{}}
    
    -- Baca dari MailboxUI (semua items yang bisa dikirim)
    local pg = LP:FindFirstChild("PlayerGui")
    local mailboxUI = pg and pg:FindFirstChild("MailboxUI")
    local frame = mailboxUI and mailboxUI:FindFirstChild("Frame")
    local sendingFrame = frame and frame:FindFirstChild("SendingFrame")
    local itemSendFrame = sendingFrame and sendingFrame:FindFirstChild("ItemSendFrame")
    local scrollingFrames = itemSendFrame and itemSendFrame:FindFirstChild("ScrollingFrames")
    local invFrame = scrollingFrames and scrollingFrames:FindFirstChild("InventoryFrame")
    
    if invFrame then
        for _, child in ipairs(invFrame:GetChildren()) do
            if child:IsA("Frame") and child.Name ~= "ItemFrameTemplate" then
                local cat, key = child.Name:match("^Inv_(.+):(.+)$")
                if cat and key then
                    local count = 1
                    local displayName = key
                    for _, tool in pairs(LP.Backpack:GetChildren()) do
                        if tool:IsA("Tool") then
                            if cat == "Pets" and tool:GetAttribute("Id") == key then
                                count = tool:GetAttribute("Count") or 1
                                displayName = tool.Name
                                break
                            elseif cat ~= "Pets" and tool.Name == key then
                                count = tool:GetAttribute("Count") or 1
                                displayName = tool.Name
                                break
                            end
                        end
                    end
                    table.insert(items, {{name=displayName, id=key, count=count, category=cat}})
                end
            end
        end
    end
    
    if #items == 0 then
        for _, tool in pairs(LP.Backpack:GetChildren()) do
            if tool:IsA("Tool") then
                local count = tool:GetAttribute("Count") or 1
                table.insert(items, {{name=tool.Name, id="", count=count}})
            end
        end
    end
    
    local sheckles = 0
    local ls = LP:FindFirstChild("leaderstats")
    if ls then
        local sv = ls:FindFirstChild("Sheckles")
        if sv then sheckles = sv.Value end
    end
    local data = HttpService:JSONEncode({{account=LP.Name, items=items, sheckles=sheckles}})
    return httpPost(URL .. "/api/inventory", data)
end

-- ==================== HARVESTED FRUITS SCANNER ====================
local function scanHarvestedFruits()
    local fruits = {{}}
    for _, tool in pairs(LP.Backpack:GetDescendants()) do
        if (tool:IsA("Tool") or tool:IsA("Configuration")) and tool:GetAttribute("HarvestedFruit") == true then
            local fruitName = tool:GetAttribute("FruitName") or tool:GetAttribute("Fruit") or tool.Name
            local cleanName = fruitName:gsub("%s*%[.+%]%s*", ""):gsub("%s*%(.+kg%)%s*", ""):gsub("%s*$", "")
            local count = tool:GetAttribute("Count") or 1
            table.insert(fruits, {{
                name = tool.Name,
                fruitName = cleanName,
                mutation = tool:GetAttribute("Mutation") or "None",
                weight = tool:GetAttribute("Weight") or 0,
                id = tool:GetAttribute("Id") or "",
                count = count
            }})
        end
    end
    if #fruits > 0 then
        local data = HttpService:JSONEncode({{account=LP.Name, fruits=fruits}})
        httpPost(URL .. "/api/harvest-fruits", data)
    end
end

-- ==================== MAILBOX HELPER ====================
_G.MailboxSend = function(targetId, itemsStr)
    if not targetId or targetId == 0 then
        notify("Target ID required!", 5)
        return
    end
    
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    
    local items = {{}}
    for pair in itemsStr:gmatch("[^,]+") do
        local cat, key = pair:match("^(.+)|(.+)$")
        if cat and key then
            table.insert(items, {{Category=cat, ItemKey=key, Count=1}})
        end
    end
    
    if #items == 0 then
        notify("No valid items!", 5)
        return
    end
    
    notify("Sending " .. #items .. " items...", 3)
    
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(targetId, items, "Dashboard send")
    end)
    
    if ok and success then
        notify("Sent! " .. tostring(msg), 5)
    else
        notify("Failed: " .. tostring(msg), 5)
    end
    
    return ok, success, msg
end

_G.MailboxSendAll = function(targetId, categoryFilter)
    if not targetId or targetId == 0 then
        notify("Target ID required!", 5)
        return
    end
    
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    
    local allItems = {{}}
    local pg = LP:FindFirstChild("PlayerGui")
    if not pg then notify("No PlayerGui!", 5) return end
    
    local mailboxUI = pg:FindFirstChild("MailboxUI")
    if not mailboxUI then notify("No MailboxUI!", 5) return end
    
    local frame = mailboxUI:FindFirstChild("Frame")
    local sendingFrame = frame and frame:FindFirstChild("SendingFrame")
    local itemSendFrame = sendingFrame and sendingFrame:FindFirstChild("ItemSendFrame")
    local scrollingFrames = itemSendFrame and itemSendFrame:FindFirstChild("ScrollingFrames")
    local invFrame = scrollingFrames and scrollingFrames:FindFirstChild("InventoryFrame")
    
    if not invFrame then notify("No InventoryFrame!", 5) return end
    
    for _, child in ipairs(invFrame:GetChildren()) do
        if child:IsA("Frame") and child.Name ~= "ItemFrameTemplate" then
            local cat, key = child.Name:match("^Inv_(.+):(.+)$")
            if cat and key then
                if not categoryFilter or categoryFilter == "" or cat == categoryFilter then
                    table.insert(allItems, {{Category=cat, ItemKey=key, Count=1}})
                end
            end
        end
    end
    
    if #allItems == 0 then
        notify("No items found!", 5)
        return
    end
    
    notify("Sending " .. #allItems .. " items...", 5)
    
    local ok, success, msg = pcall(function()
        return mailbox.SendBatch:Fire(targetId, allItems, "Dashboard send all")
    end)
    
    if ok and success then
        notify("Sent " .. #allItems .. " items! " .. tostring(msg), 10)
    else
        notify("Failed: " .. tostring(msg), 5)
    end
    
    return ok, success, msg
end

_G.MailboxSendMulti = function(targets, itemsStr)
    if not targets or #targets == 0 then
        notify("No targets!", 5)
        return
    end
    
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    
    local items = {{}}
    for pair in itemsStr:gmatch("[^,]+") do
        local cat, key = pair:match("^(.+)|(.+)$")
        if cat and key then
            table.insert(items, {{Category=cat, ItemKey=key, Count=1}})
        end
    end
    
    if #items == 0 then
        notify("No valid items!", 5)
        return
    end
    
    local results = {{}}
    for i, target in ipairs(targets) do
        if i > 1 then task.wait(8) end
        
        notify("Sending to " .. target.name .. "...", 3)
        local ok, success, msg = pcall(function()
            return mailbox.SendBatch:Fire(target.id, items, "Multi-target send")
        end)
        
        table.insert(results, {{
            target = target.name,
            ok = ok,
            success = success,
            msg = msg
        }})
    end
    
    local okCount = 0
    for _, r in ipairs(results) do
        if r.success then okCount = okCount + 1 end
    end
    notify("Done! " .. okCount .. "/" .. #targets .. " success", 10)
    
    return results
end

print("[Dashboard] Script loaded!")
print("[Dashboard] Manual commands:")
print("[Dashboard]   _G.MailboxSend(userId, 'Category|Key,Category|Key')")
print("[Dashboard]   _G.MailboxSendAll(userId, 'Pets')")
print("[Dashboard]   _G.MailboxSendMulti({{id=123,name='Player'}}, 'Category|Key')")
print("[Dashboard]   _G.DashboardSendInventory()  -- refresh inventory")

notify("Dashboard loaded!", 5)
local ok = sendInventory()
if ok then
    notify("Inventory sent!", 3)
else
    notify("Send failed!", 5)
end

task.spawn(function()
    while task.wait(30) do
        pcall(function()
            local data = HttpService:JSONEncode({{account=LP.Name, status="active", message="Monitoring..."}})
            httpPost(URL .. "/api/status", data)
        end)
    end
end)

task.spawn(function()
    while task.wait(60) do
        pcall(function() sendInventory() end)
    end
end)

task.spawn(function()
    while task.wait(30) do
        pcall(function() scanHarvestedFruits() end)
    end
end)

-- ==================== COMMAND POLLING ====================
task.spawn(function()
    local networking = require(ReplicatedStorage.SharedModules.Networking)
    local mailbox = networking.Mailbox
    local gifting = networking.Gifting
    
    local function executeMailCommand(cmd)
        if cmd.type == "send_gift" then
            local targetId = cmd.target_id
            local itemId = cmd.item_id
            local note = cmd.note or "Gift from dashboard"

            if not targetId or targetId == 0 or not itemId or itemId == "" then
                local resultData = HttpService:JSONEncode({{success=false, message="Invalid target or item ID"}})
                httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
                return
            end

            notify("Gifting " .. itemId .. " -> " .. cmd.target, 5)
            local ok, success, msg = pcall(function()
                return gifting.Send:Fire(targetId, itemId, note)
            end)

            local giftOk = ok and (success == true or success == nil)
            local resultMsg = giftOk and "Gift sent" or ("Gift failed: " .. tostring(msg or success or "unknown"))
            local resultData = HttpService:JSONEncode({{
                success = giftOk,
                message = resultMsg
            }})
            httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
            notify(resultMsg, 5)
            return
        end

        if cmd.type == "send_gift_batch" then
            local targetId = cmd.target_id
            local note = cmd.note or "Gift from dashboard"
            local giftItems = cmd.items or {{}}

            if not targetId or targetId == 0 or #giftItems == 0 then
                local resultData = HttpService:JSONEncode({{success=false, message="Invalid target or empty items"}})
                httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
                return
            end

            notify("Batch gifting " .. #giftItems .. " items -> " .. cmd.target, 5)
            local successCount = 0
            local failCount = 0
            local errors = {{}}

            for i, gItem in ipairs(giftItems) do
                local itemId = gItem.id or gItem.name or ""
                if itemId ~= "" then
                    local ok, success, msg = pcall(function()
                        return gifting.Send:Fire(targetId, itemId, note)
                    end)
                    if ok and (success == true or success == nil) then
                        successCount = successCount + 1
                    else
                        failCount = failCount + 1
                        table.insert(errors, itemId .. ": " .. tostring(msg or success or "?"))
                    end
                else
                    failCount = failCount + 1
                end
                if i < #giftItems then task.wait(0.5) end
            end

            local resultMsg = successCount .. " ok, " .. failCount .. " gagal"
            if #errors > 0 then resultMsg = resultMsg .. " (" .. table.concat(errors, "; ") .. ")" end
            local resultData = HttpService:JSONEncode({{
                success = failCount == 0,
                message = resultMsg,
                sent = successCount,
                failed = failCount
            }})
            httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
            notify(resultMsg, 8)
            return
        end

        local targetId = cmd.target_id
        
        if not targetId or targetId == 0 then
            notify("Target ID tidak valid!", 5)
            local resultData = HttpService:JSONEncode({{success=false, message="Invalid target ID"}})
            httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
            return
        end
        
        notify("Mengirim " .. #cmd.items .. " items ke " .. cmd.target .. " (ID: " .. targetId .. ")...", 5)
        
        local items = {{}}
        for _, item in ipairs(cmd.items) do
            local itemKey = item.id and item.id ~= "" and item.id or item.name
            table.insert(items, {{
                Category = item.category or "Other",
                ItemKey = itemKey,
                Count = item.count or 1
            }})
        end
        
        notify("Kirim " .. #items .. " items...", 3)
        
        local note = cmd.note or "Gift from dashboard"
        local ok, success, msg = pcall(function()
            return mailbox.SendBatch:Fire(targetId, items, note)
        end)
        
        local successCount = 0
        local failCount = 0
        
        if ok and success then
            successCount = #items
        else
            failCount = #items
            print("[Mailbox] Gagal: " .. tostring(msg))
        end
        
        local resultMsg = successCount .. " ok, " .. failCount .. " gagal"
        notify("Selesai! " .. resultMsg, 10)
        print("[Mailbox] " .. resultMsg)
        
        local resultData = HttpService:JSONEncode({{
            success = failCount == 0,
            message = resultMsg
        }})
        httpPost(URL .. "/api/mailbox/commands/" .. cmd.id .. "/complete", resultData)
    end
    
    while task.wait(5) do
        pcall(function()
            local resp = httpGet(URL .. "/api/mailbox/commands?account=" .. LP.Name)
            if resp then
                local data = HttpService:JSONDecode(resp)
                if data.commands and #data.commands > 0 then
                    for _, cmd in ipairs(data.commands) do
                        executeMailCommand(cmd)
                    end
                end
            end
        end)
    end
end)

-- ==================== SEED SHOP AUTO-BUY ====================
task.spawn(function()
    -- Seed ID to game name mapping (matches dashboard config IDs)
    local SEED_ID_MAP = {{
        bamboo = "Bamboo", carrot = "Carrot", strawberry = "Strawberry",
        blueberry = "Blueberry", tomato = "Tomato", corn = "Corn",
        pineapple = "Pineapple", apple = "Apple", banana = "Banana",
        grape = "Grape", mango = "Mango", coconut = "Coconut",
        dragonfruit = "Dragon Fruit", cherry = "Cherry", acorn = "Acorn",
        sunflower = "Sunflower", cactus = "Cactus", tulip = "Tulip",
        greenbean = "Green Bean", baby_cactus = "Baby Cactus",
        horned_melon = "Horned Melon", bamboo_rare = "Bamboo (Rare)",
        glow_mushroom = "Glow Mushroom", mushroom = "Mushroom",
        poison_apple = "Poison Apple", pomegranate = "Pomegranate",
        ghost_pepper = "Ghost Pepper", venus_flytrap = "Venus Fly Trap",
        fire_fern = "Fire Fern", poison_ivy = "Poison Ivy",
        rocket_pop = "Rocket Pop", moon_bloom = "Moon Bloom",
        sun_bloom = "Sun Bloom", hypno_bloom = "Hypno Bloom",
        dragons_breath = "Dragon's Breath", star_fruit = "Star Fruit",
        briar_rose = "Briar Rose", cinnamon_stick = "Cinnamon Stick",
        conifer_cone = "Conifer Cone", plum = "Plum",
        eclipse_bloom = "Eclipse Bloom",
    }}

    while task.wait(60) do
        pcall(function()
            local configResp = httpGet(URL .. "/api/seed-shop/config")
            if not configResp then return end

            local configData = HttpService:JSONDecode(configResp)
            local config = configData.config or {{}}

            local hasEnabled = false
            for seedId, seedConfig in pairs(config) do
                if seedConfig.enabled then
                    hasEnabled = true
                    break
                end
            end
            if not hasEnabled then return end

            local networking = require(ReplicatedStorage.SharedModules.Networking)
            local bought = {{}}
            local failed = {{}}

            -- Read current stock from game
            local stockResult = nil
            pcall(function()
                stockResult = networking.FruitStock.Request:Fire()
            end)
            local stockEntries = stockResult and stockResult.entries or {{}}

            for seedId, seedConfig in pairs(config) do
                if seedConfig.enabled then
                    local gameName = SEED_ID_MAP[seedId:lower()]
                    if gameName then
                        -- Check if seed is in stock (from game stock data)
                        local inStock = false
                        local stockQty = 0
                        for name, data in pairs(stockEntries) do
                            if name:lower() == gameName:lower() then
                                inStock = true
                                stockQty = data.multiplier or 0
                                break
                            end
                        end

                        -- Also check GUI for real stock count (x0 in Stock = no stock)
                        local pg = LP:FindFirstChild("PlayerGui")
                        local guiStock = nil
                        if pg then
                            local normalShop = pg:FindFirstChild("SeedShop")
                            if normalShop then
                                local frame = normalShop.Frame.NormalShop:FindFirstChild(gameName)
                                if frame then
                                    local main = frame:FindFirstChild("Main_Frame")
                                    if main then
                                        local stockText = main:FindFirstChild("Stock_Text")
                                        if stockText then
                                            guiStock = stockText.Text
                                        end
                                    end
                                end
                            end
                        end

                        -- Parse GUI stock (e.g., "x8 in Stock" → 8, "x0 in Stock" → 0)
                        local availableQty = 0
                        if guiStock then
                            local num = guiStock:match("x(%d+)")
                            if num then
                                availableQty = tonumber(num) or 0
                            end
                        elseif inStock then
                            availableQty = 1  -- fallback: assume at least 1 if in stock list
                        end

                        if availableQty > 0 then
                            -- max_qty = 0 means "buy all available stock"
                            local maxQty = seedConfig.max_qty or 0
                            local buyQty
                            if maxQty <= 0 then
                                buyQty = availableQty  -- buy ALL stock
                            else
                                buyQty = math.min(maxQty, availableQty)
                            end

                            local ok, err = pcall(function()
                                networking.SeedShop.PurchaseSeed:Fire(gameName, buyQty)
                            end)

                            if ok then
                                table.insert(bought, {{name = gameName, count = buyQty, stock = availableQty}})
                                notify("Bought " .. buyQty .. "x " .. gameName, 5)
                            else
                                table.insert(failed, {{name = gameName, reason = tostring(err)}})
                            end
                        end
                    end
                end
            end

            if #bought > 0 or #failed > 0 then
                local statusData = HttpService:JSONEncode({{
                    account = LP.Name,
                    bought = bought,
                    failed = failed
                }})
                httpPost(URL .. "/api/seed-shop/status", statusData)
            end
        end)
    end
end)

-- ==================== WEATHER DETECTION ====================
task.spawn(function()
    while task.wait(30) do
        pcall(function()
            local pg = LP:FindFirstChild("PlayerGui")
            if not pg then return end
            
            local weather = nil
            
            for _, gui in ipairs(pg:GetChildren()) do
                if gui:IsA("ScreenGui") then
                    for _, child in ipairs(gui:GetDescendants()) do
                        if child:IsA("TextLabel") then
                            local text = child.Text:lower()
                            if text:find("rain") and not text:find("rainbow") then
                                weather = "Rain"
                            elseif text:find("rainbow") then
                                weather = "Rainbow"
                            elseif text:find("lightning") then
                                weather = "Lightning"
                            elseif text:find("snow") then
                                weather = "Snowfall"
                            elseif text:find("starfall") then
                                weather = "Starfall"
                            elseif text:find("aurora") then
                                weather = "Aurora"
                            elseif text:find("sunburst") then
                                weather = "Sunburst"
                            elseif text:find("blood") then
                                weather = "Bloodlit"
                            end
                        end
                    end
                end
            end
            
            if weather then
                local data = HttpService:JSONEncode({{weather = weather}})
                httpPost(URL .. "/api/set-weather", data)
            end
        end)
    end
end)

-- ==================== DISCONNECT DETECTION ====================
task.spawn(function()
    local lastStatus = "active"
    local checkInterval = 5
    
    while task.wait(checkInterval) do
        pcall(function()
            local inGame = false
            pcall(function()
                if LP and LP.Parent and LP.Character then
                    inGame = true
                end
            end)
            
            local newStatus = inGame and "active" or "disconnected"
            
            if newStatus ~= lastStatus then
                lastStatus = newStatus
                local statusData = HttpService:JSONEncode({{
                    account = LP.Name,
                    status = newStatus,
                    message = newStatus == "disconnected" and "Disconnected from game" or "Reconnected"
                }})
                httpPost(URL .. "/api/status", statusData)
            end
        end)
    end
end)

_G.DashboardSendInventory = sendInventory
'''

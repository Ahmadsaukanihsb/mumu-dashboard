let accounts = [];
let servers = [];
let settings = {};
let activityLog = [];
let refreshInterval = null;
let vmDisplayNames = {};
let logRefreshInterval = null; // Bug #8 fix: deklarasi di scope global agar tidak implicit global
let inventoryData = {};
let itemThumbnails = {};

function getVmDisplayName(index) {
    return vmDisplayNames[index] || `MuMu-${index}`;
}

document.addEventListener('DOMContentLoaded', async () => {
    const auth = await api('GET', '/api/auth-status');
    if (auth && auth.has_password && !auth.authenticated) {
        window.location.href = '/login';
        return;
    }
    refreshData();
    refreshInterval = setInterval(refreshData, 5000);
    if (countdownInterval) clearInterval(countdownInterval);
    countdownInterval = setInterval(updateCountdowns, 5000);
    updateClock();
    setInterval(updateClock, 1000);
});

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

function toggleSidebarCollapse() {
    document.body.classList.toggle('sidebar-collapsed');
    const btn = document.querySelector('.sidebar-toggle-btn i');
    if (btn) {
        btn.className = document.body.classList.contains('sidebar-collapsed')
            ? 'fas fa-chevron-right'
            : 'fas fa-chevron-left';
    }
}

function showToast(msg, type = 'info', duration = 3500) {
    let container = document.getElementById('toastContainer');
    if (!container) {
        container = document.createElement('div');
        container.id = 'toastContainer';
        container.className = 'toast-container';
        document.body.appendChild(container);
    }
    const icons = { success: 'fa-check-circle', error: 'fa-exclamation-circle', warning: 'fa-exclamation-triangle', info: 'fa-info-circle' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<i class="fas ${icons[type] || icons.info} toast-icon" style="color:var(--${type === 'error' ? 'red' : type === 'success' ? 'green' : type === 'warning' ? 'yellow' : 'blue'})"></i><span class="toast-msg">${msg}</span>`;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
        toast.classList.remove('show');
        toast.classList.add('toast-hide');
        setTimeout(() => toast.remove(), 400);
    }, duration);
}

function animateValue(el, start, end, duration = 800) {
    if (!el) return;
    const range = end - start;
    const startTime = performance.now();
    const isInt = Number.isInteger(end);
    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const current = start + range * eased;
        el.textContent = isInt ? Math.round(current).toLocaleString() : current.toFixed(1);
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function switchPage(page) {
    document.getElementById('sidebar').classList.remove('open');
    const current = document.querySelector('.page.active');
    const next = document.getElementById(`page-${page}`);
    if (current === next) return;

    if (current) {
        current.style.opacity = '0';
        current.style.transform = 'translateY(8px)';
        setTimeout(() => {
            current.classList.remove('active');
            current.style.opacity = '';
            current.style.transform = '';
            next.classList.add('active');
            next.style.opacity = '0';
            next.style.transform = 'translateY(8px)';
            requestAnimationFrame(() => {
                next.style.opacity = '1';
                next.style.transform = 'translateY(0)';
            });
        }, 200);
    } else {
        next.classList.add('active');
    }

    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
    document.querySelector(`.nav-item[data-page="${page}"]`).classList.add('active');

    const pageMeta = {
        dashboard: { title: 'Dashboard', icon: 'chart-pie' },
        accounts: { title: 'Accounts', icon: 'users' },
        servers: { title: 'Servers', icon: 'server' },
        activity: { title: 'Activity', icon: 'history' },
        settings: { title: 'Settings', icon: 'cog' },
        vms: { title: 'VMs', icon: 'desktop' },
        devices: { title: 'Devices', icon: 'mobile-alt' },
        scripts: { title: 'Scripts', icon: 'code' },
        logs: { title: 'Logs', icon: 'clipboard-list' },
        inventory: { title: 'Inventory', icon: 'box-open' },
        command: { title: 'Command', icon: 'terminal' },
        termux: { title: 'Termux Guide', icon: 'mobile-alt' }
    };
    const meta = pageMeta[page] || { title: 'Dashboard', icon: 'chart-pie' };
    document.getElementById('pageTitle').textContent = meta.title;
    document.getElementById('pageIcon').innerHTML = `<i class="fas fa-${meta.icon}"></i>`;

    if (page === 'dashboard') { refreshAllScreenshots(); }
    if (page === 'scripts') loadScript();
    if (page === 'vms') { refreshMuMuVMs(); }
    if (page === 'devices') { startDevicesAutoRefresh(); } else { stopDevicesAutoRefresh(); }
    if (page === 'inventory') { refreshInventory(); }
    if (page === 'command') { initMailbox(); }
    if (page === 'logs') {
        populateLogAccountSelect();
        const sel = document.getElementById('logAccountSelect');
        if (sel.value) loadAccountLogs(sel.value);
        if (logRefreshInterval) clearInterval(logRefreshInterval);
        logRefreshInterval = setInterval(() => {
            const v = document.getElementById('logAccountSelect').value;
            if (v) loadAccountLogs(v);
        }, 5000);
    } else {
        if (logRefreshInterval) { clearInterval(logRefreshInterval); logRefreshInterval = null; }
    }
}

async function api(method, url, body = null) {
    try {
        const opts = {
            method,
            headers: { 'Content-Type': 'application/json' }
        };
        if (body) opts.body = JSON.stringify(body);
        const res = await fetch(url, opts);
        const data = await res.json();
        if (!res.ok) {
            return { _error: true, _status: res.status, ...data };
        }
        return data;
    } catch (err) {
        console.error(err);
        return null;
    }
}

async function refreshData() {
    const [accs, svs, act, sets, sum, inv, thumbs] = await Promise.all([
        api('GET', '/api/accounts'),
        api('GET', '/api/servers'),
        api('GET', '/api/activity?limit=10'),
        api('GET', '/api/settings'),
        api('GET', '/api/summary'),
        api('GET', '/api/inventory'),
        api('GET', '/api/item-thumbnails')
    ]);
    if (accs && accs._error && accs._status === 401) {
        window.location.href = '/login';
        return;
    }
    if (accs) accounts = accs;
    if (svs) servers = svs;
    if (act) activityLog = act;
    if (inv) inventoryData = inv;
    if (thumbs) itemThumbnails = thumbs;
    if (sum && typeof sum.online === 'number') {
        const ids = { statOnline: sum.online, statError: sum.error, statVMs: `${sum.running_vms}/${sum.total_vms}`, statRobux: (sum.total_robux || 0).toLocaleString(), statAccounts: accounts.length, statSheckles: (sum.total_sheckles || 0).toLocaleString(), statInventoryValue: (sum.total_inventory_value || 0).toLocaleString() };
        for (const [k, v] of Object.entries(ids)) {
            const el = document.getElementById(k);
            if (el) {
                el.textContent = v;
            }
        }
    }
    if (sum && typeof sum.online === 'number' && accounts.length === 0) {
        document.getElementById('statAccounts').textContent = '0';
    }
    if (sets) {
        settings = sets;
        if (sets.vm_display_names) {
            for (const [vmName, display] of Object.entries(sets.vm_display_names)) {
                const m = vmName.match(/MuMuPlayerGlobal-12\.0-(\d+)/);
                if (m) vmDisplayNames[parseInt(m[1])] = display;
            }
        }
    }

    try { updateDashboard(); } catch(e) { console.warn('updateDashboard:', e); }
    try { updateAccountsTable(); } catch(e) { console.warn('updateAccountsTable:', e); }
    try { updateServersTable(); } catch(e) { console.warn('updateServersTable:', e); }
    try { updateActivityLog(); } catch(e) { console.warn('updateActivityLog:', e); }
    try { updateSidebarActivity(); } catch(e) { console.warn('updateSidebarActivity:', e); }
    try { updateAccountSelect(); } catch(e) { console.warn('updateAccountSelect:', e); }
    try { updateVmSerialLabels(); } catch(e) { console.warn('updateVmSerialLabels:', e); }
    try { updateNavBadge(); } catch(e) { console.warn('updateNavBadge:', e); }
    try { updateInventory(); } catch(e) { console.warn('updateInventory:', e); }
    try { refreshGameStatus(); } catch(e) { console.warn('refreshGameStatus:', e); }
}

function updateADBStatus() {
    const el = document.getElementById('adbStatus');
    if (!el) return;
    const found = settings._adb_found;
    const path = settings.adb_path || '(auto)';
    if (found) {
        el.innerHTML = `<i class="fas fa-check-circle" style="color:var(--green)"></i> <strong>ADB Terdeteksi</strong> &mdash; ${esc(path)}`;
        el.style.borderColor = 'rgba(67,233,123,0.3)';
        el.style.background = 'rgba(67,233,123,0.05)';
    } else {
        el.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:var(--yellow)"></i> <strong>ADB Tidak Ditemukan</strong> &mdash; Install Android SDK platform-tools atau atur path manual`;
        el.style.borderColor = 'rgba(255,217,61,0.3)';
        el.style.background = 'rgba(255,217,61,0.05)';
    }
}

let gameStatusData = {};

async function refreshGameStatus() {
    const res = await api('GET', '/api/game-status');
    if (res) {
        gameStatusData = res;
        updateGameStatusDisplay();
        updateSeasonalEventsDisplay();
    }
}

function updateGameStatusDisplay() {
    const weatherEl = document.getElementById('currentWeather');
    const optionsEl = document.getElementById('weatherOptions');
    if (!weatherEl || !optionsEl) return;

    const currentWeather = gameStatusData.current_weather;
    const weatherEvents = gameStatusData.weather_events || [];

    if (currentWeather) {
        const weather = weatherEvents.find(w => w.name === currentWeather);
        if (weather) {
            weatherEl.innerHTML = `
                <div class="weather-icon">${weather.icon}</div>
                <div class="weather-info">
                    <div class="weather-name">${esc(weather.name)}</div>
                    <div class="weather-effect">${esc(weather.effect)}</div>
                    ${weather.mutation ? `<div style="font-size:11px;color:var(--yellow);margin-top:4px">Mutation: ${esc(weather.mutation)} (x${weather.mutation_multiplier})</div>` : ''}
                </div>
            `;
        }
    } else {
        weatherEl.innerHTML = `
            <div class="weather-icon">🌤️</div>
            <div class="weather-info">
                <div class="weather-name">Clear</div>
                <div class="weather-effect">No active weather event</div>
            </div>
        `;
    }

    optionsEl.innerHTML = weatherEvents.map(w => `
        <div class="weather-option ${currentWeather === w.name ? 'active' : ''}" onclick="setWeather('${w.name}')">
            ${w.icon} ${w.name}
        </div>
    `).join('') + `
        <div class="weather-option ${!currentWeather ? 'active' : ''}" onclick="setWeather(null)">
            ❌ Clear
        </div>
    `;
}

async function setWeather(weatherName) {
    const res = await api('POST', '/api/set-weather', { weather: weatherName });
    if (res && res.success) {
        gameStatusData.current_weather = res.current_weather;
        updateGameStatusDisplay();
    }
}

function updateSeasonalEventsDisplay() {
    const el = document.getElementById('seasonalEventsContent');
    if (!el) return;

    const events = gameStatusData.seasonal_events || [];
    if (events.length === 0) {
        el.innerHTML = '<div class="empty-state"><i class="fas fa-calendar"></i> No events</div>';
        return;
    }

    el.innerHTML = events.map(event => `
        <div class="event-card">
            <div class="event-icon">${event.icon}</div>
            <div class="event-info">
                <div class="event-name">${esc(event.name)}</div>
                <div class="event-desc">${esc(event.description)}</div>
            </div>
            <div class="event-status ${event.status}">${event.status}</div>
        </div>
    `).join('');
}

function updateNavBadge() {
    const badge = document.getElementById('accountErrorBadge');
    if (!badge) return;
    const count = accounts.filter(a => a.status === 'error' || a.status === 'kicked').length;
    if (count > 0) {
        badge.textContent = count;
        badge.style.display = 'flex';
    } else {
        badge.style.display = 'none';
    }
}

function updateClock() {
    const el = document.getElementById('clockTime');
    if (el) el.textContent = new Date().toLocaleTimeString('id-ID', { hour12: false });
}

function updateDashboard() {
    document.getElementById('statAccounts').textContent = accounts.length;
    const sa = document.getElementById('statAccounts');
    if (!sa.dataset.initial) {
        sa.dataset.initial = '1';
    }
    const online = accounts.filter(a => a.status === 'online' || a.status === 'in_game').length;
    const ingame = accounts.filter(a => a.status === 'in_game').length;
    const error = accounts.filter(a => a.status === 'error' || a.status === 'kicked').length;
    const onlineEl = document.getElementById('dashOnlineCount');
    if (onlineEl) onlineEl.textContent = online;
    const ingameEl = document.getElementById('dashIngameCount');
    if (ingameEl) ingameEl.textContent = ingame;
    const errorEl = document.getElementById('dashErrorCount');
    if (errorEl) errorEl.textContent = error;
    const totalEl = document.getElementById('dashTotalCount');
    if (totalEl) totalEl.textContent = accounts.length;


    const activeEl = document.activeElement;
    const isInSettings = activeEl && activeEl.closest('.settings-content');
    if (!isInSettings) {
        document.getElementById('autoJoinEnabled').checked = settings.auto_join_enabled ?? true;
        document.getElementById('rejoinDelay').value = settings.rejoin_delay ?? 3;
        document.getElementById('maxRetries').value = settings.max_retries ?? 5;
        document.getElementById('monitorInterval').value = settings.monitor_interval ?? 2;
        document.getElementById('rejoinInterval').value = (settings.rejoin_interval ?? 2400) / 60;
        document.getElementById('adbPath').value = settings.adb_path || '';
        document.getElementById('webhookUrl').value = settings.webhook_url || '';
        document.getElementById('webhookEnabled').checked = settings.webhook_enabled ?? false;
        document.getElementById('autoRestartVM').checked = settings.auto_restart_vm ?? true;
        document.getElementById('autoVerifyInterval').value = settings.auto_verify_interval ?? 0;
        const discordFields = { discordClientId: 'discord_client_id', discordClientSecret: 'discord_client_secret', discordGuildId: 'discord_guild_id' };
        Object.keys(discordFields).forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = settings[discordFields[id]] || '';
        });
        const deltaAuto = document.getElementById('deltaAutoKey');
        if (deltaAuto) deltaAuto.checked = settings.delta_auto_key ?? false;
        const dashboardUrl = document.getElementById('dashboardUrl');
        if (dashboardUrl) dashboardUrl.value = settings.dashboard_url || 'http://localhost:5000';
        
        const pwdInput = document.getElementById('dashboardPassword');
        if (settings._has_password) {
            pwdInput.placeholder = 'Password sudah diset — isi untuk mengganti';
        } else {
            pwdInput.placeholder = 'Biarkan kosong jika tidak ingin password';
        }
        pwdInput.value = '';
        document.getElementById('showPassword').checked = false;
        document.getElementById('showPassword').onchange = function() {
            const inp = document.getElementById('dashboardPassword');
            inp.type = this.checked ? 'text' : 'password';
        };
        const hasPwd = settings._has_password;
        document.getElementById('btnLogout').style.display = hasPwd ? '' : 'none';
        document.getElementById('btnClearPassword').style.display = hasPwd ? '' : 'none';
        const serials = settings.mumu_serials || [];
        const container = document.getElementById('mumuSerialLabels');
        if (container) {
            let maxVms = Math.max(serials.length, 1);
            container.innerHTML = '';
            for (let i = 0; i < maxVms; i++) {
                container.innerHTML += `
                    <div>
                        <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">${getVmDisplayName(i)}</label>
                        <input type="text" class="input mumu-serial" data-idx="${i}" placeholder="IP:5555" style="text-align:center;font-size:12px" value="${esc(serials[i] || '')}">
                    </div>
                `;
            }
        }
    }

    updateADBStatus();

    const list = document.getElementById('dashAccountsList');
    if (accounts.length === 0) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-users"></i> Belum ada account</div>';
    } else {
        list.innerHTML = accounts.slice(0, 5).map(a => {
        const inst = a.mumu_instance != null ? a.mumu_instance : '?';
        const vmLabel = getVmDisplayName(inst) || `#${inst}`;
        const rj = a.next_rejoin_in != null ? a.next_rejoin_in : null;
        return `
            <div class="account-card">
                <div class="account-avatar" style="background:${a.verified_username ? 'var(--green)' : 'var(--bg-card)'}">
                    ${a.name.charAt(0).toUpperCase()}
                    ${a.verified_username ? '<i class="fas fa-check-circle" style="position:absolute;bottom:-2px;right:-2px;font-size:10px;color:var(--green)"></i>' : ''}
                </div>
                <div class="account-info">
                    <div class="account-name">${esc(a.name)} <span style="font-size:11px;color:var(--text-muted)">${vmLabel}</span></div>
                    <div class="account-status">${getStatusBadge(a.status)}${a.verified_username ? ` <span style="font-size:10px;color:var(--text-muted)">${esc(a.verified_username)}</span>` : ''} <span class="countdown"${rj != null ? ` data-seconds="${rj}"` : ''} style="font-size:10px;color:var(--text-muted)"><i class="fas fa-history"></i> <span class="cd-time">${formatCountdown(rj)}</span></span></div>
                </div>
                <button class="btn btn-sm ${a.active ? 'btn-danger' : 'btn-primary'}" onclick="${a.active ? `disconnectAccount('${a.id}')` : `joinAccount('${a.id}')`}">
                    <i class="fas fa-${a.active ? 'stop' : 'play'}"></i>
                </button>
            </div>`;
        }).join('');
    }
}

function updateSidebarActivity() {
    const list = document.getElementById('dashActivityList');
    if (activityLog.length === 0) {
        list.innerHTML = '<div class="empty-state"><i class="fas fa-history"></i> Belum ada aktivitas</div>';
    } else {
        list.innerHTML = activityLog.slice(0, 8).map(a => `
            <div class="activity-item activity-level-${a.level}">
                <span class="activity-time">${esc(a.time)}</span>
                <span class="activity-msg">${esc(a.msg)}</span>
            </div>
        `).join('');
    }
}

function updateAccountsTable() {
    const tbody = document.getElementById('accountsTableBody');
    if (accounts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6"><div class="empty-state"><i class="fas fa-users"></i> Belum ada account</div></td></tr>';
        return;
    }
    tbody.innerHTML = accounts.map(a => {
        const aj = a.auto_join;
        const allSvs = (a.server_ids || []).map(id => servers.find(s => s.id === id)).filter(Boolean);
        const inst = (a.mumu_instance != null && a.mumu_instance !== undefined) ? a.mumu_instance : '-';
        const vmLabel = getVmDisplayName(inst);
        const displayName = a.app_label ? `${a.app_label}` : a.name;
        const subName = a.package_name ? `<span style="font-size:10px;color:var(--text-muted);font-family:monospace">${esc(a.package_name)}</span>` : '';
        return `
        <tr data-id="${a.id}">
            <td><input type="checkbox" class="account-checkbox" value="${a.id}" onchange="updateSelection()"></td>
            <td><strong style="cursor:pointer;color:var(--accent-1)" onclick="showAccountProfile('${a.id}')">${esc(displayName)} <i class="fas fa-external-link-alt" style="font-size:9px;opacity:0.5"></i></strong>${subName ? '<br>' + subName : ''}</td>
            <td>${getStatusBadge(a.status)}${renderDeltaKeyIcon(a)} <span class="countdown"${a.next_rejoin_in != null ? ` data-seconds="${a.next_rejoin_in}"` : ''} style="font-size:10px;color:var(--text-muted)"><i class="fas fa-history"></i> <span class="cd-time">${formatCountdown(a.next_rejoin_in)}</span></span></td>
            <td>${a.package_name ? `<span class="badge badge-info" title="${esc(a.package_name)}">Cloudphone</span> <span style="font-size:10px;color:var(--text-muted);font-family:var(--font-mono)">${esc(a.device_id || '')}</span>` : `<span class="badge badge-info">${vmLabel}</span>`}</td>
            <td style="font-size:11px">
                ${allSvs.length ? allSvs.map(s =>
                    s.id === a.server_id
                        ? `<span style="color:var(--green)">★ ${esc(s.name)}</span>`
                        : `<span style="color:var(--text-muted)">${esc(s.name)}</span>`
                ).join('<br>') : '<span style="color:var(--text-muted)">-</span>'}
            </td>
            <td>${a.last_joined || '<span style="color:var(--text-muted)">-</span>'}</td>
            <td>
                    <div class="actions">
                    <div class="actions-primary">
                        <button class="btn btn-sm ${aj ? 'btn-success' : 'btn-secondary'}" onclick="toggleAutoJoin('${a.id}', ${!aj})" title="Auto-Join ${aj ? 'ON' : 'OFF'}">
                            <i class="fas fa-${aj ? 'toggle-on' : 'toggle-off'}"></i>
                        </button>
                        ${allSvs.filter(s => s.id !== a.server_id).slice(0, 1).map(s =>
                            `<button class="btn btn-sm btn-outline" onclick="setAutoJoinServer('${a.id}', '${s.id}')" title="Auto-join: ${esc(s.name)}" style="font-size:10px;padding:2px 6px">${esc(s.name.slice(0, 6))}</button>`
                        ).join('')}
                        <button class="btn btn-sm ${a.active ? 'btn-danger' : 'btn-primary'}" onclick="${a.active ? `disconnectAccount('${a.id}')` : `joinAccount('${a.id}')`}">
                            <i class="fas fa-${a.active ? 'stop' : 'play'}"></i>
                        </button>
                    </div>
                    <div class="actions-more">
                        <button class="actions-more-btn" onclick="toggleActionsMenu(this)" title="More actions">
                            <i class="fas fa-ellipsis-v"></i>
                        </button>
                        <div class="actions-dropdown">
                            <button class="btn" onclick="deltaRefreshKey('${a.id}')"><i class="fas fa-key"></i> Delta Key</button>
                            <button class="btn" onclick="switchPage('logs');setTimeout(()=>selectAccountLog('${a.id}'),100)"><i class="fas fa-clipboard-list"></i> Logs</button>
                            <button class="btn" onclick="pushScript('${a.id}')"><i class="fas fa-upload"></i> Push Script</button>
                            <button class="btn" onclick="verifyAccount('${a.id}')"><i class="fas fa-check-circle"></i> Verify</button>
                            <button class="btn btn-warning" onclick="rollbackAccount('${a.id}')"><i class="fas fa-undo"></i> Rollback</button>
                            ${a.package_name ? `<button class="btn btn-warning" onclick="resetCloudphone('${a.id}', '${esc(a.package_name)}', '${esc(a.device_id || '')}')" title="Reset app (pm clear)"><i class="fas fa-broom"></i> Reset</button>` : ''}
                            <button class="btn" onclick="editAccount('${a.id}')"><i class="fas fa-edit"></i> Edit</button>
                            <button class="btn" onclick="moveAccountVM('${a.id}', '${esc(a.name)}', ${a.mumu_instance != null ? a.mumu_instance : 0})"><i class="fas fa-desktop"></i> Pindah VM</button>
                            <button class="btn btn-danger" onclick="deleteAccount('${a.id}')"><i class="fas fa-trash"></i> Delete</button>
                        </div>
                    </div>
                </div>
            </td>
        </tr>
    `}).join('');
}

function updateServersTable() {
    const tbody = document.getElementById('serversTableBody');
    if (servers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5"><div class="empty-state"><i class="fas fa-server"></i> Belum ada server</div></td></tr>';
        return;
    }
    tbody.innerHTML = servers.map(s => `
        <tr>
            <td>
                <div style="display:flex;align-items:center;gap:8px">
                    <div class="game-thumb" data-place="${esc(s.place_id)}" style="width:32px;height:32px;border-radius:5px;background:var(--bg-card);border:1px solid var(--border-color);flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:12px;color:var(--text-muted);overflow:hidden">
                        ${renderGameThumb(s.place_id)}
                    </div>
                    <div>
                        <strong>${esc(s.name)}</strong>
                        <div class="game-info-text" data-place="${esc(s.place_id)}" style="font-size:10px;color:var(--text-muted)">${renderGameInfoText(s.place_id)}</div>
                    </div>
                </div>
            </td>
            <td>${s.type === 'private'
                ? '<span class="badge badge-warning">Private</span>'
                : '<span class="badge badge-info">Public</span>'}</td>
            <td style="font-size:11px;font-family:var(--font-mono)">${esc(s.place_id || '-')}</td>
            <td style="font-size:11px;color:var(--text-muted);max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                ${s.server_code ? `<span title="${esc(s.server_code)}">${esc(s.server_code.slice(0, 12))}...</span>` : '-'}
            </td>
            <td>
                <div class="actions">
                    <button class="btn btn-sm btn-secondary" onclick="editServer('${s.id}')">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteServer('${s.id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `).join('');
    loadServerGameInfo();
}

const gameInfoCache = {};
function renderGameThumb(placeId) {
    const info = gameInfoCache[placeId];
    if (info && info.thumbnail) return `<img src="${esc(info.thumbnail)}" style="width:32px;height:32px;object-fit:cover">`;
    return '<i class="fas fa-gamepad"></i>';
}
function renderGameInfoText(placeId) {
    const info = gameInfoCache[placeId];
    if (info) {
        const parts = [];
        if (info.game_name) parts.push(esc(info.game_name).slice(0, 20));
        if (info.player_count != null) parts.push(`<span style="color:var(--green)">${info.player_count} playing</span>`);
        return parts.length ? parts.join(' &middot; ') : '<span style="color:var(--text-muted)">No data</span>';
    }
    return '<i class="fas fa-spinner fa-pulse" style="font-size:8px"></i>';
}
function renderDeltaKeyIcon(a) {
    const dk = a.delta_key || {};
    if (dk.has_key && dk.expires_in != null && dk.expires_in > 0) {
        const h = Math.floor(dk.expires_in / 3600);
        const m = Math.floor((dk.expires_in % 3600) / 60);
        return `<span title="Delta Key: ${h}h ${m}m lagi" style="font-size:10px;color:var(--green);margin-left:4px"><i class="fas fa-key"></i></span>`;
    }
    if (dk.has_key && dk.expires_in != null && dk.expires_in <= 0) {
        return `<span title="Delta Key expired" style="font-size:10px;color:var(--red);margin-left:4px"><i class="fas fa-key"></i></span>`;
    }
    return '';
}
async function loadServerGameInfo() {
    const thumbs = document.querySelectorAll('.game-thumb[data-place]');
    const texts = document.querySelectorAll('.game-info-text[data-place]');
    const placeIds = [...new Set([...thumbs].map(el => el.dataset.place).filter(Boolean))];
    for (const pid of placeIds) {
        if (!pid || pid === '-') continue;
        let info;
        if (gameInfoCache[pid]) {
            info = gameInfoCache[pid];
        } else {
            const res = await api('GET', `/api/game-info?place_id=${pid}`);
            if (res && res.info) {
                info = res.info;
                gameInfoCache[pid] = info;
            }
        }
        if (info) {
            thumbs.forEach(el => {
                if (el.dataset.place === pid) {
                    if (info.thumbnail) el.innerHTML = `<img src="${esc(info.thumbnail)}" style="width:32px;height:32px;object-fit:cover">`;
                    else el.innerHTML = '<i class="fas fa-gamepad" style="font-size:13px;color:var(--accent-1)"></i>';
                }
            });
            texts.forEach(el => {
                if (el.dataset.place === pid) {
                    const parts = [];
                    if (info.game_name) parts.push(esc(info.game_name).slice(0, 20));
                    if (info.player_count != null) parts.push(`<span style="color:var(--green)">${info.player_count} playing</span>`);
                    el.innerHTML = parts.length ? parts.join(' &middot; ') : '<span style="color:var(--text-muted)">No data</span>';
                }
            });
        }
    }
}

function updateActivityLog() {
    const container = document.getElementById('activityLog');
    if (activityLog.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-history"></i> Belum ada aktivitas</div>';
        return;
    }
    container.innerHTML = activityLog.map(a => `
        <div class="activity-item activity-level-${a.level}">
            <span class="activity-time">${esc(a.time)}</span>
            <span class="activity-msg">${esc(a.msg)}</span>
        </div>
    `).join('');
}

// Current filter state for inventory
let currentCategory = 'All';
let currentAccount = 'all';

function getItemCategory(itemName) {
    const name = itemName.toLowerCase();
    if (['shovel','trowel','watering can','axe','pickaxe','megaphone','build','teleporter','ladder','sign','wheelbarrow','basic pot','flashbang','sprinkler','super sprinkler','legendary sprinkler','common sprinkler','uncommon sprinkler','rare sprinkler'].some(t => name.includes(t))) return 'Gear';
    if (['egg','common egg','rare egg','legendary egg'].some(t => name.includes(t))) return 'Egg';
    if (['seed pack','rare seed pack','uncommon seed pack','legendary seed pack','common seed pack'].some(t => name.includes(t))) return 'Seed Pack';
    if (['mushroom','bamboo','tomato','corn','tulip','blueberry','carrot','sunflower','cactus','strawberry','pineapple','apple','dragon fruit','poison apple','moon bloom','cherry','acorn','coconut','banana','grape','green bean','pomegranate','baby cactus','horned melon','mango','fire fern','ghost pepper','venom spitter','dragon breath','hypno bloom','rocket pop'].some(t => name.includes(t))) return 'Seed';
    if (['bear','bunny','turtle','robin','deer','unicorn','owl','frog','dragonfly','bee','butterfly','monkey','raccoon','black dragon','ice serpent','bald eagle'].some(t => name.includes(t))) return 'Pet';
    if (['fruit','fruits'].some(t => name.includes(t))) return 'Fruit';
    if (['crate','pack'].some(t => name.includes(t))) return 'Seed Pack';
    return 'Other';
}

function getItemRarity(itemName) {
    const name = itemName.toLowerCase();
    if (['rocket pop'].some(t => name.includes(t))) return 'Legendary';
    if (['mushroom','hypno bloom','moon bloom','venom spitter','dragon breath','dragon fruit','fire fern','sunflower','poison ivy','pomegranate','poison apple','cherry','acorn','horned melon','common egg','rare egg','legendary egg'].some(t => name.includes(t))) return 'Rare';
    if (['bamboo','baby cactus','cactus','corn','pineapple','coconut','grape','banana','tulip','green bean'].some(t => name.includes(t))) return 'Uncommon';
    if (['tomato','apple','blueberry','carrot','strawberry'].some(t => name.includes(t))) return 'Common';
    if (['bear','unicorn','golden dragonfly','black dragon','ice serpent','raccoon','monkey','bald eagle'].some(t => name.includes(t))) return 'Mythic';
    if (['robin','turtle','deer','bee','butterfly'].some(t => name.includes(t))) return 'Legendary';
    if (['owl','bunny','frog'].some(t => name.includes(t))) return 'Uncommon';
    if (['gnome','flashbang','teleporter','megaphone'].some(t => name.includes(t))) return 'Epic';
    if (['common sprinkler','uncommon sprinkler'].some(t => name.includes(t))) return 'Common';
    if (['rare sprinkler'].some(t => name.includes(t))) return 'Rare';
    if (['legendary sprinkler'].some(t => name.includes(t))) return 'Legendary';
    if (['super sprinkler','super watering can'].some(t => name.includes(t))) return 'Super';
    return 'Common';
}

function formatSellValue(value) {
    if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
    if (value >= 1000) return (value / 1000).toFixed(0) + 'K';
    return value.toString();
}

function updateInventory() {
    const accountsList = document.getElementById('inventoryAccountsList');
    const itemsSummary = document.getElementById('inventoryItemsSummary');
    const categoryTabs = document.getElementById('inventoryCategoryTabs');
    const grid = document.getElementById('inventoryItemsGrid');
    
    if (!accountsList || !grid) return;
    
    const accNames = Object.keys(inventoryData);
    if (accNames.length === 0) {
        accountsList.innerHTML = '<div class="empty-state"><i class="fas fa-box-open"></i> Belum ada data inventory</div>';
        grid.innerHTML = '';
        return;
    }
    
    // Show ALL accounts that have inventory data (even if not in accounts list)
    const activeStatuses = ['connected', 'monitoring', 'active', 'in_game', 'rejoining', 'loading'];
    const displayAccNames = accNames;
    
    // Calculate total sheckles and net worth
    let totalSheckles = 0;
    let totalWorth = 0;
    const accountCards = displayAccNames.map(name => {
        const data = inventoryData[name];
        const sheckles = data.sheckles || 0;
        totalSheckles += sheckles;
        const items = data.items || [];
        items.forEach(item => {
            const price = itemThumbnails[item.name + '_price'] || 0;
            totalWorth += price * (item.count || 0);
        });
        const acc = accounts.find(a => a.name.toLowerCase() === name.toLowerCase());
        const statusBadge = acc ? `<span class="badge badge-${acc.status === 'active' ? 'success' : 'info'}" style="font-size:9px;margin-left:4px">${acc.status}</span>` : '';
        return `
        <div class="inventory-account-card ${currentAccount === name ? 'selected' : ''}" onclick="filterByAccount('${esc(name)}')">
            <div class="inventory-account-avatar">${name.charAt(0).toUpperCase()}</div>
            <div class="inventory-account-name">${esc(name)}${statusBadge}</div>
            <div class="inventory-account-stats">
                <div class="inventory-account-stat">
                    <span class="inventory-account-stat-label">Sheckles</span>
                    <span class="inventory-account-stat-value">${sheckles > 0 ? formatSellValue(sheckles) : '0'}</span>
                </div>
                <div class="inventory-account-stat">
                    <span class="inventory-account-stat-label">Items</span>
                    <span class="inventory-account-stat-value">${items.length}</span>
                </div>
            </div>
        </div>`;
    }).join('');
    
    accountsList.innerHTML = `
        <div class="inventory-account-card ${currentAccount === 'all' ? 'selected' : ''}" onclick="filterByAccount('all')">
            <div class="inventory-account-avatar" style="background: linear-gradient(135deg, #22c55e, #16a34a)"><i class="fas fa-users"></i></div>
            <div class="inventory-account-name">All accounts</div>
            <div class="inventory-account-stats">
                <div class="inventory-account-stat">
                    <span class="inventory-account-stat-label">Accounts</span>
                    <span class="inventory-account-stat-value">${displayAccNames.length}</span>
                </div>
                <div class="inventory-account-stat">
                    <span class="inventory-account-stat-label">Net Worth</span>
                    <span class="inventory-account-stat-value">${formatSellValue(totalWorth)}</span>
                </div>
            </div>
        </div>
        ${accountCards}`;
    
    // Collect all unique items across online accounts
    const allItems = {};
    displayAccNames.forEach(name => {
        const data = inventoryData[name];
        const items = data.items || [];
        items.forEach(item => {
            const key = item.name || item.id;
            if (!allItems[key]) {
                allItems[key] = {
                    name: item.name || item.id,
                    id: item.id || '',
                    count: 0,
                    thumbnail: item.thumbnail || itemThumbnails[item.name] || '',
                    category: getItemCategory(item.name || item.id),
                    rarity: getItemRarity(item.name || item.id),
                    accounts: []
                };
            }
            allItems[key].count += item.count || 1;
            if (!allItems[key].accounts.includes(name)) {
                allItems[key].accounts.push(name);
            }
        });
    });
    
    const itemList = Object.values(allItems);
    const uniqueCount = itemList.length;
    
    // Count items by category
    const categoryCounts = { All: uniqueCount, Pet: 0, Seed: 0, Fruit: 0, Egg: 0, 'Seed Pack': 0, Gear: 0, Other: 0 };
    itemList.forEach(item => {
        if (categoryCounts[item.category] !== undefined) {
            categoryCounts[item.category]++;
        } else {
            categoryCounts.Other++;
        }
    });
    
    // Update summary
    itemsSummary.textContent = `All accounts · ${uniqueCount} unique`;
    
    // Render category tabs
    categoryTabs.innerHTML = Object.entries(categoryCounts)
        .filter(([cat, count]) => count > 0)
        .map(([cat, count]) => `
            <div class="category-tab ${currentCategory === cat ? 'active' : ''}" onclick="filterByCategory('${esc(cat)}')">
                ${cat} <span class="count">${count}</span>
            </div>
        `).join('');
    
    // Filter items by category and account
    let filtered = itemList;
    if (currentCategory !== 'All') {
        filtered = filtered.filter(item => item.category === currentCategory);
    }
    if (currentAccount !== 'all') {
        filtered = filtered.filter(item => item.accounts.includes(currentAccount));
    }
    
    // Apply search filter
    const searchTerm = document.getElementById('inventorySearch')?.value?.toLowerCase() || '';
    if (searchTerm) {
        filtered = filtered.filter(item => item.name.toLowerCase().includes(searchTerm));
    }
    
    // Sort by count descending
    filtered.sort((a, b) => b.count - a.count);
    
    // Render items
    grid.innerHTML = filtered.map(item => {
        const thumb = item.thumbnail;
        const imgHtml = thumb ? `<img src="${esc(thumb)}" class="inventory-item-thumb" onerror="this.style.display='none'" loading="lazy">` : '<div class="inventory-item-thumb"><i class="fas fa-box" style="font-size:16px;color:var(--text-muted)"></i></div>';
        const rarityClass = item.rarity.toLowerCase().replace(' ', '-');
        const catClass = item.category.toLowerCase().replace(' ', '-');
        
        return `
        <div class="inventory-item-card rarity-${rarityClass}">
            ${imgHtml}
            <div class="inventory-item-info">
                <div class="inventory-item-top">
                    <span class="inventory-item-name">${esc(item.name)}</span>
                    <span class="inventory-item-qty">&times;${item.count.toLocaleString()}</span>
                </div>
                <div class="inventory-item-bottom">
                    <span class="inventory-item-category cat-${catClass}">${item.category}</span>
                    <span class="inventory-item-rarity rarity-${rarityClass}">${item.rarity}</span>
                    <span class="inventory-item-accounts"><i class="fas fa-user"></i> ${item.accounts.length}</span>
                </div>
            </div>
        </div>`;
    }).join('');
}

function filterByCategory(category) {
    currentCategory = category;
    updateInventory();
}

function filterByAccount(account) {
    currentAccount = account;
    // Update selected state
    document.querySelectorAll('.inventory-account-card').forEach(card => {
        card.classList.remove('selected');
        // Find the card that matches the account
        const nameEl = card.querySelector('.inventory-account-name');
        if (nameEl) {
            const cardName = nameEl.textContent.trim().toLowerCase();
            if ((account === 'all' && cardName.includes('all accounts')) ||
                (account !== 'all' && cardName.includes(account.toLowerCase()))) {
                card.classList.add('selected');
            }
        }
    });
    updateInventory();
}

function filterInventoryItems() {
    updateInventory();
}

async function refreshInventory() {
    const inv = await api('GET', '/api/inventory');
    if (inv) inventoryData = inv;
    updateInventory();
}

function updateAccountSelect() {
    const container = document.getElementById('accServerList');
    const editId = document.getElementById('editAccountId').value;
    const acc = accounts.find(a => a.id === editId);
    const selectedIds = (acc && acc.server_ids) || [];
    const autoId = (acc && acc.server_id) || '';
    if (!servers.length) {
        container.innerHTML = '<div style="padding:12px;text-align:center;color:var(--text-muted);font-size:12px">Belum ada server</div>';
    } else {
        container.innerHTML = servers.map(s => {
            const checked = selectedIds.includes(s.id) ? 'checked' : '';
            const isAuto = autoId === s.id;
            const typeBadge = s.type === 'private' ? '<span class="badge badge-warning">Private</span>' : '<span class="badge badge-info">Public</span>';
            return `
            <label class="server-check-item">
                <input type="checkbox" class="server-check" value="${s.id}" ${checked} onchange="updateServerCheck(this)">
                <span>${esc(s.name)}</span>
                ${typeBadge}
                <input type="radio" name="autoServer" value="${s.id}" ${isAuto ? 'checked' : ''} ${!checked ? 'disabled' : ''} title="Auto-join target" style="margin-left:auto">
                <span style="font-size:10px;color:var(--text-muted);margin-left:2px">auto</span>
            </label>`;
        }).join('');
    }

    const instSel = document.getElementById('accInstance');
    const curInst = instSel.value;
    const serials = settings.mumu_serials || [];
    if (serials.length === 0) serials.push('');
    instSel.innerHTML = serials.map((s, i) => {
        const vm = getVmDisplayName(i);
        const label = s ? `${vm} (${s})` : `${vm} (kosong)`;
        return `<option value="${i}">${label}</option>`;
    }).join('');
    if (curInst) instSel.value = curInst;
}

async function loadRemotePackages() {
    try {
        const res = await api('GET', '/api/remote/monitors');
        if (!res || !res.monitors || !res.monitors.length) return;
        const usedPkgs = new Set(accounts.map(a => a.package_name).filter(Boolean));
        const available = [];
        res.monitors.forEach(m => {
            (m.packages || []).forEach(p => {
                if (!usedPkgs.has(p.package)) {
                    available.push(p.package);
                }
            });
        });
        const container = document.getElementById('remotePkgButtons');
        if (!container) return;
        container.innerHTML = '';
        if (!available.length) return;
        available.forEach(pkg => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'btn btn-sm btn-secondary';
            btn.style.cssText = 'font-size:10px;font-family:monospace;padding:2px 8px';
            btn.textContent = pkg;
            btn.onclick = () => { document.getElementById('accPackage').value = pkg; };
            container.appendChild(btn);
        });
    } catch(e) {}
}

function getStatusBadge(status) {
    const badges = {
        idle: '<span class="badge badge-idle">Idle</span>',
        joining: '<span class="badge badge-info">Joining</span>',
        connected: '<span class="badge badge-success">Connected</span>',
        monitoring: '<span class="badge badge-success">Monitoring</span>',
        error: '<span class="badge badge-danger">Error</span>',
        kicked: '<span class="badge badge-danger">Kicked</span>',
        left: '<span class="badge badge-warning">Left</span>'
    };
    return badges[status] || `<span class="badge badge-idle">${esc(status)}</span>`;
}

function formatCountdown(seconds) {
    if (seconds == null || seconds < 0) return '—';
    if (seconds === 0) return '0s';
    if (seconds < 60) return `${seconds}s`;
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    if (m < 60) return `${m}m ${s}s`;
    const h = Math.floor(m / 60);
    const rm = m % 60;
    return `${h}h ${rm}m`;
}

function updateCountdowns() {
    document.querySelectorAll('.countdown[data-seconds]').forEach(el => {
        let secs = parseInt(el.dataset.seconds) || 0;
        if (secs > 0) {
            secs -= 5;
            el.dataset.seconds = Math.max(0, secs);
            const span = el.querySelector('.cd-time');
            if (span) span.textContent = formatCountdown(Math.max(0, secs));
        }
    });
}

let countdownInterval = null;

function esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
}

function togglePassword(fieldId, btn) {
    const el = document.getElementById(fieldId);
    el.type = el.type === 'password' ? 'text' : 'password';
    btn.innerHTML = el.type === 'password'
        ? '<i class="fas fa-eye"></i>'
        : '<i class="fas fa-eye-slash"></i>';
}

function toggleServerFields() {
    const isPrivate = document.getElementById('svType').value === 'private';
    document.querySelectorAll('.private-field').forEach(el => {
        el.style.display = isPrivate ? 'block' : 'none';
    });
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
}

function openModal(id) {
    document.getElementById(id).classList.add('active');
}

let _dynamicModal = null;
function showModal(html) {
    if (_dynamicModal) { _dynamicModal.remove(); _dynamicModal = null; }
    const div = document.createElement('div');
    div.className = 'modal active';
    div.style.display = 'flex';
    div.innerHTML = `<div class="modal-content" style="max-width:380px">${html}</div>`;
    div.addEventListener('click', function(e) { if (e.target === this) closeDynamicModal(); });
    document.body.appendChild(div);
    _dynamicModal = div;
}
function closeDynamicModal() {
    if (_dynamicModal) { _dynamicModal.remove(); _dynamicModal = null; }
}

async function scanVmCookies() {
    const btn = document.getElementById('btnScanCookies');
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> Scanning...';
    showModal('<div style="text-align:center"><i class="fas fa-spinner fa-pulse" style="font-size:24px"></i><p style="margin-top:12px">Memindai cookie dari semua VM...</p></div>');
    try {
        const res = await api('POST', '/api/accounts/scan-vm', {});
        if (!res) { closeDynamicModal(); alert('Gagal menghubungi server'); return; }
        let html = '<div style="max-height:400px;overflow-y:auto">';
        html += `<p style="margin-bottom:10px;font-size:13px"><strong>Ditambahkan:</strong> ${res.added} &middot; <strong>Sudah ada:</strong> ${res.already_exist}</p>`;
        for (const r of res.results || []) {
            const icon = r.status === 'added' ? '<i class="fas fa-check-circle" style="color:var(--green)"></i>'
                : r.status === 'exists' ? '<i class="fas fa-info-circle" style="color:var(--accent-2)"></i>'
                : r.status === 'not_found' ? '<i class="fas fa-search" style="color:var(--text-muted)"></i>'
                : '<i class="fas fa-times-circle" style="color:var(--red)"></i>';
            html += `<div style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px solid var(--border-color);font-size:12px">
                ${icon}
                <div><strong>${esc(r.vm)}</strong> — ${esc(r.message)}</div>
            </div>`;
        }
        html += '</div>';
        html += `<div style="margin-top:12px;text-align:center"><button class="btn btn-primary" onclick="closeDynamicModal();refreshData()"><i class="fas fa-sync"></i> Refresh</button></div>`;
        closeDynamicModal();
        showModal(html);
    } catch (e) {
        closeDynamicModal();
        showModal(`<div style="text-align:center;color:var(--red)"><i class="fas fa-exclamation-triangle" style="font-size:24px"></i><p>${esc(e.message || 'Error')}</p></div>`);
    }
    btn.disabled = false; btn.innerHTML = '<i class="fas fa-sync-alt"></i> Scan & Import';
}

async function scanServersFromAccounts() {
    const btn = document.getElementById('btnScanServers');
    btn.disabled = true; btn.innerHTML = '<i class="fas fa-spinner fa-pulse"></i> Scanning...';
    showModal('<div style="text-align:center"><i class="fas fa-spinner fa-pulse" style="font-size:24px"></i><p style="margin-top:12px">Memindai game dari semua akun...</p></div>');
    try {
        const res = await api('POST', '/api/servers/scan-from-accounts', {});
        if (!res) { closeDynamicModal(); alert('Gagal menghubungi server'); return; }
        let html = '<div style="max-height:400px;overflow-y:auto">';
        html += `<p style="margin-bottom:10px;font-size:13px"><strong>Ditambahkan:</strong> ${res.added} &middot; <strong>Sudah ada:</strong> ${res.already_exist}</p>`;
        for (const r of res.results || []) {
            const icon = r.status === 'added' ? '<i class="fas fa-check-circle" style="color:var(--green)"></i>'
                : r.status === 'exists' ? '<i class="fas fa-info-circle" style="color:var(--accent-2)"></i>'
                : '<i class="fas fa-times-circle" style="color:var(--text-muted)"></i>';
            html += `<div style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px solid var(--border-color);font-size:12px">
                ${icon}
                <div><strong>${esc(r.account)}</strong> — ${esc(r.message)}</div>
            </div>`;
        }
        html += '</div>';
        html += `<div style="margin-top:12px;text-align:center"><button class="btn btn-primary" onclick="closeDynamicModal();switchPage('servers');refreshData()"><i class="fas fa-sync"></i> Refresh</button></div>`;
        closeDynamicModal();
        showModal(html);
    } catch (e) {
        closeDynamicModal();
        showModal(`<div style="text-align:center;color:var(--red)"><i class="fas fa-exclamation-triangle" style="font-size:24px"></i><p>${esc(e.message || 'Error')}</p></div>`);
    }
    btn.disabled = false; btn.innerHTML = '<i class="fas fa-search"></i> Scan dari Akun';
}

async function deltaRefreshKey(accId) {
    const res = await api('POST', `/api/delta/refresh-key/${accId}`, {});
    if (res && res.success) {
        showToast(`Delta Key refreshed: ${res.key_preview || 'OK'}`, 'success');
    } else {
        showToast(`Delta Key error: ${(res && res.error) || 'Unknown'}`, 'error');
    }
    refreshData();
}

function setPlatform(platform) {
    document.getElementById('accPlatform').value = platform;
    const btnCloud = document.getElementById('btnPlatformCloudphone');
    const btnMumu = document.getElementById('btnPlatformMumu');
    const pkgGroup = document.getElementById('pkgNameGroup');
    const mumuGroup = document.getElementById('mumuInstGroup');
    if (platform === 'cloudphone') {
        btnCloud.className = 'btn btn-sm btn-primary';
        btnMumu.className = 'btn btn-sm btn-secondary';
        pkgGroup.style.display = 'block';
        mumuGroup.style.display = 'none';
    } else {
        btnCloud.className = 'btn btn-sm btn-secondary';
        btnMumu.className = 'btn btn-sm btn-primary';
        pkgGroup.style.display = 'none';
        mumuGroup.style.display = 'block';
    }
}

function showAddAccount() {
    document.getElementById('accountModalTitle').textContent = 'Tambah Account';
    document.getElementById('editAccountId').value = '';
    document.getElementById('accName').value = '';
    document.getElementById('accCookie').value = '';
    document.getElementById('accInstance').value = '0';
    document.getElementById('accPackage').value = '';
    setPlatform('cloudphone');
    openModal('accountModal');
    updateAccountSelect();
    loadRemotePackages();
}

function updateServerCheck(el) {
    const radio = el.closest('.server-check-item').querySelector('input[name="autoServer"]');
    if (radio) radio.disabled = !el.checked;
}

function getServerCheckData() {
    const checked = [];
    let autoId = '';
    document.querySelectorAll('.server-check:checked').forEach(cb => checked.push(cb.value));
    const autoSel = document.querySelector('input[name="autoServer"]:checked');
    if (autoSel) autoId = autoSel.value;
    if (!autoId && checked.length) autoId = checked[0];
    return { server_ids: checked, server_id: autoId };
}

async function saveAccount() {
    const id = document.getElementById('editAccountId').value;
    const name = document.getElementById('accName').value.trim();
    const cookie = document.getElementById('accCookie').value.trim();
    const { server_ids, server_id } = getServerCheckData();
    const platform = document.getElementById('accPlatform').value;

    if (!name) { showToast('Nama account harus diisi', 'warning'); return; }

    const data = { name, cookie, server_id, server_ids };

    if (platform === 'cloudphone') {
        data.package_name = document.getElementById('accPackage').value.trim();
        data.mumu_instance = 0;
    } else {
        data.mumu_instance = parseInt(document.getElementById('accInstance').value) || 0;
        data.package_name = '';
    }

    if (id) {
        await api('PUT', `/api/accounts/${id}`, data);
    } else {
        await api('POST', '/api/accounts', data);
    }
    closeModal('accountModal');
    await refreshData();
}

async function editAccount(id) {
    const acc = accounts.find(a => a.id === id);
    if (!acc) return;
    document.getElementById('accountModalTitle').textContent = 'Edit Account';
    document.getElementById('editAccountId').value = id;
    document.getElementById('accName').value = acc.name;
    document.getElementById('accCookie').value = acc.cookie || '';
    document.getElementById('accPackage').value = acc.package_name || '';
    document.getElementById('accInstance').value = (acc.mumu_instance != null) ? acc.mumu_instance : 0;
    const platform = acc.package_name ? 'cloudphone' : 'mumu';
    setPlatform(platform);
    openModal('accountModal');
    updateAccountSelect();
    if (platform === 'cloudphone') loadRemotePackages();
}

async function showAccountProfile(accId) {
    const acc = accounts.find(a => a.id === accId);
    if (!acc) return;
    showModal(`<div style="text-align:center;margin-bottom:12px"><i class="fas fa-spinner fa-pulse" style="font-size:32px;color:var(--accent-1)"></i></div><p style="text-align:center;color:var(--text-muted);font-size:13px">Loading profile...</p>`);
    const res = await api('GET', `/api/accounts/${accId}/profile`);
    closeDynamicModal();
    if (!res || !res.profile) { showToast('Gagal load profile', 'error'); return; }
    const p = res.profile;
    const presenceLabels = {0: 'Offline', 1: 'Online', 2: 'In Game', 3: 'Studio'};
    const presenceColors = {0: 'var(--red)', 1: 'var(--green)', 2: '#5865f2', 3: 'var(--yellow)'};
    const ptype = p.presence_type || 0;
    showModal(`
        <div style="text-align:center">
            <img src="${esc(p.avatar)}" style="width:80px;height:80px;border-radius:50%;border:3px solid var(--accent-1);margin-bottom:8px" onerror="this.outerHTML='<div style=\\'width:80px;height:80px;border-radius:50%;background:var(--bg-input);border:3px solid var(--accent-1);display:flex;align-items:center;justify-content:center;margin:0 auto 8px\\'><i class=\\'fas fa-user\\' style=\\'font-size:28px;color:var(--text-muted)\\'>'">
            <h3 style="font-size:16px;font-weight:700">${esc(p.username)}</h3>
            ${p.display_name && p.display_name !== p.username ? `<div style="font-size:12px;color:var(--text-muted)">${esc(p.display_name)}</div>` : ''}
            <div style="margin-top:6px">
                <span style="display:inline-flex;align-items:center;gap:4px;padding:3px 10px;border-radius:12px;font-size:11px;font-weight:600;background:${presenceColors[ptype]}22;color:${presenceColors[ptype]};border:1px solid ${presenceColors[ptype]}44">
                    <span style="width:6px;height:6px;border-radius:50%;background:${presenceColors[ptype]}"></span>
                    ${presenceLabels[ptype]}
                </span>
            </div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin:14px 0">
            <div style="text-align:center;padding:8px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border-color)">
                <div style="font-size:16px;font-weight:700;color:var(--yellow)">${p.robux != null ? p.robux.toLocaleString() : '?'}</div>
                <div style="font-size:10px;color:var(--text-muted)">Robux</div>
            </div>
            <div style="text-align:center;padding:8px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border-color)">
                <div style="font-size:16px;font-weight:700">${p.friend_count != null ? p.friend_count.toLocaleString() : '?'}</div>
                <div style="font-size:10px;color:var(--text-muted)">Friends</div>
            </div>
            <div style="text-align:center;padding:8px;background:var(--bg-input);border-radius:6px;border:1px solid var(--border-color)">
                <div style="font-size:16px;font-weight:700">${p.created ? p.created : '?'}</div>
                <div style="font-size:10px;color:var(--text-muted)">Joined</div>
            </div>
        </div>
        ${p.description ? `<div style="font-size:11px;color:var(--text-muted);padding:8px;background:var(--bg-input);border-radius:5px;margin-bottom:10px;border:1px solid var(--border-color);text-align:center">${esc(p.description)}</div>` : ''}
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;font-size:11px">
            <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px;border:1px solid var(--border-color)">
                <span style="color:var(--text-muted)">Status</span>
                <div style="font-weight:600">${getStatusBadge(p.status)}</div>
            </div>
            <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px;border:1px solid var(--border-color)">
                <span style="color:var(--text-muted)">VM</span>
                <div style="font-weight:600">${esc(getVmDisplayName(p.mumu_instance))}</div>
            </div>
            <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px;border:1px solid var(--border-color)">
                <span style="color:var(--text-muted)">Last Join</span>
                <div style="font-weight:600">${p.last_joined || '-'}</div>
            </div>
            <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px;border:1px solid var(--border-color)">
                <span style="color:var(--text-muted)">Auto-Join</span>
                <div style="font-weight:600">${p.auto_join ? '<span style="color:var(--green)">ON</span>' : '<span style="color:var(--text-muted)">OFF</span>'}</div>
            </div>
        </div>
        <div style="text-align:center;margin-top:12px;padding-top:10px;border-top:1px solid var(--border-color)">
            <button class="btn btn-secondary" onclick="closeDynamicModal()">Tutup</button>
        </div>
    `);
}

async function moveAccountVM(id, name, currentVm) {
    const serials = settings.mumu_serials || [];
    const vmCount = Math.max(serials.length, 1);
    const vms = [];
    for (let i = 0; i < vmCount; i++) vms.push(getVmDisplayName(i));
    const sel = vms.map((v, i) =>
        `<label style="display:flex;align-items:center;gap:8px;padding:8px 10px;cursor:pointer;border-radius:5px;${i === currentVm ? 'background:var(--accent-subtle)' : ''}">
            <input type="radio" name="vmChoice" value="${i}" ${i === currentVm ? 'checked' : ''}>
            <span style="font-size:13px">${esc(v)}</span>
            ${i === currentVm ? '<span style="font-size:10px;color:var(--text-muted)">(current)</span>' : ''}
        </label>`
    ).join('');
    showModal(`
        <div style="text-align:center;margin-bottom:16px">
            <div style="font-size:28px;margin-bottom:8px"><i class="fas fa-desktop" style="color:var(--accent-1)"></i></div>
            <h3 style="font-size:16px;font-weight:600">Pindah VM</h3>
            <p style="font-size:12px;color:var(--text-muted);margin-top:4px">${esc(name)}</p>
        </div>
        <div style="display:grid;gap:4px">${sel}</div>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;padding-top:12px;border-top:1px solid var(--border-color)">
            <button class="btn btn-secondary" onclick="closeDynamicModal()">Batal</button>
            <button class="btn btn-primary" id="btnMoveVM" onclick="closeDynamicModal();doMoveVM('${id}', parseInt(document.querySelector('input[name=vmChoice]:checked').value))"><i class="fas fa-check"></i> Pindah</button>
        </div>
    `);
}

async function doMoveVM(id, instance) {
    const res = await api('POST', `/api/accounts/${id}/move-vm`, { mumu_instance: instance });
    if (res && res.mumu_instance != null) {
        showToast(`Dipindah ke VM ${instance}`, 'success');
        await refreshData();
        refreshMuMuVMs();
    } else {
        showToast('Gagal pindah VM', 'error');
    }
}

async function deleteAccount(id) {
    if (!confirm('Hapus account ini?')) return;
    await api('DELETE', `/api/accounts/${id}`);
    await refreshData();
}

function toggleSelectAll(el) {
    document.querySelectorAll('.account-checkbox').forEach(cb => { cb.checked = el.checked; });
    updateSelection();
}

function updateSelection() {
    const checked = document.querySelectorAll('.account-checkbox:checked');
    const count = checked.length;
    document.getElementById('selectedCount').textContent = count;
    document.getElementById('btnDeleteSelected').style.display = count > 0 ? '' : 'none';
    document.getElementById('selectAllAccounts').checked = count > 0 && count === document.querySelectorAll('.account-checkbox').length;
}

async function deleteSelectedAccounts() {
    const checked = document.querySelectorAll('.account-checkbox:checked');
    const ids = Array.from(checked).map(cb => cb.value);
    if (!ids.length) return;
    if (!confirm(`Hapus ${ids.length} account?`)) return;
    await api('POST', '/api/accounts/batch-delete', { ids });
    document.getElementById('selectAllAccounts').checked = false;
    await refreshData();
}

let _gameSearchTimeout = null;
async function searchGame(q) {
    clearTimeout(_gameSearchTimeout);
    const container = document.getElementById('svGameResults');
    if (q.length < 2) { container.style.display = 'none'; return; }
    _gameSearchTimeout = setTimeout(async () => {
        const res = await api('GET', `/api/games/search?q=${encodeURIComponent(q)}`);
        if (!res || !res.results || res.results.length === 0) {
            container.innerHTML = '<div style="padding:10px;color:var(--text-muted);font-size:12px">Game tidak ditemukan</div>';
            container.style.display = 'block';
            return;
        }
        container.innerHTML = res.results.map(g => `
            <div class="server-check-item" style="cursor:pointer" onclick="selectGame(${g.place_id}, '${esc(g.name)}')">
                <div style="display:flex;align-items:center;gap:8px">
                    ${g.thumbnail ? `<img src="${esc(g.thumbnail)}" style="width:28px;height:28px;border-radius:4px;object-fit:cover">` : '<i class="fas fa-gamepad" style="width:28px;text-align:center;color:var(--text-muted)"></i>'}
                    <div>
                        <strong style="font-size:12px">${esc(g.name)}</strong>
                        <div style="font-size:10px;color:var(--text-muted)">${g.player_count} playing &middot; ID: ${g.place_id}</div>
                    </div>
                </div>
            </div>
        `).join('');
        container.style.display = 'block';
    }, 300);
}
function selectGame(placeId, name) {
    document.getElementById('svPlaceId').value = placeId;
    document.getElementById('svName').value = name;
    document.getElementById('svGameResults').style.display = 'none';
}

function showAddServer() {
    document.getElementById('serverModalTitle').textContent = 'Tambah Server';
    document.getElementById('editServerId').value = '';
    document.getElementById('svName').value = '';
    document.getElementById('svType').value = 'public';
    document.getElementById('svPlaceId').value = '';
    document.getElementById('svCode').value = '';
    document.getElementById('svLink').value = '';
    document.getElementById('svGameSearch').value = '';
    document.getElementById('svGameResults').style.display = 'none';
    document.getElementById('svGameResults').innerHTML = '';
    toggleServerFields();
    openModal('serverModal');
    setTimeout(() => document.getElementById('svGameSearch').focus(), 200);
}

async function saveServer() {
    const id = document.getElementById('editServerId').value;
    const name = document.getElementById('svName').value.trim();
    const type = document.getElementById('svType').value;
    const place_id = document.getElementById('svPlaceId').value.trim();
    const server_code = document.getElementById('svCode').value.trim();
    const link = document.getElementById('svLink').value.trim();

    if (!name) { showToast('Nama server harus diisi', 'warning'); return; }

    const data = { name, type, place_id, server_code, link };

    if (id) {
        await api('PUT', `/api/servers/${id}`, data);
    } else {
        await api('POST', '/api/servers', data);
    }
    closeModal('serverModal');
    await refreshData();
}

async function editServer(id) {
    const sv = servers.find(s => s.id === id);
    if (!sv) return;
    document.getElementById('serverModalTitle').textContent = 'Edit Server';
    document.getElementById('editServerId').value = id;
    document.getElementById('svName').value = sv.name;
    document.getElementById('svType').value = sv.type;
    document.getElementById('svPlaceId').value = sv.place_id || '';
    document.getElementById('svCode').value = sv.server_code || '';
    document.getElementById('svLink').value = sv.link || '';
    toggleServerFields();
    openModal('serverModal');
}

async function deleteServer(id) {
    if (!confirm('Hapus server ini?')) return;
    await api('DELETE', `/api/servers/${id}`);
    await refreshData();
}

async function verifyAllAccounts() {
    const btn = document.getElementById('btnVerifyAll');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Verifying...';
    const res = await api('POST', '/api/accounts/verify-all');
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-check-double"></i> Verify All';
    if (!res || !res.results) {
        if (res?._error) alert(`Gagal: HTTP ${res._status} ${res._statusText}`);
        else alert('Gagal memverifikasi');
        return;
    }
    const valid = res.results.filter(r => r.valid).length;
    const invalid = res.results.filter(r => !r.valid).length;
    const details = res.results.filter(r => !r.valid).map(r => `${r.name}: ${r.error || 'invalid'}`);
    let msg = `✅ ${valid} valid, ❌ ${invalid} invalid`;
    if (details.length) msg += '\n\n' + details.join('\n');
    alert(msg);
    refreshData();
}

async function verifyAccount(accId) {
    const res = await api('POST', `/api/accounts/${accId}/verify`);
    if (res && res.valid) {
        alert(`✓ Cookie valid!\nUsername: ${res.username}\nRobux: ${res.robux}`);
    } else {
        alert(`✗ Cookie invalid: ${res?.error || 'unknown'}`);
    }
    refreshData();
}

async function rollbackAccount(accId) {
    if (!confirm('Rollback akun ini?\nRoblox akan force-stop + rejoin (item consumption di-revert).')) return;
    const res = await api('POST', `/api/accounts/${accId}/rollback`);
    if (res && res.success) {
        showToast('Rollback executed: force-stop + rejoin', 'success');
    } else {
        showToast('Rollback failed: ' + (res?.error || 'unknown'), 'error');
    }
    refreshData();
}

async function resetCloudphone(accId, packageName, deviceId) {
    if (!confirm(`Reset app ${packageName}?\nSemua data & cookie akan dihapus (pm clear).\nSetelah reset, app akan auto-rejoin.`)) return;
    const res = await api('POST', `/api/accounts/${accId}/reset`);
    if (res && res.success) {
        showToast(`Reset queued: ${packageName}`, 'success');
    } else {
        showToast('Reset failed: ' + (res?.error || 'unknown'), 'error');
    }
    refreshData();
}

async function showDeviceHealth() {
    const res = await api('GET', '/api/remote/health');
    const devices = res?.devices || [];
    if (devices.length === 0) {
        showToast('Belum ada data kesehatan device', 'info');
        return;
    }
    let html = '<div style="display:flex;flex-direction:column;gap:16px">';
    for (const d of devices) {
        const mem = d.memory || {};
        const sto = d.storage || {};
        const bat = d.battery || {};
        const up = d.uptime || {};
        html += `
        <div style="background:var(--bg-input);border-radius:8px;padding:16px;border:1px solid var(--border-color)">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <strong style="font-size:14px"><i class="fas fa-mobile-alt"></i> ${esc(d.device_id)}</strong>
                <span style="font-size:11px;color:var(--text-muted)">Updated: ${d.updated_at ? new Date(d.updated_at * 1000).toLocaleTimeString() : '-'}</span>
            </div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:12px">
                <div><i class="fas fa-clock" style="color:var(--accent-1);width:16px"></i> Uptime: <strong>${up.formatted || '-'}</strong></div>
                <div><i class="fas fa-microchip" style="color:var(--accent-2);width:16px"></i> Root: <strong>${d.root ? 'Yes' : 'No'}</strong></div>
                <div style="grid-column:span 2">
                    <i class="fas fa-memory" style="color:var(--accent-1);width:16px"></i> Memory: <strong>${mem.used_mb || 0} MB / ${mem.total_mb || 0} MB</strong> (${mem.used_percent || 0}%)
                    <div style="background:var(--bg-card);border-radius:4px;height:6px;margin-top:4px;overflow:hidden">
                        <div style="background:${(mem.used_percent||0) > 80 ? 'var(--red)' : (mem.used_percent||0) > 60 ? 'var(--yellow)' : 'var(--green)'};height:100%;width:${mem.used_percent||0}%;border-radius:4px"></div>
                    </div>
                </div>
                <div style="grid-column:span 2">
                    <i class="fas fa-hdd" style="color:var(--accent-2);width:16px"></i> Storage: <strong>${sto.used_gb || 0} GB / ${sto.total_gb || 0} GB</strong> (${sto.used_percent || 0}%)
                    <div style="background:var(--bg-card);border-radius:4px;height:6px;margin-top:4px;overflow:hidden">
                        <div style="background:${(sto.used_percent||0) > 90 ? 'var(--red)' : (sto.used_percent||0) > 70 ? 'var(--yellow)' : 'var(--green)'};height:100%;width:${sto.used_percent||0}%;border-radius:4px"></div>
                    </div>
                </div>
                ${bat.level != null ? `
                <div style="grid-column:span 2">
                    <i class="fas fa-battery-${bat.level > 70 ? 'full' : bat.level > 30 ? 'half' : 'quarter'}" style="color:${bat.level > 70 ? 'var(--green)' : bat.level > 30 ? 'var(--yellow)' : 'var(--red)'};width:16px"></i> Battery: <strong>${bat.level}%</strong> ${bat.status || ''} ${bat.temperature_c ? `| ${bat.temperature_c}°C` : ''}
                </div>` : ''}
            </div>
        </div>`;
    }
    html += '</div>';
    showModal(`<div style="padding:16px"><h3 style="margin:0 0 16px;font-size:16px"><i class="fas fa-heartbeat"></i> Device Health</h3>${html}<div style="text-align:right;margin-top:16px"><button class="btn btn-secondary" onclick="closeDynamicModal()">Close</button></div></div>`);
    if (_dynamicModal) {
        const mc = _dynamicModal.querySelector('.modal-content');
        if (mc) mc.style.maxWidth = '500px';
    }
}

async function injectAccount(accId) {
    if (!confirm('Inject cookie ke device via ADB?\nApp Roblox akan di-reset.')) return;
    const res = await api('POST', `/api/accounts/${accId}/inject`);
    if (res && res.success) {
        alert(`✓ Cookie injected!\nMethod: ${res.methods_tried?.join(', ') || 'ok'}`);
    } else {
        alert(`✗ Inject failed: ${res?.error || 'unknown'}${res?.note ? '\n' + res.note : ''}`);
    }
    refreshData();
}


async function joinAccount(accId) {
    const acc = accounts.find(a => a.id === accId);
    const res = await api('POST', `/api/accounts/${accId}/join`);
    if (res && res.status === 'joining') {
        await refreshData();
        showToast(`Join ${acc?.name || accId}...`, 'info');
    }
}

async function disconnectAccount(accId) {
    await api('POST', `/api/accounts/${accId}/disconnect`);
    await refreshData();
}

async function toggleAutoJoin(accId, enabled) {
    await api('POST', `/api/accounts/${accId}/auto-join`, { auto_join: enabled });
    if (enabled) {
        await api('PUT', '/api/settings', { auto_join_enabled: true });
    }
    refreshData();
}

async function setAutoJoinServer(accId, serverId) {
    await api('POST', `/api/accounts/${accId}/auto-join`, { server_id: serverId });
    refreshData();
}

async function joinAllAccounts() {
    const res = await api('POST', '/api/join-all');
    if (res && res.status === 'joining') {
        setTimeout(refreshData, 1000);
        showToast('Joining all accounts...', 'info');
    }
}

async function saveSettings() {
    const serials = [];
    document.querySelectorAll('.mumu-serial').forEach(el => {
        serials.push(el.value.trim() || '');
    });
    
    const data = {
        auto_join_enabled: document.getElementById('autoJoinEnabled').checked,
        rejoin_delay: parseInt(document.getElementById('rejoinDelay').value) || 3,
        max_retries: parseInt(document.getElementById('maxRetries').value) || 5,
        monitor_interval: parseInt(document.getElementById('monitorInterval').value) || 2,
        rejoin_interval: (parseInt(document.getElementById('rejoinInterval').value) || 0) * 60,
        adb_path: document.getElementById('adbPath').value.trim(),
        mumu_serials: serials,
        webhook_url: document.getElementById('webhookUrl').value.trim(),
        webhook_enabled: document.getElementById('webhookEnabled').checked,
        auto_restart_vm: document.getElementById('autoRestartVM').checked,
        discord_client_id: document.getElementById('discordClientId').value.trim(),
        discord_client_secret: document.getElementById('discordClientSecret').value.trim(),
        discord_guild_id: document.getElementById('discordGuildId').value.trim(),
        auto_verify_interval: parseInt(document.getElementById('autoVerifyInterval').value) || 0,
        delta_auto_key: document.getElementById('deltaAutoKey').checked,
        dashboard_url: document.getElementById('dashboardUrl').value.trim() || 'http://localhost:5000',
    };
    const pwd = document.getElementById('dashboardPassword').value.trim();
    if (pwd) data.dashboard_password = pwd;
    const res = await api('PUT', '/api/settings', data);
    if (res && !res._error) {
        Object.assign(settings, res);
        try { updateDashboard(); } catch(e) {}
        showToast('Settings saved!', 'success');
    } else {
        showToast('Gagal simpan settings', 'error');
    }
}

async function restoreFromBackup() {
    if (!confirm('Kembalikan data dari backup (data.json.bak)?\nData saat ini akan ditimpa.')) return;
    const btn = document.getElementById('btnRestore');
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Restoring...';
    btn.disabled = true;
    const res = await api('POST', '/api/restore-data');
    if (res && res.success) {
        showToast(`Data restored! ${res.accounts} accounts, ${res.servers} servers`, 'success');
        await refreshData();
    } else {
        showToast('Gagal: ' + (res?.error || 'unknown'), 'error');
    }
    btn.innerHTML = '<i class="fas fa-undo-alt"></i> Restore';
    btn.disabled = false;
}

async function logout() {
    if (!confirm('Yakin ingin logout?')) return;
    await api('POST', '/api/logout');
    window.location.href = '/login';
}

async function clearPassword() {
    if (!confirm('Hapus password dashboard?\nDashboard akan bisa diakses tanpa password.')) return;
    await api('PUT', '/api/settings', { dashboard_password: '' });
    await refreshData();
}

async function testWebhook() {
    const url = document.getElementById('webhookUrl').value.trim();
    if (!url) { showToast('Masukkan webhook URL dulu', 'warning'); return; }
    await saveSettings();
    const res = await api('POST', '/api/webhook/test', { url });
    if (res && res.success) {
        showToast('Webhook berfungsi! Cek Discord.', 'success');
    } else {
        showToast('Gagal: ' + (res?.error || 'unknown'), 'error');
    }
}

async function testADB() {
    const btn = document.getElementById('btnTestADB');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Testing...';
    btn.disabled = true;

    await saveSettings();
    const res = await api('POST', '/api/mumu/test');

    const el = document.getElementById('adbStatus');
    const results = document.getElementById('adbTestResults');

    if (res) {
        if (res.adb_found) {
            el.innerHTML = `<i class="fas fa-check-circle" style="color:var(--green)"></i> <strong>ADB Terdeteksi</strong> &mdash; ${esc(res.adb_path)}`;
            el.style.borderColor = 'rgba(67,233,123,0.3)';
            el.style.background = 'rgba(67,233,123,0.05)';
        } else {
            el.innerHTML = `<i class="fas fa-exclamation-triangle" style="color:var(--yellow)"></i> <strong>ADB Tidak Ditemukan</strong>`;
            el.style.borderColor = 'rgba(255,217,61,0.3)';
            el.style.background = 'rgba(255,217,61,0.05)';
        }

        if (res.instances) {
            results.style.display = 'block';
            results.innerHTML = '<div style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px">' +
                res.instances.map(inst => {
                    const color = inst.connected ? 'var(--green)' : 'var(--red)';
                    const icon = inst.connected ? 'fa-check-circle' : 'fa-times-circle';
                    const label = inst.connected ? 'Connected' : 'Failed';
                    const serial = inst.serial || '(kosong)';
                    return `<div style="padding:10px;border-radius:8px;background:var(--bg-input);border:1px solid var(--border-color);text-align:center">
                        <div style="font-size:13px;font-weight:600;margin-bottom:4px">#${inst.instance}</div>
                        <div style="font-size:11px;color:var(--text-muted)">${esc(serial)}</div>
                        <div style="margin-top:4px"><i class="fas ${icon}" style="color:${color}"></i> <span style="font-size:11px;color:${color}">${label}</span></div>
                    </div>`;
                }).join('') + '</div>';
        }
    } else {
        el.innerHTML = '<i class="fas fa-exclamation-triangle" style="color:var(--yellow)"></i> <strong>Gagal</strong> &mdash; Server error';
    }

    btn.innerHTML = orig;
    btn.disabled = false;
}

async function clearActivity() {
    await api('DELETE', '/api/activity');
    activityLog = [];
    updateActivityLog();
    updateSidebarActivity();
}

async function loadScript() {
    const res = await api('GET', '/api/generate-script');
    if (res) {
        document.getElementById('scriptOutput').textContent = res.script;
    }
}

async function pushScript(accId) {
    if (!confirm('Push script monitoring ke Delta Autoexecute di VM? Script akan auto-inject tiap Roblox start.')) return;
    const btn = event.target.closest('button');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
    btn.disabled = true;
    const res = await api('POST', `/api/accounts/${accId}/push-script`);
    if (res && res.success) {
        showToast(res.message, 'success');
    } else {
        showToast('Gagal: ' + (res?.error || 'unknown'), 'error');
    }
    btn.innerHTML = orig;
    btn.disabled = false;
}

async function pushScriptToAll() {
    if (!confirm('Push script ke SEMUA instance yang aktif dan memiliki Roblox running?')) return;
    const btn = document.getElementById('btnPushAll');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Pushing...';
    btn.disabled = true;
    try {
        const res = await api('POST', '/api/push-all-active');
        if (res && res.results) {
            let html = '<div style="max-height:400px;overflow-y:auto">';
            html += `<p style="margin-bottom:10px;font-size:13px"><strong>Berhasil:</strong> ${res.pushed} / ${res.total} instance</p>`;
            for (const r of res.results) {
                const icon = r.status === 'ok' ? '<i class="fas fa-check-circle" style="color:var(--green)"></i>'
                    : r.status === 'skipped' ? '<i class="fas fa-minus-circle" style="color:var(--text-muted)"></i>'
                    : '<i class="fas fa-times-circle" style="color:var(--red)"></i>';
                html += `<div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:12px">
                    ${icon}
                    <span style="min-width:80px;font-weight:600">#${r.instance}</span>
                    <span style="flex:1">${esc(r.message)}${r.account ? ` (${esc(r.account)})` : ''}</span>
                </div>`;
            }
            html += '</div>';
            html += `<div style="margin-top:12px;text-align:center"><button class="btn btn-primary" onclick="closeDynamicModal()"><i class="fas fa-check"></i> OK</button></div>`;
            showModal(html);
            showToast(`Script pushed ke ${res.pushed} instance`, 'success');
        } else {
            showToast('Gagal: ' + (res?.error || 'server error'), 'error');
        }
    } catch (e) {
        showToast('Error: ' + e.message, 'error');
    }
    btn.innerHTML = orig;
    btn.disabled = false;
}

function populateLogAccountSelect() {
    const sel = document.getElementById('logAccountSelect');
    const current = sel.value;
    sel.innerHTML = '<option value="">— Pilih Account —</option>' +
        accounts.map(a => `<option value="${a.id}">${esc(a.name)}</option>`).join('');
    if (current) sel.value = current;
}

async function loadAccountLogs(accId) {
    const container = document.getElementById('accountLogsContainer');
    if (!accId) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-search"></i> Pilih account untuk melihat log</div>';
        return;
    }
    const res = await api('GET', `/api/accounts/${accId}/logs`);
    if (!res) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-exclamation-triangle"></i> Gagal memuat log</div>';
        return;
    }
    document.getElementById('logAccountSelect').value = accId;
    const logs = res.logs || [];
    if (logs.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-file-alt"></i> Belum ada log untuk account ini</div>';
        return;
    }
    container.innerHTML = '<div style="display:flex;flex-direction:column;gap:4px">' +
        logs.map(a => `<div class="activity-item activity-level-${a.level}">
            <span class="activity-time">${esc(a.time)}</span>
            <span class="activity-msg">${esc(a.msg)}</span>
        </div>`).join('') + '</div>';
}

function selectAccountLog(accId) {
    document.getElementById('logAccountSelect').value = accId;
    loadAccountLogs(accId);
}

async function clearAccountLogs() {
    const sel = document.getElementById('logAccountSelect');
    if (!sel.value) return;
    if (!confirm('Hapus semua log untuk account ini?')) return;
    await api('DELETE', `/api/activity?account_id=${sel.value}`);
    document.getElementById('accountLogsContainer').innerHTML = '<div class="empty-state"><i class="fas fa-check-circle"></i> Log dibersihkan</div>';
}

function refreshAllScreenshots() {
    const grid = document.getElementById('screenshotGrid');
    const serials = settings.mumu_serials || [];
    grid.innerHTML = '';
    serials.forEach((s, i) => {
        const name = getVmDisplayName(i);
        if (!s) return;
        const card = document.createElement('div');
        card.className = 'screenshot-card';
        card.innerHTML = `
            <img src="/api/mumu/${i}/screenshot?t=${Date.now()}" style="width:100%;display:block;image-rendering:pixelated" onerror="this.parentElement.innerHTML='<div style=\\'padding:40px;text-align:center;color:var(--red);font-size:13px\\'><i class=\\'fas fa-exclamation-triangle\\'></i> Screenshot failed</div>'">
            <div class="screenshot-overlay">
                <div class="screenshot-info">
                    <span class="screenshot-name">${esc(name)}</span>
                    <span class="screenshot-serial">${esc(s)}</span>
                </div>
                <span class="screenshot-time">${new Date().toLocaleTimeString()}</span>
            </div>
        `;
        grid.appendChild(card);
    });
}

async function quickJoinInstance(instanceIdx, placeId) {
    if (!placeId || !placeId.trim()) { alert('Masukkan Place ID'); return; }
    const res = await api('POST', `/api/quick-join-instance/${instanceIdx}/${placeId.trim()}`);
    refreshMuMuVMs();
    refreshData();
}

async function quickJoinGame(placeId) {
    const resultDiv = document.getElementById('quickJoinResult');
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = '<div style="padding:8px;text-align:center"><i class="fas fa-spinner fa-spin"></i> Opening game...</div>';
    const res = await api('POST', `/api/quick-join/${placeId}`);
    if (res && res.results) {
        const total = res.results.length;
        const ok = res.results.filter(r => r.status === 'ok').length;
        resultDiv.innerHTML = `<div style="display:flex;gap:6px;flex-wrap:wrap">${
            res.results.map(r => {
                const icon = r.status === 'ok' ? 'fa-check-circle' : r.status === 'skipped' ? 'fa-minus-circle' : 'fa-times-circle';
                const color = r.status === 'ok' ? 'var(--green)' : r.status === 'skipped' ? 'var(--text-muted)' : 'var(--red)';
                return `<span style="padding:4px 10px;border-radius:4px;background:var(--bg-input);border:1px solid var(--border-color);font-size:12px">
                    <i class="fas ${icon}" style="color:${color}"></i> #${r.instance}: ${r.message || r.status}
                </span>`;
            }).join('')
        }</div>`;
        setTimeout(() => { resultDiv.style.display = 'none'; }, 8000);
    } else {
        resultDiv.innerHTML = '<div style="padding:8px;color:var(--red)">Gagal</div>';
    }
}

async function scanADBSerials() {
    const btn = document.getElementById('btnScanADB');
    const orig = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning...';
    btn.disabled = true;
    const res = await api('GET', '/api/mumu/scan');
    btn.innerHTML = orig;
    btn.disabled = false;
    if (res && res.mumu_serials) {
        const container = document.getElementById('mumuSerialLabels');
        if (container) {
            container.innerHTML = '';
            res.mumu_serials.forEach((s, i) => {
                container.innerHTML += `
                    <div>
                        <label style="font-size:11px;color:var(--text-muted);display:block;margin-bottom:4px">${getVmDisplayName(i)}</label>
                        <input type="text" class="input mumu-serial" data-idx="${i}" placeholder="IP:5555" style="text-align:center;font-size:12px" value="${esc(s)}">
                    </div>
                `;
            });
        }
        const lines = [];
        for (const d of (res.devices || [])) {
            lines.push(`${d.name} → ${d.serial}`);
        }
        showToast('Scan selesai! ' + res.devices.length + ' device ditemukan', 'success');
        await saveSettings();
    } else if (res && res._error) {
        showToast('Scan gagal: ' + res._statusText, 'error');
        showToast('Tidak ada device ADB terdeteksi', 'warning');
    }
}

async function shutdownMuMuVM(vmName) {
    if (!confirm(`Shutdown VM "${vmName}"?`)) return;
    document.getElementById('mumuVMList').innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-spin"></i> Shutting down...</div>';
    const res = await api('POST', `/api/mumu/vms/${encodeURIComponent(vmName)}/stop`);
    if (res && res._error) {
        alert('Shutdown failed: ' + (res._statusText || 'unknown'));
    }
    await new Promise(r => setTimeout(r, 3000));
    refreshMuMuVMs();
}
async function restartMuMuVM(vmName) {
    if (!confirm(`Restart VM "${vmName}"?`)) return;
    document.getElementById('mumuVMList').innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-spin"></i> Restarting...</div>';
    const res = await api('POST', `/api/mumu/vms/${encodeURIComponent(vmName)}/restart`);
    if (res && res._error) {
        alert('Restart failed: ' + (res._statusText || 'unknown'));
    }
    await new Promise(r => setTimeout(r, 3000));
    refreshMuMuVMs();
}
async function refreshMuMuVMs() {
    const container = document.getElementById('mumuVMList');
    container.innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-pulse"></i> Loading VMs...</div>';
    const [res, healthRes] = await Promise.all([
        api('GET', '/api/mumu/vms'),
        api('GET', '/api/mumu/health')
    ]);
    if (!res || !res.vms) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-desktop"></i> MuMuVMM tidak ditemukan</div>';
        return;
    }
    const healthMap = {};
    if (healthRes && healthRes.health) {
        healthRes.health.forEach(h => { healthMap[h.instance] = h; });
    }
    container.innerHTML = `<div class="mumu-grid">${res.vms.map((vm, i) => {
        const m = vm.name.match(/MuMuPlayerGlobal-12\.0-(\d+)/);
        const idx = m ? parseInt(m[1]) : i;
        const display = vm.display_name || vm.name;
        vmDisplayNames[idx] = display;
        const h = healthMap[idx];
        return `
        <div class="mumu-card">
            <div class="mumu-card-header">
                <div class="mumu-card-icon"><i class="fas fa-desktop"></i></div>
                <div class="mumu-card-info">
                    <div class="mumu-card-name">${esc(display)}</div>
                    <div class="mumu-card-model">${esc(vm.name)}</div>
                </div>
            </div>
            <div class="mumu-card-status">
                <span class="mumu-status-badge ${vm.running ? 'mumu-status-active' : 'mumu-status-stopped'}">
                    <span class="status-dot ${vm.running ? 'green' : 'red'}"></span>
                    ${vm.running ? 'Running' : 'Stopped'}
                </span>
                ${vm.running ? `
                <span class="mumu-status-badge ${vm.roblox_running ? 'mumu-status-active' : 'mumu-status-stopped'}">
                    <span class="status-dot ${vm.roblox_running ? 'green' : 'red'}"></span>
                    Roblox ${vm.roblox_running ? 'Running' : 'Stopped'}
                </span>` : ''}
                ${vm.running && h && h.connected ? `
                <span class="mumu-status-badge mumu-status-active">
                    <span class="status-dot green"></span>
                    ADB OK
                </span>` : vm.running ? `
                <span class="mumu-status-badge mumu-status-stopped">
                    <span class="status-dot red"></span>
                    ADB Offline
                </span>` : ''}
            </div>
            ${vm.running && h && h.connected ? `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px;font-size:11px">
                <div style="padding:6px 8px;background:var(--bg-card);border-radius:5px;border:1px solid var(--border-color)">
                    <div style="color:var(--text-muted);margin-bottom:1px">Uptime</div>
                    <div style="font-weight:600">${esc(h.uptime || 'N/A')}</div>
                </div>
                <div style="padding:6px 8px;background:var(--bg-card);border-radius:5px;border:1px solid var(--border-color)">
                    <div style="color:var(--text-muted);margin-bottom:1px">RAM</div>
                    <div style="font-weight:600">${h.mem_used_pct != null ? h.mem_used_pct + '%' : 'N/A'}</div>
                    ${h.mem_used_pct != null ? `
                    <div style="margin-top:4px;height:4px;background:var(--border-color);border-radius:2px;overflow:hidden">
                        <div style="width:${h.mem_used_pct}%;height:100%;background:${h.mem_used_pct > 80 ? 'var(--red)' : h.mem_used_pct > 60 ? 'var(--yellow)' : 'var(--green)'};border-radius:2px"></div>
                    </div>` : ''}
                </div>
            </div>` : ''}
            <div class="mumu-card-actions">
                ${vm.running ? `
                <button class="btn btn-sm btn-warning" onclick="restartMuMuVM('${esc(vm.name)}')"><i class="fas fa-sync-alt"></i> Restart</button>
                <button class="btn btn-sm btn-danger" onclick="shutdownMuMuVM('${esc(vm.name)}')"><i class="fas fa-power-off"></i> Shutdown</button>
                ` : `
                <button class="btn btn-sm btn-primary" onclick="startMuMuVM('${esc(vm.name)}')"><i class="fas fa-play"></i> Start</button>
                `}
            </div>
        </div>`;
    }).join('')}</div>`;
    updateVmSerialLabels();
    renderVmAccountMap();
}

function updateVmSerialLabels() {
    const container = document.getElementById('mumuSerialLabels');
    if (!container) return;
    const labels = container.querySelectorAll('label');
    labels.forEach((el, i) => {
        el.textContent = getVmDisplayName(i);
    });
}

async function startAllAndJoin() {
    const btn = document.getElementById('btnStartAllJoin');
    const progress = document.getElementById('startAllProgress');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';
    progress.style.display = 'block';
    progress.innerHTML = '<div style="padding:12px;text-align:center"><i class="fas fa-spinner fa-spin"></i> Menyalakan instance & join server...</div>';

    const res = await api('POST', '/api/mumu/start-all-and-join');

    if (res && res.results) {
        progress.innerHTML = '<div style="display:grid;gap:6px">' +
            res.results.map(r => {
                const icon = r.status === 'ok' ? 'fa-check-circle' : 'fa-times-circle';
                const color = r.status === 'ok' ? 'var(--green)' : 'var(--red)';
                return `<div style="display:flex;align-items:center;gap:8px;padding:8px 12px;border-radius:6px;background:var(--bg-input);border:1px solid var(--border-color);font-size:12px">
                    <i class="fas ${icon}" style="color:${color}"></i>
                    <span style="flex:1">${esc(r.name)}</span>
                    <span style="color:var(--text-muted)">${esc(r.message || r.status)}</span>
                </div>`;
            }).join('') + '</div>';
    } else {
        progress.innerHTML = '<div style="padding:12px;text-align:center;color:var(--red)"><i class="fas fa-exclamation-triangle"></i> Gagal: server error</div>';
    }

    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-play"></i> Start All & Join';
    refreshMuMuVMs();
    refreshData();
}

async function startMuMuVM(name) {
    const res = await api('POST', `/api/mumu/vms/${encodeURIComponent(name)}/start`);
    if (res && res.success) {
        setTimeout(refreshMuMuVMs, 3000);
    }
}

async function stopMuMuVM(name) {
    if (!confirm(`Stop "${name}"?`)) return;
    const res = await api('POST', `/api/mumu/vms/${encodeURIComponent(name)}/stop`);
    if (res && res.success) {
        setTimeout(refreshMuMuVMs, 3000);
    }
}

async function copyScript() {
    const el = document.getElementById('scriptOutput');
    try {
        await navigator.clipboard.writeText(el.textContent);
        const btn = document.querySelector('#page-scripts .card-header .btn');
        const orig = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(() => btn.innerHTML = orig, 2000);
    } catch {
        const range = document.createRange();
        range.selectNode(el);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
    }
}

// ==================== DEVICES ====================

let _devicesAutoRefresh = null;

async function loadDevices() {
    const grid = document.getElementById('devicesGrid');
    if (!grid) return;
    const res = await api('GET', '/api/remote/devices');
    if (!res || !res.devices || res.devices.length === 0) {
        grid.innerHTML = '<div class="empty-state"><i class="fas fa-mobile-alt"></i> Belum ada Cloudphone device terdaftar<br><small style="color:var(--text-muted)">Jalankan remote_monitor.py di Termux</small></div>';
        return;
    }
    grid.innerHTML = res.devices.map(d => {
        const mem = d.memory || {};
        const sto = d.storage || {};
        const bat = d.battery || {};
        const up = d.uptime || {};
        const timeAgo = d.seconds_ago != null ? (d.seconds_ago < 60 ? d.seconds_ago + 's ago' : Math.floor(d.seconds_ago / 60) + 'm ago') : 'never';
        return `
        <div style="background:var(--bg-card);border:1px solid var(--border-color);border-radius:12px;padding:16px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
                <div style="display:flex;align-items:center;gap:8px">
                    <div style="width:36px;height:36px;border-radius:8px;background:${d.online ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'};display:flex;align-items:center;justify-content:center">
                        <i class="fas fa-mobile-alt" style="color:${d.online ? 'var(--green)' : 'var(--red)'}"></i>
                    </div>
                    <div>
                        <div style="font-weight:600;font-size:13px">${esc(d.device_id)}</div>
                        <div style="font-size:10px;color:var(--text-muted)">${timeAgo}</div>
                    </div>
                </div>
                <span style="padding:3px 8px;border-radius:10px;font-size:10px;font-weight:600;background:${d.online ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'};color:${d.online ? 'var(--green)' : 'var(--red)'}">${d.online ? 'ONLINE' : 'OFFLINE'}</span>
            </div>
            ${d.online ? `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:12px;font-size:11px">
                <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px">
                    <div style="color:var(--text-muted);margin-bottom:2px"><i class="fas fa-clock"></i> Uptime</div>
                    <div style="font-weight:600">${esc(up.formatted || '-')}</div>
                </div>
                <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px">
                    <div style="color:var(--text-muted);margin-bottom:2px"><i class="fas fa-microchip"></i> Root</div>
                    <div style="font-weight:600">${d.root ? 'Yes' : 'No'}</div>
                </div>
                <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px">
                    <div style="color:var(--text-muted);margin-bottom:2px"><i class="fas fa-memory"></i> RAM</div>
                    <div style="font-weight:600">${mem.used_mb || 0}/${mem.total_mb || 0} MB</div>
                    <div style="margin-top:3px;height:3px;background:var(--border-color);border-radius:2px;overflow:hidden">
                        <div style="width:${mem.used_percent||0}%;height:100%;background:${(mem.used_percent||0)>80?'var(--red)':(mem.used_percent||0)>60?'var(--yellow)':'var(--green)'};border-radius:2px"></div>
                    </div>
                </div>
                <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px">
                    <div style="color:var(--text-muted);margin-bottom:2px"><i class="fas fa-hdd"></i> Storage</div>
                    <div style="font-weight:600">${sto.used_gb || 0}/${sto.total_gb || 0} GB</div>
                    <div style="margin-top:3px;height:3px;background:var(--border-color);border-radius:2px;overflow:hidden">
                        <div style="width:${sto.used_percent||0}%;height:100%;background:${(sto.used_percent||0)>90?'var(--red)':(sto.used_percent||0)>70?'var(--yellow)':'var(--green)'};border-radius:2px"></div>
                    </div>
                </div>
                ${bat.level != null ? `
                <div style="padding:6px 8px;background:var(--bg-input);border-radius:5px;grid-column:span 2">
                    <div style="color:var(--text-muted);margin-bottom:2px"><i class="fas fa-battery-${bat.level>70?'full':bat.level>30?'half':'quarter'}"></i> Battery</div>
                    <div style="font-weight:600">${bat.level}% ${bat.status||''} ${bat.temperature_c ? '| '+bat.temperature_c+'°C' : ''}</div>
                </div>` : ''}
            </div>` : ''}
            <div style="border-top:1px solid var(--border-color);padding-top:10px">
                <div style="font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:6px">PACKAGES (${d.online_count || 0}/${d.package_count || 0} active)</div>
                <div style="display:flex;flex-wrap:wrap;gap:4px">
                    ${(d.packages || []).map(p => {
                        const statusColor = p.active ? 'var(--green)' : p.has_cookie ? 'var(--yellow)' : 'var(--text-muted)';
                        const statusIcon = p.active ? 'fa-gamepad' : p.has_cookie ? 'fa-cookie-bite' : 'fa-circle';
                        return `<div style="display:flex;align-items:center;gap:4px;padding:3px 8px;border-radius:6px;font-size:10px;background:var(--bg-input);border:1px solid var(--border-color)" title="${esc(p.package)}\nStatus: ${esc(p.status)}">
                            <i class="fas ${statusIcon}" style="color:${statusColor};font-size:8px"></i>
                            <span>${esc(p.label)}</span>
                            ${p.account ? `<span style="color:var(--text-muted);font-size:9px">${esc(p.account.split('-')[0])}</span>` : ''}
                        </div>`;
                    }).join('')}
                </div>
            </div>
        </div>`;
    }).join('');
}

function startDevicesAutoRefresh() {
    stopDevicesAutoRefresh();
    loadDevices();
    _devicesAutoRefresh = setInterval(loadDevices, 15000);
}

function stopDevicesAutoRefresh() {
    if (_devicesAutoRefresh) { clearInterval(_devicesAutoRefresh); _devicesAutoRefresh = null; }
}

// ==================== SCRIPT TABS ====================

function switchScriptTab(tab) {
    // Update tab buttons
    document.querySelectorAll('.script-tab').forEach(t => {
        t.classList.remove('active', 'btn-primary');
        t.classList.add('btn-secondary');
    });
    document.querySelector(`.script-tab[data-script="${tab}"]`).classList.add('active', 'btn-primary');
    document.querySelector(`.script-tab[data-script="${tab}"]`).classList.remove('btn-secondary');
    
    // Update content
    document.querySelectorAll('.script-content').forEach(c => c.style.display = 'none');
    document.getElementById(`script-${tab}`).style.display = 'block';
}

async function generateMailboxScript() {
    const targetId = document.getElementById('scriptTargetId').value;
    const targetName = document.getElementById('scriptTargetName').value || 'Player';
    const batchSize = document.getElementById('scriptBatchSize').value || 25;
    const delay = document.getElementById('scriptDelay').value || 8;
    
    if (!targetId) {
        showToast('Masukkan Target Player ID', 'warning');
        return;
    }
    
    try {
        const res = await api('GET', `/api/generate-mailbox-script?target_id=${targetId}&target_name=${encodeURIComponent(targetName)}&batch_size=${batchSize}&delay=${delay}`);
        if (res && res.script) {
            document.getElementById('mailboxScriptOutput').textContent = res.script;
            showToast('Mailbox script generated!', 'success');
        } else {
            showToast('Gagal generate script', 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function copyMailboxScript() {
    const el = document.getElementById('mailboxScriptOutput');
    if (el.textContent.startsWith('Klik')) {
        showToast('Generate script dulu', 'warning');
        return;
    }
    try {
        await navigator.clipboard.writeText(el.textContent);
        showToast('Script copied!', 'success');
    } catch {
        const range = document.createRange();
        range.selectNode(el);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
    }
}

async function generateCustomBatchScript() {
    const targetId = document.getElementById('customTargetId').value;
    const targetName = document.getElementById('customTargetName').value || 'Player';
    const itemsText = document.getElementById('customItems').value;
    const note = document.getElementById('customNote').value || '';
    const batchSize = document.getElementById('customBatchSize').value || 25;
    
    if (!targetId) {
        showToast('Masukkan Target Player ID', 'warning');
        return;
    }
    
    if (!itemsText.trim()) {
        showToast('Masukkan items', 'warning');
        return;
    }
    
    // Parse items from textarea
    const items = itemsText.split('\n').filter(l => l.trim()).map(line => {
        const parts = line.split('|');
        return {
            category: parts[0]?.trim() || '',
            itemKey: parts[1]?.trim() || ''
        };
    }).filter(i => i.category && i.itemKey);
    
    if (items.length === 0) {
        showToast('Format items salah. Gunakan: Category|ItemKey', 'warning');
        return;
    }
    
    try {
        const res = await api('POST', '/api/generate-mailbox-batch-script', {
            target_id: parseInt(targetId),
            target_name: targetName,
            items: items,
            note: note,
            batch_size: parseInt(batchSize)
        });
        
        if (res && res.script) {
            document.getElementById('customBatchScriptOutput').textContent = res.script;
            showToast(`Script generated for ${items.length} items!`, 'success');
        } else {
            showToast('Gagal generate script', 'error');
        }
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function copyCustomBatchScript() {
    const el = document.getElementById('customBatchScriptOutput');
    if (el.textContent.startsWith('Masukkan')) {
        showToast('Generate script dulu', 'warning');
        return;
    }
    try {
        await navigator.clipboard.writeText(el.textContent);
        showToast('Script copied!', 'success');
    } catch {
        const range = document.createRange();
        range.selectNode(el);
        window.getSelection().removeAllRanges();
        window.getSelection().addRange(range);
        document.execCommand('copy');
        window.getSelection().removeAllRanges();
    }
}

function renderVmAccountMap() {
    const container = document.getElementById('vmAccountMap');
    const allAccounts = accounts;
    const serials = settings.mumu_serials || [];
    const vmCount = Math.max(serials.length, 1);
    const vmNames = [];
    for (let i = 0; i < vmCount; i++) vmNames.push(getVmDisplayName(i));
    let html = '<div style="display:grid;gap:8px">';
    for (let i = 0; i < vmCount; i++) {
        const vmAccounts = allAccounts.filter(a => (a.mumu_instance != null ? a.mumu_instance : 0) === i);
        html += `
        <div style="display:flex;align-items:center;gap:8px;padding:8px 10px;background:var(--bg-input);border:1px solid var(--border-color);border-radius:6px">
            <div style="font-size:12px;font-weight:600;min-width:70px">${esc(vmNames[i] || `MuMu-${i}`)}</div>
            <div style="display:flex;gap:6px;flex-wrap:wrap;flex:1">
                ${vmAccounts.length ? vmAccounts.map(a => {
                    const statusColor = a.status === 'connected' || a.status === 'active' || a.status === 'monitoring' ? 'var(--green)' :
                        a.status === 'error' || a.status === 'kicked' ? 'var(--red)' :
                        a.status === 'idle' ? 'var(--yellow)' : 'var(--text-muted)';
                    return `<span style="display:inline-flex;align-items:center;gap:4px;padding:3px 8px;border-radius:4px;font-size:11px;background:rgba(255,255,255,0.04);border:1px solid var(--border-color)">
                        <span style="width:6px;height:6px;border-radius:50%;background:${statusColor};flex-shrink:0"></span>
                        ${esc(a.name)}
                    </span>`;
                }).join('') : `<span style="font-size:11px;color:var(--text-muted)"><i class="fas fa-minus"></i> No accounts</span>`}
            </div>
        </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
}

function switchSettingsTab(tab) {
    document.querySelectorAll('.settings-tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.settings-group').forEach(g => g.classList.remove('active'));
    document.querySelector(`.settings-tab[data-tab="${tab}"]`).classList.add('active');
    document.getElementById(`settings-${tab}`).classList.add('active');
}

function toggleActionsMenu(btn) {
    const dropdown = btn.nextElementSibling;
    const isOpen = dropdown.classList.contains('open');
    closeAllActionMenus();
    if (!isOpen) dropdown.classList.add('open');
}

function closeAllActionMenus() {
    document.querySelectorAll('.actions-dropdown.open').forEach(d => d.classList.remove('open'));
}

document.addEventListener('click', function(e) {
    if (!e.target.closest('.actions-more')) closeAllActionMenus();
});

// ==================== MAILBOX FUNCTIONS ====================

let mailboxInventory = [];
let mailboxSelectedItems = [];
let mailboxHistory = [];
let mailboxTargets = [];
let _selectedAccount = '';

async function loadMailboxAccounts() {
    try {
        const resp = await api('GET', '/api/mailbox/accounts');
        if (resp.error) {
            showToast(resp.error, 'error');
            return;
        }
        
        const accounts = resp.accounts || [];
        window._mailboxAccounts = accounts;
        
        const select = document.getElementById('mailboxAccountSelect');
        select.innerHTML = '<option value="">— Pilih Akun —</option>';
        
        if (accounts.length === 0) {
            select.innerHTML = '<option value="">Belum ada akun yang aktif</option>';
            showToast('Belum ada akun yang menjalankan script monitor', 'warning');
            return;
        }
        
        accounts.forEach(acc => {
            const opt = document.createElement('option');
            opt.value = acc.name;
            opt.textContent = `${acc.name} (${acc.items_count} items) - ${acc.updated_at || 'no data'}`;
            select.appendChild(opt);
        });
        
        showToast(`Found ${accounts.length} akun aktif`, 'success');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
}

async function loadMailboxInventory() {
    const select = document.getElementById('mailboxAccountSelect');
    const account = select.value;
    
    if (!account) {
        showToast('Pilih akun dulu', 'warning');
        return;
    }
    
    _selectedAccount = account;
    const container = document.getElementById('mailboxInventoryList');
    container.innerHTML = '<div class="empty-state"><i class="fas fa-spinner fa-spin"></i> Loading inventory...</div>';
    
    try {
        const resp = await api('POST', '/api/mailbox/inventory', { account });
        if (resp.error) {
            container.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-triangle"></i> ${esc(resp.error)}</div>`;
            return;
        }
        
        mailboxInventory = resp.items || [];
        
        if (mailboxInventory.length === 0) {
            container.innerHTML = '<div class="empty-state"><i class="fas fa-box-open"></i> Tidak ada inventory untuk akun ini</div>';
            return;
        }
        
        renderMailboxInventory();
        showToast(`Loaded ${mailboxInventory.length} items dari ${account}`, 'success');
    } catch (e) {
        container.innerHTML = `<div class="empty-state"><i class="fas fa-exclamation-triangle"></i> Error: ${esc(e.message)}</div>`;
    }
}

function renderMailboxInventory() {
    const container = document.getElementById('mailboxInventoryList');
    const search = (document.getElementById('mailboxSearch').value || '').toLowerCase();
    
    let filtered = mailboxInventory;
    if (search) {
        filtered = mailboxInventory.filter(item => 
            item.name.toLowerCase().includes(search)
        );
    }
    
    if (filtered.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-box-open"></i> No items found</div>';
        return;
    }
    
    let html = '';
    filtered.forEach(item => {
        const isSelected = mailboxSelectedItems.some(s => s.name === item.name);
        const hasUuid = item.id && item.id !== '' && item.id !== item.name;
        
        // Tampilkan nama item dengan benar
        let displayName = item.name;
        if (item.id && item.id !== item.name && item.id.length > 30) {
            // Item punya UUID berbeda dari nama, tampilkan nama + UUID pendek
            displayName = item.name + ' (' + item.id.substring(0, 8) + '...)';
        }
        
        html += `
        <div class="mailbox-item ${isSelected ? 'selected' : ''}" 
             onclick="toggleMailboxItem('${esc(item.name)}', '${esc(item.category || 'Other')}', '${esc(item.id || '')}', ${item.qty || 1})"
             style="display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;border-radius:6px;cursor:pointer;transition:all 0.15s;background:${isSelected ? 'rgba(34,197,94,0.15)' : 'var(--bg-input)'};border:1px solid ${isSelected ? 'var(--green)' : 'var(--border-color)'}">
            <input type="checkbox" ${isSelected ? 'checked' : ''} style="pointer-events:none">
            <span style="font-size:12px;flex:1">${esc(displayName)}</span>
            ${item.qty > 1 ? `<span style="font-size:10px;color:var(--text-muted)">x${item.qty}</span>` : ''}
            <span style="font-size:9px;color:${hasUuid ? 'var(--green)' : 'var(--text-muted)'}">${hasUuid ? '✓' : ''}</span>
        </div>`;
    });
    
    container.innerHTML = html;
    document.getElementById('mailboxTotalCount').textContent = `Total: ${filtered.length} items`;
}

function toggleMailboxItem(name, category, id, qty) {
    const idx = mailboxSelectedItems.findIndex(s => s.name === name);
    if (idx >= 0) {
        mailboxSelectedItems.splice(idx, 1);
    } else {
        mailboxSelectedItems.push({ name, category, id: id || '', qty: qty || 1 });
    }
    renderMailboxInventory();
    updateMailboxPreview();
}

function selectAllMailboxItems() {
    mailboxSelectedItems = mailboxInventory.map(item => ({
        name: item.name,
        category: item.category || 'Other',
        id: item.id || '',
        qty: item.qty || 1
    }));
    renderMailboxInventory();
    updateMailboxPreview();
}

function clearMailboxSelection() {
    mailboxSelectedItems = [];
    renderMailboxInventory();
    updateMailboxPreview();
}

function filterMailboxItems() {
    renderMailboxInventory();
}

function updateMailboxPreview() {
    const preview = document.getElementById('mailboxPreview');
    const count = document.getElementById('mailboxSelectedCount');
    
    count.textContent = mailboxSelectedItems.length;
    
    if (mailboxSelectedItems.length === 0) {
        preview.innerHTML = '<span style="color:var(--text-muted)">Pilih items dulu</span>';
        return;
    }
    
    const groups = {};
    mailboxSelectedItems.forEach(item => {
        if (!groups[item.category]) groups[item.category] = 0;
        groups[item.category]++;
    });
    
    let html = `<div style="margin-bottom:6px;font-weight:600">Dari: ${esc(_selectedAccount)}</div>`;
    html += '<div style="margin-bottom:6px;font-weight:600">Items:</div>';
    for (const [cat, cnt] of Object.entries(groups)) {
        html += `<div>${cat}: ${cnt} items</div>`;
    }
    
    const batchSize = parseInt(document.getElementById('mailboxBatchSize').value) || 25;
    const batches = Math.ceil(mailboxSelectedItems.length / batchSize);
    html += `<div style="margin-top:6px;color:var(--blue)">${mailboxSelectedItems.length} items → ${batches} batch(es)</div>`;
    
    if (mailboxTargets.length > 0) {
        html += `<div style="margin-top:4px;color:var(--yellow)">Kirim ke: ${mailboxTargets.join(', ')}</div>`;
    }
    
    preview.innerHTML = html;
}

// ==================== TARGET FUNCTIONS ====================

function addMailboxTarget() {
    const input = document.getElementById('mailboxTargetUsername');
    const username = input.value.trim();
    
    if (!username) {
        showToast('Masukkan username', 'warning');
        return;
    }
    
    if (mailboxTargets.includes(username)) {
        showToast('Sudah ditambahkan', 'warning');
        return;
    }
    
    mailboxTargets.push(username);
    renderMailboxTargets();
    updateMailboxPreview();
    input.value = '';
    showToast(`Added ${username}`, 'success');
}

function removeMailboxTarget(username) {
    mailboxTargets = mailboxTargets.filter(t => t !== username);
    renderMailboxTargets();
    updateMailboxPreview();
}

function renderMailboxTargets() {
    const container = document.getElementById('mailboxTargetList');
    
    if (mailboxTargets.length === 0) {
        container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);padding:8px;text-align:center">Belum ada target</div>';
        return;
    }
    
    let html = '';
    mailboxTargets.forEach(username => {
        html += `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 8px;margin-bottom:4px;background:var(--bg-input);border:1px solid var(--border-color);border-radius:6px">
            <i class="fas fa-user" style="color:var(--blue);font-size:11px"></i>
            <span style="font-size:12px;flex:1">${esc(username)}</span>
            <button class="btn btn-sm btn-danger" onclick="removeMailboxTarget('${esc(username)}')" style="padding:2px 6px;font-size:10px">
                <i class="fas fa-times"></i>
            </button>
        </div>`;
    });
    
    container.innerHTML = html;
}

// ==================== GENERATE SCRIPT ====================

async function sendMailboxItems() {
    if (!_selectedAccount) { showToast('Pilih akun dulu', 'warning'); return; }
    if (mailboxTargets.length === 0) { showToast('Tambah target dulu', 'warning'); return; }
    if (mailboxSelectedItems.length === 0) { showToast('Pilih items dulu', 'warning'); return; }
    
    const btn = document.getElementById('btnSendMailbox');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Mengirim...';
    
    // Show status card
    const statusCard = document.getElementById('mailboxStatusCard');
    statusCard.style.display = 'block';
    document.getElementById('mailboxStatusContent').innerHTML = `
        <div style="text-align:center;padding:20px">
            <i class="fas fa-spinner fa-spin" style="font-size:24px;color:var(--blue)"></i>
            <p style="margin-top:10px;color:var(--text-muted)">Mengirim command ke executor...</p>
        </div>
    `;
    
    let allSuccess = true;
    let totalSent = 0;
    
    // Send to each target
    for (const target of mailboxTargets) {
        try {
            // Apply max count limit
            const maxCount = parseInt(document.getElementById('mailboxMaxCount').value) || 0;
            const itemsToSend = mailboxSelectedItems.map(item => ({
                ...item,
                qty: maxCount > 0 ? Math.min(item.qty || 1, maxCount) : (item.qty || 1)
            }));
            
            const resp = await api('POST', '/api/mailbox/send', {
                account: _selectedAccount,
                targetUsername: target,
                items: itemsToSend,
                note: document.getElementById('mailboxNote')?.value || ''
            });
            
            if (resp.success) {
                totalSent++;
                
                // Update status
                document.getElementById('mailboxStatusContent').innerHTML = `
                    <div style="padding:10px">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                            <i class="fas fa-check-circle" style="color:var(--green)"></i>
                            <span>Command queued untuk <strong>${esc(target)}</strong> (ID: ${resp.target_id})</span>
                        </div>
                        <div style="font-size:12px;color:var(--text-muted)">
                            ${resp.items_count} items | Command ID: ${resp.command_id}
                        </div>
                        <div style="margin-top:10px;padding:8px;background:var(--bg-input);border-radius:6px;font-size:11px">
                            <i class="fas fa-info-circle" style="color:var(--blue)"></i>
                            Monitor script di executor akan otomatis eksekusi command ini.
                        </div>
                    </div>
                `;
                
                // Poll for result
                pollCommandResult(resp.command_id, target);
                
                // Hitung total count (quantity)
                const totalCount = itemsToSend.reduce((sum, item) => sum + (item.qty || 1), 0);
                addMailboxHistory('send', totalCount, target, 
                    `Command queued (${resp.items_count} items)`);
            } else {
                allSuccess = false;
                showToast(`${target}: ${resp.error || 'Gagal'}`, 'error');
            }
        } catch (e) {
            allSuccess = false;
            showToast(`${target}: Error - ${e.message}`, 'error');
        }
    }
    
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-paper-plane"></i> Kirim Sekarang';
    
    if (allSuccess && totalSent > 0) {
        showToast(`Command terkirim ke ${totalSent} target!`, 'success');
    }
}

async function pollCommandResult(cmdId, target) {
    let attempts = 0;
    const maxAttempts = 60; // 5 minutes max
    
    const checkResult = async () => {
        attempts++;
        if (attempts > maxAttempts) return;
        
        try {
            const resp = await api('GET', `/api/mailbox/result/${cmdId}`);
            
            if (resp.status === 'completed') {
                document.getElementById('mailboxStatusContent').innerHTML = `
                    <div style="padding:10px">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                            <i class="fas fa-check-circle" style="color:var(--green);font-size:20px"></i>
                            <span style="font-size:16px;font-weight:600">Berhasil!</span>
                        </div>
                        <div style="font-size:12px;color:var(--text-muted)">
                            ${esc(resp.message || `Items terkirim ke ${target}`)}
                        </div>
                    </div>
                `;
                addMailboxHistory('success', mailboxSelectedItems.length, target, resp.message || 'Success');
                showToast(`${target}: Berhasil!`, 'success');
                return;
            } else if (resp.status === 'failed') {
                document.getElementById('mailboxStatusContent').innerHTML = `
                    <div style="padding:10px">
                        <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
                            <i class="fas fa-exclamation-circle" style="color:var(--red);font-size:20px"></i>
                            <span style="font-size:16px;font-weight:600">Gagal</span>
                        </div>
                        <div style="font-size:12px;color:var(--text-muted)">
                            ${esc(resp.message || 'Terjadi error')}
                        </div>
                    </div>
                `;
                addMailboxHistory('failed', mailboxSelectedItems.length, target, resp.message || 'Failed');
                showToast(`${target}: Gagal - ${resp.message}`, 'error');
                return;
            }
            
            // Still pending, check again
            setTimeout(checkResult, 5000);
        } catch (e) {
            setTimeout(checkResult, 5000);
        }
    };
    
    setTimeout(checkResult, 2000);
}

// ==================== HISTORY ====================

function addMailboxHistory(type, count, target, message) {
    const now = new Date().toLocaleTimeString();
    mailboxHistory.unshift({ time: now, type, count, target, message });
    if (mailboxHistory.length > 20) mailboxHistory.pop();
    renderMailboxHistory();
}

function renderMailboxHistory() {
    const container = document.getElementById('mailboxHistory');
    
    if (mailboxHistory.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-history"></i> Belum ada history</div>';
        return;
    }
    
    let html = '';
    mailboxHistory.forEach(h => {
        const color = h.message.includes('generated') || h.message.includes('success') ? 'var(--green)' : 'var(--text-muted)';
        const countText = h.count > 1 ? `${h.count} items` : `${h.count} item`;
        html += `
        <div style="display:flex;align-items:center;gap:8px;padding:8px;margin-bottom:4px;background:var(--bg-input);border-radius:6px;font-size:11px">
            <i class="fas fa-code" style="color:${color};width:16px;text-align:center"></i>
            <span style="color:var(--text-muted);min-width:60px">${h.time}</span>
            <span style="flex:1">${countText} → ${esc(h.target)}</span>
            <span style="color:${color}">${esc(h.message)}</span>
        </div>`;
    });
    
    container.innerHTML = html;
}

function clearMailboxHistory() {
    mailboxHistory = [];
    renderMailboxHistory();
}

// ==================== HARVEST FRUITS ====================

let harvestSelectedFruits = [];
let harvestFruitsData = [];

function renderHarvestFruitList() {
    const listEl = document.getElementById('harvestFruitsList');
    if (!harvestFruitsData.length) {
        listEl.innerHTML = '<div class="empty-state"><i class="fas fa-apple-alt"></i> No harvest fruits</div>';
        return;
    }
    
    listEl.innerHTML = harvestFruitsData.map((f, i) => {
        const mutMultiplier = f.mutation_multiplier || 1;
        const mutLabel = f.mutation && f.mutation !== 'None' ? ` [${f.mutation}]` : '';
        const checked = harvestSelectedFruits.some(s => s.id === f.id) ? 'checked' : '';
        const qty = f.count || 1;
        const displayValue = f.totalValue || (f.value * qty) || 0;
        return `
        <div style="display:flex;align-items:center;gap:8px;padding:6px 0;border-bottom:1px solid var(--border-color);font-size:11px" onclick="toggleHarvestFruit(${i})">
            <input type="checkbox" ${checked} style="cursor:pointer" onchange="toggleHarvestFruit(${i})">
            <span style="flex:1">${esc(f.fruitName)}${mutLabel} ${qty > 1 ? 'x' + qty : ''} (${f.weight?.toFixed(1) || '?'}kg)</span>
            <span style="color:var(--green)">${displayValue.toLocaleString()} <span style="color:var(--text-muted);font-size:9px">(${mutMultiplier}x)</span></span>
        </div>`;
    }).join('');
    
    updateHarvestSelectedCount();
}

function toggleHarvestFruit(index) {
    const fruit = harvestFruitsData[index];
    if (!fruit) return;
    const idx = harvestSelectedFruits.findIndex(s => s.id === fruit.id);
    if (idx >= 0) {
        harvestSelectedFruits.splice(idx, 1);
    } else {
        harvestSelectedFruits.push(fruit);
    }
    renderHarvestFruitList();
}

function selectAllHarvestFruits() {
    harvestSelectedFruits = harvestFruitsData.filter(f => f.id && f.id !== '');
    renderHarvestFruitList();
    showToast(`${harvestSelectedFruits.length} fruits selected`, 'info');
}

function clearHarvestFruits() {
    harvestSelectedFruits = [];
    renderHarvestFruitList();
}

function updateHarvestSelectedCount() {
    const el = document.getElementById('harvestSelectedCount');
    if (!el) { console.warn('harvestSelectedCount not found'); return; }
    const totalQty = harvestSelectedFruits.reduce((s, f) => s + (f.count || 1), 0);
    const value = harvestSelectedFruits.reduce((s, f) => s + (f.totalValue || (f.value || 0) * (f.count || 1)), 0);
    el.textContent = `(${totalQty}) ${value.toLocaleString()}`;
}

async function loadHarvestFruits() {
    const account = document.getElementById('mailboxAccountSelect').value;
    if (!account) { showToast('Pilih akun dulu', 'warning'); return; }
    
    const btn = document.querySelector('#gift-tab-harvest .btn-primary');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Scanning...';
    
    try {
        const resp = await api('POST', '/api/mailbox/harvest-fruits', { account });
        
        if (resp.error) {
            showToast(resp.error, 'warning');
            document.getElementById('harvestFruitsResult').style.display = 'none';
            return;
        }
        
        harvestFruitsData = resp.fruits || [];
        harvestSelectedFruits = [];
        
        document.getElementById('harvestFruitsResult').style.display = 'block';
        document.getElementById('harvestTotalCount').textContent = resp.total_count + ' fruits';
        document.getElementById('harvestTotalValue').textContent = resp.formatted_value;
        
        renderHarvestFruitList();
        
        showToast(`Found ${resp.total_count} harvest fruits worth ${resp.formatted_value}`, 'success');
    } catch (e) {
        showToast(`Error: ${e.message}`, 'error');
    }
    
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-search"></i> Scan Harvest Fruits';
}

async function sendHarvestFruits() {
    const account = document.getElementById('mailboxAccountSelect').value;
    const target = mailboxTargets[0];
    
    if (!account) { showToast('Pilih akun dulu', 'warning'); return; }
    if (!target) { showToast('Tambah target dulu', 'warning'); return; }
    if (harvestSelectedFruits.length === 0) { showToast('Pilih fruits yang mau dikirim', 'warning'); return; }
    
    const btn = document.getElementById('btnSendHarvestFruits');
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Mengirim...';
    
    let successCount = 0;
    let failCount = 0;
    
    for (const fruit of harvestSelectedFruits) {
        if (!fruit.id || fruit.id === '') {
            failCount++;
            continue;
        }
        
        try {
            const sendResp = await api('POST', '/api/mailbox/send-gift', {
                account,
                targetUsername: target,
                itemId: fruit.id,
                note: `Harvest fruit: ${fruit.fruitName}${fruit.mutation !== 'None' ? ' [' + fruit.mutation + ']' : ''}`
            });
            
            if (sendResp.success) {
                successCount++;
            } else {
                failCount++;
            }
        } catch (e) {
            failCount++;
        }
    }
    
    showToast(`Selesai! ${successCount} terkirim, ${failCount} gagal`, successCount > 0 ? 'success' : 'error');
    addMailboxHistory(successCount > 0 ? 'send' : 'failed', harvestSelectedFruits.length, target,
        `Harvest fruits: ${successCount} ok, ${failCount} gagal`);
    
    // Clear sent items from selection
    harvestSelectedFruits = [];
    renderHarvestFruitList();
    
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-paper-plane"></i> Kirim Selected Fruits';
}

// ==================== INIT ====================

async function initMailbox() {
    mailboxTargets = [];
    mailboxSelectedItems = [];
    renderMailboxTargets();
    await loadMailboxAccounts();
}

// ==================== SEED SHOP FUNCTIONS ====================

let seedShopConfig = {};
let seedShopSeeds = [];

function switchMailboxTab(tab) {
    document.querySelectorAll('.mailbox-tab').forEach(t => {
        t.classList.remove('active');
        t.classList.add('btn-secondary');
        t.classList.remove('btn-primary');
    });
    document.querySelectorAll('.mailbox-content').forEach(c => c.style.display = 'none');
    
    const activeTab = document.querySelector(`.mailbox-tab[data-tab="${tab}"]`);
    if (activeTab) {
        activeTab.classList.add('active');
        activeTab.classList.remove('btn-secondary');
        activeTab.classList.add('btn-primary');
    }
    
    const content = document.getElementById(`mailbox-${tab}`);
    if (content) content.style.display = 'block';
    
    if (tab === 'seedshop') {
        loadSeedShopConfig();
    }
}

async function loadSeedShopConfig() {
    try {
        const resp = await api('GET', '/api/seed-shop/config');
        if (resp) {
            seedShopConfig = resp.config || {};
            await loadSeedList();
        }
    } catch (e) {
        console.error('Failed to load seed shop config:', e);
    }
}

async function loadSeedList() {
    try {
        const resp = await api('GET', '/api/seed-shop/seeds');
        if (resp && resp.seeds) {
            seedShopSeeds = resp.seeds;
            renderSeedShopList();
        }
    } catch (e) {
        console.error('Failed to load seed list:', e);
    }
}

function renderSeedShopList() {
    const container = document.getElementById('seedShopList');
    if (!container) return;
    
    if (seedShopSeeds.length === 0) {
        container.innerHTML = '<div class="empty-state">Tidak ada seeds tersedia</div>';
        return;
    }
    
    container.innerHTML = seedShopSeeds.map(seed => {
        const enabled = seedShopConfig[seed.id]?.enabled || false;
        const maxQty = seedShopConfig[seed.id]?.max_qty || 10;
        const rarityColors = {
            'Common': 'var(--text-muted)',
            'Uncommon': 'var(--green)',
            'Rare': 'var(--blue)',
            'Epic': 'var(--purple)',
            'Legendary': 'var(--yellow)',
            'Mythic': 'var(--red)'
        };
        const color = rarityColors[seed.rarity] || 'var(--text-muted)';
        
        return `
        <div style="padding:10px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:8px">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
                <div>
                    <span style="font-weight:600;font-size:13px">${esc(seed.name)}</span>
                    <span style="font-size:10px;color:${color};margin-left:6px">${seed.rarity}</span>
                </div>
                <label class="toggle" style="margin:0">
                    <input type="checkbox" ${enabled ? 'checked' : ''} onchange="toggleSeedConfig('${seed.id}', this.checked)">
                    <span class="toggle-slider"></span>
                </label>
            </div>
            <div style="display:flex;gap:8px;align-items:center;font-size:11px;color:var(--text-muted)">
                <span>Price: ${seed.price}</span>
                <span>|</span>
                <span>Max Qty:</span>
                <input type="number" class="input" value="${maxQty}" min="1" max="100" 
                    style="width:60px;padding:2px 6px;font-size:11px" 
                    onchange="updateSeedMaxQty('${seed.id}', this.value)">
            </div>
        </div>`;
    }).join('');
}

function toggleSeedConfig(seedId, enabled) {
    if (!seedShopConfig[seedId]) {
        seedShopConfig[seedId] = {};
    }
    seedShopConfig[seedId].enabled = enabled;
}

function updateSeedMaxQty(seedId, value) {
    if (!seedShopConfig[seedId]) {
        seedShopConfig[seedId] = {};
    }
    seedShopConfig[seedId].max_qty = parseInt(value) || 10;
}

async function saveSeedShopConfig() {
    try {
        const resp = await api('POST', '/api/seed-shop/config', seedShopConfig);
        if (resp && resp.success) {
            showToast('Seed shop config saved!', 'success');
        } else {
            showToast('Failed to save config', 'error');
        }
    } catch (e) {
        showToast('Error saving config', 'error');
    }
}

// ==================== SCHEDULE FUNCTIONS ====================

let scheduleList = [];
let scheduleHistoryList = [];
let scheduleEditItems = [];

async function loadSchedules() {
    try {
        const resp = await api('GET', '/api/schedule/list');
        if (resp) {
            scheduleList = resp.schedules || [];
            scheduleHistoryList = resp.history || [];
            renderScheduleList();
            renderScheduleHistory();
        }
    } catch (e) {
        showToast('Error loading schedules', 'error');
    }
}

function renderScheduleList() {
    const container = document.getElementById('scheduleList');
    if (!container) return;
    if (scheduleList.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-clock"></i> Belum ada schedule</div>';
        return;
    }
    container.innerHTML = scheduleList.map(s => {
        const repeatLabels = {once:'Once', daily:'Daily', every_2:'Every 2h', every_4:'Every 4h', every_6:'Every 6h', every_12:'Every 12h'};
        const repeatText = repeatLabels[s.repeat] || s.repeat;
        const itemsText = (s.items || []).map(i => `${i.name} x${i.qty}`).join(', ');
        return `
        <div style="padding:12px;background:var(--bg-card);border:1px solid var(--border-color);border-radius:8px;margin-bottom:8px">
            <div style="display:flex;justify-content:space-between;align-items:center">
                <div>
                    <div style="font-weight:600;font-size:13px">${esc(s.account)} → ${esc(s.target)}</div>
                    <div style="font-size:12px;color:var(--text-secondary);margin-top:4px">
                        Items: ${esc(itemsText)} | Time: ${s.time} | ${repeatText}
                    </div>
                    <div style="font-size:11px;color:var(--text-muted);margin-top:4px">
                        Next: ${s.next_run || 'N/A'} | Last: ${s.last_run || 'Never'}
                    </div>
                </div>
                <div style="display:flex;gap:6px;align-items:center">
                    <label class="toggle" style="margin:0">
                        <input type="checkbox" ${s.enabled ? 'checked' : ''} onchange="toggleSchedule('${s.id}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                    <button class="btn btn-sm btn-secondary" onclick="editSchedule('${s.id}')"><i class="fas fa-edit"></i></button>
                    <button class="btn btn-sm btn-danger" onclick="deleteSchedule('${s.id}')"><i class="fas fa-trash"></i></button>
                </div>
            </div>
        </div>`;
    }).join('');
}

function renderScheduleHistory() {
    const container = document.getElementById('scheduleHistory');
    if (!container) return;
    if (scheduleHistoryList.length === 0) {
        container.innerHTML = '<div class="empty-state"><i class="fas fa-history"></i> Belum ada history</div>';
        return;
    }
    container.innerHTML = scheduleHistoryList.reverse().map(h => `
        <div style="padding:8px;border-bottom:1px solid var(--border-color);font-size:12px">
            <div style="display:flex;justify-content:space-between">
                <span><strong>${esc(h.account)}</strong> → ${esc(h.target)}</span>
                <span style="color:var(--text-muted)">${h.timestamp}</span>
            </div>
            <div style="color:var(--text-secondary);margin-top:2px">
                ${h.items_sent} items | <span style="color:${h.status==='success'?'var(--green)':'var(--red)'}">${h.status}</span> | ${esc(h.message)}
            </div>
        </div>
    `).join('');
}

function showAddSchedule() {
    document.getElementById('scheduleModalTitle').innerHTML = '<i class="fas fa-clock"></i> Add Schedule';
    document.getElementById('editScheduleId').value = '';
    document.getElementById('schedTarget').value = '';
    document.getElementById('schedTime').value = '12:00';
    document.getElementById('schedRepeat').value = 'daily';
    scheduleEditItems = [];
    renderScheduleItems();
    loadScheduleAccountSelect().then(() => {
        const select = document.getElementById('schedAccount');
        if (select.value) loadScheduleInventory(select.value);
    });
    openModal('scheduleModal');
}

function editSchedule(id) {
    const sched = scheduleList.find(s => s.id === id);
    if (!sched) return;
    document.getElementById('scheduleModalTitle').innerHTML = '<i class="fas fa-clock"></i> Edit Schedule';
    document.getElementById('editScheduleId').value = id;
    document.getElementById('schedTarget').value = sched.target;
    document.getElementById('schedTime').value = sched.time;
    document.getElementById('schedRepeat').value = sched.repeat;
    scheduleEditItems = [...(sched.items || [])];
    renderScheduleItems();
    loadScheduleAccountSelect().then(() => {
        document.getElementById('schedAccount').value = sched.account;
        loadScheduleInventory(sched.account);
    });
    openModal('scheduleModal');
}

async function loadScheduleAccountSelect() {
    const select = document.getElementById('schedAccount');
    try {
        const inv = await api('GET', '/api/inventory');
        const accNames = Object.keys(inv || {});
        if (accNames.length === 0) {
            select.innerHTML = '<option value="">No active accounts</option>';
            return;
        }
        select.innerHTML = accNames.map(name => `<option value="${esc(name)}">${esc(name)}</option>`).join('');
        select.onchange = () => loadScheduleInventory(select.value);
    } catch (e) {
        select.innerHTML = '<option value="">Error loading accounts</option>';
    }
}

async function loadScheduleInventory(account) {
    const container = document.getElementById('schedItemsList');
    if (!account) { container.innerHTML = ''; return; }
    try {
        const resp = await api('POST', '/api/mailbox/inventory', {account});
        if (!resp || !resp.items || resp.items.length === 0) {
            container.innerHTML = '<div style="font-size:11px;color:var(--text-muted)">No items</div>';
            return;
        }
        container.innerHTML = `
            <div style="margin-bottom:6px">
                <button class="btn btn-sm btn-primary" onclick="addAllScheduleItems()" style="font-size:10px">
                    <i class="fas fa-check-double"></i> Add All (${resp.items.length} items)
                </button>
                <button class="btn btn-sm btn-secondary" onclick="clearScheduleItems()" style="font-size:10px">
                    <i class="fas fa-times"></i> Clear
                </button>
            </div>
            ${resp.items.map(item => `
                <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;font-size:12px;padding:4px 8px;background:var(--bg-input);border-radius:6px;cursor:pointer" onclick="addScheduleItemFromInventory('${esc(item.name)}', '${esc(item.id)}', '${esc(item.category)}', ${item.qty})">
                    <span style="flex:1">${esc(item.name)} (${item.category})</span>
                    <span style="color:var(--text-muted)">x${item.qty}</span>
                    <i class="fas fa-plus" style="color:var(--green);font-size:10px"></i>
                </div>
            `).join('')}
        `;
    } catch (e) {
        container.innerHTML = '<div style="font-size:11px;color:var(--text-muted)">Error loading inventory</div>';
    }
}

function addScheduleItemFromInventory(name, id, category, maxQty) {
    scheduleEditItems.push({name, id, category, qty: maxQty});
    renderScheduleItems();
    showToast(`Added ${name} x${maxQty}`, 'success');
}

async function addAllScheduleItems() {
    const account = document.getElementById('schedAccount').value;
    if (!account) return;
    try {
        const resp = await api('POST', '/api/mailbox/inventory', {account});
        if (resp && resp.items) {
            scheduleEditItems = resp.items.map(item => ({
                name: item.name,
                id: item.id,
                category: item.category,
                qty: item.qty
            }));
            renderScheduleItems();
            showToast(`Added ${resp.items.length} items`, 'success');
        }
    } catch (e) {
        showToast('Error loading inventory', 'error');
    }
}

function clearScheduleItems() {
    scheduleEditItems = [];
    renderScheduleItems();
}

function addScheduleItem() {
    const name = document.getElementById('schedItemName').value.trim();
    const qty = parseInt(document.getElementById('schedItemQty').value) || 100;
    if (!name) { showToast('Input item name', 'warning'); return; }
    scheduleEditItems.push({name, id: name, category: 'Seeds', qty});
    document.getElementById('schedItemName').value = '';
    renderScheduleItems();
}

function removeScheduleItem(idx) {
    scheduleEditItems.splice(idx, 1);
    renderScheduleItems();
}

function renderScheduleItems() {
    const container = document.getElementById('schedSelectedItems');
    if (!container) return;
    if (scheduleEditItems.length === 0) {
        container.innerHTML = '<div style="font-size:11px;color:var(--text-muted)">Belum ada item dipilih</div>';
        return;
    }
    container.innerHTML = '<div style="font-size:12px;font-weight:600;margin-bottom:6px">Selected Items (' + scheduleEditItems.length + '):</div>' +
        scheduleEditItems.map((item, i) => `
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;font-size:12px;padding:4px 8px;background:var(--bg-input);border-radius:6px">
            <span style="flex:1">${esc(item.name)}</span>
            <span style="color:var(--text-muted)">x${item.qty}</span>
            <button class="btn btn-sm btn-danger" onclick="removeScheduleItem(${i})" style="padding:2px 6px"><i class="fas fa-times"></i></button>
        </div>
    `).join('');
}

async function saveSchedule() {
    const id = document.getElementById('editScheduleId').value;
    const account = document.getElementById('schedAccount').value;
    const target = document.getElementById('schedTarget').value.trim();
    const time = document.getElementById('schedTime').value;
    const repeat = document.getElementById('schedRepeat').value;
    if (!account || !target) { showToast('Fill account and target', 'warning'); return; }
    if (scheduleEditItems.length === 0) { showToast('Add at least 1 item', 'warning'); return; }
    const data = {account, target, items: scheduleEditItems, time, repeat};
    try {
        if (id) {
            await api('PUT', `/api/schedule/${id}`, data);
        } else {
            await api('POST', '/api/schedule/create', data);
        }
        closeModal('scheduleModal');
        await loadSchedules();
        showToast('Schedule saved!', 'success');
    } catch (e) {
        showToast('Error saving schedule', 'error');
    }
}

async function toggleSchedule(id, enabled) {
    try {
        await api('POST', '/api/schedule/toggle', {id, enabled});
        await loadSchedules();
    } catch (e) {
        showToast('Error toggling schedule', 'error');
    }
}

async function deleteSchedule(id) {
    if (!confirm('Delete this schedule?')) return;
    try {
        await api('DELETE', `/api/schedule/${id}`);
        await loadSchedules();
        showToast('Schedule deleted', 'success');
    } catch (e) {
        showToast('Error deleting schedule', 'error');
    }
}

async function loadScheduleHistory() {
    try {
        const resp = await api('GET', '/api/schedule/history');
        if (resp) {
            scheduleHistoryList = resp.history || [];
            renderScheduleHistory();
        }
    } catch (e) {
        showToast('Error loading history', 'error');
    }
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', () => {
    setTimeout(initMailbox, 1000);
});

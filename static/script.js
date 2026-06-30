let accounts = [];
let servers = [];
let settings = {};
let activityLog = [];
let refreshInterval = null;
let vmDisplayNames = {};

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
});

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
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

    const titles = {
        dashboard: 'Dashboard',
        accounts: 'Accounts',
        servers: 'Servers',
        activity: 'Activity',
        settings: 'Settings',
        vms: 'VMs',
        scripts: 'Scripts',
        logs: 'Logs'
    };
    document.getElementById('pageTitle').textContent = titles[page] || 'Dashboard';

    if (page === 'dashboard') { refreshAllScreenshots(); }
    if (page === 'scripts') loadScript();
    if (page === 'vms') { refreshMuMuVMs(); }
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
        if (!res.ok) {
            return { _error: true, _status: res.status, _statusText: res.statusText };
        }
        return await res.json();
    } catch (err) {
        console.error(err);
        return null;
    }
}

async function refreshData() {
    const [accs, svs, act, sets, sum] = await Promise.all([
        api('GET', '/api/accounts'),
        api('GET', '/api/servers'),
        api('GET', '/api/activity?limit=10'),
        api('GET', '/api/settings'),
        api('GET', '/api/summary')
    ]);
    if (accs && accs._error && accs._status === 401) {
        window.location.href = '/login';
        return;
    }
    if (accs) accounts = accs;
    if (svs) servers = svs;
    if (act) activityLog = act;
    if (sum && typeof sum.online === 'number') {
        const ids = { statOnline: sum.online, statError: sum.error, statVMs: `${sum.running_vms}/${sum.total_vms}`, statRobux: (sum.total_robux || 0).toLocaleString(), statAccounts: accounts.length };
        const animData = { statOnline: [0, sum.online], statError: [0, sum.error], statVMs: [0, 0], statRobux: [0, sum.total_robux || 0], statAccounts: [0, accounts.length] };
        for (const [k, v] of Object.entries(ids)) {
            const el = document.getElementById(k);
            if (el && k !== 'statVMs') {
                const prev = parseInt(el.dataset.prev) || 0;
                const cur = parseInt(v.toString().replace(/[^0-9]/g, '')) || 0;
                if (cur !== prev) {
                    el.dataset.prev = cur;
                    animateValue(el, prev, cur);
                }
            } else if (el) {
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

function updateDashboard() {
    document.getElementById('statAccounts').textContent = accounts.length;
    const sa = document.getElementById('statAccounts');
    if (!sa.dataset.initial) {
        sa.dataset.initial = '1';
    }


    document.getElementById('autoJoinEnabled').checked = settings.auto_join_enabled ?? true;
    document.getElementById('rejoinDelay').value = settings.rejoin_delay ?? 3;
    document.getElementById('maxRetries').value = settings.max_retries ?? 5;
    document.getElementById('monitorInterval').value = settings.monitor_interval ?? 2;
    document.getElementById('rejoinInterval').value = (settings.rejoin_interval ?? 2400) / 60;
    document.getElementById('adbPath').value = settings.adb_path || '';
    document.getElementById('webhookUrl').value = settings.webhook_url || '';
    document.getElementById('webhookEnabled').checked = settings.webhook_enabled ?? false;
    document.getElementById('autoRestartVM').checked = settings.auto_restart_vm ?? true;
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
    const serials = settings.mumu_serials || ['', '', '', '', ''];
    document.querySelectorAll('.mumu-serial').forEach(el => {
        const idx = parseInt(el.dataset.idx);
        el.value = serials[idx] || '';
    });

    updateADBStatus();

    const list = document.getElementById('dashAccountsList');
    if (accounts.length === 0) {
        list.innerHTML = '<div class="empty-state">Belum ada account</div>';
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
        list.innerHTML = '<div class="empty-state">Belum ada aktivitas</div>';
    } else {
        list.innerHTML = activityLog.map(a => `
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
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Belum ada account</td></tr>';
        return;
    }
    tbody.innerHTML = accounts.map(a => {
        const aj = a.auto_join;
        const autoSv = servers.find(s => s.id === a.server_id);
        const allSvs = (a.server_ids || []).map(id => servers.find(s => s.id === id)).filter(Boolean);
        const inst = (a.mumu_instance != null) ? a.mumu_instance : '-';
        const vmLabel = getVmDisplayName(inst);
        return `
        <tr>
            <td><strong>${esc(a.name)}</strong></td>
            <td>${getStatusBadge(a.status)} <span class="countdown"${a.next_rejoin_in != null ? ` data-seconds="${a.next_rejoin_in}"` : ''} style="font-size:10px;color:var(--text-muted)"><i class="fas fa-history"></i> <span class="cd-time">${formatCountdown(a.next_rejoin_in)}</span></span></td>
            <td><span class="badge badge-info">${vmLabel}</span></td>
            <td style="font-size:11px">
                ${allSvs.length ? allSvs.map(s =>
                    s.id === a.server_id
                        ? `<span style="color:var(--green)">★ ${esc(s.name)}</span>`
                        : `<span style="color:var(--text-muted)">${esc(s.name)}</span>`
                ).join('<br>') : '<span style="color:var(--text-muted)">-</span>'}
            </td>
            <td>${a.last_joined || '<span style="color:var(--text-muted)">-</span>'}</td>
            <td>
                <div class="actions" style="flex-wrap:wrap">
                    <button class="btn btn-sm ${aj ? 'btn-success' : 'btn-secondary'}" onclick="toggleAutoJoin('${a.id}', ${!aj})" title="Auto-Join ${aj ? 'ON' : 'OFF'}">
                        <i class="fas fa-${aj ? 'toggle-on' : 'toggle-off'}"></i>
                    </button>
                    ${allSvs.filter(s => s.id !== a.server_id).slice(0, 2).map(s =>
                        `<button class="btn btn-sm btn-outline" onclick="setAutoJoinServer('${a.id}', '${s.id}')" title="Auto-join: ${esc(s.name)}" style="font-size:10px;padding:2px 6px">${esc(s.name.slice(0, 6))}</button>`
                    ).join('')}
                    <button class="btn btn-sm ${a.active ? 'btn-danger' : 'btn-primary'}" onclick="${a.active ? `disconnectAccount('${a.id}')` : `joinAccount('${a.id}')`}">
                        <i class="fas fa-${a.active ? 'stop' : 'play'}"></i>
                    </button>
                    <button class="btn btn-sm btn-outline" onclick="switchPage('logs');setTimeout(()=>selectAccountLog('${a.id}'),100)" title="Lihat Log">
                        <i class="fas fa-clipboard-list"></i>
                    </button>
                    <button class="btn btn-sm btn-outline" onclick="pushScript('${a.id}')" title="Push script ke Delta Autoexecute">
                        <i class="fas fa-upload"></i>
                    </button>
                    <button class="btn btn-sm btn-outline" onclick="verifyAccount('${a.id}')" title="Verify Cookie">
                        <i class="fas fa-key"></i>
                    </button>
                    <button class="btn btn-sm btn-secondary" onclick="editAccount('${a.id}')">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button class="btn btn-sm btn-danger" onclick="deleteAccount('${a.id}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </td>
        </tr>
    `}).join('');
}

function updateServersTable() {
    const tbody = document.getElementById('serversTableBody');
    if (servers.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Belum ada server</td></tr>';
        return;
    }
    tbody.innerHTML = servers.map(s => `
        <tr>
            <td><strong>${esc(s.name)}</strong></td>
            <td>${s.type === 'private'
                ? '<span class="badge badge-warning">Private</span>'
                : '<span class="badge badge-info">Public</span>'}</td>
            <td>${esc(s.place_id || '-')}</td>
            <td style="font-size:12px;color:var(--text-muted)">${esc(s.link || s.server_code || '-')}</td>
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
}

function updateActivityLog() {
    const container = document.getElementById('activityLog');
    if (activityLog.length === 0) {
        container.innerHTML = '<div class="empty-state">Belum ada aktivitas</div>';
        return;
    }
    container.innerHTML = activityLog.map(a => `
        <div class="activity-item activity-level-${a.level}">
            <span class="activity-time">${esc(a.time)}</span>
            <span class="activity-msg">${esc(a.msg)}</span>
        </div>
    `).join('');
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
            return `
            <label style="display:flex;align-items:center;gap:8px;padding:6px 12px;cursor:pointer;border-bottom:1px solid var(--border-color);font-size:12px">
                <input type="checkbox" class="server-check" value="${s.id}" ${checked} onchange="updateServerCheck(this)">
                <span style="flex:1">${esc(s.name)}</span>
                <input type="radio" name="autoServer" value="${s.id}" ${isAuto ? 'checked' : ''} ${!checked ? 'disabled' : ''} title="Auto-join target">
                <span style="font-size:10px;color:var(--text-muted)">auto</span>
            </label>`;
        }).join('');
    }

    const instSel = document.getElementById('accInstance');
    const curInst = instSel.value;
    const serials = settings.mumu_serials || ['', '', '', '', ''];
    instSel.innerHTML = serials.map((s, i) => {
        const vm = getVmDisplayName(i);
        const label = s ? `${vm} (${s})` : `${vm} (kosong)`;
        return `<option value="${i}">${label}</option>`;
    }).join('');
    if (curInst) instSel.value = curInst;
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

function showAddAccount() {
    document.getElementById('accountModalTitle').textContent = 'Tambah Account';
    document.getElementById('editAccountId').value = '';
    document.getElementById('accName').value = '';
    document.getElementById('accCookie').value = '';
    document.getElementById('accInstance').value = '0';
    openModal('accountModal');
    updateAccountSelect();
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

    if (!name) { showToast('Nama account harus diisi', 'warning'); return; }

    const mumu_instance = parseInt(document.getElementById('accInstance').value) || 0;
    const data = { name, cookie, server_id, server_ids, mumu_instance };

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
    document.getElementById('accInstance').value = (acc.mumu_instance != null) ? acc.mumu_instance : 0;
    openModal('accountModal');
    updateAccountSelect();
}

async function deleteAccount(id) {
    if (!confirm('Hapus account ini?')) return;
    await api('DELETE', `/api/accounts/${id}`);
    await refreshData();
}

function showAddServer() {
    document.getElementById('serverModalTitle').textContent = 'Tambah Server';
    document.getElementById('editServerId').value = '';
    document.getElementById('svName').value = '';
    document.getElementById('svType').value = 'public';
    document.getElementById('svPlaceId').value = '';
    document.getElementById('svCode').value = '';
    document.getElementById('svLink').value = '';
    toggleServerFields();
    openModal('serverModal');
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

async function toggleAutoJoin(accId, enabled) {
    await api('POST', `/api/accounts/${accId}/auto-join`, { auto_join: enabled });
    refreshData();
}

async function setAutoJoinServer(accId, serverId) {
    await api('POST', `/api/accounts/${accId}/auto-join`, { server_id: serverId });
    refreshData();
}

async function joinAccount(accId) {
    const res = await api('POST', `/api/accounts/${accId}/join`);
    if (res && res.status === 'joining') {
        await refreshData();
        showToast(`Join ${acc.name || accId}...`, 'info');
    }
}

async function disconnectAccount(accId) {
    await api('POST', `/api/accounts/${accId}/disconnect`);
    await refreshData();
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
        auto_restart_vm: document.getElementById('autoRestartVM').checked
    };
    const pwd = document.getElementById('dashboardPassword').value.trim();
    if (pwd) data.dashboard_password = pwd;
    const res = await api('PUT', '/api/settings', data);
    if (res && !res._error) {
        Object.assign(settings, res);
        try { updateDashboard(); } catch(e) {}
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

let logRefreshInterval = null;

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
        container.innerHTML = '<div class="empty-state">Pilih account untuk melihat log</div>';
        return;
    }
    const res = await api('GET', `/api/accounts/${accId}/logs`);
    if (!res) {
        container.innerHTML = '<div class="empty-state">Gagal memuat log</div>';
        return;
    }
    document.getElementById('logAccountSelect').value = accId;
    const logs = res.logs || [];
    if (logs.length === 0) {
        container.innerHTML = '<div class="empty-state">Belum ada log untuk account ini</div>';
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
    await api('DELETE', `/api/activity`);
    document.getElementById('accountLogsContainer').innerHTML = '<div class="empty-state">Log dibersihkan</div>';
}

function refreshAllScreenshots() {
    const grid = document.getElementById('screenshotGrid');
    const serials = [];
    document.querySelectorAll('.mumu-serial').forEach(el => {
        serials.push(el.value.trim() || '');
    });
    grid.innerHTML = '';
    serials.forEach((s, i) => {
        const label = document.querySelector(`[data-vmidx="${i}"]`);
        const name = label ? label.textContent : `MuMu-${i}`;
        if (!s) return;
        const card = document.createElement('div');
        card.style.cssText = 'background:var(--bg-input);border-radius:8px;border:1px solid var(--border-color);overflow:hidden';
        const header = document.createElement('div');
        header.style.cssText = 'padding:6px 10px;font-size:12px;font-weight:500;color:var(--text-secondary);display:flex;justify-content:space-between;align-items:center';
        header.innerHTML = `<span>${esc(name)}</span><span style="font-size:10px;color:var(--text-muted)">${esc(s)}</span>`;
        card.appendChild(header);
        const img = document.createElement('img');
        img.src = `/api/mumu/${i}/screenshot?t=${Date.now()}`;
        img.style.cssText = 'width:100%;display:block;image-rendering:pixelated';
        img.onerror = function () {
            this.parentElement.innerHTML = '<div style="padding:40px;text-align:center;color:var(--red);font-size:13px"><i class="fas fa-exclamation-triangle"></i> Screenshot failed</div>';
        };
        card.appendChild(img);
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
    if (res && res.devices && res.devices.length > 0) {
        const inputs = document.querySelectorAll('.mumu-serial');
        const lines = [];
        res.mumu_serials.forEach((s, i) => {
            if (i < inputs.length) {
                inputs[i].value = s;
            }
        });
        for (const d of res.devices) {
            lines.push(`${d.name} → ${d.serial}`);
        }
        showToast('Scan selesai! ' + res.devices.length + ' device ditemukan', 'success');
        await saveSettings();
    } else {
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
    container.innerHTML = '<div class="empty-state">Loading VMs...</div>';
    const res = await api('GET', '/api/mumu/vms');
    if (!res || !res.vms) {
        container.innerHTML = '<div class="empty-state">MuMuVMM tidak ditemukan</div>';
        return;
    }
    container.innerHTML = res.vms.map((vm, i) => {
        const m = vm.name.match(/MuMuPlayerGlobal-12\.0-(\d+)/);
        const idx = m ? parseInt(m[1]) : i;
        const display = vm.display_name || vm.name;
        if (idx < 5) vmDisplayNames[idx] = display;
        return `
        <div class="mumu-vm-item" style="display:flex;align-items:center;padding:10px 14px;border-radius:8px;background:var(--bg-input);border:1px solid var(--border-color);margin-bottom:8px">
            <div style="flex:1">
                <div style="font-weight:500;font-size:13px">${esc(display)}</div>
                <div style="font-size:11px;color:var(--text-muted);margin-top:2px">
                    <span style="font-size:10px;color:var(--text-muted)">${esc(vm.name)}</span>
                    ${vm.running ? `
                    <span style="margin:0 4px">·</span>
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--green);margin-right:4px"></span>Running
                    <span style="margin:0 4px">·</span>
                    <span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:${vm.roblox_running ? 'var(--green)' : 'var(--red)'};margin-right:4px"></span>
                    Roblox ${vm.roblox_running ? 'Running' : 'Stopped'}
                    ` : `<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--red);margin-right:4px"></span>Stopped`}
                </div>
            </div>
            ${vm.running ? `
            <div style="display:flex;gap:6px;flex-shrink:0">
                <button class="btn btn-sm btn-warning" onclick="restartMuMuVM('${esc(vm.name)}')"><i class="fas fa-sync-alt"></i> Restart</button>
                <button class="btn btn-sm btn-danger" onclick="shutdownMuMuVM('${esc(vm.name)}')"><i class="fas fa-power-off"></i> Shutdown</button>
            </div>` : `
            <div style="display:flex;gap:6px;flex-shrink:0">
                <button class="btn btn-sm btn-primary" onclick="startMuMuVM('${esc(vm.name)}')"><i class="fas fa-play"></i> Start</button>
            </div>`}
        </div>`;
    }).join('');
    updateVmSerialLabels();
}

function updateVmSerialLabels() {
    document.querySelectorAll('#mumuSerialLabels label[data-vmidx]').forEach(el => {
        const idx = el.getAttribute('data-vmidx');
        if (idx != null) {
            el.textContent = getVmDisplayName(parseInt(idx));
        }
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

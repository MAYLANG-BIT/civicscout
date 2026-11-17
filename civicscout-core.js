// CivicScout Hybrid Core v4.0 (Scout + LGU Admin + Field Responders)
const CivicCore = (() => {
    const API_BASE = window.location.protocol.startsWith('http') ? '' : 'http://localhost:8000';
    const USERS_KEY = 'civicScoutUsers_v2';
    const SESSION_KEY = 'civicScoutSession_v2';
    const REPORTS_KEY = 'civicScoutReports_v2';
    const OUTBOX_KEY = 'civicScoutOutbox_v1';
    const LGU_AUTH_CODE = 'BATIA-LGU-2026';

    function getLocalUsers() {
        let users = JSON.parse(localStorage.getItem(USERS_KEY) || '[]');
        const seeds = [
            { name: 'Brgy. Batia Desk Officer', email: 'lgu@batia.gov.ph', password: btoa('batia2026'), role: 'lgu', unitType: '', barangay: 'Brgy. Batia' },
            { name: 'Engr. Reyes (Barangay Electrician)', email: 'electrician@batia.gov.ph', password: btoa('batia2026'), role: 'responder', unitType: 'Electrician Team', barangay: 'Brgy. Batia' },
            { name: 'Garbage Truck #04 Crew', email: 'garbage@batia.gov.ph', password: btoa('batia2026'), role: 'responder', unitType: 'Garbage Truck #04', barangay: 'Brgy. Batia' },
            { name: 'Motorized Road Crew', email: 'road@batia.gov.ph', password: btoa('batia2026'), role: 'responder', unitType: 'Motorized Road Crew', barangay: 'Brgy. Batia' },
            { name: 'Drainage Maintenance Team', email: 'drainage@batia.gov.ph', password: btoa('batia2026'), role: 'responder', unitType: 'Drainage Maintenance', barangay: 'Brgy. Batia' }
        ];
        let changed = false;
        seeds.forEach(s => {
            if (!users.some(u => u.email === s.email)) {
                users.push(s);
                changed = true;
            }
        });
        if (changed) localStorage.setItem(USERS_KEY, JSON.stringify(users));
        return users;
    }

    function getSession() {
        try { return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null'); }
        catch { return null; }
    }

    function setSession(user) {
        localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    }

    function getHomeRouteForRole(role) {
        if (role === 'lgu') return 'admin.html';
        if (role === 'responder') return 'responder.html';
        return 'app.html';
    }

    function logout() {
        localStorage.removeItem(SESSION_KEY);
        window.location.href = 'index.html';
    }

    async function registerAccount({ name, email, password, role, unitType, barangay, lguCode }) {
        const cleanEmail = email.trim().toLowerCase();
        const cleanName = name.trim();
        if (!cleanName || !cleanEmail || !password) throw new Error('All fields are required.');
        if ((role === 'lgu' || role === 'responder') && lguCode !== LGU_AUTH_CODE) {
            throw new Error('Invalid Barangay Authorization Code. (Use: BATIA-LGU-2026)');
        }

        try {
            const res = await fetch(`${API_BASE}/api/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: cleanName, email: cleanEmail, password, role, unitType: unitType || '', barangay, lguCode })
            });
            if (res.ok) {
                const user = await res.json();
                setSession(user);
                return user;
            } else {
                const err = await res.json();
                throw new Error(err.detail || 'Registration failed.');
            }
        } catch (err) {
            if (err.message && !err.message.includes('fetch')) throw err;
            const users = getLocalUsers();
            if (users.some(u => u.email === cleanEmail)) throw new Error('An account with this email already exists.');
            const newUser = { name: cleanName, email: cleanEmail, password: btoa(password), role, unitType: role === 'responder' ? (unitType || 'Electrician Team') : '', barangay };
            users.push(newUser);
            localStorage.setItem(USERS_KEY, JSON.stringify(users));
            const sessionUser = { name: newUser.name, email: newUser.email, role: newUser.role, unitType: newUser.unitType, barangay: newUser.barangay };
            setSession(sessionUser);
            return sessionUser;
        }
    }

    async function loginAccount({ email, password }) {
        const cleanEmail = email.trim().toLowerCase();
        try {
            const res = await fetch(`${API_BASE}/api/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: cleanEmail, password })
            });
            if (res.ok) {
                const user = await res.json();
                setSession(user);
                return user;
            } else {
                const err = await res.json();
                throw new Error(err.detail || 'Invalid credentials.');
            }
        } catch (err) {
            if (err.message && !err.message.includes('fetch')) throw err;
            const users = getLocalUsers();
            const match = users.find(u => u.email === cleanEmail && u.password === btoa(password));
            if (!match) throw new Error('Invalid email or password.');
            const sessionUser = { name: match.name, email: match.email, role: match.role, unitType: match.unitType || '', barangay: match.barangay };
            setSession(sessionUser);
            return sessionUser;
        }
    }

    async function fetchReports() {
        try {
            const res = await fetch(`${API_BASE}/api/reports`);
            if (res.ok) {
                const data = await res.json();
                localStorage.setItem(REPORTS_KEY, JSON.stringify(data));
                return data;
            }
        } catch {}
        return JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
    }

    async function saveNewReport(report) {
        try {
            const res = await fetch(`${API_BASE}/api/reports`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(report)
            });
            if (!res.ok && res.status === 429) {
                const err = await res.json();
                throw new Error(err.detail || 'Rate limit exceeded.');
            }
            if (res.ok) {
                const local = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
                local.unshift(report);
                localStorage.setItem(REPORTS_KEY, JSON.stringify(local));
                return { reports: local, offlineQueued: false };
            }
        } catch (err) {
            if (err.message && (err.message.includes('Cooldown') || err.message.includes('Limit'))) throw err;
        }

        const local = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
        local.unshift(report);
        localStorage.setItem(REPORTS_KEY, JSON.stringify(local));

        const outbox = JSON.parse(localStorage.getItem(OUTBOX_KEY) || '[]');
        outbox.push(report);
        localStorage.setItem(OUTBOX_KEY, JSON.stringify(outbox));
        return { reports: local, offlineQueued: true };
    }

    async function flushOfflineOutbox() {
        const outbox = JSON.parse(localStorage.getItem(OUTBOX_KEY) || '[]');
        if (outbox.length === 0) return 0;
        const remaining = [];
        let syncedCount = 0;
        for (const item of outbox) {
            try {
                const res = await fetch(`${API_BASE}/api/reports`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(item)
                });
                if (res.ok || res.status === 429) syncedCount++;
                else remaining.push(item);
            } catch {
                remaining.push(item);
            }
        }
        localStorage.setItem(OUTBOX_KEY, JSON.stringify(remaining));
        return syncedCount;
    }

    async function updateReport(id, status, dispatchedUnit = null, resolvedImage = null, assignedUnitType = null) {
        const local = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
        const target = local.find(r => r.id === id);
        if (target) {
            target.status = status;
            if (dispatchedUnit !== null) target.dispatchedUnit = dispatchedUnit;
            if (assignedUnitType !== null) target.assignedUnitType = assignedUnitType;
            if (resolvedImage !== null) target.resolvedImage = resolvedImage;
            localStorage.setItem(REPORTS_KEY, JSON.stringify(local));
        }
        try {
            await fetch(`${API_BASE}/api/reports/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status, dispatchedUnit, assignedUnitType, resolvedImage })
            });
        } catch {}
        return local;
    }

    async function confirmReport(id, scoutEmail) {
        const local = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
        const target = local.find(r => r.id === id);
        if (target && target.scoutEmail !== scoutEmail) {
            target.confirmedBy = target.confirmedBy || [];
            if (!target.confirmedBy.includes(scoutEmail)) {
                target.confirmedBy.push(scoutEmail);
                target.confirmations = target.confirmedBy.length + 1;
                localStorage.setItem(REPORTS_KEY, JSON.stringify(local));
            }
        }
        try {
            await fetch(`${API_BASE}/api/reports/${id}/confirm`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ scoutEmail })
            });
        } catch {}
        return local;
    }

    function connectRealtime(onMessage) {
        if (!window.location.protocol.startsWith('http')) return;
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${wsProto}//${window.location.host}/ws`;
        function start() {
            const ws = new WebSocket(wsUrl);
            ws.onmessage = (e) => {
                try { onMessage(JSON.parse(e.data)); } catch {}
            };
            ws.onclose = () => setTimeout(start, 3000);
        }
        start();
    }

    return {
        getSession,
        setSession,
        getHomeRouteForRole,
        logout,
        registerAccount,
        loginAccount,
        fetchReports,
        saveNewReport,
        flushOfflineOutbox,
        updateReport,
        confirmReport,
        connectRealtime,
        REPORTS_KEY
    };
})();
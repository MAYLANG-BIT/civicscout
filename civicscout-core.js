// CivicScout Hybrid Core (FastAPI Backend + Automatic LocalStorage Fallback)
const CivicCore = (() => {
    const API_BASE = window.location.protocol.startsWith('http') ? '' : 'http://localhost:8000';
    const USERS_KEY = 'civicScoutUsers_v2';
    const SESSION_KEY = 'civicScoutSession_v2';
    const REPORTS_KEY = 'civicScoutReports_v2';
    const LGU_AUTH_CODE = 'BATIA-LGU-2026';

    // Ensure default demo LGU account exists in localStorage fallback
    function getLocalUsers() {
        let users = JSON.parse(localStorage.getItem(USERS_KEY) || '[]');
        if (!users.some(u => u.email === 'lgu@batia.gov.ph')) {
            users.push({
                name: 'Brgy. Batia Desk Officer',
                email: 'lgu@batia.gov.ph',
                password: btoa('batia2026'),
                role: 'lgu',
                barangay: 'Brgy. Batia'
            });
            localStorage.setItem(USERS_KEY, JSON.stringify(users));
        }
        return users;
    }

    function getSession() {
        try {
            return JSON.parse(localStorage.getItem(SESSION_KEY) || 'null');
        } catch {
            return null;
        }
    }

    function setSession(user) {
        localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    }

    function logout() {
        localStorage.removeItem(SESSION_KEY);
        window.location.href = 'index.html';
    }

    async function registerAccount({ name, email, password, role, barangay, lguCode }) {
        const cleanEmail = email.trim().toLowerCase();
        const cleanName = name.trim();

        if (!cleanName || !cleanEmail || !password) {
            throw new Error('All fields are required.');
        }
        if (role === 'lgu' && lguCode !== LGU_AUTH_CODE) {
            throw new Error('Invalid LGU Authorization Code. (Use: BATIA-LGU-2026)');
        }

        // Try Python FastAPI backend first
        try {
            const res = await fetch(`${API_BASE}/api/register`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: cleanName, email: cleanEmail, password, role, barangay, lguCode })
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
            // Fallback to localStorage
            const users = getLocalUsers();
            if (users.some(u => u.email === cleanEmail)) {
                throw new Error('An account with this email already exists.');
            }
            const newUser = {
                name: cleanName,
                email: cleanEmail,
                password: btoa(password),
                role,
                barangay
            };
            users.push(newUser);
            localStorage.setItem(USERS_KEY, JSON.stringify(users));
            const sessionUser = { name: newUser.name, email: newUser.email, role: newUser.role, barangay: newUser.barangay };
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
            if (!match) {
                throw new Error('Invalid email or password.');
            }
            const sessionUser = { name: match.name, email: match.email, role: match.role, barangay: match.barangay };
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
        const local = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
        local.unshift(report);
        localStorage.setItem(REPORTS_KEY, JSON.stringify(local));
        try {
            await fetch(`${API_BASE}/api/reports`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(report)
            });
        } catch {}
        return local;
    }

    async function updateReport(id, status, dispatchedUnit = null) {
        const local = JSON.parse(localStorage.getItem(REPORTS_KEY) || '[]');
        const target = local.find(r => r.id === id);
        if (target) {
            target.status = status;
            if (dispatchedUnit !== null) target.dispatchedUnit = dispatchedUnit;
            localStorage.setItem(REPORTS_KEY, JSON.stringify(local));
        }
        try {
            await fetch(`${API_BASE}/api/reports/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status, dispatchedUnit })
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

    return {
        getSession,
        setSession,
        logout,
        registerAccount,
        loginAccount,
        fetchReports,
        saveNewReport,
        updateReport,
        confirmReport,
        REPORTS_KEY
    };
})();
document.addEventListener('DOMContentLoaded', () => {
    console.log('thelolivaapp Init');

    let currentUser = null;
    let pollInterval = null;

    // -- Auth helpers --
    function getToken() { return localStorage.getItem('lolivaToken'); }

    async function authFetch(url, options = {}) {
        const headers = { ...(options.headers || {}), 'Authorization': `Bearer ${getToken()}` };
        const res = await fetch(url, { ...options, headers });
        if (res.status === 401) {
            logout();
            throw new Error('Unauthorized');
        }
        return res;
    }

    function logout() {
        localStorage.removeItem('lolivaToken');
        localStorage.removeItem('lolivaUser');
        currentUser = null;
        if (pollInterval) clearInterval(pollInterval);
        appContainer.style.display = 'none';
        loginOverlay.style.display = 'flex';
        showLoginStep1();
    }

    // -- Authentication Logic --
    const loginOverlay   = document.getElementById('login-overlay');
    const appContainer   = document.getElementById('app-container');
    const logoutBtn      = document.getElementById('logout-btn');
    const loginStep1     = document.getElementById('login-step-1');
    const loginStep2     = document.getElementById('login-step-2');
    const loginPassword  = document.getElementById('login-password');
    const loginConfirm   = document.getElementById('login-confirm-btn');
    const loginError     = document.getElementById('login-error');
    const loginBackBtn   = document.getElementById('login-back-btn');
    const loginLabel     = document.getElementById('login-selected-label');

    let pendingLoginUser = null;

    function showLoginStep1() {
        loginStep1.style.display = 'flex';
        loginStep2.style.display = 'none';
        loginError.style.display = 'none';
        loginPassword.value = '';
        pendingLoginUser = null;
    }

    function showLoginStep2(user) {
        pendingLoginUser = user;
        const names = { al: 'Al Pacino Gazpachino', pep: 'Pepinillo Aceitunillo' };
        loginLabel.textContent = names[user] || user;
        loginStep1.style.display = 'none';
        loginStep2.style.display = 'block';
        loginError.style.display = 'none';
        loginPassword.value = '';
        setTimeout(() => loginPassword.focus(), 50);
    }

    async function submitLogin() {
        if (!pendingLoginUser) return;
        const password = loginPassword.value;
        try {
            const res = await fetch('/api/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user: pendingLoginUser, password })
            });
            if (!res.ok) {
                loginError.style.display = 'block';
                loginPassword.value = '';
                loginPassword.focus();
                return;
            }
            const { token, user } = await res.json();
            localStorage.setItem('lolivaToken', token);
            localStorage.setItem('lolivaUser', user);
            enterApp(user);
        } catch (e) {
            console.error(e);
        }
    }

    document.querySelectorAll('.login-btn').forEach(btn => {
        btn.addEventListener('click', () => showLoginStep2(btn.getAttribute('data-user')));
    });

    loginConfirm.addEventListener('click', submitLogin);
    loginPassword.addEventListener('keydown', (e) => { if (e.key === 'Enter') submitLogin(); });
    loginBackBtn.addEventListener('click', showLoginStep1);

    logoutBtn.addEventListener('click', logout);

    function enterApp(user) {
        currentUser = user;
        loginOverlay.style.display = 'none';
        appContainer.style.display = 'block';

        if (document.querySelector('#home-view').classList.contains('active')) {
            fetchNextActivity();
            fetchScores();
        }
        if (document.querySelector('#map-container svg')) {
            startPolling();
        }
    }

    // Auto-login from saved token
    const savedToken = localStorage.getItem('lolivaToken');
    const savedUser  = localStorage.getItem('lolivaUser');
    if (savedToken && savedUser) {
        fetch('/api/me', { headers: { 'Authorization': `Bearer ${savedToken}` } })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (data && data.user) {
                    enterApp(data.user);
                }
            })
            .catch(() => {});
    }


    // -- Tabs Logic --
    const tabBtns = document.querySelectorAll('.tab-btn');
    const tabContents = document.querySelectorAll('.tab-content');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            tabBtns.forEach(b => b.classList.remove('active'));
            tabContents.forEach(c => {
                c.classList.remove('active');
                c.style.display = 'none';
            });

            btn.classList.add('active');
            const targetId = btn.getAttribute('data-target');
            const targetContent = document.getElementById(targetId);
            targetContent.classList.add('active');
            targetContent.style.display = '';

            if (targetId === 'map-view') {
                if (!document.querySelector('#map-container svg')) {
                    loadMap();
                } else {
                    startPolling();
                }
            } else {
                if (pollInterval) clearInterval(pollInterval);
                if (targetId === 'home-view') {
                    fetchNextActivity();
                    fetchScores();
                } else if (targetId === 'actividades-view') {
                    fetchActivities();
                }
            }
        });
    });


    // -- Map Server Logic --
    async function loadMap() {
        const mapContainer = document.getElementById('map-container');
        try {
            const response = await fetch('/world.svg');
            const svgContent = await response.text();
            mapContainer.innerHTML = svgContent;

            // Bind click events
            const paths = mapContainer.querySelectorAll('svg path, svg polygon');
            paths.forEach(path => {
                path.addEventListener('click', () => handleMapClick(path));

                // On iOS, panzoom intercepts touch events and prevents click synthesis.
                // Detect taps manually: fire only if finger barely moved (tap, not pan).
                let touchStartX, touchStartY;
                path.addEventListener('touchstart', (e) => {
                    touchStartX = e.touches[0].clientX;
                    touchStartY = e.touches[0].clientY;
                }, { passive: true });
                path.addEventListener('touchend', (e) => {
                    const dx = e.changedTouches[0].clientX - touchStartX;
                    const dy = e.changedTouches[0].clientY - touchStartY;
                    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) {
                        e.preventDefault();
                        handleMapClick(path);
                    }
                });
            });

            // Initialize panzoom
            const svgElement = mapContainer.querySelector('svg');
            if (typeof panzoom !== 'undefined' && svgElement) {
                mapContainer.style.touchAction = 'none';

                const pz = panzoom(svgElement, {
                    maxZoom: 10,
                    minZoom: 0.8,
                    bounds: true,
                    boundsPadding: 0.2
                });

                const width  = mapContainer.clientWidth;
                const height = mapContainer.clientHeight;
                const initialZoom = 4;

                const spainX = width  * (448 / 950);
                const spainY = height * (205 / 620);

                const dx = width  / 2 - spainX * initialZoom;
                const dy = height / 2 - spainY * initialZoom;

                pz.zoomAbs(0, 0, initialZoom);
                pz.moveTo(dx, dy);
            }

            startPolling();
        } catch (err) {
            console.error('Failed to load map:', err);
            mapContainer.innerHTML = '<p class="loading-spinner">Failed to load map data.</p>';
        }
    }

    async function handleMapClick(path) {
        if (!currentUser) return;
        const countryId = path.getAttribute('id');
        if (!countryId) return;

        try {
            const res = await authFetch('/api/click', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ countryId })
            });
            const data = await res.json();
            renderMapState(data);
        } catch (e) {
            console.error(e);
        }
    }

    function startPolling() {
        if (pollInterval) clearInterval(pollInterval);
        fetchMapState();
        fetchNextActivity();
        fetchScores();

        pollInterval = setInterval(() => {
            fetchMapState();
            fetchNextActivity();
            fetchScores();
        }, 3000);
    }

    async function fetchMapState() {
        try {
            const res = await authFetch('/api/map');
            const data = await res.json();
            renderMapState(data);
        } catch (e) {
            console.error(e);
        }
    }

    function renderMapState(state) {
        const alList  = state.al  || [];
        const pepList = state.pep || [];

        const paths = document.querySelectorAll('#map-container svg path, #map-container svg polygon');
        paths.forEach(path => {
            const id = path.getAttribute('id');
            if (!id) return;

            const isAl  = alList.includes(id);
            const isPep = pepList.includes(id);

            path.classList.remove('selected', 'selected-al', 'selected-pep', 'selected-both');

            if (isAl && isPep)   path.classList.add('selected-both');
            else if (isAl)       path.classList.add('selected-al');
            else if (isPep)      path.classList.add('selected-pep');
        });
    }

    // -- Actividades Logic --

    const toggleFormBtn = document.getElementById('toggle-form-btn');
    const formPanel     = document.getElementById('activity-form-panel');
    if (toggleFormBtn && formPanel) {
        toggleFormBtn.addEventListener('click', () => {
            const isOpen = formPanel.style.display !== 'none';
            formPanel.style.display = isOpen ? 'none' : 'block';
            toggleFormBtn.classList.toggle('open', !isOpen);
        });
    }

    const submitActivityBtn = document.getElementById('submit-activity');
    if (submitActivityBtn) {
        submitActivityBtn.addEventListener('click', async () => {
            if (!currentUser) return;
            const titleInput  = document.getElementById('activity-title');
            const descInput   = document.getElementById('activity-desc');
            const puntosInput = document.getElementById('activity-puntos');

            const titulo      = titleInput.value.trim();
            const descripcion = descInput.value.trim();
            const puntos      = parseInt(puntosInput.value, 10);

            if (!titulo || !descripcion || !puntos || puntos < 1) return;

            try {
                const res = await authFetch('/api/activity', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ titulo, descripcion, puntos })
                });

                if (res.ok) {
                    titleInput.value  = '';
                    descInput.value   = '';
                    puntosInput.value = '';
                    formPanel.style.display = 'none';
                    toggleFormBtn.classList.remove('open');
                    fetchActivities();
                }
            } catch (e) {
                console.error(e);
            }
        });
    }

    async function fetchActivities() {
        try {
            const res  = await authFetch('/api/activities');
            const data = await res.json();
            renderActivities(data);
        } catch (e) {
            console.error(e);
        }
    }

    async function fetchNextActivity() {
        try {
            const res = await authFetch('/api/next_activity');
            const act = await res.json();
            renderNextActivityBanner(act);
        } catch (e) {
            console.error(e);
        }
    }

    function renderNextActivityBanner(act) {
        const banner  = document.getElementById('next-activity-banner');
        const titleEl = document.getElementById('next-activity-title');
        const descEl  = document.getElementById('next-activity-desc');
        if (!banner || !titleEl || !descEl) return;

        if (act && act.status !== 'done') {
            titleEl.textContent = act.titulo;
            descEl.textContent  = act.descripcion;
            banner.style.display = 'block';
        } else {
            banner.style.display = 'none';
        }
    }

    // -- Winner Modal Logic --
    const winnerModal    = document.getElementById('winner-modal');
    const winnerModalPts = document.getElementById('winner-modal-pts');
    const winnerCancelBtn = document.getElementById('winner-modal-cancel');
    let _pendingToggleId = null;

    function openWinnerModal(actId, puntos) {
        _pendingToggleId = actId;
        winnerModalPts.textContent = `Esta actividad vale ${puntos} punto${puntos === 1 ? '' : 's'}.`;
        winnerModal.style.display = 'flex';
    }

    function closeWinnerModal() {
        winnerModal.style.display = 'none';
        _pendingToggleId = null;
    }

    if (winnerCancelBtn) winnerCancelBtn.addEventListener('click', closeWinnerModal);
    if (winnerModal) {
        winnerModal.addEventListener('click', (e) => {
            if (e.target === winnerModal) closeWinnerModal();
        });
    }

    document.querySelectorAll('.winner-choice-btn').forEach(btn => {
        btn.addEventListener('click', async () => {
            const winner = btn.getAttribute('data-winner');
            if (!_pendingToggleId || !winner) return;
            try {
                const res = await authFetch('/api/activity/toggle', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ id: _pendingToggleId, winner })
                });
                if (res.ok) {
                    const data = await res.json();
                    closeWinnerModal();
                    renderActivities(data);
                    fetchNextActivity();
                }
            } catch (e) {
                console.error(e);
            }
        });
    });

    function renderActivities(activitiesList) {
        const feedContainer = document.getElementById('activity-feed');
        if (!feedContainer) return;

        feedContainer.innerHTML = '';

        if (activitiesList.length === 0) {
            feedContainer.innerHTML = '<p style="text-align:center; color:var(--text-secondary);">No hay actividades todavía.</p>';
            return;
        }

        const sorted = [...activitiesList].sort((a, b) => {
            if (a.status === b.status) return 0;
            return a.status === 'pending' ? -1 : 1;
        });

        sorted.forEach(act => {
            const imgSrc      = act.user === 'al' ? '/gazpachino.png' : '/pepinillo.png';
            const isDone      = act.status === 'done';
            const statusClass = isDone ? 'done' : 'pending';
            const statusLabel = isDone ? 'Finalizada' : 'Por hacer';
            const puntos      = act.puntos ?? 1;

            let winnerChip = '';
            if (isDone && act.winner) {
                const winnerName  = act.winner === 'al' ? 'Al Pacino' : 'Pepinillo';
                const winnerColor = act.winner === 'al' ? '#c13a3a' : '#48a56a';
                const winnerImg   = act.winner === 'al' ? '/gazpachino.png' : '/pepinillo.png';
                winnerChip = `<div class="winner-chip" style="border-color:${winnerColor};">
                    <img src="${winnerImg}" class="winner-chip-avatar">
                    <span style="color:${winnerColor};">${escapeHTML(winnerName)}</span>
                </div>`;
            }

            const card = document.createElement('div');
            card.className = 'activity-card';
            card.innerHTML = `
                <img src="${imgSrc}" class="activity-avatar" alt="Avatar">
                <div class="activity-content">
                    <div style="display:flex; align-items:center; gap:0.5rem; flex-wrap:wrap;">
                        <h4>${escapeHTML(act.titulo)}</h4>
                        <span class="pts-badge">${puntos} pt${puntos === 1 ? '' : 's'}</span>
                    </div>
                    <p>${escapeHTML(act.descripcion)}</p>
                    ${winnerChip}
                    ${!isDone ? `<button class="select-next-btn" data-id="${act.id}">Seleccionar como siguiente actividad</button>` : ''}
                </div>
                <div style="display:flex; flex-direction:column; align-items:center; gap:4px;">
                    <div class="status-dot ${statusClass}" data-id="${act.id}" title="${statusLabel}"></div>
                    <span class="status-label">${statusLabel}</span>
                </div>
            `;

            card.querySelector('.status-dot').addEventListener('click', async () => {
                if (!isDone) {
                    openWinnerModal(act.id, puntos);
                } else {
                    try {
                        const res = await authFetch('/api/activity/toggle', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ id: act.id })
                        });
                        if (res.ok) {
                            const data = await res.json();
                            renderActivities(data);
                            fetchNextActivity();
                        }
                    } catch (e) {
                        console.error(e);
                    }
                }
            });

            if (!isDone) {
                card.querySelector('.select-next-btn').addEventListener('click', async () => {
                    try {
                        const res = await authFetch('/api/next_activity', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ id: act.id })
                        });
                        if (res.ok) {
                            fetchNextActivity();
                            const btn = card.querySelector('.select-next-btn');
                            btn.classList.add('selected-next');
                            btn.textContent = 'Seleccionada como siguiente';
                            setTimeout(() => {
                                btn.classList.remove('selected-next');
                                btn.innerHTML = 'Seleccionar como siguiente actividad';
                            }, 2000);
                        }
                    } catch (e) {
                        console.error(e);
                    }
                });
            }

            feedContainer.appendChild(card);
        });
    }

    // -- Clasificacion Logic --

    async function fetchScores() {
        try {
            const res    = await authFetch('/api/scores');
            const scores = await res.json();
            renderClasificacion(scores);
        } catch (e) {
            console.error(e);
        }
    }

    function renderClasificacion(scores) {
        const container = document.getElementById('clasificacion-feed');
        if (!container) return;

        const alPts  = scores.al  ?? 0;
        const pepPts = scores.pep ?? 0;
        const total  = alPts + pepPts;

        const players = [
            { key: 'al',  name: 'Al Pacino Gazpachino', avatar: '/gazpachino.png', points: alPts,  color: '#c13a3a' },
            { key: 'pep', name: 'Pepinillo Aceitunillo', avatar: '/pepinillo.png',  points: pepPts, color: '#48a56a' }
        ].sort((a, b) => b.points - a.points);

        const isTie      = players[0].points === players[1].points;
        const rankColors = ['#ffebc9', '#f0f0f0'];

        container.innerHTML = '';

        const title = document.createElement('h2');
        title.className = 'clasificacion-title';
        title.textContent = 'Clasificación';
        container.appendChild(title);

        const subtitle = document.createElement('p');
        subtitle.className = 'clasificacion-subtitle';
        if (isTie && total > 0) {
            subtitle.textContent = '¡Empate! Cada uno con ' + players[0].points + ' pts.';
        } else if (isTie) {
            subtitle.textContent = 'Aún no hay puntos. ¡A por ello!';
        } else {
            const diff = players[0].points - players[1].points;
            subtitle.textContent = players[0].name.split(' ')[0] + ' lleva ' + diff + ' punto' + (diff === 1 ? '' : 's') + ' de ventaja.';
        }
        container.appendChild(subtitle);

        if (total > 0) {
            const barWrap = document.createElement('div');
            barWrap.className = 'rank-bar-wrap neo-box';
            const alW  = Math.round((alPts / total) * 100);
            const pepW = 100 - alW;
            barWrap.innerHTML = `
                <div class="rank-bar">
                    <div class="rank-bar-segment" style="width:${alW}%; background:#c13a3a;" title="Al Pacino: ${alPts}pts"></div>
                    <div class="rank-bar-segment" style="width:${pepW}%; background:#48a56a;" title="Pepinillo: ${pepPts}pts"></div>
                </div>
                <div class="rank-bar-labels">
                    <span style="color:#c13a3a;">Al ${alW}%</span>
                    <span style="color:#48a56a;">Pep ${pepW}%</span>
                </div>
            `;
            container.appendChild(barWrap);
        }

        players.forEach((player, idx) => {
            const isFirst = idx === 0;
            const card = document.createElement('div');
            card.className = 'rank-card neo-box' + (isFirst && !isTie ? ' rank-first' : '');
            card.style.background = rankColors[idx];
            card.innerHTML = `
                <img src="${player.avatar}" class="rank-avatar" alt="${player.name}">
                <div class="rank-info">
                    <span class="rank-name">${player.name}</span>
                    <span class="rank-points" style="color:${player.color};">${player.points} <span class="rank-pts-label">pts</span></span>
                </div>
                <div class="rank-badge rank-pos-${idx + 1}">#${idx + 1}</div>
            `;
            container.appendChild(card);
        });
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g,
            tag => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[tag] || tag)
        );
    }

    // Register Service Worker
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('/sw.js').catch(err => {
                console.warn('ServiceWorker registration failed: ', err);
            });
        });
    }

    const helloBtn = document.getElementById('hello-btn');
    if (helloBtn) {
        helloBtn.addEventListener('click', () => {
            const originalText = helloBtn.querySelector('span').innerText;
            helloBtn.querySelector('span').innerText = 'Hello, World!';
            helloBtn.style.background = 'var(--accent-hover)';
            helloBtn.style.color = '#fff';
            setTimeout(() => {
                helloBtn.querySelector('span').innerText = originalText;
                helloBtn.style.background = '';
                helloBtn.style.color = '';
            }, 2000);
        });
    }
});

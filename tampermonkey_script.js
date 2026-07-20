// ==UserScript==
// @name         הערת לידים ישנים
// @namespace    http://tampermonkey.net/
// @version      4.0
// @match        https://crm.sehel.co.il/*
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    const BOT_URL = 'https://oren-cohen-bot.onrender.com';
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    // ─── פופאפ פיילוט WhatsApp ───────────────────────────────────────────────

    function createPilotPopup() {
        if (document.getElementById('wa-pilot-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'wa-pilot-overlay';
        overlay.style.cssText = `
            position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.5);z-index:99999;display:flex;
            align-items:center;justify-content:center;
        `;

        overlay.innerHTML = `
            <div style="background:#fff;border-radius:12px;padding:24px;width:480px;
                        max-height:80vh;overflow-y:auto;direction:rtl;font-family:Arial,sans-serif;
                        box-shadow:0 8px 32px rgba(0,0,0,0.3);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                    <h3 style="margin:0;font-size:18px;">🚀 שליחת WhatsApp — פיילוט</h3>
                    <button id="wa-pilot-close" style="background:none;border:none;font-size:20px;cursor:pointer;">✕</button>
                </div>

                <p style="color:#666;font-size:13px;margin-bottom:8px;">🔍 חפש לפי שם או טלפון והוסף לרשימה:</p>
                <div style="display:flex;gap:8px;margin-bottom:16px;">
                    <input id="wa-pilot-search" type="text" placeholder="יוסי כהן או 0501234567"
                        style="flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:8px;font-size:13px;direction:rtl;" />
                    <button id="wa-pilot-search-btn" style="padding:8px 14px;background:#007bff;
                        color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;">חפש</button>
                </div>
                <div id="wa-pilot-search-results" style="display:none;margin-bottom:12px;max-height:150px;
                    overflow-y:auto;border:1px solid #ddd;border-radius:8px;"></div>

                <p style="color:#666;font-size:13px;margin-bottom:8px;">
                    או הדבק רשימה — כל שורה: <strong>טלפון,שם,פרויקט</strong> (עד 100 שורות)
                </p>

                <textarea id="wa-pilot-input" style="width:100%;height:140px;border:1px solid #ddd;
                    border-radius:8px;padding:10px;font-size:13px;direction:ltr;resize:vertical;
                    box-sizing:border-box;" placeholder="0501234567,יוסי כהן,רזידנס&#10;0509876543,דנה לוי,&#10;..."></textarea>

                <div id="wa-pilot-preview" style="display:none;margin-top:12px;padding:10px;
                    background:#f8f9fa;border-radius:8px;font-size:13px;"></div>

                <div style="display:flex;gap:8px;margin-top:16px;">
                    <button id="wa-pilot-preview-btn" style="flex:1;padding:10px;background:#6c757d;
                        color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;">
                        👁 תצוגה מקדימה
                    </button>
                    <button id="wa-pilot-send-btn" style="flex:1;padding:10px;background:#25D366;
                        color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">
                        🚀 שלח הכל
                    </button>
                </div>

                <div id="wa-pilot-status" style="margin-top:12px;font-size:13px;display:none;
                    padding:10px;border-radius:8px;"></div>

                <div id="wa-pilot-progress" style="display:none;margin-top:12px;">
                    <div style="background:#e9ecef;border-radius:4px;height:8px;">
                        <div id="wa-pilot-bar" style="background:#25D366;height:8px;border-radius:4px;
                            width:0%;transition:width 0.3s;"></div>
                    </div>
                    <p id="wa-pilot-progress-text" style="text-align:center;font-size:12px;color:#666;margin-top:4px;"></p>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        document.getElementById('wa-pilot-close').onclick = () => overlay.remove();
        overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };

        document.getElementById('wa-pilot-search-btn').onclick = searchLead;
        document.getElementById('wa-pilot-search').addEventListener('keydown', e => {
            if (e.key === 'Enter') searchLead();
        });
        document.getElementById('wa-pilot-preview-btn').onclick = showPreview;
        document.getElementById('wa-pilot-send-btn').onclick = sendBulk;
    }

    async function searchLead() {
        const query = document.getElementById('wa-pilot-search').value.trim();
        if (!query) return;

        const btn = document.getElementById('wa-pilot-search-btn');
        const resultsDiv = document.getElementById('wa-pilot-search-results');
        btn.textContent = '...';
        btn.disabled = true;

        try {
            const cols = ['index','nameHtml','name1','name2','phoneHtml','phone1','phone2','email1','email2',
                'needsCity','needsRooms','needsBudget','stageHtml','stage','lastEventDate','projectNameHtml',
                'objectionHtml','tagsHtml','createDate','updateDate','timelineHtml','mediaHtml',
                'spamPermitStatus','clientId','cardButtonHtml'];
            const searchable = ['nameHtml','phoneHtml','objectionHtml'];
            const orderable = ['index','nameHtml','name1','name2','phone1','phone2','email1','email2',
                'needsCity','needsRooms','needsBudget','stageHtml','stage','lastEventDate','projectNameHtml',
                'objectionHtml','tagsHtml','createDate','updateDate','mediaHtml','spamPermitStatus','clientId'];

            const params = new URLSearchParams();
            params.append('draw', '1');
            cols.forEach((col, i) => {
                params.append(`columns[${i}][data]`, col);
                params.append(`columns[${i}][name]`, '');
                params.append(`columns[${i}][searchable]`, searchable.includes(col) ? 'true' : 'false');
                params.append(`columns[${i}][orderable]`, orderable.includes(col) ? 'true' : 'false');
                params.append(`columns[${i}][search][value]`, '');
                params.append(`columns[${i}][search][regex]`, 'false');
            });
            params.append('order[0][column]', '19');
            params.append('order[0][dir]', 'desc');
            params.append('start', '0');
            params.append('length', '20');
            params.append('search[value]', '');
            params.append('search[regex]', 'false');
            params.append('inwork', '');
            params.append('projects', '');
            params.append('needsRealtorCityIds', '');
            params.append('needsRealtorNeighborhoodIds', '');
            params.append('appTypes', '');
            params.append('dealType', ' ');
            params.append('ignoreObjection', '0');
            params.append('objections', '');
            params.append('ignoreStage', '0');
            params.append('noFollowUp', '0');
            params.append('clStage', '');
            params.append('ignoreTags', '0');
            params.append('tags', '');
            params.append('fromRooms', '');
            params.append('toRooms', '');
            params.append('events', '');
            params.append('agentFilter', '');
            params.append('ignoreMedia', '0');
            params.append('mediaList', '');
            params.append('priceSliderValues', '');
            params.append('search[value]', query);
            params.append('date-from', '');
            params.append('date-to', '');
            params.append('update-date-from', '');
            params.append('update-date-to', '');

            const res = await fetch('/api/clientsServerSide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: params.toString()
            });
            const text = await res.text();
            let data;
            try { data = JSON.parse(text); } catch(e) {
                resultsDiv.style.display = 'block';
                resultsDiv.innerHTML = '<div style="padding:10px;color:red;font-size:13px;">שגיאת פרסור</div>';
                btn.textContent = 'חפש'; btn.disabled = false;
                return;
            }
            const leads = data.data || [];

            if (!leads.length) {
                resultsDiv.style.display = 'block';
                resultsDiv.innerHTML = '<div style="padding:10px;color:#666;font-size:13px;">לא נמצאו תוצאות</div>';
                return;
            }

            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = leads.map(l => {
                const name = l.name1 || l.clientName || '';
                const phone = l.phone1 || '';
                const div = document.createElement('div');
                div.innerHTML = l.projectNameHtml || '';
                const project = div.querySelector('.label')?.innerText?.trim() || '';
                return `<div style="padding:8px 12px;cursor:pointer;border-bottom:1px solid #f0f0f0;
                    font-size:13px;hover:background:#f8f9fa;"
                    onclick="document.getElementById('wa-pilot-input').value += 
                        (document.getElementById('wa-pilot-input').value ? '\\n' : '') +
                        '${phone},${name},${project}';
                    document.getElementById('wa-pilot-search-results').style.display='none';
                    document.getElementById('wa-pilot-search').value='';"
                    onmouseover="this.style.background='#f0f7ff'"
                    onmouseout="this.style.background=''"
                >
                    📱 ${phone} &nbsp;|&nbsp; ${name} &nbsp;|&nbsp; <span style="color:#666">${project || 'יד 2'}</span>
                </div>`;
            }).join('');

        } catch(e) {
            resultsDiv.style.display = 'block';
            resultsDiv.innerHTML = `<div style="padding:10px;color:red;font-size:13px;">שגיאה: ${e.message}</div>`;
        }

        btn.textContent = 'חפש';
        btn.disabled = false;
    }

    function parseLines() {
        const raw = document.getElementById('wa-pilot-input').value.trim();
        if (!raw) return [];
        return raw.split('\n')
            .map(line => line.trim())
            .filter(line => line.length > 0)
            .slice(0, 100)
            .map(line => {
                const parts = line.split(',');
                let phone = (parts[0] || '').trim().replace(/[\s\-]/g, '');
                // נרמול לפורמט +972
                if (phone.startsWith('05')) phone = '+972' + phone.slice(1);
                else if (phone.startsWith('972')) phone = '+' + phone;
                else if (!phone.startsWith('+')) phone = '+' + phone;
                return {
                    phone,
                    name: (parts[1] || '').trim() || null,
                    project_name: (parts[2] || '').trim(),
                };
            })
            .filter(l => l.phone.length >= 10);
    }

    function showPreview() {
        const leads = parseLines();
        const preview = document.getElementById('wa-pilot-preview');
        if (!leads.length) {
            preview.style.display = 'block';
            preview.innerHTML = '<span style="color:red;">לא נמצאו שורות תקינות</span>';
            return;
        }
        preview.style.display = 'block';
        preview.innerHTML = `
            <strong>נמצאו ${leads.length} לידים:</strong><br><br>
            ${leads.slice(0, 5).map(l =>
                `✓ ${l.phone} | ${l.name || '—'} | ${l.project_name || 'יד 2'}`
            ).join('<br>')}
            ${leads.length > 5 ? `<br><span style="color:#666">...ועוד ${leads.length - 5}</span>` : ''}
        `;
    }

    async function sendBulk() {
        const leads = parseLines();
        if (!leads.length) {
            alert('לא נמצאו שורות תקינות');
            return;
        }

        const btn = document.getElementById('wa-pilot-send-btn');
        const status = document.getElementById('wa-pilot-status');
        const progress = document.getElementById('wa-pilot-progress');
        const bar = document.getElementById('wa-pilot-bar');
        const progressText = document.getElementById('wa-pilot-progress-text');

        btn.disabled = true;
        btn.textContent = '⏳ שולח...';
        progress.style.display = 'block';
        status.style.display = 'none';

        try {
            progressText.textContent = `שולח ${leads.length} הודעות...`;
            bar.style.width = '30%';

            const res = await fetch(`${BOT_URL}/api/whatsapp/bulk-reengagement`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ leads })
            });

            bar.style.width = '100%';
            const result = await res.json();

            status.style.display = 'block';
            status.style.background = result.failed === 0 ? '#d4edda' : '#fff3cd';
            status.style.color = result.failed === 0 ? '#155724' : '#856404';
            status.innerHTML = `
                ✅ נשלח: <strong>${result.sent}</strong> &nbsp;|&nbsp;
                ❌ נכשל: <strong>${result.failed}</strong>
                ${result.failed > 0 ? '<br><small>בדוק את הלוגים ב-Render</small>' : ''}
            `;
            progressText.textContent = 'הושלם!';

        } catch (e) {
            status.style.display = 'block';
            status.style.background = '#f8d7da';
            status.style.color = '#721c24';
            status.textContent = `שגיאה: ${e.message}`;
        }

        btn.disabled = false;
        btn.textContent = '🚀 שלח הכל';
    }

    // ─── הערת לידים ישנים (קוד מקורי) ──────────────────────────────────────

    function parseSehelDate(str) {
        if (!str) return null;
        const m = str.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$/);
        if (!m) return null;
        let y = parseInt(m[3]);
        if (y < 100) y += 2000;
        return new Date(y, parseInt(m[2]) - 1, parseInt(m[1]));
    }

    async function getLastNoteDate(clientId) {
        await fetch(`/client/${clientId}`, { credentials: 'include' });
        await sleep(300);
        const res = await fetch('/api/getSystemMessageHtml.php', {
            credentials: 'include',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        if (!res.ok) return null;
        const html = await res.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        const firstDay = doc.querySelector('li.tl-day');
        return firstDay ? parseSehelDate(firstDay.textContent.trim()) : null;
    }

    async function wakeUpLeads() {
        alert("מתחיל בתהליך... נא לא לסגור את הדפדפן.");

        let allLeads = [];
        let start = 0;
        const pageSize = 500;

        while (true) {
            const response = await fetch('/api/clientsServerSide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: `draw=1&start=${start}&length=${pageSize}`
            });
            const data = await response.json();
            const page = data.data || [];
            allLeads = allLeads.concat(page);
            if (page.length < pageSize) break;
            start += pageSize;
        }

        const SIX_MONTHS_AGO = new Date();
        SIX_MONTHS_AGO.setMonth(SIX_MONTHS_AGO.getMonth() - 6);

        alert(`נמצאו ${allLeads.length} לידים. בודק הערות...`);

        const toWakeUp = [];

        for (let i = 0; i < allLeads.length; i++) {
            const lead = allLeads[i];
            const clientId = lead.clientId || lead.id;

            let lastDate = await getLastNoteDate(clientId);

            if (!lastDate) {
                const parts = (lead.createDate || '').split(' ')[0].split('-');
                if (parts.length === 3) lastDate = new Date(+parts[2], +parts[1] - 1, +parts[0]);
            }

            if (lastDate && lastDate < SIX_MONTHS_AGO) {
                toWakeUp.push({ ...lead, _lastDate: lastDate });
            }

            if ((i + 1) % 20 === 0) {
                console.log(`[הערת לידים] ${i + 1}/${allLeads.length} — להעיר: ${toWakeUp.length}`);
            }

            await sleep(200);
        }

        alert(`נמצאו ${toWakeUp.length} לידים ללא קשר מעל 6 חודשים. מתחיל העברה...`);

        let success = 0, failed = 0, skipped = 0;
        const BATCH = 20;

        for (let i = 0; i < toWakeUp.length; i += BATCH) {
            const batch = toWakeUp.slice(i, i + BATCH);
            await Promise.all(batch.map(async lead => {
                try {
                    const div = document.createElement("div");
                    div.innerHTML = lead.projectNameHtml || "";
                    const projectName = div.querySelector(".label")?.innerText?.trim() || "";
                    const agentName = div.querySelector(".routedAgent")?.innerText?.trim() || "";

                    const res = await fetch(`${BOT_URL}/api/whatsapp/start-reengagement`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            phone: lead.phone1,
                            name: lead.name1,
                            project_name: projectName,
                            agent_name: agentName,
                        })
                    });
                    const result = await res.json();
                    if (result.status === "skipped") skipped++;
                    else success++;
                } catch (e) {
                    failed++;
                }
            }));

            if (i + BATCH < toWakeUp.length) {
                await sleep(3 * 60 * 1000);
            }
        }

        alert(`סיום!\nהועברו: ${success}\nדולגו: ${skipped}\nנכשלו: ${failed}`);
    }

    // ─── כפתורים בניווט ──────────────────────────────────────────────────────

    function addButtons() {
        const projectsLink = document.querySelector('a[href="/projects/app/listing"]');
        if (!projectsLink) return;

        // כפתור הערת לידים (מקורי)
        const li1 = document.createElement("li");
        li1.innerHTML = `
            <a href="javascript:void(0)" id="wakeUpNavBtn">
                <i class="fa-regular fa-bell"></i>
                <span>הערת לידים</span>
            </a>`;
        projectsLink.closest("li").insertAdjacentElement("afterend", li1);
        document.getElementById("wakeUpNavBtn").addEventListener("click", wakeUpLeads);

        // כפתור פיילוט WhatsApp
        const li2 = document.createElement("li");
        li2.innerHTML = `
            <a href="javascript:void(0)" id="waPilotNavBtn">
                <i class="fa-brands fa-whatsapp"></i>
                <span>פיילוט WhatsApp</span>
            </a>`;
        li1.insertAdjacentElement("afterend", li2);
        document.getElementById("waPilotNavBtn").addEventListener("click", createPilotPopup);
    }

    const interval = setInterval(() => {
        if (document.querySelector('a[href="/projects/app/listing"]')) {
            clearInterval(interval);
            addButtons();
        }
    }, 500);

})();

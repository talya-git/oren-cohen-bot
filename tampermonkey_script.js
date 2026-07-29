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
    const SIMULATE = true; // ← שנה ל-false לשליחה אמיתית
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

                <div style="margin-top:16px;border-top:1px solid #eee;padding-top:12px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <strong style="font-size:13px;">📊 תוצאות פיילוט</strong>
                        <div style="display:flex;gap:6px;">
                            <button id="wa-pilot-refresh" style="padding:4px 10px;background:#007bff;color:#fff;
                                border:none;border-radius:6px;cursor:pointer;font-size:12px;">🔄 רענן</button>
                            <button id="wa-pilot-clear" style="padding:4px 10px;background:#dc3545;color:#fff;
                                border:none;border-radius:6px;cursor:pointer;font-size:12px;">🗑 נקה</button>
                        </div>
                    </div>
                    <div id="wa-pilot-results-table" style="font-size:12px;max-height:200px;overflow-y:auto;">
                        <p style="color:#999;text-align:center;">לחץ רענן לטעינת תוצאות</p>
                    </div>
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
        document.getElementById('wa-pilot-refresh').onclick = refreshResults;
        document.getElementById('wa-pilot-clear').onclick = async () => {
            await fetch(`${BOT_URL}/api/whatsapp/pilot-clear`, { method: 'POST' });
            refreshResults();
        };
    }

    async function refreshResults() {
        const table = document.getElementById('wa-pilot-results-table');
        if (!table) return;
        try {
            const res = await fetch(`${BOT_URL}/api/whatsapp/pilot-results`);
            const data = await res.json();
            const results = data.results || [];
            if (!results.length) {
                table.innerHTML = '<p style="color:#999;text-align:center;">אין נתונים עדיין</p>';
                return;
            }
            const scoreColor = s => s === 'High' ? '#28a745' : s === 'Medium' ? '#fd7e14' : s === 'Low' ? '#dc3545' : '#999';
            table.innerHTML = `
                <table style="width:100%;border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f8f9fa;">
                            <th style="padding:6px;text-align:right;border-bottom:1px solid #dee2e6;">טלפון</th>
                            <th style="padding:6px;text-align:right;border-bottom:1px solid #dee2e6;">שם</th>
                            <th style="padding:6px;text-align:center;border-bottom:1px solid #dee2e6;">ענה?</th>
                            <th style="padding:6px;text-align:center;border-bottom:1px solid #dee2e6;">העברה?</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${results.map(r => `
                            <tr style="border-bottom:1px solid #f0f0f0;">
                                <td style="padding:5px 6px;font-size:11px;">${r.phone}</td>
                                <td style="padding:5px 6px;">${r.name || '—'}</td>
                                <td style="padding:5px 6px;text-align:center;">${r.replied ? '✅' : '⏳'}</td>
                                <td style="padding:5px 6px;text-align:center;">${r.handoff ? '✅' : '—'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            `;
        } catch(e) {
            table.innerHTML = `<p style="color:red;font-size:12px;">שגיאה: ${e.message}</p>`;
        }
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

    async function enrichLeadsFromSehel(leads) {
        const results = [];
        for (const lead of leads) {
            if (lead.project_name) { results.push(lead); continue; }
            try {
                const params = new URLSearchParams();
                params.append('draw', '1');
                ['index','nameHtml','name1','name2','phoneHtml','phone1','phone2','email1','email2',
                 'needsCity','needsRooms','needsBudget','stageHtml','stage','lastEventDate','projectNameHtml',
                 'objectionHtml','tagsHtml','createDate','updateDate','timelineHtml','mediaHtml',
                 'spamPermitStatus','clientId','cardButtonHtml'].forEach((col, i) => {
                    params.append(`columns[${i}][data]`, col);
                    params.append(`columns[${i}][name]`, '');
                    params.append(`columns[${i}][searchable]`, ['nameHtml','phoneHtml','objectionHtml'].includes(col) ? 'true' : 'false');
                    params.append(`columns[${i}][orderable]`, 'true');
                    params.append(`columns[${i}][search][value]`, '');
                    params.append(`columns[${i}][search][regex]`, 'false');
                });
                params.append('order[0][column]', '19'); params.append('order[0][dir]', 'desc');
                params.append('start', '0'); params.append('length', '5');
                params.append('search[value]', ''); params.append('search[regex]', 'false');
                ['inwork','projects','needsRealtorCityIds','needsRealtorNeighborhoodIds','appTypes',
                 'objections','clStage','tags','fromRooms','toRooms','events','agentFilter','mediaList','priceSliderValues',
                 'date-from','date-to','update-date-from','update-date-to'].forEach(k => params.append(k, ''));
                params.append('dealType', ' '); params.append('ignoreObjection', '0');
                params.append('ignoreStage', '0'); params.append('noFollowUp', '0');
                params.append('ignoreTags', '0'); params.append('ignoreMedia', '0');
                params.append('search[value]', lead.phone.replace('+972', '0').replace('+', ''));

                const res = await fetch('/api/clientsServerSide', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                    body: params.toString()
                });
                const data = JSON.parse(await res.text());
                const found = (data.data || [])[0];
                if (found) {
                    const div = document.createElement('div');
                    div.innerHTML = found.projectNameHtml || '';
                    const project = div.querySelector('.label')?.innerText?.trim() || '';
                    if (!lead.name) lead.name = found.name1 || lead.name;
                    lead.project_name = project;
                }
            } catch(e) {}
            results.push(lead);
        }
        return results;
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
            progressText.textContent = 'מחפש פרטים בשכל...';
            bar.style.width = '15%';
            const enriched = await enrichLeadsFromSehel(leads);

            progressText.textContent = `שולח ${enriched.length} הודעות...`;
            bar.style.width = '30%';

            const res = await fetch(`${BOT_URL}/api/whatsapp/bulk-reengagement`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ leads: enriched })
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

    // ─── הערת לידים — ממשק חדש ──────────────────────────────────────────────

    const AGENTS = [
        { label: 'ינון',    email: 'yaniv@orencohengroup.com' },
        { label: 'משה',     email: 'moshe@orencohengroup.com' },
        { label: 'מירי',    email: 'miri@orencohengroup.com' },
        { label: 'מיכאל',  email: 'michael@orencohengroup.com' },
        { label: 'רבקה',   email: 'rivka@orencohengroup.com' },
        { label: 'אוריאל', email: 'uriel400@orencohengroup.com' },
        { label: 'אלחנן',  email: 'elchanan@orencohengroup.com' },
        { label: 'אורן',   email: 'oren@orencohengroup.com' },
        { label: 'אריה',   email: 'aryeh@orencohengroup.com' },
        { label: 'בועז',   email: 'office@orencohengroup.com' },
        { label: 'חנה',    email: 'hannah@orencohengroup.com' },
        { label: 'אהרון',  email: 'aaron@orencohengroup.com' },
        { label: 'ליסה',   email: 'lisa@orencohengroup.com' },
        { label: 'דב',     email: 'dovr@orencohengroup.com' },
    ];

    // state
    let wl_agent = null;       // { label, email }
    let wl_offset = 0;         // דף נוכחי
    let wl_leads = [];         // הלידים המוצגים כרגע
    let wl_sentPhones = new Set();

    async function fetchSentPhones() {
        try {
            const res = await fetch(`${BOT_URL}/api/whatsapp/sent-phones?agent_email=${encodeURIComponent(wl_agent.email)}`);
            const data = await res.json();
            wl_sentPhones = new Set(data.phones || []);
        } catch(e) { wl_sentPhones = new Set(); }
    }

    function normalizePhone(p) {
        if (!p) return '';
        p = p.trim().replace(/[\s\-]/g, '');
        if (p.startsWith('05')) return '+972' + p.slice(1);
        if (p.startsWith('972')) return '+' + p;
        if (!p.startsWith('+')) return '+' + p;
        return p;
    }

    function parseSehelDate(str) {
        if (!str) return null;
        // DD.MM.YYYY or DD.MM.YY
        const m = str.trim().match(/^(\d{1,2})\.(\d{1,2})\.(\d{2,4})$/);
        if (!m) return null;
        let y = parseInt(m[3]);
        if (y < 100) y += 2000;
        return new Date(y, parseInt(m[2]) - 1, parseInt(m[1]));
    }

    // טוען עמוד של 20 לידים לפי סוכן, מסנן 6 חודשים + לא נשלח
    async function loadWlPage() {
        const tbody = document.getElementById('wl-tbody');
        const statusEl = document.getElementById('wl-status');
        if (!tbody) return;
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:12px;color:#666;">טוען...</td></tr>';

        const SIX_MONTHS_AGO = new Date(); // בדיקה — מציג הכל
        // SIX_MONTHS_AGO.setMonth(SIX_MONTHS_AGO.getMonth() - 6);

        const cols = ['index','nameHtml','name1','name2','phoneHtml','phone1','phone2','email1','email2',
            'needsCity','needsRooms','needsBudget','stageHtml','stage','lastEventDate','projectNameHtml',
            'objectionHtml','tagsHtml','createDate','updateDate','timelineHtml','mediaHtml',
            'spamPermitStatus','clientId','cardButtonHtml'];

        const params = new URLSearchParams();
        params.append('draw', '1');
        cols.forEach((col, i) => {
            params.append(`columns[${i}][data]`, col);
            params.append(`columns[${i}][name]`, '');
            params.append(`columns[${i}][searchable]`, ['nameHtml','phoneHtml','objectionHtml'].includes(col) ? 'true' : 'false');
            params.append(`columns[${i}][orderable]`, 'true');
            params.append(`columns[${i}][search][value]`, '');
            params.append(`columns[${i}][search][regex]`, 'false');
        });
        params.append('order[0][column]', '19'); params.append('order[0][dir]', 'asc'); // ישנים קודם
        params.append('start', String(wl_offset));
        params.append('length', '500'); // טוענים 500 כדי לסנן ל-20
        params.append('search[value]', ''); params.append('search[regex]', 'false');
        ['inwork','projects','needsRealtorCityIds','needsRealtorNeighborhoodIds','appTypes',
         'objections','clStage','tags','fromRooms','toRooms','events','mediaList','priceSliderValues',
         'date-from','date-to','update-date-from','update-date-to'].forEach(k => params.append(k, ''));
        params.append('dealType', ' '); params.append('ignoreObjection', '0');
        params.append('ignoreStage', '0'); params.append('noFollowUp', '0');
        params.append('ignoreTags', '0'); params.append('ignoreMedia', '0');
        params.append('agentFilter[]', wl_agent.email);

        let raw = [];
        try {
            const res = await fetch('/api/clientsServerSide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: params.toString()
            });
            const data = await res.json();
            raw = data.data || [];
        } catch(e) {
            tbody.innerHTML = `<tr><td colspan="4" style="color:red;padding:12px;">${e.message}</td></tr>`;
            return;
        }

        // סינון: לא נשלח בלבד (ללא סינון תאריך לבדיקה)
        // קוד מקורי עם סינון 6 חודשים:
        // const SIX_MONTHS_AGO = new Date();
        // SIX_MONTHS_AGO.setMonth(SIX_MONTHS_AGO.getMonth() - 6);
        // const filtered = raw.filter(lead => {
        //     const phone = normalizePhone(lead.phone1);
        //     if (wl_sentPhones.has(phone)) return false;
        //     const parts = (lead.updateDate || lead.createDate || '').split(' ')[0].split('-');
        //     let d = null;
        //     if (parts.length === 3) d = new Date(+parts[2], +parts[1] - 1, +parts[0]);
        //     return d && d < SIX_MONTHS_AGO;
        // }).slice(0, 20);
        const filtered = raw.filter(lead => {
            const phone = normalizePhone(lead.phone1);
            return !wl_sentPhones.has(phone);
        }).slice(0, 20);

        wl_leads = filtered;

        if (statusEl) statusEl.textContent = `נמצאו ${filtered.length} לידים (עמוד ${Math.floor(wl_offset/100)+1})`;

        if (!filtered.length) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:12px;color:#666;">אין לידים נוספים</td></tr>';
            return;
        }

        tbody.innerHTML = filtered.map((lead, idx) => {
            const phone = normalizePhone(lead.phone1);
            const name = lead.name1 || '—';
            const div = document.createElement('div');
            div.innerHTML = lead.projectNameHtml || '';
            const project = div.querySelector('.label')?.innerText?.trim() || 'יד 2';
            const parts = (lead.updateDate || lead.createDate || '').split(' ')[0].split('-');
            const dateStr = parts.length === 3 ? `${parts[0]}.${parts[1]}.${parts[2]}` : '—';
            return `
                <tr style="border-bottom:1px solid #f0f0f0;">
                    <td style="padding:6px;text-align:center;">
                        <input type="checkbox" class="wl-cb" data-idx="${idx}" checked>
                    </td>
                    <td style="padding:6px;font-size:13px;">${name}<br><span style="color:#888;font-size:11px;">${phone}</span></td>
                    <td style="padding:6px;font-size:12px;color:#555;">${project}</td>
                    <td style="padding:6px;font-size:11px;color:#999;">${dateStr}</td>
                    <td style="padding:6px;text-align:center;">
                        <input type="text" class="wl-name-edit" data-idx="${idx}"
                            value="${name !== '—' ? name : ''}"
                            placeholder="ללא שם"
                            style="width:90px;padding:3px 6px;border:1px solid #ddd;border-radius:4px;font-size:12px;direction:rtl;">
                    </td>
                </tr>`;
        }).join('');
    }

    async function sendWlSelected() {
        const checkboxes = document.querySelectorAll('.wl-cb:checked');
        if (!checkboxes.length) { alert('לא נבחרו לידים'); return; }

        const btn = document.getElementById('wl-send-btn');
        btn.disabled = true;
        btn.textContent = '⏳ שולח...';

        let success = 0, skipped = 0, failed = 0;
        const sentPhones = [];
        for (const cb of checkboxes) {
            const lead = wl_leads[parseInt(cb.dataset.idx)];
            if (!lead) continue;
            const div = document.createElement('div');
            div.innerHTML = lead.projectNameHtml || '';
            const project = div.querySelector('.label')?.innerText?.trim() || '';
            const phone = normalizePhone(lead.phone1);
            try {
                const nameInput = document.querySelector(`.wl-name-edit[data-idx="${cb.dataset.idx}"]`);
                const editedName = nameInput ? nameInput.value.trim() || null : lead.name1 || null;
                const res = await fetch(`${BOT_URL}/api/whatsapp/start-reengagement`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        phone: lead.phone1,
                        name: editedName,
                        project_name: project,
                        agent_email: wl_agent.email,
                    })
                });
                const r = await res.json();
                if (r.status === 'skipped') skipped++;
                else { success++; sentPhones.push(phone); }
                wl_sentPhones.add(phone);
            } catch(e) { failed++; }
            await sleep(500);
        }

        // יצירת batch ושליחת הודעת אישור לסוכן
        if (sentPhones.length) {
            try {
                await fetch(`${BOT_URL}/api/whatsapp/notify-agent`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        agent_email: wl_agent.email,
                        agent_label: wl_agent.label,
                        phones: sentPhones,
                    })
                });
            } catch(e) {}
        }

        const statusEl = document.getElementById('wl-send-status');
        if (statusEl) {
            statusEl.style.display = 'block';
            statusEl.textContent = `✅ נשלח: ${success} | דולג: ${skipped} | נכשל: ${failed} — תקבל דוח במייל תוך 24 שעות`;
        }
        btn.disabled = false;
        btn.textContent = '📤 שלח מסומנים';
        wl_offset += 100;
        await loadWlPage();
    }

    function createWakeUpPopup() {
        if (document.getElementById('wl-overlay')) return;

        const overlay = document.createElement('div');
        overlay.id = 'wl-overlay';
        overlay.style.cssText = `position:fixed;top:0;left:0;width:100%;height:100%;
            background:rgba(0,0,0,0.5);z-index:99999;display:flex;
            align-items:center;justify-content:center;`;

        overlay.innerHTML = `
            <div style="background:#fff;border-radius:12px;padding:24px;width:560px;
                        max-height:85vh;overflow-y:auto;direction:rtl;font-family:Arial,sans-serif;
                        box-shadow:0 8px 32px rgba(0,0,0,0.3);">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
                    <h3 style="margin:0;font-size:18px;">🔔 הערת לידים ישנים</h3>
                    <button id="wl-close" style="background:none;border:none;font-size:20px;cursor:pointer;">✕</button>
                </div>

                <!-- בחירת סוכן -->
                <p style="font-size:13px;color:#555;margin-bottom:8px;">בחר סוכן:</p>
                <div id="wl-agents" style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px;">
                    ${AGENTS.map(a => `
                        <button class="wl-agent-btn" data-email="${a.email}"
                            style="padding:6px 12px;border:1px solid #ddd;border-radius:20px;
                                   background:#f8f9fa;cursor:pointer;font-size:13px;">
                            ${a.label}
                        </button>`).join('')}
                </div>

                <!-- סטטוס שליחה -->
                <div id="wl-send-status" style="display:none;margin-top:10px;padding:10px;border-radius:8px;
                    background:#d4edda;color:#155724;font-size:13px;text-align:center;"></div>

                <!-- טבלת לידים -->
                <div id="wl-table-wrap" style="display:none;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                        <span id="wl-status" style="font-size:13px;color:#555;"></span>
                        <label style="font-size:12px;cursor:pointer;">
                            <input type="checkbox" id="wl-select-all" checked> בחר הכל
                        </label>
                    </div>
                    <table style="width:100%;border-collapse:collapse;font-size:13px;">
                        <thead>
                            <tr style="background:#f8f9fa;">
                                <th style="padding:6px;width:32px;"></th>
                                <th style="padding:6px;text-align:right;">שם / טלפון</th>
                                <th style="padding:6px;text-align:right;">פרויקט</th>
                                <th style="padding:6px;text-align:right;">עדכון</th>
                                <th style="padding:6px;text-align:center;">שם לשליחה</th>
                            </tr>
                        </thead>
                        <tbody id="wl-tbody"></tbody>
                    </table>
                    <div style="display:flex;gap:8px;margin-top:12px;">
                        <button id="wl-send-btn" style="flex:1;padding:10px;background:#25D366;
                            color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:bold;">
                            📤 שלח מסומנים
                        </button>
                        <button id="wl-next-btn" style="flex:1;padding:10px;background:#007bff;
                            color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;">
                            ⏭ 20 הבאים
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(overlay);

        document.getElementById('wl-close').onclick = () => overlay.remove();
        overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };

        document.getElementById('wl-select-all').addEventListener('change', function() {
            document.querySelectorAll('.wl-cb').forEach(cb => cb.checked = this.checked);
        });

        document.querySelectorAll('.wl-agent-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                document.querySelectorAll('.wl-agent-btn').forEach(b => {
                    b.style.background = '#f8f9fa'; b.style.borderColor = '#ddd'; b.style.color = '#000';
                });
                btn.style.background = '#25D366'; btn.style.borderColor = '#25D366'; btn.style.color = '#fff';
                wl_agent = AGENTS.find(a => a.email === btn.dataset.email);
                wl_offset = 0;
                document.getElementById('wl-table-wrap').style.display = 'block';
                await fetchSentPhones();
                await loadWlPage();
            });
        });

        document.getElementById('wl-send-btn').onclick = sendWlSelected;
        document.getElementById('wl-next-btn').onclick = async () => {
            wl_offset += 100;
            await loadWlPage();
        };
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
        document.getElementById("wakeUpNavBtn").addEventListener("click", createWakeUpPopup);

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

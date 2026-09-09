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
    const SIMULATE = true;
    const sleep = ms => new Promise(r => setTimeout(r, ms));

    const AGENTS = [
        { label: 'יניב',    email: 'yaniv@orencohengroup.com' },
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
        { label: 'נתנאל',  email: 'netanel@orencohengroup.com' },
        { label: 'נעמי',   email: 'NaomiS@orencohengroup.com' },
        { label: 'אייזיק', email: 'aizik@orencohengroup.com' },
    ];

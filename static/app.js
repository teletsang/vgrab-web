// ============================================================
// vgrab-web 前端（IIFE 隔离全局作用域）
// ============================================================
(function(window) {
'use strict';

// ============================================================
// 通用轮询工具（指数退避 + 最大重试）
// ============================================================
function createPoller(url, onData, opts) {
    opts = opts || {};
    var initialInterval = opts.initialInterval || 1000;
    var maxInterval = opts.maxInterval || 10000;
    var backoffFactor = opts.backoffFactor || 1.5;
    var maxRetries = opts.maxRetries || 60;
    var isComplete = opts.isComplete || function(data) {
        return !['queued','downloading','analyzing','transcribing','recording','stopping','organizing'].includes(data.status);
    };

    var interval = initialInterval;
    var active = true;
    var retries = 0;

    var poll = function() {
        if (!active) return;
        fetch(url)
            .then(function(r) { return r.json(); })
            .then(function(data) {
                interval = initialInterval;
                retries = 0;
                onData(data);
                if (!isComplete(data) && active) {
                    setTimeout(poll, interval);
                }
            })
            .catch(function() {
                retries++;
                if (retries >= maxRetries) {
                    active = false;
                    return;
                }
                interval = Math.min(interval * backoffFactor, maxInterval);
                if (active) setTimeout(poll, interval);
            });
    };

    poll();
    return { stop: function() { active = false; } };
}

// ============================================================
// Tab 切换
// ============================================================
function switchTab(name) {
    const labels = {'download':'下载','transcribe':'转录','analyze':'分析','record':'录制','settings':'设置'};
    document.querySelectorAll('.tab').forEach(t => {
        t.classList.toggle('active', t.textContent.trim() === labels[name]);
    });
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    document.getElementById('tab-' + name).classList.add('active');
}

// ============================================================
// 初始化
// ============================================================
fetch('/api/status').then(r => r.json()).then(data => {
    document.getElementById('current-dir').textContent = '当前: ' + data.download_dir;
    document.getElementById('opt-output').placeholder = data.download_dir;
    // 显示版本号
    if (data.version) {
        var vEl = document.getElementById('app-version');
        if (vEl) vEl.textContent = 'v' + data.version;
    }
});

// 加载设置（localStorage 持久化）
function loadSettings() {
    const keys = ['opt-llm-url', 'opt-llm-model', 'opt-api-key', 'opt-frame-interval', 'opt-max-tokens', 'opt-temperature', 'opt-proxy', 'opt-output'];
    keys.forEach(k => {
        const v = localStorage.getItem('vgrab_' + k);
        if (v) document.getElementById(k).value = v;
    });
}
function saveSettings() {
    const keys = ['opt-llm-url', 'opt-llm-model', 'opt-api-key', 'opt-frame-interval', 'opt-max-tokens', 'opt-temperature', 'opt-proxy', 'opt-output'];
    keys.forEach(k => {
        localStorage.setItem('vgrab_' + k, document.getElementById(k).value);
    });
}
loadSettings();
// 自动保存
document.querySelectorAll('#tab-settings input, #tab-settings select').forEach(el => {
    el.addEventListener('change', saveSettings);
    el.addEventListener('input', saveSettings);
});

// 回车触发下载
document.getElementById('url-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') startDownload();
});

// ============================================================
// 下载
// ============================================================
let downloadPolling = new Set();

function startDownload() {
    const url = document.getElementById('url-input').value.trim();
    if (!url) return;

    const options = {
        audio_only: document.getElementById('opt-audio').checked,
        subs: document.getElementById('opt-subs').checked,
        proxy: document.getElementById('opt-proxy').value.trim() || null,
        output_dir: document.getElementById('opt-output').value.trim() || null,
    };

    document.getElementById('download-btn').disabled = true;

    fetch('/api/download', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url, options})
    })
    .then(r => r.json())
    .then(data => {
        if (data.task_id) {
            addDownloadCard(data.task_id, url);
            pollDownload(data.task_id);
            document.getElementById('url-input').value = '';
        }
        document.getElementById('download-btn').disabled = false;
    })
    .catch(err => {
        showToast('网络错误: ' + err);
        document.getElementById('download-btn').disabled = false;
    });
}

function addDownloadCard(taskId, url) {
    const list = document.getElementById('download-tasks');
    const div = document.createElement('div');
    div.className = 'task downloading';
    div.id = 'dl-' + taskId;
    div.innerHTML = `
        <div class="task-header">
            <span class="task-title">${esc(url)}</span>
            <span class="badge downloading">下载中</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
        <div class="progress-text">准备中...</div>
    `;
    list.prepend(div);
}

function pollDownload(taskId) {
    if (downloadPolling.has(taskId)) return;
    downloadPolling.add(taskId);
    createPoller('/api/task/' + taskId, function(data) {
        updateDownloadCard(taskId, data);
        if (data.status !== 'downloading' && data.status !== 'queued') {
            downloadPolling.delete(taskId);
        }
    }, { isComplete: function(d) { return d.status !== 'downloading' && d.status !== 'queued'; } });
}

function updateDownloadCard(taskId, data) {
    const card = document.getElementById('dl-' + taskId);
    if (!card) return;

    card.className = 'task ' + data.status;
    const badge = card.querySelector('.badge');
    badge.className = 'badge ' + data.status;
    badge.textContent = data.status === 'done' ? '完成' : data.status === 'error' ? '失败' : '下载中';

    if (data.title && data.title !== data.url) card.querySelector('.task-title').textContent = data.title;
    card.querySelector('.progress-fill').style.width = (data.percent || 0) + '%';
    card.querySelector('.progress-text').textContent = data.progress || '';

    if (data.status === 'done' && data.files && !card.querySelector('.file-list')) {
        const fl = document.createElement('div');
        fl.className = 'file-list';
        fl.innerHTML = data.files.map(f => {
            const isVideo = f.name.match(/\.(mp4|mkv|webm|avi|mov)$/i);
            return `
            <div class="file-item">
                <div class="file-info">
                    <div class="file-name">${esc(f.name)}</div>
                    <div class="file-size">${fmtSize(f.size)}</div>
                </div>
                ${isVideo ? `<a class="file-download" style="background:rgba(48,209,88,0.15);color:var(--green)" href="javascript:void(0)" onclick="previewVideo('/api/file/${taskId}/${encodeURIComponent(f.name)}')">\u9884\u89c8</a>` : ''}
                <a class="file-download" href="/api/file/${taskId}/${encodeURIComponent(f.name)}?download" download>\u4fdd\u5b58</a>
            </div>
        `}).join('');
        // 操作按钮
        const hasVid = data.files.some(f => f.name.match(/\.(mp4|mkv|webm|avi|mov)$/i));
        if (hasVid) {
            const vidPath = data.files.find(f => f.name.match(/\.(mp4|mkv|webm|avi|mov)$/i)).path;
            fl.innerHTML += `<div style="display:flex;gap:8px;margin-top:12px">`;
            fl.innerHTML += `<button class="btn btn-ghost" style="flex:1;font-size:0.85rem" onclick="transcribeFromDownload('${esc(vidPath)}')">\u8f6c\u5f55</button>`;
            fl.innerHTML += `<button class="btn btn-ghost" style="flex:1;font-size:0.85rem" onclick="analyzeFromDownload('${esc(vidPath)}')">AI \u5206\u6790</button>`;
            fl.innerHTML += `</div>`;
        }
        card.appendChild(fl);
    }
}

// ============================================================
// 分析
// ============================================================
let analyzePolling = new Set();

function analyzeFromDownload(videoPath) {
    document.getElementById('analyze-path').value = videoPath;
    switchTab('analyze');
    startAnalyze();
}

function startAnalyze() {
    const videoPath = document.getElementById('analyze-path').value.trim();
    if (!videoPath) return;

    const settings = {
        llm_url: document.getElementById('opt-llm-url').value.trim() || 'http://127.0.0.1:8080',
        model: document.getElementById('opt-llm-model').value.trim() || 'gemma-4',
        api_key: document.getElementById('opt-api-key').value.trim() || '',
        mode: document.getElementById('opt-analyze-mode').value,
        frame_interval: parseInt(document.getElementById('opt-frame-interval').value) || 30,
        max_tokens: parseInt(document.getElementById('opt-max-tokens').value) || 4096,
        temperature: parseFloat(document.getElementById('opt-temperature').value) || 0.3,
    };

    fetch('/api/analyze', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({video_path: videoPath, settings})
    })
    .then(r => r.json())
    .then(data => {
        if (data.analyze_id) {
            addAnalyzeCard(data.analyze_id, videoPath);
            pollAnalyze(data.analyze_id);
        } else {
            showToast(data.error || '启动分析失败');
        }
    });
}

function addAnalyzeCard(analyzeId, videoPath) {
    const list = document.getElementById('analyze-tasks');
    const div = document.createElement('div');
    div.className = 'task downloading';
    div.id = 'az-' + analyzeId;
    const name = videoPath.split('/').pop();
    div.innerHTML = `
        <div class="task-header">
            <span class="task-title">${esc(name)}</span>
            <span class="badge analyzing">分析中</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
        <div class="progress-text">准备中...</div>
    `;
    list.prepend(div);
}

function pollAnalyze(analyzeId) {
    if (analyzePolling.has(analyzeId)) return;
    analyzePolling.add(analyzeId);
    createPoller('/api/analyze/' + analyzeId, function(data) {
        updateAnalyzeCard(analyzeId, data);
        if (data.status !== 'analyzing') {
            analyzePolling.delete(analyzeId);
        }
    }, { initialInterval: 2000, isComplete: function(d) { return d.status !== 'analyzing'; } });
}

function updateAnalyzeCard(analyzeId, data) {
    const card = document.getElementById('az-' + analyzeId);
    if (!card) return;

    const statusMap = { analyzing: 'downloading', done: 'done', error: 'error' };
    card.className = 'task ' + (statusMap[data.status] || 'downloading');

    const badge = card.querySelector('.badge');
    badge.className = 'badge ' + (data.status === 'analyzing' ? 'analyzing' : data.status);
    badge.textContent = data.status === 'done' ? '完成' : data.status === 'error' ? '失败' : '分析中';

    // 进度
    const pct = data.slices_total ? (data.slices_done / data.slices_total * 100) : 0;
    card.querySelector('.progress-fill').style.width = (data.status === 'done' ? 100 : pct) + '%';
    card.querySelector('.progress-text').textContent = data.progress || '';

    // 结果
    if (data.status === 'done' && data.result && !card.querySelector('.analysis-result')) {
        const res = document.createElement('div');
        res.className = 'analysis-result';
        res.textContent = data.result;
        card.appendChild(res);
    }
}

// ============================================================
// 工具函数
// ============================================================
function esc(s) { return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#39;'); }
function fmtSize(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b/1024).toFixed(1) + ' KB';
    if (b < 1073741824) return (b/1048576).toFixed(1) + ' MB';
    return (b/1073741824).toFixed(2) + ' GB';
}

// Toast 通知（替代 alert）
function showToast(message, type) {
    type = type || 'error';
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    const colors = { error: 'var(--red, #ff453a)', success: 'var(--green, #30d158)', info: 'var(--accent, #0a84ff)' };
    toast.style.cssText = 'position:fixed;bottom:24px;left:50%;transform:translateX(-50%);'
        + 'padding:12px 24px;border-radius:10px;font-size:0.85rem;font-weight:500;z-index:10000;'
        + 'animation:fadeInUp 0.3s ease;color:#fff;box-shadow:0 8px 32px rgba(0,0,0,0.4);'
        + 'background:' + (colors[type] || colors.error) + ';max-width:80%;text-align:center';
    document.body.appendChild(toast);
    setTimeout(function() { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; setTimeout(function() { toast.remove(); }, 300); }, 4000);
}

// 视频预览播放器
function previewVideo(url) {
    // 移除已有的
    const old = document.getElementById('video-preview-overlay');
    if (old) old.remove();

    const overlay = document.createElement('div');
    overlay.id = 'video-preview-overlay';
    overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.9);z-index:9999;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px';
    overlay.innerHTML = `
        <div style="position:absolute;top:20px;right:24px">
            <button onclick="closePreview()" style="background:rgba(255,255,255,0.15);border:none;color:#fff;font-size:1.2rem;padding:8px 16px;border-radius:8px;cursor:pointer">✕ 关闭</button>
        </div>
        <video controls autoplay style="max-width:90%;max-height:80%;border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,0.5)" src="${url}"></video>
    `;
    overlay.addEventListener('click', (e) => { if (e.target === overlay) closePreview(); });
    document.body.appendChild(overlay);
}

function closePreview() {
    const el = document.getElementById('video-preview-overlay');
    if (el) el.remove();
}

// ============================================================
// 转录
// ============================================================
let transcribePolling = new Set();

function transcribeFromDownload(videoPath) {
    document.getElementById('transcribe-path').value = videoPath;
    switchTab('transcribe');
    startTranscribe();
}

function startTranscribe() {
    const videoPath = document.getElementById('transcribe-path').value.trim();
    if (!videoPath) return;

    fetch('/api/transcribe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({video_path: videoPath, settings: {}})
    })
    .then(r => r.json())
    .then(data => {
        if (data.transcribe_id) {
            addTranscribeCard(data.transcribe_id, videoPath);
            pollTranscribe(data.transcribe_id);
        } else {
            showToast(data.error || '启动转录失败');
        }
    });
}

function addTranscribeCard(transcribeId, videoPath) {
    const list = document.getElementById('transcribe-tasks');
    const div = document.createElement('div');
    div.className = 'task downloading';
    div.id = 'tr-' + transcribeId;
    const name = videoPath.split('/').pop();
    div.innerHTML = `
        <div class="task-header">
            <span class="task-title">${esc(name)}</span>
            <span class="badge analyzing">转录中</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
        <div class="progress-text">准备中...</div>
    `;
    list.prepend(div);
}

function pollTranscribe(transcribeId) {
    if (transcribePolling.has(transcribeId)) return;
    transcribePolling.add(transcribeId);
    createPoller('/api/transcribe/' + transcribeId, function(data) {
        updateTranscribeCard(transcribeId, data);
        if (data.status !== 'transcribing') {
            transcribePolling.delete(transcribeId);
        }
    }, { initialInterval: 2000, isComplete: function(d) { return d.status !== 'transcribing'; } });
}

function updateTranscribeCard(transcribeId, data) {
    const card = document.getElementById('tr-' + transcribeId);
    if (!card) return;

    const statusMap = { transcribing: 'downloading', done: 'done', error: 'error' };
    card.className = 'task ' + (statusMap[data.status] || 'downloading');

    const badge = card.querySelector('.badge');
    badge.className = 'badge ' + (data.status === 'transcribing' ? 'analyzing' : data.status);
    badge.textContent = data.status === 'done' ? '完成' : data.status === 'error' ? '失败' : '转录中';

    // 转录没有进度百分比，用脉冲动画
    card.querySelector('.progress-fill').style.width = data.status === 'done' ? '100%' : '60%';
    card.querySelector('.progress-text').textContent = data.progress || '';

    if (data.status === 'done' && data.result && !card.querySelector('.analysis-result')) {
        const res = document.createElement('div');
        res.className = 'analysis-result';
        res.textContent = data.result;
        card.appendChild(res);

        // 整理笔记按钮
        if (!card.querySelector('.organize-btn')) {
            const btn = document.createElement('button');
            btn.className = 'btn btn-ghost organize-btn';
            btn.style.cssText = 'margin-top:12px;width:100%;font-size:0.85rem';
            btn.textContent = '\u6574\u7406\u7b14\u8bb0';
            btn.onclick = () => organizeTranscript(card, data.result);
            card.appendChild(btn);
        }
    }
}

// ============================================================
// 录制
// ============================================================
let recordPolling = new Set();

function startRecord() {
    const url = document.getElementById('record-url').value.trim();
    if (!url) return;

    const title = document.getElementById('record-title').value.trim() || '直播录制';
    const maxMin = parseInt(document.getElementById('record-max-duration').value) || 0;
    const settings = { title };
    if (maxMin > 0) settings.max_duration = maxMin * 60;

    fetch('/api/record', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url, settings})
    })
    .then(r => r.json())
    .then(data => {
        if (data.live_id) {
            addRecordCard(data.live_id, title);
            pollRecord(data.live_id);
            document.getElementById('record-url').value = '';
        } else {
            showToast(data.error || '启动录制失败');
        }
    });
}

function addRecordCard(liveId, title) {
    const list = document.getElementById('record-tasks');
    const div = document.createElement('div');
    div.className = 'task downloading';
    div.id = 'rc-' + liveId;
    div.innerHTML = `
        <div class="task-header">
            <span class="task-title">${esc(title)}</span>
            <span class="badge downloading">录制中</span>
        </div>
        <div class="progress-track"><div class="progress-fill" style="width:0%"></div></div>
        <div class="progress-text">连接中...</div>
        <button class="btn" style="margin-top:12px;width:100%;background:var(--red)" onclick="stopRecord('${liveId}')">停止录制</button>
    `;
    list.prepend(div);
}

function stopRecord(liveId) {
    fetch('/api/record/' + liveId + '/stop', { method: 'POST' })
    .then(r => r.json())
    .then(() => {
        const card = document.getElementById('rc-' + liveId);
        if (card) {
            const btn = card.querySelector('button');
            if (btn) btn.textContent = '停止中...';
        }
    });
}

function pollRecord(liveId) {
    if (recordPolling.has(liveId)) return;
    recordPolling.add(liveId);
    createPoller('/api/record/' + liveId, function(data) {
        updateRecordCard(liveId, data);
        if (data.status !== 'recording' && data.status !== 'stopping') {
            recordPolling.delete(liveId);
        }
    }, { initialInterval: 2000, isComplete: function(d) { return d.status !== 'recording' && d.status !== 'stopping'; } });
}

function updateRecordCard(liveId, data) {
    const card = document.getElementById('rc-' + liveId);
    if (!card) return;

    const statusMap = { recording: 'downloading', done: 'done', error: 'error', stopping: 'downloading' };
    card.className = 'task ' + (statusMap[data.status] || 'downloading');

    const badge = card.querySelector('.badge');
    badge.className = 'badge ' + (data.status === 'recording' ? 'downloading' : data.status === 'done' ? 'done' : data.status === 'error' ? 'error' : 'analyzing');
    badge.textContent = data.status === 'done' ? '完成' : data.status === 'error' ? '失败' : data.status === 'stopping' ? '停止中' : '录制中';

    card.querySelector('.progress-fill').style.width = data.status === 'done' ? '100%' : '50%';
    card.querySelector('.progress-text').textContent = data.progress || '';

    // 录制完成后显示操作按钮
    if ((data.status === 'done') && !card.querySelector('.file-list')) {
        const btn = card.querySelector('button');
        if (btn) btn.remove();

        const fl = document.createElement('div');
        fl.className = 'file-list';
        const fileName = data.file_path ? data.file_path.split('/').pop() : '录制文件';
        fl.innerHTML = `
            <div class="file-item">
                <div class="file-info">
                    <div class="file-name">${esc(fileName)}</div>
                    <div class="file-size">${fmtSize(data.file_size || 0)}</div>
                </div>
            </div>
            <div style="display:flex;gap:8px;margin-top:12px">
                <button class="btn btn-ghost" style="flex:1;font-size:0.85rem" onclick="transcribeFromDownload('${esc(data.file_path || '')}')">转录</button>
                <button class="btn btn-ghost" style="flex:1;font-size:0.85rem" onclick="analyzeFromDownload('${esc(data.file_path || '')}')">AI 分析</button>
            </div>
        `;
        card.appendChild(fl);
    }
}

// ============================================================
// 整理笔记
// ============================================================
function organizeTranscript(card, transcript) {
    // 去掉时间轴部分，只取纯文本
    const textOnly = transcript.split('---')[0].trim();
    if (!textOnly) return;

    const settings = {
        llm_url: document.getElementById('opt-llm-url').value.trim() || 'http://127.0.0.1:8080',
        model: document.getElementById('opt-llm-model').value.trim() || 'gemma-4',
        api_key: document.getElementById('opt-api-key').value.trim() || '',
        max_tokens: parseInt(document.getElementById('opt-max-tokens').value) || 4096,
        temperature: 0.3,
    };

    // 替换按钮文字
    const btn = card.querySelector('.organize-btn');
    if (btn) { btn.textContent = '整理中...'; btn.disabled = true; }

    fetch('/api/organize', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({transcript: textOnly, settings})
    })
    .then(r => r.json())
    .then(data => {
        if (data.note_id) {
            pollOrganize(data.note_id, card, btn);
        } else {
            if (btn) { btn.textContent = '整理失败'; btn.disabled = false; }
        }
    });
}

function pollOrganize(noteId, card, btn) {
    createPoller('/api/organize/' + noteId, function(data) {
        if (data.status === 'done') {
            if (btn) btn.remove();
            const existing = card.querySelector('.analysis-result');
            if (existing) existing.textContent = data.result;
            const tag = document.createElement('div');
            tag.style.cssText = 'font-size:0.7rem;color:var(--green);margin-top:8px;font-weight:600';
            tag.textContent = '✓ 已整理';
            card.appendChild(tag);
        } else if (data.status === 'error') {
            if (btn) { btn.textContent = '整理失败'; btn.disabled = false; }
        }
    }, { initialInterval: 2000, isComplete: function(d) { return d.status !== 'organizing'; } });
}

// ============================================================
// 文件浏览器
// ============================================================

let _fileBrowserTarget = null;

function openFileBrowser(targetInputId) {
    _fileBrowserTarget = targetInputId;
    _browseTo('');
    document.getElementById('file-browser-overlay').style.display = 'flex';
}

function closeFileBrowser() {
    document.getElementById('file-browser-overlay').style.display = 'none';
}

function _browseTo(path) {
    const list = document.getElementById('file-browser-list');
    const pathDisplay = document.getElementById('file-browser-path');
    list.innerHTML = '<div style="padding:20px;opacity:0.5">加载中...</div>';
    
    fetch('/api/browse?path=' + encodeURIComponent(path))
        .then(r => r.json())
        .then(data => {
            if (data.error) {
                const errDiv = document.createElement('div');
                errDiv.style.cssText = 'padding:20px;color:#ff6b6b';
                errDiv.textContent = data.error;
                list.innerHTML = '';
                list.appendChild(errDiv);
                return;
            }
            pathDisplay.textContent = data.path;
            list.innerHTML = '';
            data.items.forEach(item => {
                const el = document.createElement('div');
                el.className = 'file-browser-item' + (item.type === 'dir' ? ' is-dir' : '');
                const icon = item.type === 'dir' ? '📁' : '🎬';
                const size = item.size ? ` (${_fmtSize(item.size)})` : '';
                el.innerHTML = `<span>${icon} ${esc(item.name)}${size}</span>`;
                el.onclick = () => {
                    if (item.type === 'dir') {
                        _browseTo(item.path);
                    } else {
                        document.getElementById(_fileBrowserTarget).value = item.path;
                        closeFileBrowser();
                    }
                };
                list.appendChild(el);
            });
        })
        .catch(err => {
            list.innerHTML = `<div style="padding:20px;color:#ff6b6b">加载失败</div>`;
        });
}

function _fmtSize(b) {
    if (b < 1024) return b + ' B';
    if (b < 1048576) return (b / 1024).toFixed(1) + ' KB';
    if (b < 1073741824) return (b / 1048576).toFixed(1) + ' MB';
    return (b / 1073741824).toFixed(2) + ' GB';
}

// ============================================================
// 暴露全局函数（供 HTML onclick 使用）
// ============================================================
window.switchTab = switchTab;
window.startDownload = startDownload;
window.startAnalyze = startAnalyze;
window.startTranscribe = startTranscribe;
window.startRecord = startRecord;
window.stopRecord = stopRecord;
window.openFileBrowser = openFileBrowser;
window.closeFileBrowser = closeFileBrowser;
window.previewVideo = previewVideo;
window.closePreview = closePreview;
window.analyzeFromDownload = analyzeFromDownload;
window.transcribeFromDownload = transcribeFromDownload;

})(window);

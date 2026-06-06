const state = {
  page: 1,
  perPage: 20,
  total: 0,
  source: "",
  loggedIn: false,
  filterMode: "all",
  allCourses: [],
};

const els = {
  status: document.getElementById("status"),
  authView: document.getElementById("authView"),
  appView: document.getElementById("appView"),
  loginForm: document.getElementById("loginForm"),
  reuseCookieBtn: document.getElementById("reuseCookieBtn"),
  authError: document.getElementById("authError"),
  authLoading: document.getElementById("authLoading"),
  form: document.getElementById("searchForm"),
  courseBody: document.getElementById("courseBody"),
  resultMeta: document.getElementById("resultMeta"),
  loading: document.getElementById("loading"),
  errorBox: document.getElementById("errorBox"),
  pageInfo: document.getElementById("pageInfo"),
  prevPage: document.getElementById("prevPage"),
  nextPage: document.getElementById("nextPage"),
  shutdownBtn: document.getElementById("shutdownBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  liveSpaceLink: document.getElementById("liveSpaceLink"),
  filterToggle: document.getElementById("filterToggle"),
  cacheAllBtn: document.getElementById("cacheAllBtn"),
  collegeSelect: document.getElementById("collegeSelect"),
  termSelect: document.getElementById("termSelect"),
  campusSelect: document.getElementById("campusSelect"),
  buildingSelect: document.getElementById("buildingSelect"),
  roomSelect: document.getElementById("roomSelect"),
};

async function api(path) {
  const resp = await fetch(path);
  const data = await resp.json();
  if (!resp.ok) {
    throw new Error(data.error || data.msg || `请求失败 (${resp.status})`);
  }
  return data;
}

async function apiPost(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : "{}",
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    throw new Error(data.error || data.msg || `请求失败 (${resp.status})`);
  }
  return data;
}

function setStatus(text, ok) {
  els.status.textContent = text;
  els.status.className = "status " + (ok ? "ok" : "err");
}

function showLoading(on) {
  els.loading.classList.toggle("hidden", !on);
}

function showError(msg) {
  if (!msg) {
    els.errorBox.classList.add("hidden");
    els.errorBox.textContent = "";
    return;
  }
  els.errorBox.textContent = msg;
  els.errorBox.classList.remove("hidden");
}

function showAuthError(msg) {
  if (!msg) {
    els.authError.classList.add("hidden");
    els.authError.textContent = "";
    return;
  }
  els.authError.textContent = msg;
  els.authError.classList.remove("hidden");
}

function showAuthLoading(on) {
  els.authLoading.classList.toggle("hidden", !on);
}

function showApp(on) {
  els.authView.classList.toggle("hidden", on);
  els.appView.classList.toggle("hidden", !on);
  if (els.logoutBtn) els.logoutBtn.style.display = on ? "" : "none";
  if (els.liveSpaceLink) els.liveSpaceLink.style.display = on ? "" : "none";
}

function fillSelect(select, items, valueKey, labelKey, placeholder) {
  select.innerHTML = "";
  const first = document.createElement("option");
  first.value = "";
  first.textContent = placeholder;
  select.appendChild(first);
  for (const item of items) {
    const opt = document.createElement("option");
    opt.value = String(item[valueKey]);
    opt.textContent = item[labelKey];
    select.appendChild(opt);
  }
}

async function loadMeta() {
  const [status, terms, colleges, campuses] = await Promise.all([
    api("/api/status"),
    api("/api/meta/terms"),
    api("/api/meta/colleges"),
    api("/api/meta/campuses"),
  ]);

  setStatus(`已登录 · ${status.user}`, true);

  fillSelect(els.termSelect, terms.list, "id", "term_name", "全部学期");
  fillSelect(
    els.collegeSelect,
    colleges.list,
    "kkxy_code",
    "kkxy_name",
    "全部学院"
  );
  fillSelect(
    els.campusSelect,
    campuses.list,
    "id",
    "campus_name",
    "全部校区"
  );
}

async function loadAuth() {
  try {
    const data = await api("/api/auth/status");
    if (data.logged_in) {
      state.loggedIn = true;
      setStatus(`已登录 · ${data.user}`, true);
      showApp(true);
      await loadMeta();
      // 默认显示当天课程
      const dateInput = els.form.querySelector('input[name="create_at"]');
      if (dateInput) dateInput.value = new Date().toISOString().slice(0, 10);
      state.page = 1;
      runSearch();
      return;
    }
    setStatus("未登录", false);
    showApp(false);
  } catch (err) {
    setStatus(err.message, false);
    showApp(false);
  }
}

function formParams() {
  const fd = new FormData(els.form);
  const params = new URLSearchParams();
  for (const [key, value] of fd.entries()) {
    if (String(value).trim()) {
      params.set(key, String(value).trim());
    }
  }
  params.set("page", String(state.page));
  params.set("per_page", String(state.perPage));
  // 将筛选模式传给后端
  if (state.filterMode !== "all") {
    params.set("status_filter", state.filterMode);
  }
  return params;
}

function applyFilter(courses) {
  // 筛选已在服务端完成，前端不再二次过滤
  return courses;
}

function updateFilterButtons() {
  els.filterToggle.querySelectorAll(".toggle-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.filter === state.filterMode);
  });
  // 一键缓存按钮在"直播中"和"回放生成中"时显示
  if (els.cacheAllBtn) {
    els.cacheAllBtn.style.display = (state.filterMode === 'live' || state.filterMode === 'generating') ? '' : 'none';
    if (state.filterMode === 'generating') els.cacheAllBtn.textContent = '⬇ 一键缓存直播链接';
  }
}

function renderCourses(list) {
  const filtered = applyFilter(list);
  if (!filtered.length) {
    const hint = state.filterMode === "live" ? "没有正在直播的课程" :
                 state.filterMode === "playback" ? "没有可回放的课程" :
                 state.filterMode === "generating" ? "没有回放生成中的课程" : "没有匹配的课程";
    els.courseBody.innerHTML = `<tr><td colspan="8" class="empty">${hint}</td></tr>`;
    return;
  }

  els.courseBody.innerHTML = list
    .map((c) => {
      const time = [c.time_slot, c.course_time, c.sub_title]
        .filter(Boolean)
        .join(" · ");
      const playerUrl = [
        `/player/?course_id=${encodeURIComponent(c.course_id || '')}`,
        `sub_id=${encodeURIComponent(c.sub_id || '')}`,
        `search_time=${encodeURIComponent(
          (document.querySelector('input[name="create_at"]')?.value || '')
        )}`,
      ].join('&');
      return `<tr class="course-row" data-href="${escapeAttr(playerUrl)}"
                  data-course-id="${escapeAttr(c.course_id || '')}"
                  data-sub-id="${escapeAttr(c.sub_id || '')}">
        <td><strong>${escapeHtml(c.title)}</strong></td>
        <td>${escapeHtml(c.course_code || "-")}</td>
        <td>${escapeHtml(c.lecturer_name || "-")}</td>
        <td>${escapeHtml(c.kkxy_name || "-")}</td>
        <td>${escapeHtml(time || "-")}</td>
        <td>${escapeHtml(c.room_name || "-")}</td>
        <td title="${escapeAttr(c._raw_status || '')}">${escapeHtml(c.status_label || "-")}</td>
        <td>
          <a href="${escapeAttr(playerUrl)}" class="play-link" title="打开播放器">▶</a>
          ${c.status_label === '直播中' ? `<button class="cache-btn" data-course="${escapeAttr(c.course_id||'')}" data-sub="${escapeAttr(c.sub_id||'')}" data-title="${escapeAttr(c.title||'')}" data-teacher="${escapeAttr(c.lecturer_name||'')}" data-room="${escapeAttr(c.room_name||'')}" data-stitle="${escapeAttr(c.sub_title||'')}" data-stime="${escapeAttr((document.querySelector('input[name=create_at]')?.value||''))}" title="缓存直播链接">⬇</button>` : ''}
        </td>
      </tr>`;
    })
    .join("");

  // 直播缓存按钮
  els.courseBody.querySelectorAll('.cache-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      e.stopPropagation();
      e.preventDefault();
      const origText = btn.textContent;
      btn.textContent = '⏳';
      btn.disabled = true;
      try {
        const courseId = btn.dataset.course;
        const subId = btn.dataset.sub;
        // 先获取课程详情拿到直播流 URL
        const detailResp = await api(`/api/courses/detail?course_id=${courseId}&sub_id=${subId}&search_time=${btn.dataset.stime || ''}`);
        const liveUrl = detailResp.detail?.sources?.live?.url || detailResp.detail?.trans_socket_url || '';
        if (!liveUrl) throw new Error('该课程无直播流地址');

        const resp = await fetch('/api/live/cache', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            course_id: courseId,
            sub_id: subId,
            title: btn.dataset.title,
            lecturer_name: btn.dataset.teacher,
            room_name: btn.dataset.room,
            sub_title: btn.dataset.stitle,
            live_url: liveUrl,
            search_time: btn.dataset.stime,
          }),
        });
        const data = await resp.json();
        if (!resp.ok || !data.ok) throw new Error(data.error || '缓存失败');
        btn.textContent = data.url_working ? '✅' : '⚠️';
        btn.classList.add('cached');
        setTimeout(() => { btn.textContent = origText; btn.classList.remove('cached'); }, 2000);
      } catch (err) {
        btn.textContent = '❌';
        setTimeout(() => { btn.textContent = origText; btn.disabled = false; }, 1500);
        console.error('缓存失败:', err);
      }
    });
  });

  // 整行点击跳转播放器
  els.courseBody.querySelectorAll('.course-row').forEach(row => {
    row.addEventListener('click', (e) => {
      // 如果点的是播放链接或缓存按钮，让它们自己处理
      if (e.target.closest('a') || e.target.closest('button')) return;
      const href = row.dataset.href;
      if (href) window.open(href, '_blank');
    });
  });
}

function escapeAttr(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeHtml(text) {
  return String(text)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function updatePager() {
  const pages = Math.max(1, Math.ceil(state.total / state.perPage));
  els.pageInfo.textContent = `第 ${state.page} / ${pages} 页`;
  els.prevPage.disabled = state.page <= 1;
  els.nextPage.disabled = state.page >= pages;
}

async function runSearch() {
  showError("");
  showLoading(true);
  try {
    const params = formParams();
    const data = await api(`/api/courses/search?${params.toString()}`);
    state.total = Number(data.total || 0);
    state.source = data.source || "";
    state.allCourses = data.list || [];
    renderCourses(state.allCourses);
    const date = new FormData(els.form).get("create_at");
    const dateHint = date ? ` · 日期 ${date}` : "";
    const msgHint = data.msg ? ` · ${data.msg}` : "";
    els.resultMeta.textContent = `共 ${state.total} 条 · 数据源 ${state.source}${dateHint}${msgHint}`;
    updatePager();
  } catch (err) {
    showError(err.message);
    renderCourses([]);
    els.resultMeta.textContent = "";
  } finally {
    showLoading(false);
  }
}

els.form.addEventListener("submit", (e) => {
  e.preventDefault();
  state.page = 1;
  runSearch();
});

document.getElementById("resetBtn").addEventListener("click", () => {
  els.form.reset();
  els.buildingSelect.disabled = true;
  els.roomSelect.disabled = true;
  els.buildingSelect.innerHTML = '<option value="">先选择校区</option>';
  els.roomSelect.innerHTML = '<option value="">先选择教学楼</option>';
  state.page = 1;
  state.total = 0;
  state.filterMode = "all";
  state.allCourses = [];
  updateFilterButtons();
  renderCourses([]);
  els.resultMeta.textContent = "";
  updatePager();
});

document.getElementById("loadAllBtn").addEventListener("click", () => {
  els.form.reset();
  const dateInput = els.form.querySelector('input[name="create_at"]');
  if (dateInput) {
    dateInput.value = new Date().toISOString().slice(0, 10);
  }
  state.page = 1;
  runSearch();
});

els.prevPage.addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    runSearch();
  }
});

els.nextPage.addEventListener("click", () => {
  const pages = Math.max(1, Math.ceil(state.total / state.perPage));
  if (state.page < pages) {
    state.page += 1;
    runSearch();
  }
});

if (els.logoutBtn) {
  els.logoutBtn.addEventListener("click", async () => {
    els.logoutBtn.disabled = true;
    setStatus("正在登出…", true);
    try {
      const data = await apiPost("/api/auth/logout");
      if (!data.ok) throw new Error(data.error);
      state.loggedIn = false;
      setStatus("未登录", false);
      showApp(false);
      renderCourses([]);
      els.resultMeta.textContent = "";
      toast("已登出");
    } catch (err) {
      setStatus(err.message, false);
    }
    els.logoutBtn.disabled = false;
  });
}

if (els.shutdownBtn) {
  els.shutdownBtn.addEventListener("click", async () => {
    els.shutdownBtn.disabled = true;
    setStatus("正在退出…", true);
    try {
      const resp = await fetch("/api/shutdown", { method: "POST" });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        throw new Error(data.error || data.msg || `请求失败 (${resp.status})`);
      }
      setStatus(data.msg || "服务已退出", true);
      els.resultMeta.textContent = "服务已停止，可关闭此页面";
    } catch (err) {
      els.shutdownBtn.disabled = false;
      setStatus(err.message, false);
    }
  });
}

els.campusSelect.addEventListener("change", async () => {
  const campusId = els.campusSelect.value;
  els.buildingSelect.disabled = !campusId;
  els.roomSelect.disabled = true;
  els.roomSelect.innerHTML = '<option value="">先选择教学楼</option>';
  if (!campusId) {
    els.buildingSelect.innerHTML = '<option value="">先选择校区</option>';
    return;
  }
  const data = await api(`/api/meta/buildings?campus_id=${campusId}`);
  fillSelect(
    els.buildingSelect,
    data.list,
    "id",
    "building_name",
    "全部教学楼"
  );
});

els.buildingSelect.addEventListener("change", async () => {
  const buildingId = els.buildingSelect.value;
  els.roomSelect.disabled = !buildingId;
  if (!buildingId) {
    els.roomSelect.innerHTML = '<option value="">先选择教学楼</option>';
    return;
  }
  const data = await api(`/api/meta/rooms?building_id=${buildingId}`);
  const rooms = (data.list || []).map((r) => ({
    id: r.id,
    label: [r.campus_name, r.building_name, r.room_name].filter(Boolean).join(" · "),
  }));
  fillSelect(els.roomSelect, rooms, "id", "label", "全部教室");
});

const dateInput = els.form.querySelector('input[name="create_at"]');
if (dateInput) {
  dateInput.addEventListener("change", () => {
    state.page = 1;
    runSearch();
  });
}

// ---- 一键缓存全部直播 ----
if (els.cacheAllBtn) {
  els.cacheAllBtn.addEventListener('click', async () => {
    const targetLabel = state.filterMode === 'generating' ? '回放生成中' : '直播中';
    const coursesToCache = state.allCourses.filter(c => c.status_label === targetLabel);
    if (!coursesToCache.length) return;
    const origText = els.cacheAllBtn.textContent;
    let done = 0, fail = 0;
    els.cacheAllBtn.disabled = true;
    for (const c of coursesToCache) {
      els.cacheAllBtn.textContent = `⬇ 缓存中 ${done+1}/${coursesToCache.length}`;
      try {
        const detailResp = await api(`/api/courses/detail?course_id=${c.course_id}&sub_id=${c.sub_id}&search_time=${document.querySelector('input[name=create_at]')?.value || ''}`);
        const liveUrl = detailResp.detail?.sources?.live?.url || detailResp.detail?.trans_socket_url || '';
        if (!liveUrl) { fail++; continue; }
        const resp = await fetch('/api/live/cache', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            course_id: c.course_id, sub_id: c.sub_id,
            title: c.title, lecturer_name: c.lecturer_name,
            room_name: c.room_name, sub_title: c.sub_title,
            live_url: liveUrl,
            search_time: document.querySelector('input[name=create_at]')?.value || '',
          }),
        });
        const data = await resp.json();
        if (data.ok) done++; else fail++;
      } catch (err) { fail++; }
    }
    els.cacheAllBtn.textContent = origText;
    els.cacheAllBtn.disabled = false;
    setStatus(`缓存完成: ${done} 成功, ${fail} 失败`, fail === 0);
    setTimeout(() => setStatus('已登录', true), 3000);
  });
}

// ---- 直播/回放 筛选切换 ----
if (els.filterToggle) {
  els.filterToggle.addEventListener("click", (e) => {
    const btn = e.target.closest(".toggle-btn");
    if (!btn) return;
    state.filterMode = btn.dataset.filter;
    state.page = 1;
    updateFilterButtons();
    // 始终触发后端搜索，确保拿到完整数据（直接客户端过滤可能漏掉直播课）
    const dateInp = els.form.querySelector('input[name="create_at"]');
    if (dateInp && !dateInp.value) dateInp.value = new Date().toISOString().slice(0, 10);
    runSearch();
    els.resultMeta.textContent = state.filterMode === "live" ? "筛选：直播中" :
                                 state.filterMode === "playback" ? "筛选：可回放" :
                                 state.filterMode === "generating" ? "筛选：回放生成中" : "";
  });
}

loadMeta()
  .catch((err) => setStatus(err.message, false));

loadAuth();

if (els.loginForm) {
  els.loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    showAuthError("");
    showAuthLoading(true);
    try {
      const fd = new FormData(els.loginForm);
      const data = await apiPost("/api/auth/login", {
        username: String(fd.get("username") || "").trim(),
        password: String(fd.get("password") || "").trim(),
      });
      state.loggedIn = true;
      setStatus(`已登录 · ${data.user}`, true);
      showApp(true);
      await loadMeta();
      // 默认显示当天课程
      const dateInp = els.form.querySelector('input[name="create_at"]');
      if (dateInp) dateInp.value = new Date().toISOString().slice(0, 10);
      state.page = 1;
      runSearch();
    } catch (err) {
      showAuthError(err.message);
      setStatus(err.message, false);
    } finally {
      showAuthLoading(false);
    }
  });
}

if (els.reuseCookieBtn) {
  els.reuseCookieBtn.addEventListener("click", async () => {
    showAuthError("");
    showAuthLoading(true);
    try {
      const data = await api("/api/auth/status");
      if (!data.logged_in) {
        throw new Error("未发现可用 cookie，请先登录一次");
      }
      state.loggedIn = true;
      setStatus(`已登录 · ${data.user}`, true);
      showApp(true);
      await loadMeta();
      // 默认显示当天课程
      const dateInp = els.form.querySelector('input[name="create_at"]');
      if (dateInp) dateInp.value = new Date().toISOString().slice(0, 10);
      state.page = 1;
      runSearch();
    } catch (err) {
      showAuthError(err.message);
      setStatus(err.message, false);
    } finally {
      showAuthLoading(false);
    }
  });
}

const FAVORITES_STORAGE_KEY = "bbuaa_favorite_courses_v1";

function loadFavorites() {
  try {
    const value = JSON.parse(localStorage.getItem(FAVORITES_STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => item && typeof item === "object") : [];
  } catch (_err) {
    return [];
  }
}

const state = {
  page: 1,
  perPage: 20,
  total: 0,
  source: "",
  loggedIn: false,
  filterMode: "all",
  allCourses: [],
  favorites: loadFavorites(),
  currentTermId: "",
  resultMode: "search",
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
  favoritesBtn: document.getElementById("favoritesBtn"),
  logoutBtn: document.getElementById("logoutBtn"),
  filterToggle: document.getElementById("filterToggle"),
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

function toast(message) {
  const item = document.createElement("div");
  item.className = "toast";
  item.textContent = message;
  document.body.appendChild(item);
  window.setTimeout(() => item.remove(), 3000);
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
}

function selectedProxyConfig() {
  if (!els.loginForm) return { proxy_mode: "direct", proxy_url: "" };
  const fd = new FormData(els.loginForm);
  const proxyMode = String(fd.get("proxy_mode") || "direct");
  const proxyUrl = String(fd.get("proxy_url") || "").trim();
  return { proxy_mode: proxyMode, proxy_url: proxyMode === "proxy" ? proxyUrl : "" };
}

function syncProxyInputState() {
  if (!els.loginForm) return;
  const proxyInput = els.loginForm.querySelector('input[name="proxy_url"]');
  const proxyMode = els.loginForm.querySelector('input[name="proxy_mode"]:checked');
  if (proxyInput) {
    proxyInput.disabled = !proxyMode || proxyMode.value !== "proxy";
  }
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
  state.currentTermId = String(
    terms.current_term_id || terms.list?.[0]?.id || ""
  );
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
    const data = await api("/api/auth/status?" + new URLSearchParams(selectedProxyConfig()));
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
}

function cleanIdentity(value) {
  return String(value || "").trim().toLocaleLowerCase();
}

function sameFavoriteCourse(course, favorite) {
  const courseId = cleanIdentity(course.course_id);
  const favoriteId = cleanIdentity(favorite.course_id);
  if (courseId && favoriteId && courseId === favoriteId) return true;

  const courseCode = cleanIdentity(course.course_code);
  const favoriteCode = cleanIdentity(favorite.course_code);
  if (courseCode && favoriteCode && courseCode === favoriteCode) return true;

  const title = cleanIdentity(course.title);
  const favoriteTitle = cleanIdentity(favorite.title);
  if (!title || title !== favoriteTitle) return false;
  const lecturer = cleanIdentity(course.lecturer_name);
  const favoriteLecturer = cleanIdentity(favorite.lecturer_name);
  return !favoriteLecturer || lecturer === favoriteLecturer;
}

function favoriteForCourse(course) {
  return state.favorites.find((favorite) => sameFavoriteCourse(course, favorite));
}

function favoriteRecord(course) {
  return {
    course_id: String(course.course_id || ""),
    course_code: String(course.course_code || ""),
    title: String(course.title || ""),
    lecturer_name: String(course.lecturer_name || ""),
  };
}

function saveFavorites() {
  try {
    localStorage.setItem(FAVORITES_STORAGE_KEY, JSON.stringify(state.favorites));
    return true;
  } catch (_err) {
    showError("浏览器无法保存收藏，请检查本地存储设置。");
    return false;
  }
}

function toggleFavorite(course) {
  const existing = favoriteForCourse(course);
  if (existing) {
    state.favorites = state.favorites.filter((favorite) => favorite !== existing);
    saveFavorites();
    toast(`已取消收藏「${course.title || "未命名课程"}」`);
    if (state.resultMode === "favorites") {
      state.allCourses = state.allCourses.filter(
        (item) => !sameFavoriteCourse(item, existing)
      );
      state.total = state.allCourses.length;
      const pages = Math.max(1, Math.ceil(state.total / state.perPage));
      state.page = Math.min(state.page, pages);
      renderFavoritePage();
      return;
    }
  } else {
    state.favorites.push(favoriteRecord(course));
    saveFavorites();
    toast(`已收藏「${course.title || "未命名课程"}」`);
  }
  renderCourses(state.allCourses);
}

function renderCourses(list) {
  const filtered = applyFilter(list);
  if (!filtered.length) {
    const hint = state.resultMode === "favorites" ? "本学期暂无已收藏课程的课次" :
                 state.filterMode === "live" ? "没有正在直播的课程" :
                 state.filterMode === "playback" ? "没有可回放的课程" :
                 state.filterMode === "generating" ? "没有回放生成中的课程" : "没有匹配的课程";
    els.courseBody.innerHTML = `<tr><td colspan="9" class="empty">${hint}</td></tr>`;
    return;
  }

  els.courseBody.innerHTML = filtered
    .map((c, index) => {
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
      const isFavorite = Boolean(favoriteForCourse(c));
      return `<tr class="course-row" data-href="${escapeAttr(playerUrl)}"
                  data-course-id="${escapeAttr(c.course_id || '')}"
                  data-sub-id="${escapeAttr(c.sub_id || '')}">
        <td class="favorite-column">
          <button type="button" class="favorite-btn${isFavorite ? ' active' : ''}"
                  data-course-index="${index}" aria-pressed="${isFavorite}"
                  title="${isFavorite ? '取消收藏' : '收藏课程'}"
                  aria-label="${isFavorite ? '取消收藏' : '收藏课程'}">${isFavorite ? '★' : '☆'}</button>
        </td>
        <td><strong>${escapeHtml(c.title || "-")}</strong></td>
        <td>${escapeHtml(c.course_code || "-")}</td>
        <td>${escapeHtml(c.lecturer_name || "-")}</td>
        <td>${escapeHtml(c.kkxy_name || "-")}</td>
        <td>${escapeHtml(time || "-")}</td>
        <td>${escapeHtml(c.room_name || "-")}</td>
        <td title="${escapeAttr(c._raw_status || '')}">${escapeHtml(c.status_label || "-")}</td>
        <td><a href="${escapeAttr(playerUrl)}" class="play-link" title="打开播放器">▶</a></td>
      </tr>`;
    })
    .join("");

  // 整行点击跳转播放器
  els.courseBody.querySelectorAll('.course-row').forEach(row => {
    row.addEventListener('click', (e) => {
      if (e.target.closest('a, button')) return;
      const href = row.dataset.href;
      if (href) window.open(href, '_blank');
    });
  });
  els.courseBody.querySelectorAll('.favorite-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const course = filtered[Number(button.dataset.courseIndex)];
      if (course) toggleFavorite(course);
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

function renderFavoritePage() {
  const start = (state.page - 1) * state.perPage;
  renderCourses(state.allCourses.slice(start, start + state.perPage));
  const termLabel = els.termSelect.selectedOptions[0]?.textContent || "本学期";
  els.resultMeta.textContent = `我的收藏 · ${termLabel} · 共 ${state.total} 条课次`;
  updatePager();
}

async function runSearch() {
  state.resultMode = "search";
  els.favoritesBtn?.classList.remove("active");
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

async function runFavoriteSearch() {
  showError("");
  if (!state.favorites.length) {
    state.resultMode = "favorites";
    state.page = 1;
    state.total = 0;
    state.allCourses = [];
    els.favoritesBtn?.classList.add("active");
    renderFavoritePage();
    showError("还没有收藏课程，请先点击课程行左侧的星标。");
    return;
  }
  if (!state.currentTermId) {
    showError("无法确定当前学期，请刷新后重试。");
    return;
  }

  showLoading(true);
  els.favoritesBtn.disabled = true;
  try {
    els.form.reset();
    els.termSelect.value = state.currentTermId;
    state.filterMode = "all";
    state.resultMode = "favorites";
    state.page = 1;
    updateFilterButtons();
    els.favoritesBtn.classList.add("active");
    const data = await apiPost("/api/courses/favorites/search", {
      favorites: state.favorites,
      term: state.currentTermId,
    });
    state.allCourses = data.list || [];
    state.total = state.allCourses.length;
    renderFavoritePage();
    if (data.errors?.length) {
      showError(`部分收藏查询失败：${data.errors.join("；")}`);
    }
  } catch (err) {
    state.allCourses = [];
    state.total = 0;
    renderFavoritePage();
    showError(err.message);
  } finally {
    showLoading(false);
    els.favoritesBtn.disabled = false;
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
  state.resultMode = "search";
  state.allCourses = [];
  els.favoritesBtn?.classList.remove("active");
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

if (els.favoritesBtn) {
  els.favoritesBtn.addEventListener("click", runFavoriteSearch);
}

els.prevPage.addEventListener("click", () => {
  if (state.page > 1) {
    state.page -= 1;
    if (state.resultMode === "favorites") renderFavoritePage();
    else runSearch();
  }
});

els.nextPage.addEventListener("click", () => {
  const pages = Math.max(1, Math.ceil(state.total / state.perPage));
  if (state.page < pages) {
    state.page += 1;
    if (state.resultMode === "favorites") renderFavoritePage();
    else runSearch();
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
  els.loginForm
    .querySelectorAll('input[name="proxy_mode"]')
    .forEach((input) => input.addEventListener("change", syncProxyInputState));
  syncProxyInputState();

  els.loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    showAuthError("");
    showAuthLoading(true);
    try {
      const fd = new FormData(els.loginForm);
      const data = await apiPost("/api/auth/login", {
        username: String(fd.get("username") || "").trim(),
        password: String(fd.get("password") || "").trim(),
        ...selectedProxyConfig(),
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
      const data = await api("/api/auth/status?" + new URLSearchParams(selectedProxyConfig()));
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

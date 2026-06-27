import { chapterAt, stateAt, validateStory } from "./player.mjs";

const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

let story;
let research;
let currentTime = 0;
let playing = false;
let speed = 1;
let lastFrame = 0;

const TYPE_LABELS = {
  mission: "OBSERVE",
  graph: "TASK GRAPH",
  position: "FLIGHT",
  telemetry: "TELEMETRY",
  tool: "TOOL",
  detection: "DETECTION",
  fault: "FAULT",
  recovery: "RECOVERY",
  report: "REPORT",
};

function formatTime(seconds) {
  const value = Math.max(0, Math.round(seconds));
  return `${String(Math.floor(value / 60)).padStart(2, "0")}:${String(value % 60).padStart(2, "0")}`;
}

function svgElement(tag, attributes = {}) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

function waypointMap() {
  return Object.fromEntries(story.map.waypoints.map((point) => [point.id, point]));
}

function pointsFor(route) {
  const points = waypointMap();
  return route.map((id) => `${points[id].x},${points[id].y}`).join(" ");
}

function renderStaticMap() {
  const routeLayer = $("#route-layer");
  const waypointLayer = $("#waypoint-layer");
  routeLayer.replaceChildren();
  waypointLayer.replaceChildren();

  routeLayer.append(svgElement("polyline", {
    points: pointsFor(story.map.original_route),
    class: "route-original",
  }));

  for (const point of story.map.waypoints) {
    const group = svgElement("g", { "data-waypoint": point.id });
    group.append(svgElement("circle", { cx: point.x, cy: point.y, r: 10, class: "waypoint" }));
    const label = svgElement("text", { x: point.x + 15, y: point.y - 13, class: "waypoint-label" });
    label.textContent = point.id;
    group.append(label);
    waypointLayer.append(group);
  }
}

function setWaypointClass(id, className, enabled) {
  const circle = document.querySelector(`[data-waypoint="${id}"] .waypoint`);
  if (circle) circle.classList.toggle(className, enabled);
}

function interpolatePosition(position) {
  const points = waypointMap();
  const from = points[position.from] || points.HOME;
  const to = points[position.to] || from;
  const progress = Math.max(0, Math.min(1, position.progress || 0));
  return {
    x: from.x + (to.x - from.x) * progress,
    y: from.y + (to.y - from.y) * progress,
  };
}

function renderMap(state) {
  const point = interpolatePosition(state.position);
  $("#drone").setAttribute("transform", `translate(${point.x} ${point.y})`);
  $$(".waypoint").forEach((node) => node.classList.remove("active", "blocked"));
  setWaypointClass(state.position.to, "active", true);

  const routeLayer = $("#route-layer");
  routeLayer.querySelectorAll(".route-repaired").forEach((node) => node.remove());
  if (state.repairedRoute) {
    routeLayer.append(svgElement("polyline", {
      points: pointsFor(state.repairedRoute),
      class: "route-repaired",
    }));
  }

  const detectionLayer = $("#detection-layer");
  detectionLayer.replaceChildren();
  if (state.detection?.visible) {
    const region = story.map.regions.find((item) => item.id === state.detection.regionId);
    if (region) {
      detectionLayer.append(svgElement("circle", {
        cx: region.x, cy: region.y, r: region.radius, class: "detection-zone",
      }));
      const label = svgElement("text", { x: region.x + 52, y: region.y + 5, class: "detection-text" });
      label.textContent = `疑似病害 ${(state.detection.confidence * 100).toFixed(0)}%`;
      detectionLayer.append(label);
    }
  }

  const alert = $("#map-alert");
  const latest = state.trace[state.trace.length - 1];
  alert.className = "map-alert";
  if (latest?.type === "fault") {
    alert.hidden = false;
    alert.classList.add("fault");
    alert.textContent = `FAULT · ${latest.detail}`;
    setWaypointClass(latest.payload?.waypoint, "blocked", true);
  } else if (latest?.type === "recovery" || state.repairedRoute) {
    alert.hidden = false;
    alert.classList.add("recovery");
    alert.textContent = "RECOVERY · 局部航段已替换，任务继续执行";
  } else if (latest?.type === "detection") {
    alert.hidden = false;
    alert.textContent = `DETECTION · 置信度 ${(latest.payload.confidence * 100).toFixed(0)}%，触发补拍`;
  } else {
    alert.hidden = true;
  }
}

function renderGraph(state) {
  const completed = Object.values(state.nodeStatuses).filter((status) => status === "completed").length;
  $("#graph-progress").textContent = `${completed} / ${story.graph.nodes.length}`;
  $("#task-count").textContent = `${completed} / ${story.graph.nodes.length}`;
  $("#graph-nodes").replaceChildren(...story.graph.nodes.map((node) => {
    const item = document.createElement("li");
    const status = state.nodeStatuses[node.id] || "pending";
    item.className = `graph-node ${status}`;
    const title = document.createElement("strong");
    title.textContent = node.label;
    const meta = document.createElement("span");
    meta.textContent = `${node.kind} · ${status}`;
    item.append(title, meta);
    return item;
  }));
}

function renderTrace(state) {
  const trace = $("#trace");
  if (!state.trace.length) {
    const empty = document.createElement("p");
    empty.className = "trace-empty";
    empty.textContent = "等待任务启动";
    trace.replaceChildren(empty);
    return;
  }
  trace.replaceChildren(...state.trace.map((event) => {
    const item = document.createElement("article");
    item.className = `trace-event ${event.type}`;
    const meta = document.createElement("div");
    meta.className = "trace-meta";
    const type = document.createElement("span");
    type.textContent = TYPE_LABELS[event.type] || "EVENT";
    const time = document.createElement("time");
    time.textContent = formatTime(event.time);
    meta.append(type, time);
    const title = document.createElement("strong");
    title.textContent = event.title || event.type;
    const detail = document.createElement("p");
    detail.textContent = event.detail || "";
    item.append(meta, title, detail);
    return item;
  }));
}

function renderChapters(state) {
  const active = chapterAt(story.chapters, state.time);
  $$(".chapter").forEach((button) => button.classList.toggle("active", button.dataset.chapter === active?.id));
}

function renderStatus(state) {
  const status = $("#mission-state");
  const label = state.reportReady ? "MISSION COMPLETE" : state.missionStatus.toUpperCase();
  status.className = "status-pill";
  if (state.missionStatus === "recovering") status.classList.add("recovering");
  if (state.missionStatus === "fault") status.classList.add("fault");
  status.innerHTML = `<i></i>${label}`;
  $("#clock").textContent = `${formatTime(state.time)} / ${formatTime(story.duration)}`;
  $("#timeline").value = String(state.time);
  $("#battery").textContent = `${state.telemetry.battery ?? "--"}%`;
  $("#altitude").textContent = `${state.telemetry.altitude ?? "--"} m`;
  $("#tool-count").textContent = String(state.telemetry.calls ?? "--");
  $("#recovery-count").textContent = `${state.recovery.successes} / ${state.recovery.attempts}`;
  $("#map-caption").textContent = `ALT ${state.telemetry.altitude ?? "--"} M · ${story.mission.location}`;
}

function render() {
  const state = stateAt(story, currentTime);
  renderStatus(state);
  renderGraph(state);
  renderMap(state);
  renderTrace(state);
  renderChapters(state);
}

function createChapters() {
  $("#chapter-nav").replaceChildren(...story.chapters.map((chapter) => {
    const button = document.createElement("button");
    button.className = "chapter";
    button.dataset.chapter = chapter.id;
    button.textContent = `${formatTime(chapter.time)}  ${chapter.label}`;
    button.addEventListener("click", () => seek(chapter.time));
    return button;
  }));
}

function seek(seconds) {
  currentTime = Math.max(0, Math.min(story.duration, Number(seconds)));
  if (currentTime >= story.duration) setPlaying(false);
  render();
}

function setPlaying(next) {
  playing = next;
  $("#play-toggle").textContent = playing ? "Ⅱ" : "▶";
  $("#play-toggle").title = playing ? "暂停" : "播放";
  $("#play-toggle").setAttribute("aria-label", playing ? "暂停" : "播放");
  lastFrame = performance.now();
}

function frame(timestamp) {
  if (playing) {
    const delta = Math.min((timestamp - lastFrame) / 1000, 0.25);
    currentTime = Math.min(story.duration, currentTime + delta * speed);
    if (currentTime >= story.duration) setPlaying(false);
    render();
  }
  lastFrame = timestamp;
  requestAnimationFrame(frame);
}

function renderResearch() {
  $("#benchmark-note").textContent = research.mock_benchmark_note;
  $("#benchmark-chart").replaceChildren(...research.mock_benchmark.map((row) => {
    const wrapper = document.createElement("div");
    wrapper.className = `bar-row ${row.method === "AgentFly" ? "agentfly" : ""}`;
    const label = document.createElement("span");
    label.textContent = row.method;
    const track = document.createElement("div");
    track.className = "bar-track";
    const fill = document.createElement("div");
    fill.className = "bar-fill";
    fill.style.width = `${row.task_success_rate * 100}%`;
    track.append(fill);
    const value = document.createElement("span");
    value.className = "bar-value";
    value.textContent = row.task_success_rate.toFixed(3);
    wrapper.append(label, track, value);
    return wrapper;
  }));

  const deepseekMetrics = [
    ["FIRST-PASS VALID", `${(research.deepseek.first_pass_plan_validity * 100).toFixed(0)}%`],
    ["AVG LATENCY", `${research.deepseek.average_latency_s.toFixed(3)} s`],
    ["TOTAL TOKENS", research.deepseek.total_tokens.toLocaleString()],
    ["API RETRIES", String(research.deepseek.api_response_retries)],
  ];
  $("#deepseek-metrics").replaceChildren(...deepseekMetrics.map(([label, value]) => {
    const item = document.createElement("div");
    item.className = "metric";
    const name = document.createElement("span");
    name.textContent = label;
    const metric = document.createElement("strong");
    metric.textContent = value;
    item.append(name, metric);
    return item;
  }));
  $("#deepseek-note").textContent = research.deepseek.note;

  const pairs = [
    ["约束覆盖率", research.semantic_repair.direct_constraint_coverage, research.semantic_repair.repaired_constraint_coverage],
    ["完整约束落地任务率", research.semantic_repair.direct_fully_grounded_task_rate, research.semantic_repair.repaired_fully_grounded_task_rate],
  ];
  $("#repair-chart").replaceChildren(...pairs.map(([label, direct, repaired]) => {
    const pair = document.createElement("div");
    pair.className = "repair-pair";
    const heading = document.createElement("div");
    heading.className = "repair-label";
    heading.innerHTML = `<span>${label}</span><span>${(direct * 100).toFixed(1)}% → ${(repaired * 100).toFixed(1)}%</span>`;
    const bars = document.createElement("div");
    bars.className = "repair-bars";
    const directBar = document.createElement("div");
    directBar.className = "repair-bar";
    directBar.innerHTML = `<i style="width:${direct * 100}%"></i>`;
    const repairedBar = document.createElement("div");
    repairedBar.className = "repair-bar repaired";
    repairedBar.innerHTML = `<i style="width:${repaired * 100}%"></i>`;
    bars.append(directBar, repairedBar);
    pair.append(heading, bars);
    return pair;
  }));
  $("#repair-note").textContent = research.semantic_repair.note;
}

function bindControls() {
  $("#play-toggle").addEventListener("click", () => {
    if (currentTime >= story.duration) currentTime = 0;
    setPlaying(!playing);
  });
  $("#restart").addEventListener("click", () => {
    seek(0);
    setPlaying(true);
  });
  $("#speed").addEventListener("click", () => {
    speed = speed === 1 ? 2 : 1;
    $("#speed").textContent = `${speed}×`;
  });
  $("#timeline").addEventListener("input", (event) => seek(event.target.value));
  $$(".tab").forEach((tab) => tab.addEventListener("click", () => {
    const selected = tab.dataset.view;
    $$(".tab").forEach((item) => {
      const active = item === tab;
      item.classList.toggle("active", active);
      item.setAttribute("aria-pressed", String(active));
    });
    $("#mission-view").hidden = selected !== "mission";
    $("#research-view").hidden = selected !== "research";
  }));
}

async function loadData() {
  const [storyResponse, researchResponse] = await Promise.all([
    fetch("data/agriculture_story.json"),
    fetch("data/research_results.json"),
  ]);
  if (!storyResponse.ok || !researchResponse.ok) throw new Error("请通过本地 HTTP 服务打开 Demo，不能直接双击 HTML 文件。");
  story = validateStory(await storyResponse.json());
  research = await researchResponse.json();
}

async function start() {
  try {
    await loadData();
    $("#mission-id").textContent = `MISSION ${story.mission.id}`;
    $("#scenario-title").textContent = story.mission.scenario;
    $("#instruction").textContent = story.mission.instruction;
    $("#timeline").max = String(story.duration);
    createChapters();
    renderStaticMap();
    renderResearch();
    bindControls();
    render();
    $("#loading").hidden = true;
    $("#error-panel").hidden = true;
    $("#app").hidden = false;
    requestAnimationFrame(frame);
  } catch (error) {
    $("#loading").hidden = true;
    $("#app").hidden = true;
    $("#error-message").textContent = error instanceof Error ? error.message : String(error);
    $("#error-panel").hidden = false;
  }
}

$("#retry").addEventListener("click", () => window.location.reload());
start();

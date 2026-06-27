const SUPPORTED_EVENTS = new Set([
  "mission",
  "graph",
  "position",
  "telemetry",
  "tool",
  "detection",
  "fault",
  "recovery",
  "report",
]);


export function validateStory(story) {
  if (!story || typeof story !== "object") {
    throw new Error("story must be an object");
  }
  if (!Number.isFinite(story.duration) || story.duration <= 0) {
    throw new Error("story duration must be positive");
  }
  if (!story.graph || !Array.isArray(story.graph.nodes) || !Array.isArray(story.events)) {
    throw new Error("story requires graph nodes and events");
  }
  let previous = -Infinity;
  for (const event of story.events) {
    if (!Number.isFinite(event.time) || event.time < previous) {
      throw new Error("story events must be chronological");
    }
    previous = event.time;
  }
  return story;
}


export function initialState(story) {
  return {
    time: 0,
    missionStatus: "ready",
    nodeStatuses: Object.fromEntries(
      story.graph.nodes.map((node) => [node.id, node.status || "pending"]),
    ),
    telemetry: { battery: 100, altitude: 0, signal: 100, completed: 0, calls: 0 },
    position: { from: "HOME", to: "HOME", progress: 0 },
    detection: null,
    repairedRoute: null,
    trace: [],
    reportReady: false,
    recovery: { attempts: 0, successes: 0 },
    warnings: [],
  };
}


function applyEvent(state, event) {
  const payload = event.payload || {};
  if (!SUPPORTED_EVENTS.has(event.type)) {
    state.warnings.push("Unsupported event type: " + event.type);
    return state;
  }
  if (event.type === "mission") state.missionStatus = payload.status || state.missionStatus;
  if (event.type === "graph" && payload.nodeId) state.nodeStatuses[payload.nodeId] = payload.status;
  if (event.type === "position") state.position = { ...state.position, ...payload };
  if (event.type === "telemetry") state.telemetry = { ...state.telemetry, ...payload };
  if (event.type === "tool" && Number.isFinite(payload.calls)) state.telemetry.calls = payload.calls;
  if (event.type === "detection") state.detection = { ...payload };
  if (event.type === "fault") state.missionStatus = payload.status || "fault";
  if (event.type === "recovery") {
    state.missionStatus = payload.status || "executing";
    state.repairedRoute = payload.route || null;
    state.recovery = {
      attempts: payload.attempts || 0,
      successes: payload.successes || 0,
    };
  }
  if (event.type === "report") {
    state.reportReady = true;
    state.missionStatus = payload.status || "succeeded";
    state.telemetry = { ...state.telemetry, ...payload };
  }
  state.trace.push(event);
  if (state.trace.length > 6) state.trace.shift();
  return state;
}


export function chapterAt(chapters, seconds) {
  if (!Array.isArray(chapters) || chapters.length === 0) return null;
  let current = chapters[0];
  for (const chapter of chapters) {
    if (chapter.time > seconds) break;
    current = chapter;
  }
  return current;
}


export function stateAt(story, seconds) {
  validateStory(story);
  const time = Math.max(0, Math.min(story.duration, Number(seconds) || 0));
  const state = initialState(story);
  state.time = time;
  for (const event of story.events) {
    if (event.time > time) break;
    applyEvent(state, event);
  }
  return state;
}

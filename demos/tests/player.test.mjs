import test from "node:test";
import assert from "node:assert/strict";

import { chapterAt, stateAt, validateStory } from "../player.mjs";


const story = {
  duration: 10,
  mission: { id: "test" },
  graph: { nodes: [{ id: "move", status: "pending" }] },
  events: [
    { time: 2, type: "graph", title: "moving", detail: "start", payload: { nodeId: "move", status: "running" } },
    { time: 4, type: "telemetry", title: "battery", detail: "ok", payload: { battery: 82 } },
    { time: 6, type: "fault", title: "blocked", detail: "WP-04", payload: { status: "recovering" } },
  ],
};


test("stateAt reduces all events through the requested time", () => {
  const state = stateAt(story, 5);

  assert.equal(state.nodeStatuses.move, "running");
  assert.equal(state.telemetry.battery, 82);
  assert.equal(state.trace.length, 2);
});


test("stateAt clamps playback time to the story duration", () => {
  assert.equal(stateAt(story, 99).time, 10);
  assert.equal(stateAt(story, -5).time, 0);
});


test("validateStory rejects decreasing timestamps", () => {
  assert.throws(
    () => validateStory({
      duration: 2,
      mission: {},
      graph: { nodes: [] },
      events: [
        { time: 2, type: "mission" },
        { time: 1, type: "mission" },
      ],
    }),
    /chronological/,
  );
});


test("chapterAt selects the latest started chapter", () => {
  const chapters = [
    { time: 0, id: "start" },
    { time: 5, id: "fault" },
  ];

  assert.equal(chapterAt(chapters, 7).id, "fault");
});


test("unknown event types become warnings without stopping reduction", () => {
  const state = stateAt({
    duration: 3,
    mission: {},
    graph: { nodes: [] },
    events: [{ time: 1, type: "future-event", title: "new" }],
  }, 3);

  assert.equal(state.warnings.length, 1);
});

(function (global) {
  "use strict";

  const allowedNames = new Set([
    "page_view",
    "active_time",
    "element_exposure",
    "element_interaction",
    "process_start",
    "process_success",
    "measurement_status",
  ]);

  function requireToken(value, label) {
    if (typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(value)) {
      throw new Error(`Invalid ${label}`);
    }
    return value;
  }

  function commandFor(observation, manifestVersion) {
    if (!observation || !allowedNames.has(observation.name)) {
      throw new Error("Unsupported observation");
    }
    const subject = observation.subject
      ? requireToken(observation.subject, "subject")
      : null;
    const value = observation.value || {};

    const detail =
      subject ||
      (observation.name === "page_view"
        ? "page"
        : requireToken(
            value.duration_bucket || value.status || value.interaction_type,
            "event value",
          ));
    const eventName = `${manifestVersion}:${detail}`;
    const parameters = new URLSearchParams({
      e_c: "thactual_sensor",
      e_a: observation.name,
      e_n: eventName,
    });
    return ["queueRequest", parameters.toString()];
  }

  function initialize(config) {
    if (!config || config.schemaVersion !== "1") throw new Error("Unsupported schema version");
    const manifestVersion = requireToken(config.manifestVersion, "manifest version");
    const siteId = String(config.siteId || "");
    if (!/^\d{1,10}$/.test(siteId)) throw new Error("Invalid site ID");

    const queue = (global._paq = global._paq || []);
    queue.push(["disableCookies"]);
    queue.push(["disablePerformanceTracking"]);
    queue.push(["setRequestMethod", "POST"]);
    queue.push(["setRequestQueueInterval", 2500]);
    queue.push(["setTrackerUrl", "/thactual/observe"]);
    queue.push(["setSiteId", siteId]);

    const api = Object.freeze({
      observe(observation) {
        queue.push(commandFor(observation, manifestVersion));
      },
    });
    global.ThactualSensor = api;
    return api;
  }

  global.ThactualSensorBootstrap = Object.freeze({ initialize });
})(window);

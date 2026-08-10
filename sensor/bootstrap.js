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

    if (observation.name === "page_view") return ["trackPageView"];
    if (observation.name === "element_exposure") {
      return ["trackContentImpression", subject, manifestVersion, global.location.pathname];
    }
    if (observation.name === "element_interaction") {
      return [
        "trackContentInteraction",
        requireToken(value.interaction_type, "interaction type"),
        subject,
        manifestVersion,
        global.location.pathname,
      ];
    }
    return [
      "trackEvent",
      "thactual_sensor",
      observation.name,
      subject || requireToken(value.duration_bucket || value.status, "event value"),
    ];
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

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
  const allowedKinds = new Set(["exposure", "interaction", "process"]);
  const allowedEvidence = new Set([
    "click_proxy",
    "thank_you_url",
    "success_state",
    "application_event",
  ]);

  function requireToken(value, label) {
    if (typeof value !== "string" || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(value)) {
      throw new Error(`Invalid ${label}`);
    }
    return value;
  }

  function requireVersion(value, label) {
    if (typeof value !== "string" || !/^[0-9A-Za-z][0-9A-Za-z._-]{0,39}$/.test(value)) {
      throw new Error(`Invalid ${label}`);
    }
    return value;
  }

  function validateManifest(manifest, manifestVersion) {
    if (!manifest || manifest.schema_version !== "1") throw new Error("Invalid manifest");
    if (requireVersion(manifest.manifest_version, "manifest version") !== manifestVersion) {
      throw new Error("Manifest version mismatch");
    }
    if (manifest.page_match !== global.location.pathname) throw new Error("Manifest page mismatch");
    if (!manifest.expires_at || Date.parse(manifest.expires_at) <= Date.now()) {
      throw new Error("Manifest expired");
    }
    if (
      !Array.isArray(manifest.observations) ||
      manifest.observations.length < 1 ||
      manifest.observations.length > 20
    ) {
      throw new Error("Invalid manifest observations");
    }
    const keys = new Set();
    return manifest.observations.map((observation) => {
      const key = requireToken(observation && observation.key, "observation key");
      const locator = requireToken(observation.locator, "observation locator");
      if (!allowedKinds.has(observation.kind) || keys.has(key)) {
        throw new Error("Invalid manifest observation");
      }
      keys.add(key);
      return Object.freeze({key, locator, kind: observation.kind});
    });
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
    if (config.measurementAllowed !== true) throw new Error("Measurement not allowed");
    const manifestVersion = requireVersion(config.manifestVersion, "manifest version");
    const siteId = String(config.siteId || "");
    if (!/^\d{1,10}$/.test(siteId)) throw new Error("Invalid site ID");

    const queue = (global._paq = global._paq || []);
    queue.push(["disableCookies"]);
    queue.push(["disablePerformanceTracking"]);
    queue.push(["setRequestMethod", "POST"]);
    queue.push(["setRequestQueueInterval", 2500]);
    queue.push(["setTrackerUrl", "/thactual/observe"]);
    queue.push(["setSiteId", siteId]);

    let observer = null;
    const listeners = [];
    const processKeys = new Set();
    const startedProcesses = new Set();
    const succeededProcesses = new Set();
    const exposureTimers = new Map();
    const exposedKeys = new Set();

    function enqueueObservation(observation) {
      queue.push(commandFor(observation, manifestVersion));
    }

    function addListener(element, type, handler) {
      element.addEventListener(type, handler);
      listeners.push([element, type, handler]);
    }

    function applyManifest(manifest) {
      const observations = validateManifest(manifest, manifestVersion);
      const exposureTargets = new Map();
      for (const observation of observations) {
        const matches = global.document.querySelectorAll(
          `[data-thactual="${observation.locator}"]`,
        );
        if (matches.length !== 1) continue;
        const element = matches[0];
        if (observation.kind === "exposure") {
          exposureTargets.set(element, observation.key);
          addListener(element, "click", () =>
            enqueueObservation({
              name: "element_interaction",
              subject: observation.key,
              value: {interaction_type: "click"},
            }),
          );
        } else if (observation.kind === "interaction") {
          addListener(element, "click", () =>
            enqueueObservation({
              name: "element_interaction",
              subject: observation.key,
              value: {interaction_type: "click"},
            }),
          );
        } else {
          processKeys.add(observation.key);
          const eventType = element.tagName === "FORM" ? "submit" : "click";
          addListener(element, eventType, () => {
            if (startedProcesses.has(observation.key)) return;
            startedProcesses.add(observation.key);
            enqueueObservation({name: "process_start", subject: observation.key, value: {}});
          });
        }
      }

      if (exposureTargets.size) {
        observer = new global.IntersectionObserver(
          (entries) => {
            for (const entry of entries) {
              const key = exposureTargets.get(entry.target);
              if (!key || exposedKeys.has(key)) continue;
              if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
                if (!exposureTimers.has(key)) {
                  exposureTimers.set(
                    key,
                    global.setTimeout(() => {
                      exposureTimers.delete(key);
                      exposedKeys.add(key);
                      observer.unobserve(entry.target);
                      enqueueObservation({
                        name: "element_exposure",
                        subject: key,
                        value: {visibility_bucket: "half_1s"},
                      });
                    }, 1000),
                  );
                }
              } else if (exposureTimers.has(key)) {
                global.clearTimeout(exposureTimers.get(key));
                exposureTimers.delete(key);
              }
            }
          },
          {threshold: [0.5]},
        );
        for (const element of exposureTargets.keys()) observer.observe(element);
      }
      enqueueObservation({name: "page_view", value: {}});
    }

    const api = Object.freeze({
      observe(observation) {
        enqueueObservation(observation);
      },
      processSuccess(key, evidenceStrength) {
        const subject = requireToken(key, "process key");
        if (
          !processKeys.has(subject) ||
          succeededProcesses.has(subject) ||
          !allowedEvidence.has(evidenceStrength)
        ) {
          throw new Error("Invalid process success");
        }
        succeededProcesses.add(subject);
        enqueueObservation({
          name: "process_success",
          subject,
          value: {evidence_strength: evidenceStrength},
        });
      },
      destroy() {
        if (observer) observer.disconnect();
        for (const timer of exposureTimers.values()) global.clearTimeout(timer);
        for (const [element, type, handler] of listeners) {
          element.removeEventListener(type, handler);
        }
      },
    });
    global.ThactualSensor = api;
    if (config.manifest) applyManifest(config.manifest);
    return api;
  }

  global.ThactualSensorBootstrap = Object.freeze({ initialize });
})(window);

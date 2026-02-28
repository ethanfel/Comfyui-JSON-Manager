import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.project.dynamic",

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectLoaderDynamic") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            // Hide internal widgets (managed by JS)
            for (const name of ["output_keys", "output_types"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) { w.type = "hidden"; w.computeSize = () => [0, -4]; }
            }

            // Do NOT remove default outputs synchronously here.
            // During graph loading, ComfyUI creates all nodes (firing onNodeCreated)
            // before configuring them. Other nodes (e.g. Kijai Set/Get) may resolve
            // links to our outputs during their configure step. If we remove outputs
            // here, those nodes find no output slot and error out.
            //
            // Instead, defer cleanup: for loaded workflows onConfigure sets _configured
            // before this runs; for new nodes the defaults are cleaned up.
            this._configured = false;

            // Add Refresh button
            this.addWidget("button", "Refresh Outputs", null, () => {
                this.refreshDynamicOutputs();
            });

            // Auto-refresh with 500ms debounce on widget changes
            this._refreshTimer = null;
            const autoRefreshWidgets = ["project_name", "file_name", "sequence_number"];
            for (const widgetName of autoRefreshWidgets) {
                const w = this.widgets?.find(w => w.name === widgetName);
                if (w) {
                    const origCallback = w.callback;
                    const node = this;
                    w.callback = function (...args) {
                        origCallback?.apply(this, args);
                        clearTimeout(node._refreshTimer);
                        node._refreshTimer = setTimeout(() => {
                            node.refreshDynamicOutputs();
                        }, 500);
                    };
                }
            }

            queueMicrotask(() => {
                if (!this._configured) {
                    // New node (not loading) — remove the Python default outputs
                    // and add only the fixed total_sequences slot
                    while (this.outputs.length > 0) {
                        this.removeOutput(0);
                    }
                    this.addOutput("total_sequences", "INT");
                    this.setSize(this.computeSize());
                    app.graph?.setDirtyCanvas(true, true);
                }
            });
        };

        nodeType.prototype._setStatus = function (status, message) {
            const baseTitle = "Project Loader (Dynamic)";
            if (status === "ok") {
                this.title = baseTitle;
                this.color = undefined;
                this.bgcolor = undefined;
            } else if (status === "error") {
                this.title = baseTitle + " - ERROR";
                this.color = "#ff4444";
                this.bgcolor = "#331111";
                if (message) this.title = baseTitle + ": " + message;
            } else if (status === "loading") {
                this.title = baseTitle + " - Loading...";
            }
            app.graph?.setDirtyCanvas(true, true);
        };

        nodeType.prototype.refreshDynamicOutputs = async function () {
            const urlWidget = this.widgets?.find(w => w.name === "manager_url");
            const projectWidget = this.widgets?.find(w => w.name === "project_name");
            const fileWidget = this.widgets?.find(w => w.name === "file_name");
            const seqWidget = this.widgets?.find(w => w.name === "sequence_number");

            if (!urlWidget?.value || !projectWidget?.value || !fileWidget?.value) return;

            this._setStatus("loading");

            try {
                const resp = await api.fetchApi(
                    `/json_manager/get_project_keys?url=${encodeURIComponent(urlWidget.value)}&project=${encodeURIComponent(projectWidget.value)}&file=${encodeURIComponent(fileWidget.value)}&seq=${seqWidget?.value || 1}`
                );

                if (!resp.ok) {
                    let errorMsg = `HTTP ${resp.status}`;
                    try {
                        const errData = await resp.json();
                        if (errData.message) errorMsg = errData.message;
                    } catch (_) {}
                    this._setStatus("error", errorMsg);
                    return;
                }

                const data = await resp.json();
                const keys = data.keys;
                const types = data.types;

                // If the API returned an error or missing data, keep existing outputs and links intact
                if (data.error || !Array.isArray(keys) || !Array.isArray(types)) {
                    const errMsg = data.error ? data.message || data.error : "Missing keys/types";
                    this._setStatus("error", errMsg);
                    return;
                }

                // Store keys and types in hidden widgets for persistence (comma-separated)
                const okWidget = this.widgets?.find(w => w.name === "output_keys");
                if (okWidget) okWidget.value = keys.join(",");
                const otWidget = this.widgets?.find(w => w.name === "output_types");
                if (otWidget) otWidget.value = types.join(",");

                // Slot 0 is always total_sequences (INT) — ensure it exists
                if (this.outputs.length === 0 || this.outputs[0].name !== "total_sequences") {
                    this.outputs.unshift({ name: "total_sequences", type: "INT", links: null });
                }
                this.outputs[0].type = "INT";

                // Build a map of current dynamic output names to slot indices (skip slot 0)
                const oldSlots = {};
                for (let i = 1; i < this.outputs.length; i++) {
                    oldSlots[this.outputs[i].name] = i;
                }

                // Build new dynamic outputs, reusing existing slots to preserve links
                const newOutputs = [this.outputs[0]]; // Keep total_sequences at slot 0
                for (let k = 0; k < keys.length; k++) {
                    const key = keys[k];
                    const type = types[k] || "*";
                    if (key in oldSlots) {
                        const slot = this.outputs[oldSlots[key]];
                        slot.type = type;
                        slot.label = key;
                        newOutputs.push(slot);
                        delete oldSlots[key];
                    } else {
                        newOutputs.push({ name: key, label: key, type: type, links: null });
                    }
                }

                // Disconnect links on slots that are being removed
                for (const name in oldSlots) {
                    const idx = oldSlots[name];
                    if (this.outputs[idx]?.links?.length) {
                        for (const linkId of [...this.outputs[idx].links]) {
                            this.graph?.removeLink(linkId);
                        }
                    }
                }

                // Reassign the outputs array and fix link slot indices
                this.outputs = newOutputs;
                if (this.graph) {
                    for (let i = 0; i < this.outputs.length; i++) {
                        const links = this.outputs[i].links;
                        if (!links) continue;
                        for (const linkId of links) {
                            const link = this.graph.links[linkId];
                            if (link) link.origin_slot = i;
                        }
                    }
                }

                this._setStatus("ok");
                this.setSize(this.computeSize());
                app.graph?.setDirtyCanvas(true, true);
            } catch (e) {
                console.error("[ProjectLoaderDynamic] Refresh failed:", e);
                this._setStatus("error", "Server unreachable");
            }
        };

        // Restore state on workflow load
        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);
            this._configured = true;

            // Hide internal widgets
            for (const name of ["output_keys", "output_types"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) { w.type = "hidden"; w.computeSize = () => [0, -4]; }
            }

            const okWidget = this.widgets?.find(w => w.name === "output_keys");
            const otWidget = this.widgets?.find(w => w.name === "output_types");

            const keys = okWidget?.value
                ? okWidget.value.split(",").filter(k => k.trim())
                : [];
            const types = otWidget?.value
                ? otWidget.value.split(",")
                : [];

            // Ensure slot 0 is total_sequences (INT)
            if (this.outputs.length === 0 || this.outputs[0].name !== "total_sequences") {
                this.outputs.unshift({ name: "total_sequences", type: "INT", links: null });
                const node = this;
                queueMicrotask(() => {
                    if (!node.graph) return;
                    for (const output of node.outputs) {
                        output.links = null;
                    }
                    for (const linkId in node.graph.links) {
                        const link = node.graph.links[linkId];
                        if (!link || link.origin_id !== node.id) continue;
                        link.origin_slot += 1;
                        const output = node.outputs[link.origin_slot];
                        if (output) {
                            if (!output.links) output.links = [];
                            output.links.push(link.id);
                        }
                    }
                    app.graph?.setDirtyCanvas(true, true);
                });
            }
            this.outputs[0].type = "INT";
            this.outputs[0].name = "total_sequences";

            if (keys.length > 0) {
                for (let i = 0; i < keys.length; i++) {
                    const slotIdx = i + 1;
                    if (slotIdx < this.outputs.length) {
                        this.outputs[slotIdx].name = keys[i].trim();
                        this.outputs[slotIdx].label = keys[i].trim();
                        if (types[i]) this.outputs[slotIdx].type = types[i];
                    }
                }
                while (this.outputs.length > keys.length + 1) {
                    this.removeOutput(this.outputs.length - 1);
                }
            } else if (this.outputs.length > 1) {
                // Widget values empty but serialized dynamic outputs exist — sync widgets
                const dynamicOutputs = this.outputs.slice(1);
                if (okWidget) okWidget.value = dynamicOutputs.map(o => o.name).join(",");
                if (otWidget) otWidget.value = dynamicOutputs.map(o => o.type).join(",");
            }

            this.setSize(this.computeSize());
        };
    },
});

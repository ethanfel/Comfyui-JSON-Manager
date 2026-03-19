import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.project.key",

    // Re-sync all ProjectKey nodes from their sources before queueing
    // This fixes stale config when the user edits a ProjectSource after
    // a ProjectKey already selected it.
    async beforeQueuePrompt() {
        if (!app.graph?._nodes) return;
        for (const node of app.graph._nodes) {
            if (node.type === "ProjectKey" && node._syncFromSource) {
                node._syncFromSource();
            }
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectKey") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            this._configured = false;

            // Hide the connection-config widgets (synced from source by JS)
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number", "key_type"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) { w.type = "hidden"; w.computeSize = () => [0, -4]; }
            }

            // Convert source_label to a dynamic combo
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) {
                srcWidget.type = "combo";
                srcWidget.options = { values: [] };
                srcWidget.value = srcWidget.value || "";
                const node = this;
                const origCb = srcWidget.callback;
                srcWidget.callback = function (...args) {
                    origCb?.apply(this, args);
                    node._syncFromSource();
                    node._refreshKeys();
                };
            }

            // Convert key_name to a dynamic combo
            const keyWidget = this.widgets?.find(w => w.name === "key_name");
            if (keyWidget) {
                keyWidget.type = "combo";
                keyWidget.options = { values: [] };
                keyWidget.value = keyWidget.value || "";
                const node = this;
                const origCb = keyWidget.callback;
                keyWidget.callback = function (...args) {
                    origCb?.apply(this, args);
                    node._applyKeySelection();
                };
            }

            queueMicrotask(() => {
                if (!this._configured) {
                    // New node — set output to a generic slot
                    if (this.outputs.length === 0) {
                        this.addOutput("value", "*");
                    }
                    this.setSize(this.computeSize());
                }
            });
        };

        // --- Find all ProjectSource nodes and their labels (deduplicated) ---
        nodeType.prototype._getSourceLabels = function () {
            const seen = new Set();
            const labels = [];
            if (!this.graph) return labels;
            for (const node of this.graph._nodes) {
                if (node.type === "ProjectSource") {
                    const lw = node.widgets?.find(w => w.name === "label");
                    if (lw?.value && !seen.has(lw.value)) {
                        seen.add(lw.value);
                        labels.push(lw.value);
                    } else if (lw?.value && seen.has(lw.value)) {
                        console.warn(`[ProjectKey] Duplicate source label "${lw.value}" (node ${node.id}) — only first will be used`);
                    }
                }
            }
            return labels;
        };

        // --- Find the ProjectSource node matching a label ---
        nodeType.prototype._findSource = function (label) {
            if (!this.graph || !label) return null;
            for (const node of this.graph._nodes) {
                if (node.type === "ProjectSource") {
                    const lw = node.widgets?.find(w => w.name === "label");
                    if (lw?.value === label) return node;
                }
            }
            return null;
        };

        // --- Copy config from source node into hidden widgets ---
        nodeType.prototype._syncFromSource = function () {
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            const source = this._findSource(srcWidget?.value);
            if (!source) return;
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const dst = this.widgets?.find(w => w.name === name);
                const src = source.widgets?.find(w => w.name === name);
                if (dst && src) dst.value = src.value;
            }
        };

        // --- Fetch keys from API and populate key_name dropdown ---
        nodeType.prototype._refreshKeys = async function () {
            const urlW = this.widgets?.find(w => w.name === "manager_url");
            const projW = this.widgets?.find(w => w.name === "project_name");
            const fileW = this.widgets?.find(w => w.name === "file_name");
            const seqW = this.widgets?.find(w => w.name === "sequence_number");

            if (!urlW?.value || !projW?.value || !fileW?.value) return;

            try {
                const resp = await api.fetchApi(
                    `/json_manager/get_project_keys?url=${encodeURIComponent(urlW.value)}&project=${encodeURIComponent(projW.value)}&file=${encodeURIComponent(fileW.value)}&seq=${seqW?.value || 1}`
                );
                if (!resp.ok) return;

                const data = await resp.json();
                if (data.error || !Array.isArray(data.keys)) return;

                // Store keys/types for lookup
                this._availableKeys = data.keys;
                this._availableTypes = data.types;

                // Update key_name combo values
                const keyWidget = this.widgets?.find(w => w.name === "key_name");
                if (keyWidget) {
                    keyWidget.options.values = data.keys;
                    // Keep current selection if still valid
                    if (!data.keys.includes(keyWidget.value)) {
                        keyWidget.value = data.keys[0] || "";
                    }
                    this._applyKeySelection();
                }
            } catch (e) {
                console.error("[ProjectKey] Failed to refresh keys:", e);
            }
        };

        // --- Update output slot based on selected key ---
        nodeType.prototype._applyKeySelection = function () {
            const keyWidget = this.widgets?.find(w => w.name === "key_name");
            if (!keyWidget?.value) return;

            const keyIdx = (this._availableKeys || []).indexOf(keyWidget.value);
            const keyType = keyIdx >= 0 ? (this._availableTypes[keyIdx] || "*") : "*";

            // Update hidden key_type widget
            const ktWidget = this.widgets?.find(w => w.name === "key_type");
            if (ktWidget) ktWidget.value = keyType;

            // Update output slot
            if (this.outputs.length > 0) {
                this.outputs[0].name = keyWidget.value;
                this.outputs[0].label = keyWidget.value;
                this.outputs[0].type = keyType;
            }

            this.title = keyWidget.value ? `Key: ${keyWidget.value}` : "Project Key";
            this.setSize(this.computeSize());
            app.graph?.setDirtyCanvas(true, true);
        };

        // --- Populate source dropdown on click (lazy refresh) ---
        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            origOnMouseDown?.apply(this, arguments);
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) {
                srcWidget.options.values = this._getSourceLabels();
            }
        };

        // --- Restore state on workflow load ---
        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);
            this._configured = true;

            // Hide config widgets
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number", "key_type"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) { w.type = "hidden"; w.computeSize = () => [0, -4]; }
            }

            // Restore combo types
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) {
                srcWidget.type = "combo";
                srcWidget.options = { values: this._getSourceLabels() };
            }

            const keyWidget = this.widgets?.find(w => w.name === "key_name");
            if (keyWidget) {
                keyWidget.type = "combo";
                keyWidget.options = { values: [] };
            }

            // Update title from saved key
            if (keyWidget?.value) {
                this.title = `Key: ${keyWidget.value}`;
            }

            // Restore output slot name from saved key_name
            if (keyWidget?.value && this.outputs.length > 0) {
                this.outputs[0].name = keyWidget.value;
                this.outputs[0].label = keyWidget.value;
                const ktWidget = this.widgets?.find(w => w.name === "key_type");
                if (ktWidget?.value) this.outputs[0].type = ktWidget.value;
            }

            this.setSize(this.computeSize());

            // Deferred: sync from source and refresh key dropdown once graph is ready
            const node = this;
            queueMicrotask(() => {
                node._syncFromSource();
                node._refreshKeys();
            });
        };
    },
});

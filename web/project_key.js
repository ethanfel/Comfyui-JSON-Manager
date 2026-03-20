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

        // Helper: properly hide a widget (works for all types including INT)
        function hideWidget(widget) {
            if (widget.origType === undefined) widget.origType = widget.type;
            widget.type = "hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
        }

        // Helper: replace a STRING widget with a proper combo widget
        function replaceWithCombo(node, name, values, callback) {
            const idx = node.widgets?.findIndex(w => w.name === name);
            if (idx === -1 || idx === undefined) return null;
            const oldWidget = node.widgets[idx];
            const savedValue = oldWidget.value || "";
            // Ensure values list is never empty (combo shows undefined otherwise)
            const comboValues = values.length > 0 ? values : [""];
            const defaultValue = comboValues.includes(savedValue) ? savedValue : comboValues[0];
            // Remove old STRING widget
            node.widgets.splice(idx, 1);
            // Insert a real combo widget at the same position
            const combo = node.addWidget("combo", name, defaultValue, callback, { values: comboValues });
            // Move it from the end to the original position
            if (node.widgets.length > 1) {
                node.widgets.splice(node.widgets.length - 1, 1);
                node.widgets.splice(idx, 0, combo);
            }
            return combo;
        }

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            this._configured = false;

            // Hide the connection-config widgets (synced from source by JS)
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number", "key_type"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            // Replace source_label STRING with a proper combo widget
            const node = this;
            const sourceLabels = this._getSourceLabels?.() || [];
            const srcCombo = replaceWithCombo(this, "source_label", sourceLabels, function (value) {
                node._syncFromSource();
                node._refreshKeys();
            });
            // Set first available source or "none" placeholder
            if (srcCombo) srcCombo.value = sourceLabels[0] || "";

            // Replace key_name STRING with a proper combo widget
            const keyCombo = replaceWithCombo(this, "key_name", [], function (value) {
                node._applyKeySelection();
            });
            if (keyCombo) keyCombo.value = "";

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
            if (!source) {
                console.log(`[ProjectKey] _syncFromSource id=${this.id}: no source found for label="${srcWidget?.value}"`);
                return;
            }
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const dst = this.widgets?.find(w => w.name === name);
                const src = source.widgets?.find(w => w.name === name);
                if (dst && src) {
                    dst.value = src.value;
                    console.log(`[ProjectKey] _syncFromSource id=${this.id}: ${name}="${src.value}"`);
                }
            }
        };

        // --- Fetch keys from API and populate key_name dropdown ---
        nodeType.prototype._refreshKeys = async function () {
            const urlW = this.widgets?.find(w => w.name === "manager_url");
            const projW = this.widgets?.find(w => w.name === "project_name");
            const fileW = this.widgets?.find(w => w.name === "file_name");
            const seqW = this.widgets?.find(w => w.name === "sequence_number");

            console.log(`[ProjectKey] _refreshKeys id=${this.id}: url="${urlW?.value}" project="${projW?.value}" file="${fileW?.value}" seq=${seqW?.value}`);
            if (!urlW?.value || !projW?.value || !fileW?.value) {
                console.log(`[ProjectKey] _refreshKeys: skipped (missing config)`);
                return;
            }

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

                // Update key_name combo options only — never change the selection
                const keyWidget = this.widgets?.find(w => w.name === "key_name");
                if (keyWidget) {
                    keyWidget.options.values = data.keys;
                    // Selection is sticky: user must change it manually
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

        // --- Sync config on click (lazy, no key refresh to avoid race) ---
        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            origOnMouseDown?.apply(this, arguments);
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) {
                srcWidget.options.values = this._getSourceLabels();
            }
            // Sync config values from source (synchronous, safe)
            this._syncFromSource();
        };

        // --- Restore state on workflow load ---
        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);
            this._configured = true;

            // Hide config widgets
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number", "key_type"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            // Ensure source_label is a proper combo (may still be STRING from serialization)
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget && srcWidget.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "source_label", this._getSourceLabels(), function (value) {
                    node._syncFromSource();
                    node._refreshKeys();
                });
            } else if (srcWidget) {
                srcWidget.options.values = this._getSourceLabels();
            }

            // Ensure key_name is a proper combo
            const keyWidget = this.widgets?.find(w => w.name === "key_name");
            if (keyWidget && keyWidget.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "key_name", [], function (value) {
                    node._applyKeySelection();
                });
            }

            // Re-find widgets after possible replacement
            const finalKeyWidget = this.widgets?.find(w => w.name === "key_name");

            // Update title from saved key
            if (finalKeyWidget?.value) {
                this.title = `Key: ${finalKeyWidget.value}`;
            }

            // Restore output slot name from saved key_name
            if (finalKeyWidget?.value && this.outputs.length > 0) {
                this.outputs[0].name = finalKeyWidget.value;
                this.outputs[0].label = finalKeyWidget.value;
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

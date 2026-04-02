import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "json.manager.project.resolution",

    async beforeQueuePrompt() {
        if (!app.graph?._nodes) return;
        for (const node of app.graph._nodes) {
            if (node.type === "ProjectResolution" && node._syncFromSource) {
                node._syncFromSource();
            }
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectResolution") return;

        function hideWidget(widget) {
            if (widget.origType === undefined) widget.origType = widget.type;
            widget.type = "hidden";
            widget.hidden = true;
            widget.computeSize = () => [0, -4];
        }

        function replaceWithCombo(node, name, values, callback) {
            const idx = node.widgets?.findIndex(w => w.name === name);
            if (idx === -1 || idx === undefined) return null;
            const oldWidget = node.widgets[idx];
            const savedValue = oldWidget.value || "";
            const comboValues = values.length > 0 ? values : [""];
            if (savedValue && !comboValues.includes(savedValue)) {
                comboValues.unshift(savedValue);
            }
            const defaultValue = savedValue || comboValues[0];
            node.widgets.splice(idx, 1);
            const combo = node.addWidget("combo", name, defaultValue, callback, { values: comboValues });
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

            // Hide synced config widgets — index stays visible, user wires it from loop node
            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            const node = this;
            const sourceLabels = this._getSourceLabels?.() || [];
            const srcCombo = replaceWithCombo(this, "source_label", sourceLabels, function (value) {
                node._syncFromSource();
                node._refreshKeys();
            });
            if (srcCombo) srcCombo.value = sourceLabels[0] || "";

            const keyCombo = replaceWithCombo(this, "key_name", [], function (value) {
                node.title = value ? `Resolution: ${value}` : "Project Resolution";
                app.graph?.setDirtyCanvas(true, true);
            });
            if (keyCombo && !keyCombo.value) keyCombo.value = "resolutions";

            queueMicrotask(() => {
                if (!this._configured) {
                    this.setSize(this.computeSize());
                }
            });
        };

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
                    }
                }
            }
            return labels;
        };

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

                const keyWidget = this.widgets?.find(w => w.name === "key_name");
                if (keyWidget) {
                    keyWidget.options.values = data.keys.length > 0 ? data.keys : [""];
                }
            } catch (e) {
                console.error("[ProjectResolution] Failed to refresh keys:", e);
            }
        };

        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            origOnMouseDown?.apply(this, arguments);
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) srcWidget.options.values = this._getSourceLabels();
            this._syncFromSource();
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);
            this._configured = true;

            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

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

            const keyWidget = this.widgets?.find(w => w.name === "key_name");
            if (keyWidget && keyWidget.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "key_name", [], function (value) {
                    node.title = value ? `Resolution: ${value}` : "Project Resolution";
                    app.graph?.setDirtyCanvas(true, true);
                });
            }

            const finalKeyWidget = this.widgets?.find(w => w.name === "key_name");
            if (finalKeyWidget?.value) {
                this.title = `Resolution: ${finalKeyWidget.value}`;
            }

            this.setSize(this.computeSize());

            const node = this;
            queueMicrotask(() => {
                node._syncFromSource();
                node._refreshKeys();
            });
        };
    },
});

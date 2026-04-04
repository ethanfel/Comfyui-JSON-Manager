import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "json.manager.project.frame_names",

    async beforeQueuePrompt() {
        if (!app.graph?._nodes) return;
        for (const node of app.graph._nodes) {
            if (node.type === "ProjectFrameNames" && node._syncFromSource) {
                node._syncFromSource();
            }
        }
    },

    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ProjectFrameNames") return;

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
            if (savedValue && !comboValues.includes(savedValue)) comboValues.unshift(savedValue);
            const defaultValue = savedValue || comboValues[0];
            node.widgets.splice(idx, 1);
            const combo = node.addWidget("combo", name, defaultValue, callback, { values: comboValues });
            if (node.widgets.length > 1) {
                node.widgets.splice(node.widgets.length - 1, 1);
                node.widgets.splice(idx, 0, combo);
            }
            return combo;
        }

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

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);

            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            const node = this;
            replaceWithCombo(this, "source_label", this._getSourceLabels?.() || [], function () {
                node._syncFromSource();
            });

            this.title = "Project Frame Names";
            this.setSize(this.computeSize());
        };

        const origOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            origOnConfigure?.apply(this, arguments);

            for (const name of ["manager_url", "project_name", "file_name", "sequence_number"]) {
                const w = this.widgets?.find(w => w.name === name);
                if (w) hideWidget(w);
            }

            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget && srcWidget.type !== "combo") {
                const node = this;
                replaceWithCombo(this, "source_label", this._getSourceLabels?.() || [], function () {
                    node._syncFromSource();
                });
            } else if (srcWidget) {
                srcWidget.options.values = this._getSourceLabels?.() || [];
            }

            this.setSize(this.computeSize());

            const node = this;
            queueMicrotask(() => node._syncFromSource());
        };

        const origOnMouseDown = nodeType.prototype.onMouseDown;
        nodeType.prototype.onMouseDown = function (e, localPos, graphCanvas) {
            origOnMouseDown?.apply(this, arguments);
            const srcWidget = this.widgets?.find(w => w.name === "source_label");
            if (srcWidget) srcWidget.options.values = this._getSourceLabels?.() || [];
            this._syncFromSource();
        };
    },
});
